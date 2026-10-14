# Global Agent Rules

## GitHub CLI

When working with GitHub, always use `gh` and its direct subcommands (`gh pr`, `gh issue`, `gh repo`, `gh run`, etc.). Use `gh api` only as a last resort when the data cannot be obtained via direct commands.

## Pull requests

- Before telling the user a PR is ready to merge, run `gh-pr-status <N>` (all open PRs without a number). It is ready only when the script prints `ready`: CI green on the head commit, mergeable, not a draft, Copilot has reviewed the head commit, and no unresolved review threads. Copilot reviews a few minutes after each push: if it hasn't reviewed the head yet, wait for it and check again instead of reporting the PR ready.
- Fix what Copilot is right about, answer the rest in the thread, and resolve each thread.

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

## Private notes

`~/Code/notes` is the user's private notes repo for all projects: local git, no remote, never push it anywhere. When the user asks to save something private (plans, business, ideas, anything not meant for the project repo), write it to `~/Code/notes/<project>/` (`general/` for things across projects) and commit with a short line. Never copy these notes into a project repository.
