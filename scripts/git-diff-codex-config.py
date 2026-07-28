#!/usr/bin/env python3

"""Remove local and volatile values from Codex config comparisons in Git.

Git runs this script as the ``codex-config`` clean filter configured in the
Makefile and .gitattributes. It reads ``config.toml`` from stdin and writes a
stable representation to stdout, excluding:

- root-level model selection settings;
- generated marketplace metadata;
- local ``[projects."..."]`` trust sections.

The working copy is not modified. The filter tracks the current TOML section
without parsing or serializing values, so comments and formatting remain
intact.
"""

import re
import sys

MARKETPLACE_GENERATED_SETTING_RE = re.compile(r"^\s*(?:last_updated|source)\s*=")
ROOT_LOCAL_SETTING_RE = re.compile(r"^\s*(?:model|model_reasoning_effort|service_tier)\s*=")


def filter_config(lines: list[str]) -> str:
    output: list[str] = []
    section, subsection = "root", ""

    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith("[") and stripped_line.endswith("]"):
            # Split only once: any remaining dots belong to the subsection.
            section, _, subsection = stripped_line[1:-1].partition(".")

        # Project trust is local to a machine, so discard the whole section.
        if section == "projects":
            continue

        # Model selection is local, but only when defined at the document root.
        if section == "root" and ROOT_LOCAL_SETTING_RE.match(line):
            continue

        # Marketplace refreshes regenerate this local metadata.
        if section == "marketplaces" and MARKETPLACE_GENERATED_SETTING_RE.match(line):
            continue

        output.append(line)

    # Keep at most two consecutive blank lines between retained content.
    text = re.sub(r"\n{4,}", "\n\n\n", "".join(output))
    text = text.rstrip("\n")
    return f"{text}\n" if text else ""


def main() -> None:
    sys.stdout.write(filter_config(sys.stdin.readlines()))


if __name__ == "__main__":
    main()
