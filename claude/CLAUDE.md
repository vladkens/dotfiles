# Global Agent Rules

## GitHub CLI

When working with GitHub, always use `gh` and its direct subcommands (`gh pr`, `gh issue`, `gh repo`, `gh run`, etc.). Use `gh api` only as a last resort when the data cannot be obtained via direct commands.

## Responses

- Keep responses short and to the point. No unnecessary explanations, no padding. One sentence per update is usually enough.
- Do not open with reassurance/placating filler ("everything's fine", "nothing's broken", "don't worry", etc.) before saying what actually happened. State the fact/result first, plainly.
- Do not editorialize about the user's tone, don't get defensive, and don't snap back — just answer the question or do the task.

## Think before acting

- Think first, act second. Do not run commands or edit files reflexively before reasoning through what the action does and whether it is correct.
- Before any consequential, irreversible, or uncertain action, stop and verify. When unsure, confirm against the actual source (read the docs, read the code) instead of answering or acting from memory.
- Use other agents as a check: when an action or claim is non-trivial or you are not confident, delegate a verification to another agent (e.g. `claude-code-guide` for Claude Code / API questions) before proceeding, not after.

## Bash

- Write single, simple commands. Do not use `cd` or chain commands with `;`, `&&`, or `||` in one invocation — chained/`cd`-prefixed commands cannot match the permission allowlist and trigger prompts.
- Never use `git -C <path>` when `<path>` is the current working directory. Run the plain `git <subcommand>` instead — `-C` breaks the permission allowlist and triggers a prompt every time.
