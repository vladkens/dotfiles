#!/usr/bin/env python3

import re
import sys


TABLE_HEADER = re.compile(r"^\s*\[\[?.+\]\]?\s*(?:#.*)?$")
PROJECT_HEADER = re.compile(r'^\s*\[projects\."(?:\\.|[^"\\])*"\]\s*(?:#.*)?$')
NOISE_KEY = re.compile(r"^\s*(?:last_updated|source)\s*=")


def filter_config(lines: list[str]) -> list[str]:
    output = []
    separator = []
    skipping_project = False

    for line in lines:
        if TABLE_HEADER.match(line):
            if PROJECT_HEADER.match(line):
                separator = []
                while output and not output[-1].strip():
                    separator.insert(0, output.pop())
                skipping_project = True
                continue

            if skipping_project:
                output.extend(separator)
                separator = []
                skipping_project = False

        if skipping_project or NOISE_KEY.match(line):
            continue

        output.append(line)

    return output


def main() -> None:
    lines = sys.stdin.readlines()
    sys.stdout.writelines(filter_config(lines))


if __name__ == "__main__":
    main()
