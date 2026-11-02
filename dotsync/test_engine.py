#!/usr/bin/python3

from __future__ import annotations

import io
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from contextlib import AbstractContextManager, redirect_stdout
from pathlib import Path
from unittest import mock

import engine
from engine import (
    ACTIVATE_SETTINGS,
    AppleAgent,
    ConfigError,
    Default,
    Hotkey,
    LaunchAgent,
    LaunchDaemon,
    Module,
    Profile,
    apply,
    backup_path,
    check_names,
    installed_cargo,
    job_status,
    link_status,
    make_plan,
    read_state,
    resolve,
    run,
    same,
    setup_hash,
    setup_reason,
    step_actions,
    stray_links,
    summary,
    typed,
)

NOTHING = {"formula": set(), "cask": set(), "cargo": set()}


class Clean(unittest.TestCase):
    def setUp(self) -> None:
        engine.MODULES.clear()
        engine.PROFILES.clear()


class ResolveTest(Clean):
    def test_needs_come_first_once(self) -> None:
        base = Module("base")
        fonts = Module("fonts")
        a = Module("a", needs=[base, fonts])
        b = Module("b", needs=[base])

        self.assertEqual(resolve([a, b]), [base, fonts, a, b])

    def test_keeps_profile_order(self) -> None:
        a, b = Module("a"), Module("b")

        self.assertEqual(resolve([b, a]), [b, a])

    def test_cycle(self) -> None:
        a = Module("a")
        b = Module("b", needs=[a])
        c = Module("c", needs=[b])
        a.needs.append(c)

        with self.assertRaisesRegex(ConfigError, "dependency cycle: a -> c -> b -> a"):
            resolve([a])

    def test_self_cycle(self) -> None:
        a = Module("a")
        a.needs.append(a)

        with self.assertRaisesRegex(ConfigError, "dependency cycle: a -> a"):
            resolve([a])

    def test_need_is_not_a_module(self) -> None:
        a = Module("a", needs=["git"])

        with self.assertRaisesRegex(ConfigError, "a needs 'git', which is not a module"):
            resolve([a])

    def test_profile_item_is_not_a_module(self) -> None:
        with self.assertRaisesRegex(ConfigError, "'git' is not a module"):
            resolve(["git"])

    def test_duplicate_names(self) -> None:
        Module("git")
        Module("git")

        with self.assertRaisesRegex(ConfigError, "two modules are named git"):
            check_names()

    def test_duplicate_profile_names(self) -> None:
        Profile("air", [])
        Profile("air", [])

        with self.assertRaisesRegex(ConfigError, "two profiles are named air"):
            check_names()


