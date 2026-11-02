from __future__ import annotations

import filecmp
import hashlib
import json
import os
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Any, NamedTuple

REPO = Path(__file__).resolve().parent.parent
RUN_STAMP = time.strftime("%Y%m%d-%H%M%S")
CHECK_TIMEOUT = 30
LAUNCH_DAEMONS = Path("/Library/LaunchDaemons")
APPLE_AGENTS = Path("/System/Library/LaunchAgents")
ACTIVATE_SETTINGS = (
    "/System/Library/PrivateFrameworks/SystemAdministration.framework/Resources/activateSettings"
)
RESTART = {
    "com.apple.dock": "Dock",
    "com.apple.finder": "Finder",
    "com.apple.menuextra.clock": "ControlCenter",
}

# MARK: Models

MODULES: list[Module] = []
PROFILES: list[Profile] = []


class ConfigError(Exception):
    pass


class Default(NamedTuple):
    domain: str
    key: str
    value: Any
    logout: bool = False
    activate: bool = False

    def __str__(self) -> str:
        return f"{self.domain} {self.key} = {self.value}"


class Hotkey(NamedTuple):
    id: int
    params: list[int]
    enabled: bool = True
    domain = "com.apple.symbolichotkeys"
    key = "AppleSymbolicHotKeys"
    logout = False
    activate = True

    @property
    def value(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "value": {"parameters": self.params, "type": "standard"}}

    def __str__(self) -> str:
        return f"hotkey {self.id}"


@dataclass
class LaunchAgent:
    label: str
    program: list[Any]
    run_at_load: bool = True
    hourly: bool = False
    system = False

    @property
    def plist(self) -> dict[str, Any]:
        program = [
            a if isinstance(a, str) else json.dumps(a, separators=(",", ":")) for a in self.program
        ]
        plist = {"Label": self.label, "ProgramArguments": program, "RunAtLoad": self.run_at_load}
        if self.hourly:
            plist["StartCalendarInterval"] = {"Minute": 0}

        return plist

    @property
    def path(self) -> Path:
        if self.system:
            return LAUNCH_DAEMONS / f"{self.label}.plist"

        return Path("~/Library/LaunchAgents").expanduser() / f"{self.label}.plist"

    @property
    def domain(self) -> str:
        return "system" if self.system else f"gui/{os.getuid()}"


class LaunchDaemon(LaunchAgent):
    system = True


@dataclass
class AppleAgent:
    label: str

    @property
    def path(self) -> Path:
        return APPLE_AGENTS / f"{self.label}.plist"

    @property
    def domain(self) -> str:
        return f"gui/{os.getuid()}"


@dataclass(eq=False)
class Module:
    name: str
    brew: list[str] = field(default_factory=list)
    cask: list[str] = field(default_factory=list)
    cargo: list[str] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)
    needs: list[Module] = field(default_factory=list)
    defaults: list[Default | Hotkey] = field(default_factory=list)
    launchd: list[LaunchAgent | AppleAgent] = field(default_factory=list)
    # Shell script run after the packages, links, defaults and launchd jobs of all modules, right
    # before this module's cargo installs; it reruns whenever the module changes or the script
    # itself does, so it must be safe to repeat: declare a state, never toggle or append.
    setup: str = ""
    # Shell command that exits 0 while the setup's result is in place; reruns the setup otherwise.
    setup_check: str = ""

    def __post_init__(self) -> None:
        MODULES.append(self)


@dataclass(eq=False)
class Profile:
    name: str
    modules: list[Module]

    def __post_init__(self) -> None:
        PROFILES.append(self)


@dataclass
class Step:
    module: Module
    brew: list[str]
    cask: list[str]
    cargo: list[str]
    links: list[tuple[Path, Path, str]]
    setup_reason: str | None
    # Each differing setting with the value it has now, None when it is unset.
    defaults: list[tuple[Default | Hotkey, Any]] = field(default_factory=list)
    jobs: list[tuple[LaunchAgent | AppleAgent, str]] = field(default_factory=list)

    @property
    def changes(self) -> bool:
        return bool(
            self.brew
            or self.cask
            or self.cargo
            or self.links
            or self.setup_reason
            or self.defaults
            or self.jobs
        )


