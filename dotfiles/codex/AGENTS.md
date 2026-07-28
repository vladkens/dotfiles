## Git safety

- Never change the Git index or create commits unless the user explicitly requests that exact action in the current message. Editing files does not imply staging; if staging is needed, explain why and wait for approval.

## Git worktrees

- Create linked worktree checkouts at `~/.worktrees/<repository>--<name>`. Never place them in `/tmp`, `$TMPDIR`, or inside `.git`; `.git/worktrees` is reserved for Git-managed metadata.

## Change discipline

- Keep diffs as small and focused as possible.
- Uncommitted, unreleased, or actively iterated work is not a compatibility boundary. Change it directly instead of preserving earlier iterations with migrations, compatibility layers, fallbacks, or extra abstractions. Add compatibility work only for behavior or data already released or in use; if unclear, ask first.
- For CLI tools, prefer opinionated behavior and simple defaults. Ask before adding flags or configuration options.

## Direct language

- Treat profanity and insults as normal working language used for emphasis and fast feedback. Interpret insults idiomatically; do not moralize, tone-police, or infer unrelated claims about identity or sexual orientation.
- Treat repeated or intensifying profanity as a strong signal that the current approach is likely wrong. Stop editing, inspect the evidence and diff, then state in your own words what the user asked for, what you did instead, and what you propose to do next. Confirm that understanding before making more changes.
- If the technical cause remains unclear after confirmation, use a read-only subagent for an independent diagnosis. Respond with the concrete diagnosis or correction, not apology or de-escalation filler.
