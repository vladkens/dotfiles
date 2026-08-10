#!/usr/bin/env python3

import argparse
import errno
import os
from pathlib import Path


def normalized_target(link: Path) -> tuple[Path, str]:
    raw_target = os.readlink(link)
    target = Path(raw_target)
    if not target.is_absolute():
        target = link.parent / target
    return Path(os.path.realpath(target)), raw_target


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def is_dangling(link: Path) -> bool:
    try:
        link.stat()
    except OSError as error:
        if error.errno in {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}:
            return True
        raise
    return False


def prune(source: Path, destination: Path, workdir: Path) -> None:
    if not destination.is_dir():
        return

    source = Path(os.path.realpath(source))
    workdir = Path(os.path.realpath(workdir))

    for link in destination.iterdir():
        if not link.is_symlink() or not is_dangling(link):
            continue
        if os.path.lexists(source / link.name):
            continue

        target, raw_target = normalized_target(link)
        if not (is_within(target, source) or is_within(target, workdir)):
            continue

        link.unlink()
        print(f"Removed stale symlink: {link} -> {raw_target}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove stale links created by dotdrop link_children."
    )
    parser.add_argument("link_type")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("workdir", type=Path)
    args = parser.parse_args()

    if args.link_type == "link_children":
        prune(args.source, args.destination, args.workdir)


if __name__ == "__main__":
    main()
