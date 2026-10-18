#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Switch the one Claude Code profile (~/.claude) between subscription accounts.

Usage (prefix with `uv run --script account-switch.py`):
  add NAME    save the account logged in now as NAME (log in with /login first, never /logout)
  add NAME --from DIR
              move the login of the profile in DIR (a CLAUDE_CONFIG_DIR) here as NAME; that
              profile is logged out without revoking, so close its sessions first
  use NAME    make NAME the login of every Claude session of the profile
  status      show the saved accounts, the live one and when a full one frees up
  measure     read session.measure rate limits as JSON on stdin and switch when needed

Accounts are used in PRIORITY order: the first one until its 5-hour or weekly window reaches
THRESHOLD percent, then the next one with room, and back once the first one's window resets.
Running sessions pick a switch up within about 30 s, when Claude Code's Keychain cache expires.
Only the default profile is handled: with CLAUDE_CONFIG_DIR or CLAUDE_SECURESTORAGE_CONFIG_DIR
set it refuses.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import datetime
from pathlib import Path

PRIORITY = ("sw", "personal")
THRESHOLD = 97  # percent of a window that counts as full
SETTLE = 60  # seconds after a switch when sessions may still report the previous account
LOCK_WAIT = 20  # seconds to wait for all of Claude Code's locks together

CLAUDE_DIR = Path.home() / ".claude"
CONFIG = Path.home() / ".claude.json"
STATE = CLAUDE_DIR / "account-switch.json"  # no secrets: when each full account frees up
LIVE = "Claude Code-credentials"  # the Keychain item Claude Code reads its login from
SAVED = "Claude Code-account-switch"  # one item per saved account, keyed by its name
WINDOWS = ("five_hour", "seven_day")
# The fields of the live item that belong to one login: the ones Claude Code's logout clears.
# The rest (MCP servers' OAuth and the like) stays with the profile.
LOGIN_FIELDS = (
    "claudeAiOauth",
    "organizationUuid",
    "trustedDeviceToken",
    "enterpriseGateway",
    "designOauth",
)


# MARK: Keychain


def keychain_user() -> str:
    # The Keychain account name Claude Code uses.
    user = os.environ.get("USER") or os.getlogin()
    return user if re.fullmatch(r"[a-zA-Z0-9._-]+", user) else "claude-code-user"


def keychain_read(service: str, account: str) -> dict | None:
    rs = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-w", "-s", service],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if rs.returncode == 44:
        return None

    if rs.returncode:
        raise SystemExit(f"Keychain read of {service!r} failed (security exit {rs.returncode})")

    return json.loads(rs.stdout.strip())


def keychain_write(service: str, account: str, data: dict) -> None:
    # The way Claude Code writes its own item, so the item's access list stays the same.
    hexed = json.dumps(data, separators=(",", ":")).encode().hex()
    line = f'add-generic-password -U -a "{account}" -s "{service}" -X "{hexed}"\n'
    if len(line) <= 4032:
        args, stdin = ["security", "-i"], line
    else:
        args = ["security", "add-generic-password", "-U", "-a", account, "-s", service]
        args, stdin = [*args, "-X", hexed], None

    rs = subprocess.run(args, input=stdin, capture_output=True, text=True, check=False, timeout=10)
    if rs.returncode or keychain_read(service, account) != data:
        raise SystemExit(f"Keychain write of {service!r} failed (security exit {rs.returncode})")


def keychain_delete(service: str, account: str) -> None:
    rs = subprocess.run(
        ["security", "delete-generic-password", "-a", account, "-s", service],
        capture_output=True,
        check=False,
        timeout=10,
    )
    if rs.returncode not in (0, 44):
        raise SystemExit(f"Keychain delete of {service!r} failed (security exit {rs.returncode})")


def profile_item(directory: Path) -> str:
    # The Keychain item Claude Code keeps the login of a CLAUDE_CONFIG_DIR profile in.
    path = unicodedata.normalize("NFC", str(directory))
    return f"{LIVE}-{hashlib.sha256(path.encode()).hexdigest()[:8]}"


# MARK: Locks and files


