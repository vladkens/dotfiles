# Global Agent Rules

## Git

- The user reviews every change in git themselves. Don't stage or commit unless explicitly told to; a stated goal isn't that; after a review they either commit themselves or ask you to.
- Create worktrees only at `<project-root>/.worktrees/<name>` (the main checkout is the project root); keep `node_modules`, `.venv` and build outputs local to each worktree.
- Never open a pull request for a change of a line or two, a rule tweak or a docs fix: add it to an open PR close in topic, or keep it for the next one.

## Code

- Separate logical steps in code with a blank line, also after an `if`, `for`, `while`, `loop` or `match` block before the next statement; formatters don't add it.
- Keep each Markdown paragraph on one physical line.
- Makefiles: line 1 is `.PHONY:` with the base targets that exist, in this order: `prepare` (format, autofix), `check` (read-only lint and type checks), `test`, `build`, `update` (dependencies), `clean`; they follow in that order after the shared variables. Project targets come after them under their own `.PHONY:`, each with a short `# what it does`; a target longer than a line or two calls a script.

## Apps

- An app never shows a window, popup, alert or dialog by itself and never takes the focus from the window the user works in: not on a hotkey, not on an error, not at launch. Errors and missing permissions go to the app's own quiet status (its HUD, its menu bar icon and menu, the log). A window opens only when the user asks for it (a menu item, a button, opening the app).

## Packages

- A placeholder that reserves a name on a registry (crates.io, PyPI, npm) is version `0.0.0`. A publish can't be undone: check the version before every one.

## Private notes

`~/Code/notes` is the user's private notes repo: local git, no remote, never push it. Save private things (plans, business, ideas) to `~/Code/notes/<project>/` (the root for cross-project) by its `agents.md`, and commit once per finished result, not per step. Never copy them into a project repo.

## Content plan

Before planning or publishing a post, article, release announcement or list submission, read `~/Code/notes/content-plan.md`: pick a free day by its rules, add a row, mark it published afterwards.
