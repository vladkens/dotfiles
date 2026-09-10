#!/usr/bin/env python3

"""Rewrite shell commands before Codex evaluates command rules.

Codex prefix rules compare literal command arguments, so ``$HOME/.codex/tool``
and ``~/.codex/tool`` do not match the same rule. This PreToolUse hook rewrites
standalone absolute HOME path tokens to their ``~`` form. Paths beneath the
real targets of symlinked ``~/.codex/skills`` entries use their logical Codex
paths instead.

The same literal-prefix behavior affects read-only GitHub API calls. REST calls
that rely on gh's implicit GET do not match the explicit ``gh api -X GET``
rule, so this hook adds that method when the command has no explicit method or
request-body flags.

This is intentionally lexical normalization, not full shell parsing:
whitespace-separated tokens equal to $HOME become ``~``, and tokens beginning
with ``$HOME/`` become ``~/...``. Tokens that do not themselves begin with
$HOME, such as directly quoted paths or ``--path=$HOME/project``, are left
unchanged. Because this is not shell-aware, it does not track a quote opened in
an earlier whitespace-separated token.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

SHELL_OPERATORS = {"&&", "||", ";", "|", "&"}
METHOD_FLAGS = {"-X", "--method"}
BODY_FLAGS = {"-f", "--raw-field", "-F", "--field", "--input"}


def codex_skill_aliases(home: str) -> tuple[tuple[str, str], ...]:
    skills_dir = os.path.join(home, ".codex", "skills")
    try:
        entries = os.scandir(skills_dir)
    except OSError:
        return ()

    aliases = []
    with entries:
        for entry in entries:
            if not entry.is_symlink():
                continue
            aliases.append((os.path.realpath(entry.path), entry.path))

    return tuple(sorted(aliases, key=lambda alias: len(alias[0]), reverse=True))


def normalize_home_paths(command: str, home: str) -> str:
    home_prefix = f"{home}/"
    skill_aliases = codex_skill_aliases(home)
    tokens = re.split(r"([\t \r\n]+)", command)

    for index, token in enumerate(tokens):
        for real_path, logical_path in skill_aliases:
            if token == real_path or token.startswith(f"{real_path}/"):
                token = f"{logical_path}{token[len(real_path) :]}"
                break

        if token == home:
            token = "~"
        elif token.startswith(home_prefix):
            token = f"~/{token[len(home_prefix) :]}"
        tokens[index] = token

    return "".join(tokens)


def leading_command_args(command: str) -> list[str] | None:
    """Parse only the command being normalized; Codex evaluates later segments."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="&;|")
        lexer.commenters = ""
        lexer.whitespace_split = True
    except ValueError:
        return None

    args: list[str] = []
    try:
        for token in lexer:
            if token in SHELL_OPERATORS:
                break
            args.append(token)
    except ValueError:
        return None

    return args


def has_option(args: list[str], names: set[str]) -> bool:
    for token in args:
        if token in names:
            return True
        if token.startswith("--") and "=" in token and token.split("=", 1)[0] in names:
            return True
        if len(token) > 2 and token[:2] in names:
            return True
    return False


def normalize_gh_api_get(command: str) -> str:
    args = leading_command_args(command)
    if args is None or len(args) < 3 or args[:2] != ["gh", "api"] or args[2] == "graphql":
        return command
    if has_option(args[2:], METHOD_FLAGS | BODY_FLAGS):
        return command

    return re.sub(r"^(\s*)gh\s+api(?=\s)", r"\1gh api -X GET", command, count=1)


def main() -> None:
    input_data = json.load(sys.stdin)
    command = input_data.get("tool_input", {}).get("command")
    home = os.environ.get("HOME")

    if (
        input_data.get("hook_event_name") != "PreToolUse"
        or input_data.get("tool_name") != "Bash"
        or not isinstance(command, str)
    ):
        return

    rewritten_command = normalize_home_paths(command, home) if home else command
    rewritten_command = normalize_gh_api_get(rewritten_command)
    if rewritten_command == command:
        return

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": {
                    "command": rewritten_command,
                },
            },
        },
        sys.stdout,
        separators=(",", ":"),
    )


if __name__ == "__main__":
    main()