@contextmanager
def dir_lock(path: Path, deadline: float):
    """A proper-lockfile lock as Claude Code takes it: a directory, stale when its mtime is old."""
    while True:
        try:
            path.mkdir()
            break
        except FileExistsError:
            try:
                # 15 s is the shortest stale time Claude Code gives its locks (.storage-write).
                if time.time() - path.stat().st_mtime > 15:
                    path.rmdir()
                    continue
            except FileNotFoundError:
                continue

            if time.monotonic() > deadline:
                raise SystemExit(f"{path} is held by another process; try again") from None

            time.sleep(0.1)

    try:
        yield
    finally:
        # Held well under any stale time, so the lock is still ours; gone is fine too.
        if path.is_dir():
            path.rmdir()


@contextmanager
def login_locks(directory: Path | None = None, config: Path | None = None):
    # Claude Code's locks of a profile (the default one unless given): the OAuth refresh locks,
    # the config file lock and last the credential write lock (every read-modify-write of the
    # live item), held the shortest as Claude retries it only briefly. While they are held no
    # session refreshes a token or rewrites the login underneath the switch.
    directory, config = directory or CLAUDE_DIR, config or CONFIG
    deadline = time.monotonic() + LOCK_WAIT
    with ExitStack() as stack:
        for path in (
            directory / ".oauth_refresh.lock",
            Path(f"{directory.resolve()}.lock"),
            Path(f"{config.resolve()}.lock"),
            directory / ".storage-write.lock",
        ):
            stack.enter_context(dir_lock(path, deadline))

        yield