class TempHome(Clean):
    def setUp(self) -> None:
        super().setUp()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name).resolve() / "repo"
        self.home = Path(temp.name, "home")
        (self.repo / "config").mkdir(parents=True)
        (self.repo / "config" / "app.conf").write_text("x")
        (self.home / ".config").mkdir(parents=True)

        patches = [
            mock.patch.object(engine, "REPO", self.repo),
            mock.patch.dict(os.environ, {"HOME": str(self.home)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)


class ProfilesTest(TempHome):
    def setUp(self) -> None:
        super().setUp()
        (self.repo / ".profile").write_text("air\n")

    def plan(self, *profiles: Profile, args: tuple[str, ...] = ()) -> str:
        out = io.StringIO()
        with (
            mock.patch("sys.argv", ["config.py", *args]),
            mock.patch.object(engine, "find_brew", return_value=None),
            mock.patch.object(engine, "installed_cargo", return_value=set()),
            redirect_stdout(out),
        ):
            run(*profiles)

        return out.getvalue()

    def fails(self, *profiles: Profile, args: tuple[str, ...] = ()) -> str:
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            self.plan(*profiles, args=args)

        return str(raised.exception.code)

    def test_plan_and_apply_need_a_profile(self) -> None:
        profiles = Profile("air", []), Profile("pro", [])
        commands = ((), ("plan",), ("apply",), ("apply", "--force"))
        for content in (None, "", "\n", "mini\n"):
            (self.repo / ".profile").unlink(missing_ok=True)
            if content is not None:
                (self.repo / ".profile").write_text(content)

            for args in commands:
                with mock.patch.object(engine, "check_names") as checked:
                    error = self.fails(*profiles, args=args)

                self.assertEqual(
                    error, "choose a profile: echo <name> > .profile (profiles: air, pro)"
                )
                self.assertFalse(checked.called)

    def test_bad_args(self) -> None:
        air = Profile("air", [])
        cases = (
            ("air",),
            ("--force",),
            ("--force", "apply"),
            ("plan", "air"),
            ("plan", "--force"),
            ("apply", "air"),
            ("apply", "-x"),
            ("apply", "--force", "--force"),
            ("profile",),
            ("profile", "pro"),
        )
        for args in cases:
            self.assertEqual(self.fails(air, args=args), engine.USAGE)

        self.assertEqual((self.repo / ".profile").read_text(), "air\n")

    def test_broken_other_profile_is_reported(self) -> None:
        a = Module("a")
        b = Module("b")
        b.needs = [b]
        air = Profile("air", [a])
        Profile("mini", [a, b])

        self.assertIn("profile mini: dependency cycle: b -> b", self.fails(air))

    def test_conflict_in_other_profile_is_reported(self) -> None:
        a = Module("a", defaults=[DOCK])
        air = Profile("air", [a])
        Profile("mini", [a, Module("b", defaults=[DOCK])])

        error = self.fails(air)
        self.assertIn("profile mini: com.apple.dock tilesize is set twice", error)

    def test_unused_module_is_checked(self) -> None:
        Module("npm", setup_check="true")
        air = Profile("air", [Module("a")])

        self.assertIn("npm: setup_check needs a setup", self.fails(air))

    def test_unused_modules_may_set_the_same_key(self) -> None:
        Module("a", defaults=[DOCK])
        Module("b", defaults=[DOCK])

        self.assertIn("unused: a, b", self.plan(Profile("air", [Module("c")])))

    def test_unused_modules(self) -> None:
        base = Module("base")
        app = Module("app", needs=[base])
        Module("npm")
        Module("mise")
        air = Profile("air", [app])

        self.assertIn("unused: npm, mise — no profile uses them\n", self.plan(air))

    def test_no_unused_line_when_all_are_used(self) -> None:
        self.assertNotIn("unused", self.plan(Profile("air", [Module("a")])))

    def test_run_takes_a_profile(self) -> None:
        fonts = Module("fonts")
        app = Module("app", needs=[fonts])
        output = self.plan(Profile("air", [fonts, app]))

        self.assertEqual(output.splitlines()[-1], "No changes.")


class LinksTest(TempHome):
    def test_status(self) -> None:
        source = self.repo / "config" / "app.conf"
        target = self.home / ".config" / "app.conf"
        self.assertEqual(link_status(source, target), "new")

        target.write_text("old")
        self.assertEqual(link_status(source, target), "differs")

        target.write_text("x")
        self.assertEqual(link_status(source, target), "same")

        target.unlink()
        target.symlink_to(source)
        self.assertEqual(link_status(source, target), "ok")

        target.unlink()
        target.symlink_to(self.repo / "config")
        self.assertEqual(link_status(source, target), "relink")

        self.assertEqual(link_status(self.repo / "gone", target), "missing")

    def test_folder_content(self) -> None:
        source = self.repo / "config"
        target = self.home / ".config" / "copy"
        shutil.copytree(source, target)
        self.assertEqual(link_status(source, target), "same")

        (target / "app.conf").write_text("edited")
        self.assertEqual(link_status(source, target), "differs")

        (target / "app.conf").write_text("x")
        (target / "extra").write_text("")
        self.assertEqual(link_status(source, target), "differs")

    def test_folder_with_hidden_differences(self) -> None:
        source = self.repo / "config"
        target = self.home / ".config" / "copy"
        shutil.copytree(source, target)
        (target / ".git").mkdir()
        self.assertEqual(link_status(source, target), "differs")

        shutil.rmtree(target / ".git")
        (source / "x").write_text("")
        (target / "x").mkdir()
        (target / "x" / "data").write_text("mine")
        self.assertEqual(link_status(source, target), "differs")

    def test_target_inside_a_linked_parent(self) -> None:
        parent = self.home / ".config" / "linked"
        parent.symlink_to(self.repo / "config")

        self.assertEqual(link_status(self.repo / "config" / "app.conf", parent / "app.conf"), "ok")

    def test_stray_links(self) -> None:
        wanted = Module("wanted", files={"config/app.conf": "~/.config/app.conf"})
        Module("other", files={"config": "~/.config/other"})
        (self.home / ".config" / "app.conf").symlink_to(self.repo / "config" / "app.conf")
        (self.home / ".config" / "other").symlink_to(self.repo / "config")
        (self.home / ".config" / "old").symlink_to(self.repo / "gone")
        (self.home / ".config" / "foreign").symlink_to(self.home)

        stray = dict(stray_links([wanted]))

        self.assertEqual(
            stray,
            {
                self.home / ".config" / "other": "other is not in the profile",
                self.home / ".config" / "old": "broken",
            },
        )


class DiffTest(TempHome):
    def actions(self, source: str, target: str) -> list[str]:
        (step,) = make_plan([Module("m", files={source: target})], NOTHING, {})
        with redirect_stdout(io.StringIO()):
            return step_actions(step)

    def test_file(self) -> None:
        (self.repo / "config" / "app.conf").write_text("a\nb\nnew\nc\nd\ne\n")
        (self.home / ".config" / "app.conf").write_text("a\nb\nold\nc\nd\ne\n")

        self.assertEqual(
            self.actions("config/app.conf", "~/.config/app.conf"),
            [
                "  ! ~/.config/app.conf (differs)",
                "      --- ~/.config/app.conf",
                "      +++ config/app.conf",
                "      @@ -1,5 +1,5 @@",
                "       a",
                "       b",
                "      -old",
                "      +new",
                "       c",
                "       d",
            ],
        )

    def test_long_diff_is_cut(self) -> None:
        (self.repo / "config" / "app.conf").write_text("".join(f"new {i}\n" for i in range(30)))
        (self.home / ".config" / "app.conf").write_text("old\n")

        lines = self.actions("config/app.conf", "~/.config/app.conf")

        self.assertEqual(len(lines), 1 + engine.DIFF_LINES + 1)
        self.assertEqual(lines[-2:], ["      +new 15", "      … 14 more lines"])

    def test_directory(self) -> None:
        source = self.repo / "config"
        (source / "sub").mkdir()
        (source / "sub" / "a.txt").write_text("one\n")
        (source / "added").write_text("")
        target = self.home / ".config" / "dir"
        shutil.copytree(source, target)
        (target / "sub" / "a.txt").write_text("two\n")
        (target / "app.conf").write_bytes(b"\0\1")
        (target / "added").unlink()
        (target / "extra").write_text("")

        self.assertEqual(
            self.actions("config", "~/.config/dir"),
            [
                "  ! ~/.config/dir (differs)",
                "      + added",
                "      ~ app.conf",
                "      - extra",
                "      ~ sub/a.txt",
                "      --- ~/.config/dir/sub/a.txt",
                "      +++ config/sub/a.txt",
                "      @@ -1 +1 @@",
                "      -two",
                "      +one",
            ],
        )

    def test_many_files_are_cut(self) -> None:
        target = self.home / ".config" / "dir"
        shutil.copytree(self.repo / "config", target)
        for i in range(12):
            (target / f"extra{i:02}").write_text("")

        lines = self.actions("config", "~/.config/dir")

        self.assertEqual(lines[-2:], ["      - extra09", "      … 2 more files"])

    def test_binary(self) -> None:
        (self.repo / "config" / "app.conf").write_bytes(b"\xff\xfe")
        (self.home / ".config" / "app.conf").write_text("text\n")

        self.assertEqual(
            self.actions("config/app.conf", "~/.config/app.conf")[1:], ["      binary file differs"]
        )


class PlanTest(TempHome):
    def test_installed_packages_are_skipped(self) -> None:
        module = Module("m", brew=["git", "umputun/apps/revdiff", "fish"], cask=["zed"])

        (step,) = make_plan(
            [module], {"formula": {"git", "revdiff"}, "cask": {"zed", "fish"}, "cargo": set()}, {}
        )

        self.assertEqual((step.brew, step.cask), (["fish"], []))
        self.assertTrue(step.changes)

    def test_shared_package_is_planned_once(self) -> None:
        a = Module("a", brew=["uv", "gh"])
        b = Module("b", brew=["uv", "jq"])

        steps = make_plan([a, b], {"formula": {"gh"}, "cask": set(), "cargo": set()}, {})

        self.assertEqual([step.brew for step in steps], [["uv"], ["jq"]])

    def test_each_entry_of_a_folder(self) -> None:
        (self.repo / "config" / ".DS_Store").write_text("")
        (self.repo / "config" / "__pycache__").mkdir()
        (self.repo / "config" / "tool").write_text("")
        module = Module("m", files={"config/*": "~/bin"})

        (step,) = make_plan([module], NOTHING, {})

        targets = [target for _, target, _ in step.links]
        self.assertEqual(targets, [self.home / "bin" / "app.conf", self.home / "bin" / "tool"])

    def test_nothing_to_change(self) -> None:
        target = self.home / ".config" / "app.conf"
        target.symlink_to(self.repo / "config" / "app.conf")
        module = Module("m", brew=["git"], files={"config/app.conf": "~/.config/app.conf"})

        (step,) = make_plan([module], {"formula": {"git"}, "cask": set(), "cargo": set()}, {})

        self.assertFalse(step.changes)

    def test_backup_path(self) -> None:
        backup = backup_path(self.home / ".config" / "app.conf")

        self.assertEqual(backup.parent.parent.parent, self.repo / ".backup")
        self.assertEqual(backup.relative_to(backup.parent.parent), Path(".config/app.conf"))


class ToolsTest(TempHome):
    def fake(self, name: str, script: str) -> dict[str, str]:
        bin_dir = self.home / "bin"
        bin_dir.mkdir(exist_ok=True)
        path = bin_dir / name
        path.write_text(f"#!/bin/sh\n{script}\n")
        path.chmod(0o755)
        return {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}

    def test_installed_cargo(self) -> None:
        env = self.fake(
            "cargo",
            "printf 'cargo-edit v0.13.13:\\n    cargo-add\\nwavo v0.1.0 (git):\\n    wavo\\n'",
        )

        self.assertEqual(installed_cargo(env), {"cargo-edit", "wavo"})

    def test_no_cargo(self) -> None:
        self.assertEqual(installed_cargo({"PATH": str(self.home)}), set())

    def test_plan_tools(self) -> None:
        module = Module("m", cargo=["cargo-edit", "shipo"])

        (step,) = make_plan(
            [module], {"formula": set(), "cask": set(), "cargo": {"cargo-edit"}}, {}
        )

        self.assertEqual(step.cargo, ["shipo"])

    def test_setup_runs_before_cargo(self) -> None:
        log = self.home / "log.txt"
        env = self.fake("cargo", f'echo "cargo $*" >> "{log}"')
        module = Module("m", cargo=["shipo"], setup=f'echo setup >> "{log}"')

        out = io.StringIO()
        with redirect_stdout(out):
            apply(make_plan([module], NOTHING, {}), None, env)

        self.assertEqual(log.read_text(), "setup\ncargo install --locked --quiet shipo\n")
        self.assertEqual(out.getvalue(), "▶ setup m ok\n▶ cargo shipo ok\n")


class SetupReasonTest(Clean):
    def test_reasons(self) -> None:
        module = Module("m", setup="echo one")
        recorded = {"m": setup_hash(module)}

        self.assertIsNone(setup_reason(Module("plain"), True, {}))
        self.assertEqual(setup_reason(module, False, {}), "first run")
        self.assertEqual(setup_reason(module, False, {"m": "old"}), "changed")
        self.assertEqual(setup_reason(module, True, recorded), "module changed")
        self.assertIsNone(setup_reason(module, False, recorded))

    def test_check_passes(self) -> None:
        module = Module("m", setup="echo one", setup_check="true")

        self.assertIsNone(setup_reason(module, False, {"m": setup_hash(module)}))

    def test_check_fails(self) -> None:
        module = Module("m", setup="echo one", setup_check="exit 1")
        recorded = {"m": setup_hash(module)}

        self.assertEqual(setup_reason(module, False, recorded), "check failed")
        self.assertEqual(setup_reason(module, True, recorded), "check failed")

    def test_check_runs_with_env_in_repo(self) -> None:
        module = Module(
            "m", setup="echo one", setup_check='[ "$(pwd -P)" = "$WANT" ] && [ "$X" = 1 ]'
        )
        recorded = {"m": setup_hash(module)}
        env = {**os.environ, "WANT": str(engine.REPO), "X": "1"}

        self.assertIsNone(setup_reason(module, False, recorded, env))
        self.assertEqual(setup_reason(module, False, recorded, {**env, "X": "2"}), "check failed")

    def test_check_not_run_before_setup(self) -> None:
        module = Module("m", setup="echo one", setup_check="true")

        with mock.patch.object(engine.subprocess, "run") as run_check:
            self.assertEqual(setup_reason(module, False, {}), "first run")
            self.assertEqual(setup_reason(module, False, {"m": "old"}), "changed")

        run_check.assert_not_called()

    def test_check_timeout_fails(self) -> None:
        module = Module("m", setup="echo one", setup_check="sleep 5")

        with mock.patch.object(engine, "CHECK_TIMEOUT", 0.1):
            self.assertEqual(setup_reason(module, False, {"m": setup_hash(module)}), "check failed")

    def test_check_without_setup(self) -> None:
        with self.assertRaisesRegex(ConfigError, "m: setup_check needs a setup"):
            make_plan([Module("m", setup_check="true")], NOTHING, {})

    def test_plan_shows_failed_check(self) -> None:
        module = Module("m", setup="echo one", setup_check="false")

        (step,) = make_plan([module], NOTHING, {"m": setup_hash(module)})

        self.assertEqual(step_actions(step), ["  > setup (check failed)"])

    def test_hash_ignores_indentation(self) -> None:
        a = Module("a", setup="\n    echo one\n    ")
        b = Module("b", setup="echo one")

        self.assertEqual(setup_hash(a), setup_hash(b))


class ApplyTest(TempHome):
    def module(self) -> Module:
        return Module(
            "m", files={"config/app.conf": "~/.config/app.conf", "config": "~/.config/dir"}
        )

    def run_main(self, answer: str, *flags: str) -> None:
        (self.repo / ".profile").write_text("p\n")
        with (
            mock.patch("sys.argv", ["config.py", "apply", *flags]),
            mock.patch("builtins.input", return_value=answer),
            mock.patch.object(engine, "find_brew", return_value=None),
            mock.patch.object(engine, "installed_cargo", return_value=set()),
            mock.patch("sys.stdout"),
        ):
            run(Profile("p", [self.module()]))

    def test_declined(self) -> None:
        (self.home / ".config" / "app.conf").write_text("x")

        self.run_main("y")

        self.assertFalse((self.home / ".config" / "app.conf").is_symlink())
        self.assertFalse((self.home / ".config" / "dir").exists())

    def test_same_content_is_replaced_without_backup(self) -> None:
        (self.home / ".config" / "app.conf").write_text("x")
        shutil.copytree(self.repo / "config", self.home / ".config" / "dir")

        self.run_main("yes")

        target = self.home / ".config" / "app.conf"
        self.assertEqual(Path(os.readlink(target)), self.repo / "config" / "app.conf")
        self.assertEqual(Path(os.readlink(self.home / ".config" / "dir")), self.repo / "config")
        self.assertEqual(
            sorted(p.name for p in (self.home / ".config").iterdir()), ["app.conf", "dir"]
        )

    def test_differences_stop_apply(self) -> None:
        (self.home / ".config" / "app.conf").write_text("old")

        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            self.run_main("yes")

        self.assertFalse((self.home / ".config" / "app.conf").is_symlink())
        self.assertFalse((self.home / ".config" / "dir").exists())

    def test_force_moves_differences_to_backup(self) -> None:
        target = self.home / ".config" / "app.conf"
        target.write_text("old")
        backup = backup_path(target)

        self.run_main("yes", "--force")

        self.assertEqual(Path(os.readlink(target)), self.repo / "config" / "app.conf")
        self.assertEqual(backup.read_text(), "old")
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["app.conf", "dir"])

    def test_relink_and_setup(self) -> None:
        target = self.home / ".config" / "app.conf"
        target.symlink_to(self.home)
        module = Module(
            "m",
            files={"config/app.conf": "~/.config/app.conf"},
            setup='echo done > "$HOME/setup.txt"',
        )

        with mock.patch("sys.stdout"):
            apply(make_plan([module], NOTHING, {}), None, dict(os.environ))

        self.assertEqual(Path(os.readlink(target)), self.repo / "config" / "app.conf")
        self.assertEqual((self.home / "setup.txt").read_text(), "done\n")

    def test_setup_reruns_only_when_changed(self) -> None:
        module = Module("m", setup='echo run >> "$HOME/runs.txt"')
        with mock.patch("sys.stdout"):
            apply(make_plan([module], NOTHING, read_state()), None, dict(os.environ))

        (step,) = make_plan([module], NOTHING, read_state())
        self.assertFalse(step.changes)

        module.setup = 'echo run >> "$HOME/runs.txt"\necho more'
        (step,) = make_plan([module], NOTHING, read_state())
        self.assertEqual(step.setup_reason, "changed")
        with mock.patch("sys.stdout"):
            apply([step], None, dict(os.environ))

        self.assertEqual((self.home / "runs.txt").read_text(), "run\nrun\n")

    def test_setup_is_quiet(self) -> None:
        module = Module("m", setup="echo hidden\necho hidden too >&2")

        out = io.StringIO()
        with redirect_stdout(out):
            apply(make_plan([module], NOTHING, {}), None, dict(os.environ))

        self.assertEqual(out.getvalue(), "▶ setup m ok\n")

    def test_failed_setup_shows_output_and_is_not_recorded(self) -> None:
        module = Module("m", setup="echo one\necho two >&2\nexit 3\necho never")

        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(subprocess.CalledProcessError) as raised:
            apply(make_plan([module], NOTHING, read_state()), None, dict(os.environ))

        self.assertEqual(out.getvalue(), "▶ setup m failed\n    one\n    two\n")
        self.assertEqual(raised.exception.returncode, 3)
        self.assertEqual(read_state(), {})

    def test_setup_fails_on_unset_variable(self) -> None:
        module = Module("m", setup='echo "$UNSET_DOTSYNC_VAR"')
        env = {k: v for k, v in os.environ.items() if k != "UNSET_DOTSYNC_VAR"}

        with redirect_stdout(io.StringIO()), self.assertRaises(subprocess.CalledProcessError):
            apply(make_plan([module], NOTHING, {}), None, env)


DOCK = Default("com.apple.dock", "tilesize", 56)
SPEED = Default("-g", "KeyRepeat", 5, logout=True)
FN = Default("-g", "com.apple.keyboard.fnState", True, activate=True)
QUICK = Default("-g", "QLPanelAnimationDuration", 0.05)
CLOCK = Default("com.apple.menuextra.clock", "ShowSeconds", True)
HOTKEY = Hotkey(61, [65535, 80, 0])
HOTKEY_ENTRY = {"enabled": True, "value": {"parameters": [65535, 80, 0], "type": "standard"}}
REMAP = LaunchAgent("test.remap", ["/bin/true", {"a": [1, 2]}])
SNAP = LaunchDaemon("test.snap", ["/usr/bin/tmutil", "localsnapshot"], hourly=True)
RCD = AppleAgent("com.apple.rcd")


class Mac:
    def __init__(
        self,
        domains: dict | None = None,
        loaded: tuple[str, ...] = (),
        fails: dict | None = None,
        missing: tuple[str, ...] = (),
        overrides: dict | None = None,
    ) -> None:
        self.domains = domains or {}
        self.loaded = set(loaded)
        self.fails = fails or {}
        self.missing = set(missing)
        self.overrides = overrides or {}
        self.asked = False
        self.exports = []
        self.commands = []
        self.installed = {}

    def run(self, command: list, **options: object) -> subprocess.CompletedProcess:
        code, stdout = 0, b""
        if command[0] in self.missing:
            raise FileNotFoundError(command[0])

        if command[:2] == ["defaults", "export"]:
            self.exports.append(command[2])
            stdout = plistlib.dumps(self.domains.get(command[2], {}))
        elif command[:2] == ["launchctl", "print-disabled"]:
            lines = [f'\t\t"{label}" => {state}' for label, state in self.overrides.items()]
            stdout = "\n".join(["\tdisabled services = {", *lines, "\t}"]).encode()
        elif command[:2] == ["launchctl", "print"]:
            code = 0 if command[2] in self.loaded else 113
        else:
            if command[:2] == ["sudo", "install"]:
                self.installed[command[-1]] = plistlib.loads(Path(command[-2]).read_bytes())

            self.commands.append(command)
            code = 113 if "bootout" in command else 0
            for prefix, times in self.fails.items():
                if times and tuple(command[: len(prefix)]) == prefix:
                    self.fails[prefix] -= 1
                    code = 5

        if code and options.get("check"):
            raise subprocess.CalledProcessError(code, command)

        return subprocess.CompletedProcess(command, code, stdout, b"")

    def patch(self) -> AbstractContextManager:
        return mock.patch.object(engine.subprocess, "run", self.run)

    def plan(self, *modules: Module) -> list:
        with self.patch():
            return make_plan(list(modules), NOTHING, {})

    def apply(self, *modules: Module) -> str:
        out = io.StringIO()
        with self.patch(), mock.patch.object(engine.time, "sleep"), redirect_stdout(out):
            try:
                apply(self.plan(*modules), None, {})
            finally:
                self.output = out.getvalue()

        return self.output

    def main(self, answer: str, *modules: Module) -> str:
        out = io.StringIO()
        with (
            self.patch(),
            tempfile.TemporaryDirectory() as repo,
            mock.patch.object(engine, "REPO", Path(repo)),
            mock.patch.object(engine, "read_profile", lambda profiles: profiles[0]),
            mock.patch("sys.argv", ["config.py", "apply"]),
            mock.patch("builtins.input", return_value=answer) as asked,
            mock.patch.object(engine, "find_brew", return_value=None),
            mock.patch.object(engine, "installed_cargo", return_value=set()),
            redirect_stdout(out),
        ):
            run(Profile("p", list(modules)))

        self.asked = asked.called
        return out.getvalue()


class SameTest(unittest.TestCase):
    def test_types_matter(self) -> None:
        self.assertTrue(same(True, True))
        self.assertFalse(same(1, True))
        self.assertFalse(same(2, 2.0))
        self.assertFalse(same(None, False))

    def test_numbers_compare_by_value(self) -> None:
        for current, wanted in [(0, False), (1, True), (True, 1), (25.0, 25), (1.0, True)]:
            self.assertTrue(same(current, wanted, numbers=True), (current, wanted))

        for current, wanted in [(2, True), (0, True), (25.5, 25), ("1", 1), (1, "1"), (None, 0)]:
            self.assertFalse(same(current, wanted, numbers=True), (current, wanted))

        self.assertTrue(same(0.05000000074505806, 0.05, numbers=True))
        self.assertFalse(same(0.06, 0.05, numbers=True))

    def test_float32_precision(self) -> None:
        self.assertTrue(same(0.05000000074505806, 0.05))
        self.assertTrue(same(1.5, 1.5))
        self.assertFalse(same(0.06, 0.05))

    def test_nested_dicts_ignore_order(self) -> None:
        wanted = {"enabled": True, "value": {"type": "standard", "parameters": [1, 2]}}
        current = {"value": {"parameters": [1, 2], "type": "standard"}, "enabled": True}
        floats = {**current, "enabled": 1, "value": {"type": "standard", "parameters": [1.0, 2]}}

        self.assertTrue(same(current, wanted))
        self.assertFalse(same({**current, "enabled": 1}, wanted))
        self.assertTrue(same(floats, wanted, numbers=True))
        self.assertFalse(same({**floats, "enabled": False}, wanted, numbers=True))
        self.assertFalse(same({**floats, "value": {"parameters": [1, 3]}}, wanted, numbers=True))
        self.assertFalse(same({**current, "extra": 1}, wanted))

    def test_value_types(self) -> None:
        self.assertEqual(typed(False), ["-bool", "false"])
        self.assertEqual(typed(5), ["-int", "5"])
        self.assertEqual(typed(2.0), ["-float", "2.0"])
        self.assertEqual(typed("Nlsv"), ["-string", "Nlsv"])


class DefaultsTest(Clean):
    def test_plan_lists_only_differing_settings(self) -> None:
        mac = Mac(
            {
                "com.apple.dock": {"tilesize": 56},
                "NSGlobalDomain": {
                    "KeyRepeat": 5.0,
                    "com.apple.keyboard.fnState": 0,
                    "QLPanelAnimationDuration": 0.05000000074505806,
                },
                "com.apple.symbolichotkeys": {"AppleSymbolicHotKeys": {"61": {"enabled": False}}},
            }
        )
        module = Module("m", defaults=[DOCK, SPEED, FN, QUICK, HOTKEY])

        (step,) = mac.plan(module)

        self.assertEqual(step.defaults, [(FN, 0), (HOTKEY, {"enabled": False})])
        self.assertEqual(
            sorted(mac.exports),
            ["NSGlobalDomain", "com.apple.dock", "com.apple.symbolichotkeys"],
        )
        self.assertEqual(
            step_actions(step),
            [
                "  ~ -g com.apple.keyboard.fnState: 0 → True",
                "  ~ hotkey 61: disabled → 65535, 80, 0",
            ],
        )
        self.assertEqual(summary([step]), "Plan: 2 defaults to write.")

    def test_global_domain_is_read_once(self) -> None:
        mac = Mac({"NSGlobalDomain": {"KeyRepeat": 5}})
        alias = Default("NSGlobalDomain", "InitialKeyRepeat", 25)

        (step,) = mac.plan(Module("m", defaults=[SPEED, alias]))

        self.assertEqual(mac.exports, ["NSGlobalDomain"])
        self.assertEqual(step.defaults, [(alias, None)])
        self.assertEqual(step_actions(step), ["  ~ NSGlobalDomain InitialKeyRepeat: unset → 25"])

    def test_plan_shows_current_values(self) -> None:
        moved = {"enabled": True, "value": {"parameters": [32, 49, 262144], "type": "standard"}}
        mac = Mac(
            {
                "com.apple.dock": {"tilesize": 48},
                "com.apple.symbolichotkeys": {"AppleSymbolicHotKeys": {"61": moved}},
            }
        )
        off = Hotkey(60, [32, 49, 0], enabled=False)

        (step,) = mac.plan(Module("m", defaults=[DOCK, HOTKEY, off]))

        self.assertEqual(
            step_actions(step),
            [
                "  ~ com.apple.dock tilesize: 48 → 56",
                "  ~ hotkey 61: 32, 49, 262144 → 65535, 80, 0",
                "  ~ hotkey 60: unset → disabled 32, 49, 0",
            ],
        )

    def test_hotkey_entries_are_compared_one_by_one(self) -> None:
        other = {"60": {"enabled": True}}
        hotkeys = {**other, "61": HOTKEY_ENTRY}
        mac = Mac({"com.apple.symbolichotkeys": {"AppleSymbolicHotKeys": hotkeys}})

        (step,) = mac.plan(Module("m", defaults=[HOTKEY]))

        self.assertEqual(step.defaults, [])
        self.assertFalse(step.changes)

        disabled = Hotkey(61, [65535, 80, 0], enabled=False)
        (step,) = mac.plan(Module("n", defaults=[disabled]))
        self.assertEqual(step.defaults, [(disabled, HOTKEY_ENTRY)])
        self.assertEqual(
            step_actions(step), ["  ~ hotkey 61: 65535, 80, 0 → disabled 65535, 80, 0"]
        )

    def test_nothing_to_write(self) -> None:
        mac = Mac({"com.apple.dock": {"tilesize": 56}, "NSGlobalDomain": {"KeyRepeat": 5}})

        output = mac.main("yes", Module("m", defaults=[DOCK, SPEED]))

        self.assertFalse(mac.asked)
        self.assertEqual(mac.commands, [])
        self.assertIn("No changes.", output)

    def test_declined(self) -> None:
        mac = Mac()

        mac.main("no", Module("m", defaults=[DOCK]))

        self.assertTrue(mac.asked)
        self.assertEqual(mac.commands, [])

    def test_writes_restarts_activates_and_asks_to_log_out(self) -> None:
        mac = Mac({"com.apple.dock": {"tilesize": 48}})
        module = Module("m", defaults=[DOCK, SPEED, FN, CLOCK, HOTKEY])

        output = mac.main("yes", module)

        hotkey_write = mac.commands[4]
        self.assertEqual(
            mac.commands[:4] + [hotkey_write[:6]] + mac.commands[5:],
            [
                ["defaults", "write", "com.apple.dock", "tilesize", "-int", "56"],
                ["defaults", "write", "-g", "KeyRepeat", "-int", "5"],
                ["defaults", "write", "-g", "com.apple.keyboard.fnState", "-bool", "true"],
                ["defaults", "write", "com.apple.menuextra.clock", "ShowSeconds", "-bool", "true"],
                [
                    "defaults",
                    "write",
                    "com.apple.symbolichotkeys",
                    "AppleSymbolicHotKeys",
                    "-dict-add",
                    "61",
                ],
                ["killall", "ControlCenter"],
                ["killall", "Dock"],
                [ACTIVATE_SETTINGS, "-u"],
            ],
        )
        self.assertEqual(plistlib.loads(hotkey_write[6].encode()), HOTKEY_ENTRY)
        self.assertIn("~ com.apple.dock tilesize = 56", output)
        self.assertLess(
            output.index("log out to apply: -g KeyRepeat\n"), output.index("activateSettings")
        )

    def test_hotkey_alone_activates(self) -> None:
        mac = Mac()

        mac.main("yes", Module("m", defaults=[HOTKEY]))

        self.assertEqual(mac.commands[-1], [ACTIVATE_SETTINGS, "-u"])

    def test_no_restart_or_activate_when_not_needed(self) -> None:
        mac = Mac()

        output = mac.main("yes", Module("m", defaults=[SPEED]))

        self.assertEqual(mac.commands, [["defaults", "write", "-g", "KeyRepeat", "-int", "5"]])
        self.assertIn("log out to apply", output)

    def test_bad_settings(self) -> None:
        with self.assertRaisesRegex(ConfigError, "m: .* is not a Default or Hotkey"):
            Mac().plan(Module("m", defaults=[("-g", "KeyRepeat", 5)]))

        with self.assertRaisesRegex(ConfigError, "m: .* needs a string domain and key"):
            Mac().plan(Module("m", defaults=[Default("-g", 1, 5)]))

        for value, kind in ((None, "NoneType"), ([1], "list"), ({"61": 1}, "dict")):
            with self.assertRaisesRegex(ConfigError, f"m: -g Bad has a value of type {kind}"):
                Mac().plan(Module("m", defaults=[Default("-g", "Bad", value)]))

        for hotkey in (Hotkey("61", [1]), Hotkey(61, (1, 2)), Hotkey(61, [1.0]), Hotkey(61, [], 1)):
            with self.assertRaisesRegex(ConfigError, "needs an int id, int params and a bool"):
                Mac().plan(Module("m", defaults=[hotkey]))

    def test_duplicate_settings(self) -> None:
        base = Module("base", defaults=[SPEED])
        again = Default("NSGlobalDomain", "KeyRepeat", 2)

        with self.assertRaisesRegex(
            ConfigError, "NSGlobalDomain KeyRepeat is set twice, in base and m"
        ):
            Mac().plan(base, Module("m", defaults=[again]))

        with self.assertRaisesRegex(ConfigError, "hotkey 61 is set twice, in m and m"):
            Mac().plan(Module("m", defaults=[HOTKEY, Hotkey(61, [65535, 79, 0])]))

        (step,) = Mac().plan(Module("n", defaults=[HOTKEY, Hotkey(60, [32, 49, 0])]))
        self.assertEqual(len(step.defaults), 2)

    def test_bad_config_stops_before_asking(self) -> None:
        mac = Mac()

        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            mac.main("yes", Module("a", defaults=[DOCK]), Module("b", defaults=[DOCK]))

        self.assertFalse(mac.asked)
        self.assertEqual(mac.commands, [])

    def test_failed_write_still_restarts_and_activates(self) -> None:
        mac = Mac(fails={("defaults", "write", "-g", "KeyRepeat"): 1})

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            mac.apply(Module("m", defaults=[FN, DOCK, SPEED, QUICK]))

        self.assertEqual(raised.exception.cmd[:4], ["defaults", "write", "-g", "KeyRepeat"])
        self.assertEqual(
            [command[:4] for command in mac.commands],
            [
                ["defaults", "write", "-g", "com.apple.keyboard.fnState"],
                ["defaults", "write", "com.apple.dock", "tilesize"],
                ["defaults", "write", "-g", "KeyRepeat"],
                ["killall", "Dock"],
                [ACTIVATE_SETTINGS, "-u"],
            ],
        )
        self.assertNotIn("log out to apply", mac.output)

    def test_failed_activate_does_not_hide_the_write_error(self) -> None:
        fails = {("defaults", "write", "-g", "KeyRepeat"): 1, (ACTIVATE_SETTINGS,): 1}
        mac = Mac(fails=fails)

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            mac.apply(Module("m", defaults=[FN, SPEED]))

        self.assertEqual(raised.exception.cmd[:4], ["defaults", "write", "-g", "KeyRepeat"])

        mac = Mac(fails={("defaults", "write", "-g", "KeyRepeat"): 1}, missing=(ACTIVATE_SETTINGS,))
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            mac.apply(Module("m", defaults=[DOCK, FN, SPEED]))

        self.assertEqual(raised.exception.cmd[:4], ["defaults", "write", "-g", "KeyRepeat"])
        self.assertEqual(mac.commands[-1], ["killall", "Dock"])

    def test_failed_activate_fails_the_apply(self) -> None:
        mac = Mac(fails={(ACTIVATE_SETTINGS,): 1})

        with self.assertRaises(subprocess.CalledProcessError) as raised:
            mac.apply(Module("m", defaults=[SPEED, FN]))

        self.assertEqual(raised.exception.cmd, [ACTIVATE_SETTINGS, "-u"])
        self.assertIn("log out to apply: -g KeyRepeat", mac.output)


class LaunchdTest(TempHome):
    def setUp(self) -> None:
        super().setUp()
        self.daemons = self.home / "LaunchDaemons"
        patch = mock.patch.object(engine, "LAUNCH_DAEMONS", self.daemons)
        patch.start()
        self.addCleanup(patch.stop)
        self.uid = os.getuid()

    def test_plists(self) -> None:
        self.assertEqual(
            REMAP.plist,
            {
                "Label": "test.remap",
                "ProgramArguments": ["/bin/true", '{"a":[1,2]}'],
                "RunAtLoad": True,
            },
        )
        self.assertEqual(
            SNAP.plist,
            {
                "Label": "test.snap",
                "ProgramArguments": ["/usr/bin/tmutil", "localsnapshot"],
                "RunAtLoad": True,
                "StartCalendarInterval": {"Minute": 0},
            },
        )
        self.assertFalse(LaunchAgent("x", ["/bin/true"], run_at_load=False).plist["RunAtLoad"])
        self.assertEqual(REMAP.path, self.home / "Library/LaunchAgents/test.remap.plist")
        self.assertEqual(SNAP.path, self.daemons / "test.snap.plist")
        self.assertEqual((REMAP.domain, SNAP.domain), (f"gui/{self.uid}", "system"))

    def test_status(self) -> None:
        path = self.home / "Library/LaunchAgents/test.remap.plist"
        loaded = Mac(loaded=(f"gui/{self.uid}/test.remap",))
        with loaded.patch():
            self.assertEqual(job_status(REMAP), "missing")

            path.parent.mkdir(parents=True)
            path.write_bytes(plistlib.dumps(REMAP.plist))
            self.assertEqual(job_status(REMAP), "ok")

            path.write_bytes(plistlib.dumps({**REMAP.plist, "RunAtLoad": 1}))
            self.assertEqual(job_status(REMAP), "differs")

            path.write_text("garbage")
            self.assertEqual(job_status(REMAP), "differs")

        path.write_bytes(plistlib.dumps(REMAP.plist))
        with Mac().patch():
            self.assertEqual(job_status(REMAP), "differs")

    def test_plan(self) -> None:
        path = self.home / "Library/LaunchAgents/test.remap.plist"
        path.parent.mkdir(parents=True)
        path.write_bytes(plistlib.dumps({**REMAP.plist, "RunAtLoad": False}))

        (step,) = Mac().plan(Module("m", launchd=[REMAP, SNAP]))

        self.assertEqual(
            [(job.label, status) for job, status in step.jobs],
            [("test.remap", "differs"), ("test.snap", "missing")],
        )
        self.assertEqual(step_actions(step), ["  ~ launchd test.remap", "  + launchd test.snap"])
        self.assertEqual(summary([step]), "Plan: 2 launchd to load.")

    def test_user_job(self) -> None:
        mac = Mac()

        mac.main("yes", Module("m", launchd=[REMAP]))

        path = self.home / "Library/LaunchAgents/test.remap.plist"
        self.assertEqual(plistlib.loads(path.read_bytes()), REMAP.plist)
        self.assertEqual(path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(
            mac.commands,
            [
                ["launchctl", "bootout", f"gui/{self.uid}/test.remap"],
                ["launchctl", "bootstrap", f"gui/{self.uid}", str(path)],
            ],
        )

    def test_bootstrap_is_retried_once(self) -> None:
        mac = Mac(fails={("launchctl", "bootstrap"): 1})

        mac.apply(Module("m", launchd=[REMAP]))

        bootstrap = ["launchctl", "bootstrap", f"gui/{self.uid}", str(REMAP.path)]
        self.assertEqual(mac.commands[1:], [bootstrap, bootstrap])

        mac = Mac(fails={("launchctl", "bootstrap"): 2})
        with self.assertRaises(subprocess.CalledProcessError):
            mac.apply(Module("m", launchd=[REMAP]))

        self.assertEqual(len(mac.commands), 3)

    def test_log_out_note_comes_before_launchd(self) -> None:
        mac = Mac(fails={("launchctl", "bootstrap"): 2})

        with self.assertRaises(subprocess.CalledProcessError):
            mac.apply(Module("m", defaults=[SPEED], launchd=[REMAP]))

        note = mac.output.index("log out to apply: -g KeyRepeat")
        self.assertLess(note, mac.output.index("launchd test.remap"))

    def test_bad_jobs(self) -> None:
        with self.assertRaisesRegex(ConfigError, "m: .* is not a LaunchAgent, LaunchDaemon or"):
            Mac().plan(Module("m", launchd=[{"Label": "x"}]))

        for job in (
            LaunchAgent(1, ["/bin/true"]),
            LaunchAgent("x", "/bin/true"),
            LaunchAgent("x", []),
        ):
            with self.assertRaisesRegex(ConfigError, "needs a string label and a program list"):
                Mac().plan(Module("m", launchd=[job]))

        with self.assertRaisesRegex(ConfigError, "m: launchd x has an unwritable value"):
            Mac().plan(Module("m", launchd=[LaunchAgent("x", ["/bin/true", {1, 2}])]))

        copy = LaunchDaemon("test.remap", ["/bin/false"])
        with self.assertRaisesRegex(ConfigError, "launchd test.remap is defined twice, in a and b"):
            Mac().plan(Module("a", launchd=[REMAP]), Module("b", launchd=[copy]))

        with self.assertRaisesRegex(ConfigError, "m: .* needs a string label$"):
            Mac().plan(Module("m", launchd=[AppleAgent(1)]))

        with self.assertRaisesRegex(ConfigError, "launchd test.remap is defined twice, in a and b"):
            Mac().plan(
                Module("a", launchd=[REMAP]), Module("b", launchd=[AppleAgent("test.remap")])
            )

    def test_system_job_goes_through_sudo(self) -> None:
        mac = Mac()

        mac.main("yes", Module("m", launchd=[SNAP]))

        path = str(self.daemons / "test.snap.plist")
        install, *rest = mac.commands
        self.assertEqual(
            install[:8], ["sudo", "install", "-o", "root", "-g", "wheel", "-m", "0644"]
        )
        self.assertEqual(install[-1], path)
        self.assertEqual(mac.installed, {path: SNAP.plist})
        self.assertEqual(
            rest,
            [
                ["sudo", "launchctl", "bootout", "system/test.snap"],
                ["sudo", "launchctl", "bootstrap", "system", path],
            ],
        )
        self.assertFalse(self.daemons.exists())


class AppleAgentTest(Clean):
    def setUp(self) -> None:
        super().setUp()
        self.service = f"gui/{os.getuid()}/com.apple.rcd"

    def test_ok(self) -> None:
        self.assertEqual(RCD.path, Path("/System/Library/LaunchAgents/com.apple.rcd.plist"))
        mac = Mac(loaded=(self.service,), overrides={"com.apple.rcd": "enabled", "x": "disabled"})

        (step,) = mac.plan(Module("m", launchd=[RCD]))

        self.assertEqual(step.jobs, [])
        self.assertEqual(mac.commands, [])

    def test_disabled_override(self) -> None:
        mac = Mac(loaded=(self.service,), overrides={"com.apple.rcd": "disabled"})

        (step,) = mac.plan(Module("m", launchd=[RCD]))

        self.assertEqual(step.jobs, [(RCD, "disabled")])
        self.assertEqual(step_actions(step), ["  ~ launchd com.apple.rcd"])
        self.assertEqual(summary([step]), "Plan: 1 launchd to load.")

    def test_not_loaded(self) -> None:
        (step,) = Mac().plan(Module("m", launchd=[RCD]))

        self.assertEqual(step.jobs, [(RCD, "unloaded")])
        self.assertEqual(step_actions(step), ["  ~ launchd com.apple.rcd"])

    def test_apply(self) -> None:
        uid = os.getuid()
        enable = ["launchctl", "enable", self.service]
        mac = Mac()

        mac.apply(Module("m", launchd=[RCD]))

        bootstrap = ["launchctl", "bootstrap", f"gui/{uid}", str(RCD.path)]
        self.assertEqual(mac.commands, [enable, bootstrap])

        mac = Mac(loaded=(self.service,), overrides={"com.apple.rcd": "disabled"})
        mac.apply(Module("m", launchd=[RCD]))
        self.assertEqual(mac.commands, [enable])


if __name__ == "__main__":
    unittest.main()
