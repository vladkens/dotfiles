#!/usr/bin/env python3
"""Collect bounded staged Git context for commit-message generation."""

import subprocess
import sys

PATCH_LIMIT = 16_000
HISTORY_COUNT = 10
DEFAULT_EXCLUDES = (
    ":(glob,exclude)**/*.lock",
    ":(glob,exclude)**/*.lockb",
    ":(glob,exclude)**/*-lock.*",
    ":(glob,exclude)**/*.min.*",
    ":(glob,exclude)**/*.map",
)


def run_git(args, required=True):
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0 and required:
        message = result.stderr.strip() or result.stdout.strip()
        print(f"ERROR: {message}", file=sys.stderr)
        raise SystemExit(result.returncode)
    return result.stdout if result.returncode == 0 else ""


def clip_middle(text, limit, marker):
    if len(text) <= limit:
        return text.rstrip()

    marker = f"\n{marker}\n"
    available = max(0, limit - len(marker))
    head_size = available // 2
    tail_size = available - head_size
    head = text[:head_size]
    tail = text[-tail_size:] if tail_size else ""

    if "\n" in head:
        head = head.rsplit("\n", 1)[0]
    if "\n" in tail:
        tail = tail.split("\n", 1)[1]
    return f"{head.rstrip()}{marker}{tail.lstrip()}".rstrip()


def split_files(patch):
    marker = "\ndiff --git "
    first, *rest = patch.split(marker)
    blocks = [first] if first.strip() else []
    blocks.extend(f"diff --git {part}" for part in rest)
    return blocks


def shrink_patch(patch):
    if len(patch) <= PATCH_LIMIT:
        return patch.rstrip()

    blocks = split_files(patch)
    per_file = max(160, PATCH_LIMIT // max(1, len(blocks)))
    excerpts = []
    for block in blocks:
        excerpts.append(clip_middle(block, per_file, "[... file diff shortened ...]"))

    result = "\n\n".join(excerpts)
    return clip_middle(result, PATCH_LIMIT, "[... patch shortened ...]")


def main():
    paths = sys.argv[1:]
    if paths[:1] == ["--"]:
        paths = paths[1:]

    stat = run_git(
        [
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--stat",
            "--",
            *paths,
        ]
    ).rstrip()
    if not stat:
        print("NO_STAGED_CHANGES")
        return

    patch_paths = paths or list(DEFAULT_EXCLUDES)
    patch = run_git(
        [
            "diff",
            "--cached",
            "--no-ext-diff",
            "--no-textconv",
            "--no-color",
            "--diff-algorithm=minimal",
            "--find-renames",
            "-U1",
            "--patch",
            "--",
            *patch_paths,
        ]
    )

    stat = clip_middle(stat, PATCH_LIMIT // 4, "[... stat shortened ...]")
    patch = shrink_patch(patch)
    if not patch:
        patch = "(patch omitted by default filters; inspect a specific path if needed)"

    parts = [f"STAGED\n{stat}", f"PATCH\n{patch}"]
    if not paths:
        history = run_git(["log", f"-{HISTORY_COUNT}", "--format=%s"], required=False).rstrip()
        parts.append(f"HISTORY\n{history or '(no commits)'}")

    print("\n\n".join(parts))


if __name__ == "__main__":
    main()
