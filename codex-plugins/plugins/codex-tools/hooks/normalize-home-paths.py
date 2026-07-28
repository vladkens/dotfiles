#!/usr/bin/env python3

"""Normalize absolute paths below $HOME before Codex evaluates command rules.

Why this exists:
Codex prefix rules compare literal command arguments, so ``$HOME/.codex/tool``
and ``~/.codex/tool`` do not match the same rule. This PreToolUse hook rewrites
standalone absolute HOME path tokens to their ``~`` form.

Codex hook pipeline, verified against rust-v0.145.0:
1. PreToolUse parses ``permissionDecision: "allow"`` plus ``updatedInput`` into
   an updated input value. The ``allow`` value is required by the rewrite
   protocol; omitting it makes the hook output invalid.
2. The tool registry replaces the original invocation with ``updatedInput``.
3. The shell or unified-exec handler then evaluates exec policy, sandboxing,
   and approvals against the rewritten command.

Therefore this PreToolUse ``allow`` does not itself approve shell escalation.
Approval overrides belong to the separate PermissionRequest hook event, which
this plugin does not register.

Codex sources:
- PreToolUse output parsing and required allow/update pair:
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/hooks/src/engine/output_parser.rs#L121-L174
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/hooks/src/engine/output_parser.rs#L434-L473
- Replacing the invocation before executing its handler:
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/core/src/tools/registry.rs#L489-L532
- Exec-policy evaluation after the rewrite:
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/core/src/tools/handlers/shell.rs#L168-L180
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/core/src/unified_exec/process_manager.rs#L1093-L1109
- PermissionRequest is a separate decision stage:
  https://github.com/openai/codex/blob/rust-v0.145.0/codex-rs/core/src/hook_runtime.rs#L222-L255

This is intentionally lexical normalization, not full shell parsing:
whitespace-separated tokens equal to $HOME become ``~``, and tokens beginning
with ``$HOME/`` become ``~/...``. Tokens that do not themselves begin with
$HOME, such as directly quoted paths or ``--path=$HOME/project``, are left
unchanged. Because this is not shell-aware, it does not track a quote opened in
an earlier whitespace-separated token.
"""

import json
import os
import re
import sys


def normalize_home_paths(command: str, home: str) -> str:
    home_prefix = f"{home}/"
    tokens = re.split(r"([\t \r\n]+)", command)

    for index, token in enumerate(tokens):
        if token == home:
            tokens[index] = "~"
        elif token.startswith(home_prefix):
            tokens[index] = f"~/{token[len(home_prefix) :]}"

    return "".join(tokens)


def main() -> None:
    input_data = json.load(sys.stdin)
    command = input_data.get("tool_input", {}).get("command")
    home = os.environ.get("HOME")

    if input_data.get("tool_name") != "Bash" or not isinstance(command, str) or not home:
        return

    rewritten_command = normalize_home_paths(command, home)
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
