# Global Agent Rules

## Git

- Change the Git index or create commits only when the user asks; a request for autonomous work or plan execution authorizes committing verified changes owned by that run.
- Create linked worktrees only at `<project-root>/.worktrees/<name>`, using the main checkout as the project root; keep `node_modules`, `.venv`, and build outputs worktree-local instead of copying or symlinking them across checkouts.

## Pull requests

- A task is done in one pass, mostly locally: implement the whole task as far as you can, check it yourself (build, tests, the manual and VM checks it needs), then run Codex review locally and fix its findings until it returns nothing critical. Only then push: open the PR, or push the new commits to an existing one. No early or draft PRs, no pushes while the work is in progress.
- After the push, wait for Copilot's review, fix what it finds in one more push, and the task is done. One Copilot round, not one per commit: it is slow, and every push costs CI minutes.
- Before telling the user a PR is ready to merge, run `gh-pr-status <N>` (all open PRs without a number). It is ready only when the script prints `ready`: CI green on the head commit, mergeable, not a draft, Copilot has reviewed the head commit, and no unresolved review threads. Copilot reviews a few minutes after each push: if it hasn't reviewed the head yet, wait for it and check again instead of reporting the PR ready.
- Fix what Copilot is right about, answer the rest in the thread, and resolve each thread.
- Push to a PR once per finished batch: finish and check the whole set of changes locally, then push. Collect review fixes (Copilot, own review, docs, plan updates) into one push. Don't push to a PR the user is reviewing until they respond.
- While the user is iterating on a design (UI, output, look), keep the changes local and hand them a local build to try; push only after they approve the design.

## Code

- Edit unshipped work directly; add migrations or compatibility layers only for shipped or in-use behavior and data, and ask when usage is unclear.
- For CLI tools, prefer sensible defaults; add flags or settings only when requested or necessary for the task.
- Separate logical steps in code with a blank line, including after an `if`, `for`, `while`, `loop` or `match` block before the next statement; formatters don't add it, so check it before each commit.
- Keep each Markdown paragraph on one physical line.

## Makefiles

- Line 1 is `.PHONY:` with the base targets that exist, in this order: `prepare` (rewrites: format, autofix), `check` (read-only lint and type checks), `test`, `build`, `update` (dependencies), `clean`. They follow in the same order, right after the shared variables.
- Project-specific targets come after the base ones, under their own `.PHONY:` line, each with a short `# what it does` on the target line. A target longer than a line or two calls a script.

## GitHub CLI

When working with GitHub, always use `gh` and its direct subcommands (`gh pr`, `gh issue`, `gh repo`, `gh run`, etc.). Use `gh api` only as a last resort when the data cannot be obtained via direct commands.

## Shell

- Write single, simple commands. Do not use `cd` or chain commands with `;`, `&&`, or `||` in one invocation — chained/`cd`-prefixed commands cannot match the permission allowlist and trigger prompts.
- Never use `git -C <path>` when `<path>` is the current working directory. Run the plain `git <subcommand>` instead — `-C` breaks the permission allowlist and triggers a prompt every time.

## Think before acting

- Think first, act second. Do not run commands or edit files reflexively before reasoning through what the action does and whether it is correct.
- Before any consequential, irreversible, or uncertain action, stop and verify. When unsure, confirm against the actual source (read the docs, read the code) instead of answering or acting from memory.
- When the platform or tool can't do what is asked natively, say so plainly ("can't, because …"). Build a workaround only when the user asks for one.
- Use other agents as a check: when an action or claim is non-trivial or you are not confident, delegate a verification to another agent (e.g. `claude-code-guide` for Claude Code / API questions) before proceeding, not after.

## Responses

- Keep responses short and to the point. No unnecessary explanations, no padding. One sentence per update is usually enough.
- Do not open with reassurance/placating filler ("everything's fine", "nothing's broken", "don't worry", etc.) before saying what actually happened. State the fact/result first, plainly.
- Do not editorialize about the user's tone, don't get defensive, and don't snap back — just answer the question or do the task.

## Private notes

`~/Code/notes` is the user's private notes repo for all projects: local git, no remote, never push it anywhere. When the user asks to save something private (plans, business, ideas, anything not meant for the project repo), write it to `~/Code/notes/<project>/` (`general/` for things across projects) and commit with a short line. Never copy these notes into a project repository.