# MARK: Resolve


def check_names() -> None:
    for kind, items in (("modules", MODULES), ("profiles", PROFILES)):
        seen = set()
        for item in items:
            if item.name in seen:
                raise ConfigError(f"two {kind} are named {item.name}")

            seen.add(item.name)


def resolve(profile: list[Module]) -> list[Module]:
    ordered: list[Module] = []
    path: list[Module] = []

    def visit(module: Module) -> None:
        if not isinstance(module, Module):
            if not path:
                raise ConfigError(f"{module!r} is not a module")

            raise ConfigError(f"{path[-1].name} needs {module!r}, which is not a module")

        if module in path:
            cycle = path[path.index(module) :] + [module]
            raise ConfigError(f"dependency cycle: {' -> '.join(m.name for m in cycle)}")

        if module in ordered:
            return

        path.append(module)
        for need in module.needs:
            visit(need)

        path.pop()
        ordered.append(module)

    for module in profile:
        visit(module)

    return ordered


def check_profiles() -> list[Module]:
    # Check each module on its own, used or not; profiles then check their modules together.
    for module in MODULES:
        check_module(module)

    used: set[Module] = set()
    for profile in PROFILES:
        try:
            modules = resolve(profile.modules)
            check_config(modules)
        except ConfigError as error:
            raise ConfigError(f"profile {profile.name}: {error}") from None

        used.update(modules)

    return [module for module in MODULES if module not in used]


# MARK: Packages


def find_brew() -> str | None:
    found = shutil.which("brew")
    if found is not None:
        return found

    for prefix in ("/opt/homebrew", "/usr/local"):
        if os.access(f"{prefix}/bin/brew", os.X_OK):
            return f"{prefix}/bin/brew"

    return None


def installed_packages(brew: str | None, kind: str) -> set[str]:
    if brew is None:
        return set()

    command = [brew, "list", f"--{kind}", "-1"]
    return set(subprocess.run(command, capture_output=True, text=True, check=True).stdout.split())


def package_name(package: str) -> str:
    return package.rsplit("/", 1)[-1]


def tool_env(brew: str | None) -> dict[str, str]:
    paths = [str(Path("~/.cargo/bin").expanduser())]
    if brew is not None:
        prefix = Path(brew).parent.parent
        paths = [str(prefix / "bin"), str(prefix / "opt/rustup/bin"), *paths]

    env = dict(os.environ)
    env["PATH"] = ":".join([*paths, env.get("PATH", "")])
    return env


def installed_cargo(env: dict[str, str]) -> set[str]:
    try:
        result = subprocess.run(
            ["cargo", "install", "--list"], check=False, capture_output=True, text=True, env=env
        )
    except FileNotFoundError:
        return set()

    lines = result.stdout.splitlines() if result.returncode == 0 else []
    return {line.split()[0] for line in lines if line and not line[0].isspace()}


# MARK: Links


def link_status(source: Path, target: Path) -> str:
    if not source.exists():
        return "missing"

    if target.is_symlink():
        return "ok" if target.readlink() == source else "relink"

    if target.exists() and target.resolve() == source.resolve():
        return "ok"

    if target.exists():
        return "same" if same_content(source, target) else "differs"

    return "new"


def same_content(source: Path, target: Path) -> bool:
    if source.is_file() and target.is_file():
        return filecmp.cmp(source, target, shallow=False)

    if not (source.is_dir() and target.is_dir()):
        return False

    def equal(compared: filecmp.dircmp) -> bool:
        if compared.left_only or compared.right_only or compared.common_funny:
            return False

        _, mismatch, errors = filecmp.cmpfiles(
            compared.left, compared.right, compared.common_files, shallow=False
        )
        if mismatch or errors:
            return False

        return all(equal(sub) for sub in compared.subdirs.values())

    return equal(filecmp.dircmp(source, target, ignore=[]))


