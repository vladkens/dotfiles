# Global Agent Rules

## Working with agents

- The agent the user talks to writes no code itself: it gives each task to a fresh subagent, checks the result by the diff and the checks rather than the report, and keeps the user informed. A subagent does its own task and delegates nothing.
- A fresh read-only reviewer reads every step's diff before the step is reported to the user.
- Report a blocker at once; never build a degraded version around it.
- Ask only when the answer changes the direction; otherwise decide and say what you decided.
- When the user has to act, give the exact command to run or a full link (a PR's URL, never just its number).
- The user reads replies in a terminal and copies from them: text meant to be copied (posts, messages, snippets) goes as plain text, never in Markdown blockquotes (`>`), whose markers come along in the copy.
- Check facts about the outside world (companies, projects, releases, versions, people) on the web before stating them; never answer such things from memory.
- Talk only about what the user is working on now: don't bring up other open work (PRs, CI, agents, tasks) unless asked, and never close, reopen or open a PR on your own to quiet a hook or tidy up.

## Instruction files

- A repository's `agents.md` holds only what an agent must know about that project and wouldn't do anyway: what it is and where each fact lives, its boundaries (what changes only with the person's approval, allowed dependencies), and its conventions that differ from the defaults. Personal and cross-project rules go here; the readme's Contributing only welcomes pull requests, agent-made ones included, and points to `agents.md`; no slogans, generic advice or what a formatter or CI enforces.
- A public repo's readme ends with these sections in this order: Roadmap (if any), `## 🤖 How it's made`, Contributing, License. How it's made is one paragraph: "<name> is built with AI agents following [agents.md](agents.md): I choose what to build, review the changes and test them on real machines. Before agents, I wrote software by hand for years ([macmon](https://github.com/vladkens/macmon), [twscrape](https://github.com/vladkens/twscrape), [ecloop](https://github.com/vladkens/ecloop)). Releases are rare on purpose: I'd rather test and polish a set of changes than ship each one as it lands, and I try not to break your config or data; when something has to break, [changelog.md](changelog.md) says so." A project first written by hand starts "<name> started hand-written and is now built with AI agents…" and leaves itself out of the list; without agents.md drop "following [agents.md](agents.md)"; without changelog.md end at "config or data."

## Git

- Stage or commit only when the user asks: they review every change in git themselves, and a stated goal isn't a request.
- A commit subject and a PR title (its squash commit's subject) are short, at most ~50 characters: one change, no second clause after `;` or `,`; details go in the PR's description on GitHub, never in a commit body.
- Create worktrees only at `<project-root>/.worktrees/<name>`; keep `node_modules`, `.venv` and build outputs local to each worktree.
- Never open a pull request for a change of a line or two, a rule tweak or a docs fix: add it to an open PR close in topic, or keep it for the next one.
- Rewriting history (rebase, amend, filter-repo) keeps each commit's date: the committer date equals the author date (`git rebase --committer-date-is-author-date`, or `GIT_COMMITTER_DATE` from `%aI`); check with `git log --format='%aI %cI'`.

## Code

- Separate logical steps in code with a blank line, also after an `if`, `for`, `while`, `loop` or `match` block before the next statement.
- Keep each Markdown paragraph on one physical line.
- Makefiles: line 1 is `.PHONY:` with the base targets that exist, in this order: `prepare` (format, autofix), `check` (read-only lint and type checks), `test`, `build`, `update` (dependencies), `clean`; they follow in that order after the shared variables. Project targets come after them under their own `.PHONY:`, each with a short `# what it does`; a target longer than a line or two calls a script.

## Apps

- An app never opens a window, popup or dialog by itself and never takes the focus: not on a hotkey, an error or at launch. Errors and missing permissions go to its quiet status (HUD, menu bar icon and menu, log).

## Packages

- A placeholder that reserves a name on a registry (crates.io, PyPI, npm) is version `0.0.0`. A publish can't be undone: check the version before every one.

## Machine

- VMs: run Linux, Windows and macOS checks in `~/Code/vm` through its `./vm` (see its readme); never edit that project from another one, keep at most two VMs running (`./vm stop <profile>` the rest), never quit UTM yourself.
- Never run Instruments or `xcrun xctrace`: on this Mac they froze the window server and needed a hard reset.
- `~/Code/notes` is the user's private notes repo: local git, no remote, never push it. Save private things (plans, business, ideas) to `~/Code/notes/<project>/` (the root for cross-project) by its `agents.md`, commit once per finished result, and never copy them into a project repo.
- Plan and log every publication (post, article, release announcement, comment, reply, list submission) with the promo skill, which checks each channel's posting rules; when the user says something went out, run `promo done` with the link.
