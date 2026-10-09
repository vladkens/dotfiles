#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Remove dangling repository links that are no longer in Dotter's cache."""

import os
import tomllib
from pathlib import Path


def deployment_roots(repo: Path, home: Path) -> list[Path]:
    config = tomllib.loads((repo / ".dotter/global.toml").read_text())
    roots = set()
    for package in config.values():
        if not isinstance(package, dict):
            continue

        for source, value in package.get("files", {}).items():
            target = value if isinstance(value, str) else value["target"]
            target = Path(os.path.expandvars(target)).expanduser().absolute()
            roots.add(target if (repo / source).is_dir() else target.parent)

    return sorted(
        root
        for root in roots
        if not any(
            parent != home and root != parent and root.is_relative_to(parent) for parent in roots
        )
    )


def broken_links(repo: Path, home: Path) -> list[Path]:
    repo = repo.resolve()
    links = []
    for root in deployment_roots(repo, home):
        if root.is_symlink():
            paths = [root]
        elif root == home:
            paths = list(root.iterdir())
        else:
            paths = []
            for directory, directories, filenames in root.walk():
                directories[:] = [name for name in directories if name != ".git"]
                paths.extend(directory / name for name in filenames)

        for path in paths:
            if not path.is_symlink():
                continue

            target = path.readlink()
            if not target.is_absolute():
                target = path.parent / target
            target = target.resolve()
            if not target.is_relative_to(repo):
                continue

            try:
                path.stat()
            except FileNotFoundError:
                links.append(path)

    return sorted(set(links))


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    for path in broken_links(repo, Path.home()):
        path.unlink()
        print(f"removed stale link: {path}")


if __name__ == "__main__":
    main()