def module_links(module: Module) -> list[tuple[Path, Path]]:
    pairs = []
    for source, target in module.files.items():
        directory = REPO / source[:-2]
        if source.endswith("/*") and directory.is_dir():
            for entry in sorted(directory.iterdir()):
                if not entry.name.startswith(".") and entry.name != "__pycache__":
                    pairs.append((entry, Path(target).expanduser() / entry.name))
        else:
            pairs.append((REPO / source, Path(target).expanduser()))

    return pairs


def links_into_repo(path: Path) -> bool:
    return path.is_symlink() and (path.parent / path.readlink()).resolve().is_relative_to(REPO)


def stray_links(modules: list[Module]) -> list[tuple[Path, str]]:
    wanted = {target for module in modules for _, target in module_links(module)}
    stray = {}
    for module in MODULES:
        if module in modules:
            continue

        for _, target in module_links(module):
            if links_into_repo(target):
                stray[target] = f"{module.name} is not in the profile"

    roots = {target.parent for module in MODULES for _, target in module_links(module)}
    for root in roots:
        if not root.is_dir():
            continue

        for path in root.iterdir():
            if path not in wanted and links_into_repo(path) and not path.exists():
                stray[path] = "broken"

    return sorted(stray.items())


def backup_path(target: Path) -> Path:
    return REPO / ".backup" / RUN_STAMP / target.relative_to(Path.home())


def link(source: Path, target: Path, status: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if status == "differs":
        backup = backup_path(target)
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup))
    elif target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    elif target.is_symlink() or target.exists():
        target.unlink()

    target.symlink_to(source)


# MARK: Setup state


def state_path() -> Path:
    return Path("~/.local/state/dotsync/setup.json").expanduser()


def read_state() -> dict[str, str]:
    try:
        return json.loads(state_path().read_text())
    except (FileNotFoundError, ValueError):
        return {}


