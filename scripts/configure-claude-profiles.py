#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

import json
from pathlib import Path


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "claude/settings.json"
    settings = json.loads(source.read_text())
    defaults = {
        "statusLine": settings["statusLine"],
        "permissions": {"defaultMode": settings["permissions"]["defaultMode"]},
        "attribution": {key: settings["attribution"][key] for key in ("commit", "pr")},
    }
    for name in (".claude-qh", ".claude-sw"):
        directory = Path.home() / name
        if not directory.is_dir():
            continue

        path = directory / "settings.json"
        original = path.read_text() if path.exists() else "{}"
        profile = json.loads(original)
        for section, values in defaults.items():
            profile.setdefault(section, {}).update(values)

        if profile == json.loads(original):
            continue

        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
        print(f"Updated Claude defaults in {path}")


if __name__ == "__main__":
    main()
