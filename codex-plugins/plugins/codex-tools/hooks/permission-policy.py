#!/usr/bin/env python3

"""Apply automatic decisions to Codex permission requests.

GitHub GraphQL queries are semantically read-only but use POST transport
because the query is a request parameter. This PermissionRequest hook approves
only inline GraphQL documents that are clearly queries. Mutations, file-backed
documents, compound shell commands, and ambiguous inputs keep the normal
approval flow.
"""

from __future__ import annotations

import json
import re
import shlex
import sys


SHELL_OPERATORS = {"&&", "||", ";", "|", "&"}
METHOD_FLAGS = {"-X", "--method"}
FIELD_FLAGS = {"-f", "--raw-field", "-F", "--field"}


def shell_args(command: str) -> list[str] | None:
    try:
        args = shlex.split(command)
    except ValueError:
        return None

    if any(token in SHELL_OPERATORS for token in args):
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


def option_values(args: list[str], names: set[str]) -> list[str] | None:
    values: list[str] = []
    index = 0

    while index < len(args):
        token = args[index]
        if token in names:
            if index + 1 >= len(args):
                return None
            values.append(args[index + 1])
            index += 2
            continue

        if token.startswith("--") and "=" in token:
            name, value = token.split("=", 1)
            if name in names:
                values.append(value)
        elif len(token) > 2 and token[:2] in names:
            values.append(token[2:])

        index += 1

    return values


def explicit_method(args: list[str]) -> str | None:
    values = option_values(args, METHOD_FLAGS)
    if not values:
        return None
    if len(values) != 1:
        return ""
    return values[0].upper()


def graphql_query_values(args: list[str]) -> list[str] | None:
    values = option_values(args, FIELD_FLAGS)
    if values is None:
        return None
    return [value.removeprefix("query=") for value in values if value.startswith("query=")]


def strip_graphql_prefix(document: str) -> str:
    document = document.lstrip("\ufeff, \t\r\n")
    while document.startswith("#"):
        _, separator, document = document.partition("\n")
        if not separator:
            return ""
        document = document.lstrip("\ufeff, \t\r\n")
    return document


def is_readonly_graphql_query(command: str) -> bool:
    args = shell_args(command)
    if args is None or len(args) < 4 or args[:3] != ["gh", "api", "graphql"]:
        return False
    if has_option(args[3:], {"--input"}):
        return False

    method = explicit_method(args[3:])
    if method not in (None, "GET", "POST"):
        return False

    queries = graphql_query_values(args[3:])
    if queries is None or len(queries) != 1 or queries[0].startswith("@"):
        return False

    document = strip_graphql_prefix(queries[0])
    if not (document.startswith("{") or re.match(r"query\b", document)):
        return False
    return re.search(r"\b(?:mutation|subscription)\b", document) is None


def main() -> None:
    input_data = json.load(sys.stdin)
    command = input_data.get("tool_input", {}).get("command")

    if (
        input_data.get("hook_event_name") != "PermissionRequest"
        or input_data.get("tool_name") != "Bash"
        or not isinstance(command, str)
    ):
        return

    if not is_readonly_graphql_query(command):
        return

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            },
        },
        sys.stdout,
        separators=(",", ":"),
    )


if __name__ == "__main__":
    main()
