#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
#
# References:
# https://gist.github.com/paultheman/808be117d447c490a29d6405975d41bd
# https://developer.apple.com/library/archive/technotes/tn2450/_index.html

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.local.KeyRemapping"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
KEY_MAPPING = {
    "UserKeyMapping": [
        {
            "HIDKeyboardModifierMappingSrc": 0x700000039,  # Caps Lock
            "HIDKeyboardModifierMappingDst": 0x70000006E,  # F19
        }
    ]
}
HIDUTIL_COMMAND = [
    "/usr/bin/hidutil",
    "property",
    "--set",
    json.dumps(KEY_MAPPING, separators=(",", ":")),
]
CLEAR_MAPPING_COMMAND = [
    "/usr/bin/hidutil",
    "property",
    "--set",
    '{"UserKeyMapping":[]}',
]
JOB = {"Label": LABEL, "ProgramArguments": HIDUTIL_COMMAND, "RunAtLoad": True}


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
    domain = f"gui/{os.getuid()}"
    print(f"Installing {LABEL} to {PLIST_PATH}")
    run_cmd(
        ["launchctl", "bootout", f"{domain}/{LABEL}"],
        required=False,
    )

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as plist:
        plistlib.dump(JOB, plist)
    PLIST_PATH.chmod(0o644)

    run_cmd(["launchctl", "bootstrap", domain, str(PLIST_PATH)])
    run_cmd(HIDUTIL_COMMAND)

    active_mapping = run_cmd(["/usr/bin/hidutil", "property", "--get", "UserKeyMapping"])
    mapping = KEY_MAPPING["UserKeyMapping"][0]
    expected_values = {str(value) for value in mapping.values()}
    if not all(value in active_mapping for value in expected_values):
        raise RuntimeError(f"key mapping was not applied:\n{active_mapping.strip()}")

    print(f"Installed and verified {LABEL}: Caps Lock -> F19")


def uninstall() -> None:
    domain = f"gui/{os.getuid()}"
    print(f"Uninstalling {LABEL} from {PLIST_PATH}")
    run_cmd(["launchctl", "bootout", f"{domain}/{LABEL}"], required=False)
    PLIST_PATH.unlink(missing_ok=True)
    run_cmd(CLEAR_MAPPING_COMMAND)
    print("Uninstalled and cleared the active key mapping.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the key-remapping LaunchAgent.")
    parser.add_argument("action", nargs="?", choices=["install", "uninstall"], default="install")
    args = parser.parse_args()
    install() if args.action == "install" else uninstall()


if __name__ == "__main__":
    main()
