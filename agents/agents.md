# Global Agent Rules

## Git

- The user reviews every change in git themselves. Don't stage or commit unless asked; after a review they either commit themselves or ask you to.
- Create worktrees only at `<project-root>/.worktrees/<name>` (the main checkout is the project root); keep `node_modules`, `.venv` and build outputs local to each worktree.

## Code

- Separate logical steps in code with a blank line, also after an `if`, `for`, `while`, `loop` or `match` block before the next statement; formatters don't add it.
- Keep each Markdown paragraph on one physical line.
- Makefiles: line 1 is `.PHONY:` with the base targets that exist, in this order: `prepare` (format, autofix), `check` (read-only lint and type checks), `test`, `build`, `update` (dependencies), `clean`; they follow in that order after the shared variables. Project targets come after them under their own `.PHONY:`, each with a short `# what it does`; a target longer than a line or two calls a script.

## Packages

- A placeholder that reserves a name on a registry (crates.io, PyPI, npm) is version `0.0.0`. A publish can't be undone: check the version before every one.

## Private notes

`~/Code/notes` is the user's private notes repo: local git, no remote, never push it. Save private things (plans, business, ideas) to `~/Code/notes/<project>/` (`general/` for cross-project) and commit with a short line. Never copy them into a project repo.

## Content plan

Before planning or publishing a post, article, release announcement or list submission, read `~/Code/notes/general/content-plan.md`: pick a free day by its rules, add a row, mark it published afterwards.