def write_state(state: dict[str, str]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def setup_hash(module: Module) -> str:
    return hashlib.sha256(dedent(module.setup).strip().encode()).hexdigest()


def setup_holds(module: Module, env: dict[str, str] | None) -> bool:
    command = ["sh", "-c", dedent(module.setup_check).strip()]
    try:
        result = subprocess.run(
            command,
            cwd=REPO,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=CHECK_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False

    return result.returncode == 0


def setup_reason(
    module: Module, other_changes: bool, state: dict[str, str], env: dict[str, str] | None = None
) -> str | None:
    if not module.setup:
        return None

    if module.name not in state:
        return "first run"

    if state[module.name] != setup_hash(module):
        return "changed"

    if module.setup_check and not setup_holds(module, env):
        return "check failed"

    return "module changed" if other_changes else None


# MARK: Defaults


def domain_name(domain: str) -> str:
    return "NSGlobalDomain" if domain == "-g" else domain


def setting_place(module: Module, setting: Any) -> str:
    if isinstance(setting, Hotkey):
        params = isinstance(setting.params, list) and all(type(p) is int for p in setting.params)
        if type(setting.id) is not int or not params or not isinstance(setting.enabled, bool):
            raise ConfigError(f"{module.name}: {setting!r} needs an int id, int params and a bool")

        return str(setting)

    if not isinstance(setting, Default):
        raise ConfigError(f"{module.name}: {setting!r} is not a Default or Hotkey")

    if not (isinstance(setting.domain, str) and isinstance(setting.key, str)):
        raise ConfigError(f"{module.name}: {setting!r} needs a string domain and key")

    if not isinstance(setting.value, (bool, int, float, str)):
        kind = type(setting.value).__name__
        raise ConfigError(
            f"{module.name}: {setting.domain} {setting.key} has a value of type {kind}"
        )

    return f"{domain_name(setting.domain)} {setting.key}"


def check_job(module: Module, job: Any) -> None:
    if isinstance(job, AppleAgent):
        if not isinstance(job.label, str):
            raise ConfigError(f"{module.name}: {job!r} needs a string label")

        return

    if not isinstance(job, LaunchAgent):
        raise ConfigError(
            f"{module.name}: {job!r} is not a LaunchAgent, LaunchDaemon or AppleAgent"
        )

    if not (isinstance(job.label, str) and isinstance(job.program, list) and job.program):
        raise ConfigError(f"{module.name}: {job!r} needs a string label and a program list")

    try:
        plistlib.dumps(job.plist)
    except (TypeError, ValueError, OverflowError):
        raise ConfigError(f"{module.name}: launchd {job.label} has an unwritable value") from None


def check_module(module: Module) -> None:
    if module.setup_check and not module.setup:
        raise ConfigError(f"{module.name}: setup_check needs a setup")

    for setting in module.defaults:
        setting_place(module, setting)

    for job in module.launchd:
        check_job(module, job)


def check_config(modules: list[Module]) -> None:
    owners: dict[str, str] = {}
    jobs: dict[str, str] = {}
    for module in modules:
        check_module(module)
        for setting in module.defaults:
            place = setting_place(module, setting)
            if place in owners:
                raise ConfigError(f"{place} is set twice, in {owners[place]} and {module.name}")

            owners[place] = module.name

        for job in module.launchd:
            if job.label in jobs:
                raise ConfigError(
                    f"launchd {job.label} is defined twice, in {jobs[job.label]} and {module.name}"
                )

            jobs[job.label] = module.name


def float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def same(current: Any, wanted: Any, numbers: bool = False) -> bool:
    if isinstance(wanted, dict):
        return (
            isinstance(current, dict)
            and current.keys() == wanted.keys()
            and all(same(current[key], value, numbers) for key, value in wanted.items())
        )

    if isinstance(wanted, list):
        return (
            isinstance(current, list)
            and len(current) == len(wanted)
            and all(same(c, w, numbers) for c, w in zip(current, wanted))
        )

    # With `numbers`, bool, int and float match by value, as macOS may store 0 for False or 25.0
    # for 25; `defaults write -float` stores a float32, so 0.05 reads back as 0.05000000074505806.
    kinds = {type(current), type(wanted)}
    if (numbers and kinds <= {bool, int, float}) or kinds == {float}:
        return float32(current) == float32(wanted) if float in kinds else current == wanted

    return type(current) is type(wanted) and current == wanted


def current_value(setting: Default | Hotkey, values: dict[str, Any]) -> Any:
    current = values.get(setting.key)
    if isinstance(setting, Hotkey):
        current = current.get(str(setting.id)) if isinstance(current, dict) else None

    return current


def hotkey_text(entry: Any) -> str:
    if not isinstance(entry, dict):
        return "unset"

    value = entry.get("value")
    params = value.get("parameters") if isinstance(value, dict) else None
    params = ", ".join(map(str, params)) if isinstance(params, list) else ""
    if entry.get("enabled") is True:
        return params or "enabled"

    return f"disabled {params}" if params else "disabled"


def change_text(setting: Default | Hotkey, current: Any) -> str:
    if isinstance(setting, Hotkey):
        return f"{setting}: {hotkey_text(current)} → {hotkey_text(setting.value)}"

    was = "unset" if current is None else current
    return f"{setting.domain} {setting.key}: {was} → {setting.value}"


def read_domain(domain: str) -> dict[str, Any]:
    command = ["defaults", "export", domain_name(domain), "-"]
    return plistlib.loads(subprocess.run(command, capture_output=True, check=True).stdout)


def typed(value: Any) -> list[str]:
    if isinstance(value, bool):
        return ["-bool", "true" if value else "false"]

    if isinstance(value, int):
        return ["-int", str(value)]

    if isinstance(value, float):
        return ["-float", repr(value)]

    return ["-string", value]


def write_command(setting: Default | Hotkey) -> list[str]:
    command = ["defaults", "write", setting.domain, setting.key]
    if isinstance(setting, Hotkey):
        return command + ["-dict-add", str(setting.id), plistlib.dumps(setting.value).decode()]

    return command + typed(setting.value)


def settle(written: list[Default | Hotkey]) -> None:
    logout = [f"{s.domain} {s.key}" for s in written if s.logout]
    if logout:
        print(paint(f"log out to apply: {', '.join(logout)}", "33"))

    for app in sorted({RESTART[s.domain] for s in written if s.domain in RESTART}):
        heading(f"restart {app}")
        subprocess.run(["killall", app], check=False, capture_output=True)

    if any(s.activate for s in written):
        execute([ACTIVATE_SETTINGS, "-u"])


def write_defaults(settings: list[Default | Hotkey]) -> None:
    heading("defaults")
    written = []
    try:
        for setting in settings:
            subprocess.run(write_command(setting), check=True)
            written.append(setting)
            print(action("~", "33", str(setting)))
    except BaseException:
        # Settle what was written, but let the original error through.
        with suppress(Exception):
            settle(written)

        raise

    settle(written)


# MARK: Launchd


def loaded(job: LaunchAgent | AppleAgent) -> bool:
    command = ["launchctl", "print", f"{job.domain}/{job.label}"]
    return subprocess.run(command, check=False, capture_output=True).returncode == 0


def job_status(job: LaunchAgent | AppleAgent) -> str:
    if isinstance(job, AppleAgent):
        command = ["launchctl", "print-disabled", job.domain]
        listing = subprocess.run(command, check=False, capture_output=True).stdout.decode()
        if f'"{job.label}" => disabled' in listing:
            return "disabled"

        return "ok" if loaded(job) else "unloaded"

    try:
        current = plistlib.loads(job.path.read_bytes())
    except FileNotFoundError:
        return "missing"
    except (OSError, ValueError):
        return "differs"

    if not same(current, job.plist):
        return "differs"

    return "ok" if loaded(job) else "differs"


def install_job(job: LaunchAgent | AppleAgent) -> None:
    heading(f"launchd {job.label}")
    if isinstance(job, AppleAgent):
        subprocess.run(["launchctl", "enable", f"{job.domain}/{job.label}"], check=True)
        if not loaded(job):
            subprocess.run(["launchctl", "bootstrap", job.domain, str(job.path)], check=True)

        return

    sudo = ["sudo"] if job.system else []
    if job.system:
        with tempfile.NamedTemporaryFile() as plist:
            plistlib.dump(job.plist, plist)
            plist.flush()
            owned = ["install", "-o", "root", "-g", "wheel", "-m", "0644"]
            subprocess.run([*sudo, *owned, plist.name, str(job.path)], check=True)
    else:
        job.path.parent.mkdir(parents=True, exist_ok=True)
        job.path.write_bytes(plistlib.dumps(job.plist))
        job.path.chmod(0o644)

    service = f"{job.domain}/{job.label}"
    subprocess.run([*sudo, "launchctl", "bootout", service], check=False, capture_output=True)
    bootstrap = [*sudo, "launchctl", "bootstrap", job.domain, str(job.path)]
    # launchd can still be tearing the old job down right after `bootout`.
    if subprocess.run(bootstrap, check=False, capture_output=True).returncode != 0:
        time.sleep(1)
        subprocess.run(bootstrap, check=True)


# MARK: Plan


def make_plan(
    modules: list[Module],
    installed: dict[str, set[str]],
    state: dict[str, str],
    env: dict[str, str] | None = None,
) -> list[Step]:
    check_config(modules)
    covered = {kind: set(names) for kind, names in installed.items()}

    def missing(kind: str, names: list[str]) -> list[str]:
        result = [name for name in names if package_name(name) not in covered[kind]]
        covered[kind].update(package_name(name) for name in result)
        return result

    domains: dict[str, dict[str, Any]] = {}
    steps = []
    for module in modules:
        links = []
        for source, target in module_links(module):
            status = link_status(source, target)
            if status != "ok":
                links.append((source, target, status))

        defaults = []
        for setting in module.defaults:
            name = domain_name(setting.domain)
            if name not in domains:
                domains[name] = read_domain(name)

            current = current_value(setting, domains[name])
            if not same(current, setting.value, numbers=True):
                defaults.append((setting, current))

        jobs = []
        for job in module.launchd:
            status = job_status(job)
            if status != "ok":
                jobs.append((job, status))

        brew = missing("formula", module.brew)
        cask = missing("cask", module.cask)
        tools = missing("cargo", module.cargo)
        reason = setup_reason(module, bool(brew or cask or links), state, env)
        steps.append(Step(module, brew, cask, tools, links, reason, defaults, jobs))

    return steps


# MARK: Output

LINK_STYLES = {
    "new": ("+", "32", "", "to link"),
    "same": ("~", "33", "", "to replace (same content)"),
    "differs": ("!", "1;31", "(differs)", "differ from the repository"),
    "relink": ("~", "33", "(relink)", "to relink"),
    "missing": ("!", "1;31", "(missing in the repository)", "missing in the repository"),
}


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


def tilde(path: Path) -> str:
    return f"~/{path.relative_to(Path.home())}"


def action(symbol: str, color: str, text: str, note: str = "") -> str:
    line = f"  {paint(symbol, color)} {text}"
    return f"{line} {paint(note, '2')}" if note else line


def step_actions(step: Step) -> list[str]:
    lines = []
    for kind, packages in (("brew", step.brew), ("cask", step.cask), ("cargo", step.cargo)):
        if packages:
            lines.append(action("+", "32", f"{kind}: {' '.join(packages)}"))

    for _, target, status in step.links:
        symbol, color, note, _ = LINK_STYLES[status]
        lines.append(action(symbol, color, tilde(target), note))

    for setting, current in step.defaults:
        lines.append(action("~", "33", change_text(setting, current)))

    for job, status in step.jobs:
        symbol, color = ("+", "32") if status == "missing" else ("~", "33")
        lines.append(action(symbol, color, f"launchd {job.label}"))

    if step.setup_reason:
        lines.append(action(">", "36", "setup", f"({step.setup_reason})"))

    return lines


def summary(steps: list[Step]) -> str:
    statuses = [status for step in steps for _, _, status in step.links]
    counts = [(sum(len(s.brew) + len(s.cask) + len(s.cargo) for s in steps), "to install")]
    counts += [(statuses.count(status), style[3]) for status, style in LINK_STYLES.items()]
    counts.append((sum(len(s.defaults) for s in steps), "defaults to write"))
    counts.append((sum(len(s.jobs) for s in steps), "launchd to load"))
    counts.append((sum(bool(s.setup_reason) for s in steps), "setup"))
    parts = [f"{count} {what}" for count, what in counts if count]
    return f"Plan: {', '.join(parts)}." if parts else "No changes."


def diff_command(source: Path, target: Path) -> str:
    home_path = shlex.quote(str(target.relative_to(Path.home())))
    return f"diff -ru ~/{home_path} {shlex.quote(str(source.relative_to(REPO)))}"


def show_plan(steps: list[Step], unused: list[Module]) -> None:
    unchanged = []
    for step in steps:
        lines = step_actions(step)
        if not lines:
            unchanged.append(step.module.name)
            continue

        print(paint(step.module.name, "1"))
        print("\n".join(lines))

    if unchanged and len(unchanged) < len(steps):
        print(paint(f"no changes: {', '.join(unchanged)}", "2"))

    differing = [link for step in steps for link in step.links if link[2] == "differs"]
    if differing:
        print(paint("compare, then move what you want to keep into the repository:", "1;31"))
        for source, target, _ in differing:
            print(f"  {diff_command(source, target)}")

    if unused:
        names = ", ".join(module.name for module in unused)
        print(paint(f"unused: {names} — no profile uses them", "2"))

    stray = stray_links([step.module for step in steps])
    if stray:
        print(paint("stray links, left as they are:", "33"))
        for path, reason in stray:
            print(action("?", "33", tilde(path), f"({reason})"))

    print()
    print(paint(summary(steps), "1"))


# MARK: Apply


def confirm() -> bool:
    try:
        answer = input(paint('Apply? Type "yes" to continue: ', "1"))
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer.strip() == "yes"


def heading(text: str) -> None:
    print(paint(f"▶ {text}", "1;35"), flush=True)


def execute(command: list[str], **options: object) -> None:
    heading(shlex.join([Path(command[0]).name, *command[1:]]))
    subprocess.run(command, check=True, **options)


def apply(steps: list[Step], brew: str | None, env: dict[str, str]) -> None:
    formulae = [package for step in steps for package in step.brew]
    casks = [package for step in steps for package in step.cask]
    quiet = {**env, "HOMEBREW_NO_ASK": "1", "HOMEBREW_NO_ENV_HINTS": "1"}
    if formulae or casks:
        execute([brew, "update", "--quiet"], env=quiet)

    quiet["HOMEBREW_NO_AUTO_UPDATE"] = "1"
    if formulae:
        execute([brew, "install", "--quiet", "--formula", *formulae], env=quiet)

    if casks:
        execute([brew, "install", "--quiet", "--cask", *casks], env=quiet)

    links = [link for step in steps for link in step.links]
    if links:
        heading("links")

    for source, target, status in links:
        note = (
            f"(old one in {backup_path(target).relative_to(REPO)})" if status == "differs" else ""
        )
        link(source, target, status)
        symbol, color, _, _ = LINK_STYLES[status]
        print(action(symbol, color, tilde(target), note))

    settings = [setting for step in steps for setting, _ in step.defaults]
    if settings:
        write_defaults(settings)

    for job, _ in [job for step in steps for job in step.jobs]:
        install_job(job)

    state = read_state()
    traced = {**env, "PS4": paint("$ ", "36") + " "}
    for step in steps:
        if step.setup_reason:
            heading(f"setup {step.module.name}")
            setup = dedent(step.module.setup)
            subprocess.run(["sh", "-eux", "-c", setup], cwd=REPO, env=traced, check=True)
            state[step.module.name] = setup_hash(step.module)
            write_state(state)

        if step.cargo:
            execute(["cargo", "install", "--locked", "--quiet", *step.cargo], env=env)


# MARK: Run


USAGE = "usage: config.py [plan | apply [--force]]"


def parse_args(args: list[str]) -> tuple[str, str | None]:
    command, rest = (args[0], args[1:]) if args else ("plan", [])
    valid = {"plan": not rest, "apply": rest in ([], ["--force"])}
    if not valid.get(command):
        sys.exit(USAGE)

    return command, rest[0] if rest else None


def read_profile(profiles: tuple[Profile, ...]) -> Profile | None:
    # The profile is chosen once per machine and kept in the untracked .profile.
    name = ""
    with suppress(FileNotFoundError):
        name = (REPO / ".profile").read_text().strip()

    return next((profile for profile in profiles if profile.name == name), None)


def run(*profiles: Profile) -> None:
    command, arg = parse_args(sys.argv[1:])
    profile = read_profile(profiles)
    if profile is None:
        names = ", ".join(p.name for p in profiles)
        sys.exit(f"choose a profile: echo <name> > .profile (profiles: {names})")

    try:
        check_names()
        unused = check_profiles()
        modules = resolve(profile.modules)
        brew = find_brew()
        env = tool_env(brew)
        installed = {
            "formula": installed_packages(brew, "formula"),
            "cask": installed_packages(brew, "cask"),
            "cargo": installed_cargo(env),
        }
        steps = make_plan(modules, installed, read_state(), env)
        print(paint(f"profile: {profile.name}", "1"))
        show_plan(steps, unused)

        links = [link for step in steps for link in step.links]
        if any(status == "missing" for _, _, status in links):
            raise ConfigError("some files are missing in the repository, see the plan")

        if command == "plan" or not any(step.changes for step in steps):
            return

        differing = [link for link in links if link[2] == "differs"]
        if differing and arg != "--force":
            sys.stdout.flush()
            sys.exit(
                "Some files differ from the repository, see the plan above; resolve them\nor run `config.py apply --force` to move them to .backup/ here."
            )

        if brew is None and any(step.brew or step.cask for step in steps):
            raise ConfigError("Homebrew is not installed: install it from https://brew.sh first")

        if not confirm():
            print("Nothing changed.")
            return

        apply(steps, brew, env)
    except ConfigError as error:
        sys.exit(paint(f"config error: {error}", "1;31"))
    except subprocess.CalledProcessError as error:
        sys.exit(paint(f"failed: {' '.join(map(str, error.cmd))}", "1;31"))
    except OSError as error:
        sys.exit(paint(f"failed: {error}", "1;31"))
