#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["markdown-it-py==4.2.0"]
# ///

import argparse
import html
import re
import shutil
from pathlib import Path

from markdown_it import MarkdownIt

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
    ".markdown",
    ".svg",
    ".txt",
    ".xml",
}
LOCAL_REFERENCE = re.compile(
    rb"file://|/Users/|/home/[^/]+/|localhost|127\.0\.0\.1",
    re.IGNORECASE,
)
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PAGE_STYLE = """
body { margin: 0; color: #24292f; background: #fff; font: 17px/1.65 system-ui, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 32px 24px; overflow-wrap: anywhere; }
h1, h2, h3, h4 { line-height: 1.25; margin-top: 1.5em; }
a { color: #0969da; }
img { max-width: 100%; height: auto; }
pre, code { font-family: ui-monospace, monospace; font-size: 0.9em; background: #f6f8fa; }
code { padding: 0.15em 0.3em; border-radius: 4px; }
pre { padding: 16px; overflow-x: auto; border-radius: 6px; }
pre code { padding: 0; }
blockquote { margin-left: 0; padding-left: 16px; border-left: 4px solid #d0d7de; color: #57606a; }
table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
th, td { padding: 8px 12px; border: 1px solid #d0d7de; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 24px 0; }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare an HTML page, Markdown document, or static site for sharing."
    )
    parser.add_argument("source", type=Path, help="HTML or Markdown file, or static site directory")
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

    if source.is_file() and source.suffix.lower() not in {".html", ".htm"} | MARKDOWN_SUFFIXES:
        raise ValueError("single-file source must be an HTML or Markdown file")
    if source.is_dir() and not (source / "index.html").is_file():
        raise ValueError("source directory must contain index.html at its root")
    if not source.is_file() and not source.is_dir():
        raise ValueError("source must be a regular HTML or Markdown file, or directory")


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


def render_markdown(source: Path) -> str:
    body = MarkdownIt("js-default").render(source.read_text(encoding="utf-8"))
    title = html.escape(source.stem)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{PAGE_STYLE}</style>
</head>
<body><main>{body}</main></body>
</html>
"""


def stage_source(source: Path, output: Path) -> None:
    if source.is_file():
        output.mkdir(parents=True)
        if source.suffix.lower() in MARKDOWN_SUFFIXES:
            (output / "index.html").write_text(render_markdown(source), encoding="utf-8")
        else:
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
