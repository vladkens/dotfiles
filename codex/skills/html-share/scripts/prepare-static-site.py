#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import argparse
import re
import shutil
from pathlib import Path

BLOCKED_NAMES = {".git", ".env", "id_rsa", "id_ed25519"}
BLOCKED_SUFFIXES = {".pem", ".key"}
TEXT_SUFFIXES = {
    ".css",
    ".htm",
    ".html",
    ".js",
    ".json",
    ".map",
    ".md",
    ".svg",
    ".txt",
    ".xml",
}
LOCAL_REFERENCE = re.compile(
    rb"file://|/Users/|/home/[^/]+/|localhost|127\.0\.0\.1",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a static HTML page or build directory for sharing."
    )
    parser.add_argument("source", type=Path, help="HTML file or static site directory")
    parser.add_argument("output", type=Path, help="new staging directory")
    return parser.parse_args()


def validate_source(source: Path, output: Path) -> None:
    if not source.exists():
        raise ValueError(f"source does not exist: {source}")
    if source.is_symlink():
        raise ValueError("source must not be a symlink")
    if output.exists():
        raise ValueError(f"output already exists; choose a new path: {output}")

    resolved_source = source.resolve()
    resolved_output = output.resolve()
    if source.is_dir() and resolved_output.is_relative_to(resolved_source):
        raise ValueError("output must not be inside the source directory")

    if source.is_file() and source.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("single-file source must be an HTML file")
    if source.is_dir() and not (source / "index.html").is_file():
        raise ValueError("source directory must contain index.html at its root")
    if not source.is_file() and not source.is_dir():
        raise ValueError("source must be a regular HTML file or directory")


def validate_tree(source: Path) -> None:
    paths = [source] if source.is_file() else source.rglob("*")
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"source contains a symlink: {path}")

        name = path.name
        if name in BLOCKED_NAMES or name.startswith(".env."):
            raise ValueError(f"source contains a repository or credential path: {path}")
        if path.is_file() and path.suffix.lower() in BLOCKED_SUFFIXES:
            raise ValueError(f"source contains a possible credential file: {path}")


def stage_source(source: Path, output: Path) -> None:
    if source.is_file():
        output.mkdir(parents=True)
        shutil.copy2(source, output / "index.html")
        return

    shutil.copytree(source, output)


def validate_staged_content(output: Path) -> None:
    for path in output.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if LOCAL_REFERENCE.search(path.read_bytes()):
            raise ValueError(f"staged site contains a local path or URL: {path}")


def format_size(byte_count: int) -> str:
    size = float(byte_count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def main() -> int:
    args = parse_args()
    source = args.source.expanduser()
    output = args.output.expanduser()

    try:
        validate_source(source, output)
        validate_tree(source)
    except (OSError, ValueError) as error:
        print(f"error: {error}")
        return 1

    try:
        stage_source(source, output)
        validate_staged_content(output)
    except (OSError, ValueError) as error:
        if output.exists():
            shutil.rmtree(output)
        print(f"error: {error}")
        return 1

    files = [path for path in output.rglob("*") if path.is_file()]
    total_size = sum(path.stat().st_size for path in files)
    print(f"prepared: {output}")
    print(f"files: {len(files)}")
    print(f"size: {format_size(total_size)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