@contextmanager
def state_lock(wait: bool = True):
    """The script's own state, one process at a time; None without `wait` when it is busy."""
    with STATE.with_suffix(".lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield None
            return

        state = json.loads(STATE.read_text()) if STATE.exists() else {}
        yield state

        STATE.write_text(json.dumps(state, indent=2) + "\n")


def config_account() -> dict | None:
    return json.loads(CONFIG.read_text()).get("oauthAccount")


def set_config_account(account: dict) -> None:
    path = CONFIG.resolve()
    config = json.loads(path.read_text())
    config["oauthAccount"] = account
    tmp = path.with_name(f".{path.name}.account-switch")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    os.chmod(tmp, path.stat().st_mode)
    os.replace(tmp, path)


# MARK: Accounts


def same_account(a: dict | None, b: dict | None) -> bool:
    if not a or not b or not a.get("accountUuid"):
        return False

    keys = ("accountUuid", "organizationUuid")
    return [a.get(key) for key in keys] == [b.get(key) for key in keys]


def refresh_token(login: dict) -> str | None:
    return (login.get("claudeAiOauth") or {}).get("refreshToken")


def saved_accounts() -> dict[str, dict]:
    accounts = {name: keychain_read(SAVED, name) for name in PRIORITY}
    return {name: data for name, data in accounts.items() if data}


def owner(saved: dict[str, dict], account: dict | None) -> str | None:
    return next(
        (n for n, data in saved.items() if same_account(data["oauthAccount"], account)), None
    )


def switch(name: str) -> bool:
    """Make `name` the live login; False when it already is."""
    with login_locks():
        user = keychain_user()
        item = keychain_read(LIVE, user) or {}
        live = config_account()
        saved = saved_accounts()
        if name not in saved:
            raise SystemExit(f"{name} is not saved; log in as it and run `add {name}`")

        current = owner(saved, live)
        if current == name:
            return False

        token = refresh_token(item)
        if current is None or not token:
            raise SystemExit("The live login is no saved account; save it with `add` first")

        # ~/.claude.json and the Keychain item must name the same account before its tokens
        # are kept: a token another saved account still holds means they disagree.
        if any(refresh_token(data["login"]) == token for n, data in saved.items() if n != current):
            raise SystemExit("The live tokens are not the live account's; run /login and `add`")

        # The live item holds the latest refresh token of the current account: keep it.
        login = {key: item[key] for key in LOGIN_FIELDS if key in item}
        keychain_write(SAVED, current, {"login": login, "oauthAccount": live})
        shared = {key: value for key, value in item.items() if key not in LOGIN_FIELDS}
        try:
            keychain_write(LIVE, user, shared | saved[name]["login"])
            set_config_account(saved[name]["oauthAccount"])
        except BaseException:
            keychain_write(LIVE, user, item)
            set_config_account(live)
            raise

    return True


def pick(current: str, limits: list[dict], saved: list[str], full: dict, now: float) -> str:
    """The account to use after `current` reported `limits`; updates `full` (name: free at)."""
    resets = [
        datetime.fromisoformat(limit["resetsAt"]).timestamp()
        if limit.get("resetsAt")
        else now + 5 * 3600
        for limit in limits
        if limit["kind"] in WINDOWS and limit["percentUsed"] >= THRESHOLD
    ]
    if resets:
        full[current] = max(resets)
    else:
        full.pop(current, None)

    free = [name for name in PRIORITY if name in saved and full.get(name, 0) <= now]
    return free[0] if free else current


# MARK: Commands


def cmd_add(args: argparse.Namespace) -> None:
    user = keychain_user()
    source = Path(os.path.abspath(os.path.expanduser(args.source))) if args.source else None
    service = profile_item(source) if source else LIVE
    config = source / ".claude.json" if source else CONFIG
    with login_locks(source, config) if source else nullcontext():
        item = keychain_read(service, user)
        account = json.loads(config.read_text()).get("oauthAccount") if config.exists() else None
        if not item or not refresh_token(item) or not account:
            raise SystemExit(f"No Claude login in {source or '~/.claude'}; run /login there first")

        for name, data in saved_accounts().items():
            if name != args.name and same_account(data["oauthAccount"], account):
                raise SystemExit(f"This login is already saved as {name}")

        login = {key: item[key] for key in LOGIN_FIELDS if key in item}
        keychain_write(SAVED, args.name, {"login": login, "oauthAccount": account})
        if source:
            # Two profiles refreshing one refresh token kill it: the old profile gives it up.
            keychain_delete(service, user)

    moved = f", {source} is logged out" if source else ""
    print(f"Saved {account.get('emailAddress', 'the login')} as {args.name}{moved}")


def cmd_use(args: argparse.Namespace) -> None:
    with state_lock() as state:
        if switch(args.name):
            state["switchedAt"] = time.time()
            print(f"Switched to {args.name}; running sessions follow within about 30 s")
        else:
            print(f"Already on {args.name}")


def cmd_status(args: argparse.Namespace) -> None:
    saved = saved_accounts()
    live = owner(saved, config_account())
    full = json.loads(STATE.read_text()).get("full", {}) if STATE.exists() else {}
    for name in PRIORITY:
        if name not in saved:
            print(f"  {name}: not saved")
            continue

        email = saved[name]["oauthAccount"].get("emailAddress", "")
        until = full.get(name, 0)
        note = (
            f", full until {datetime.fromtimestamp(until):%H:%M %d.%m}"
            if until > time.time()
            else ""
        )
        print(f"{'*' if name == live else ' '} {name}: {email}{note}")


def cmd_measure(args: argparse.Namespace) -> None:
    limits = json.load(sys.stdin)
    if not limits:
        return

    # Sessions measure at once: one of them decides, the others' readings are skipped.
    with state_lock(wait=False) as state:
        now = time.time()
        if state is None or now - state.get("switchedAt", 0) < SETTLE:
            return

        saved = saved_accounts()
        current = owner(saved, config_account())
        if current is None:
            return

        target = pick(current, limits, list(saved), state.setdefault("full", {}), now)
        if target != current and switch(target):
            state["switchedAt"] = now
            print(f"Claude account: {current} → {target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Save the live login under a name.")
    add.add_argument("name", choices=PRIORITY)
    add.add_argument("--from", dest="source", help="Move the login of this profile directory.")
    commands.add_parser("use", help="Switch every session to a saved account.").add_argument(
        "name", choices=PRIORITY
    )
    commands.add_parser("status", help="Show the saved accounts and the live one.")
    commands.add_parser("measure", help="Switch on rate limits read from stdin (the mod).")
    args = parser.parse_args()

    # Either variable moves Claude Code's login to another Keychain item and config file.
    other = [
        var for var in ("CLAUDE_CONFIG_DIR", "CLAUDE_SECURESTORAGE_CONFIG_DIR") if var in os.environ
    ]
    if other and args.command == "measure":
        return

    if other:
        raise SystemExit(f"Only the default profile is switched; {other[0]} is set")

    globals()[f"cmd_{args.command}"](args)


if __name__ == "__main__":
    main()
