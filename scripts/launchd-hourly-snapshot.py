#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

import argparse
import plistlib
import subprocess
import sys
import tempfile

LABEL = "local.hourly-snapshot"
PLIST_PATH = f"/Library/LaunchDaemons/{LABEL}.plist"
JOB = {
    "Label": LABEL,
    "ProgramArguments": ["/usr/bin/tmutil", "localsnapshot"],
    "StartCalendarInterval": {"Minute": 0},
    "RunAtLoad": True,
}


def run_cmd(cmd: list[str], required: bool = True) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        if required:
            message = result.stderr.strip() or result.stdout.strip()
            print(f"ERROR: {' '.join(cmd)} failed: {message}", file=sys.stderr)
            sys.exit(result.returncode)
        return ""
    return result.stdout.strip()


def install() -> None:
    print(f"Installing {LABEL} to {PLIST_PATH}")
    run_cmd(["sudo", "launchctl", "bootout", f"system/{LABEL}"], required=False)

    with tempfile.NamedTemporaryFile() as plist:
        plistlib.dump(JOB, plist)
        plist.flush()
        run_cmd(
            [
                "sudo",
                "install",
                "-o",
                "root",
                "-g",
                "wheel",
                "-m",
                "0644",
                plist.name,
                PLIST_PATH,
            ],
        )

    run_cmd(["sudo", "launchctl", "bootstrap", "system", PLIST_PATH])
    print(f"Installed {LABEL}. Check snapshots with: tmutil listlocalsnapshots /")


def uninstall() -> None:
    print(f"Uninstalling {LABEL} from {PLIST_PATH}")
    run_cmd(["sudo", "launchctl", "bootout", f"system/{LABEL}"], required=False)
    run_cmd(["sudo", "rm", "-f", PLIST_PATH])
    print("Uninstalled. Existing local snapshots were not removed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the hourly snapshot LaunchDaemon.")
    parser.add_argument("action", nargs="?", choices=["install", "uninstall"], default="install")
    args = parser.parse_args()
    install() if args.action == "install" else uninstall()


if __name__ == "__main__":
    main()
