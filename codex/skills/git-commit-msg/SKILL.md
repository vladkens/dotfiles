---
name: git-commit-msg
description: Generate a commit message from staged Git changes using the repository's existing style. Use when the user asks to write, suggest, regenerate, or commit a message for staged changes.
---

# Commit Message Generator

Generate a commit message for staged changes, calibrated to the project's own commit style.

## Step 1: Gather context

Use the caller-authorized staged scope. For the full index, run:

```bash
<skill-dir>/scripts/collect-context.py
```

The script returns the staged stat, bounded per-file patch excerpts, and recent commit subjects in one response.

When the caller authorizes only a subset of staged work, collect only that scope using the path form below. If unrelated staged work is present, return the scoped message to the caller to handle the commit; do not run an unrestricted commit or change the index to isolate work yourself. If authorized and unrelated hunks cannot be distinguished, report the blocker before generating a message.

If it prints `NO_STAGED_CHANGES`, stop and say so briefly in the language of the current conversation.

If an omitted or truncated file prevents understanding the change, collect only the relevant staged paths:

```bash
<skill-dir>/scripts/collect-context.py -- <path>...
```

Do not collect more diff context when the message is already clear.

## Step 2: Analyse the context

From the history, note:

- Which commit types are used (`feat`, `fix`, `refactor`, `chore`, `docs`, `perf`, `test`, `style`, `ci`)
- Whether scopes are used, how they are separated (e.g. `feat/api:` or `feat(api):`), and how they are named
- Message length and style (terse vs descriptive, imperative vs past tense)
- Language (if commits mix languages, use English)
- Any project-specific conventions (e.g. always lowercase, emoji prefixes, etc.)

From the staged changes, identify:

- What changed (files, functions, logic)
- Why it changed (if inferable from the diff context)
- Whether the project consistently uses typed commit messages

Do not introduce a Conventional Commit type when the project history uses plain messages. If typed messages are established, select the type from the dominant change:

- `feat` — new feature or capability
- `fix` — bug fix
- `refactor` — code restructure with no behaviour change
- `perf` — performance improvement
- `chore` — dependency updates, tooling, or config
- `docs` — documentation only
- `test` — tests only
- `style` — formatting or whitespace
- `ci` — CI/CD pipeline changes

## Step 3: Generate the message

Produce **one** commit message that:

- Matches the presence or absence of types and scopes in the project history
- Uses a scope only when the project history establishes its syntax
- Uses lowercase for type and scope
- Matches the project's capitalization; otherwise starts the description with a lowercase verb
- Is concise: subject line ≤ 72 characters
- Matches the style and verbosity observed in Step 2

If the changes span multiple concerns, pick the dominant one for the subject. Do not add a body unless the change is genuinely non-obvious. Inspect recent commit bodies separately before adding one.

## Step 4: Output

Always respond with a plain text message. Do not use Codex interactive `request_user_input` menus for this skill, even when they are available.

When called only to generate a message during autonomous or plan execution, or when the policy defers the commit, return the message to the caller without committing or showing a confirmation menu.

If a commit is due and already authorized by the current request or autonomous/plan execution policy, and the staged scope above can be safely committed, use the generated message to commit without another confirmation. Report the commit identifier and message to the caller; during autonomous execution, return control to the task instead of ending the run with options.

Otherwise show the generated commit message first, then end the response with numbered options. The user must be able to reply with a number.

Use this format:

```text
<generated commit message>

Options:
1. Commit with this message.
2. Regenerate another message.
```

Without existing commit authorization, wait for an explicit answer before committing. A request only to suggest or regenerate a message does not authorize a commit.

Based on the answer:

- **1** → run `git commit -m "<the message>"`
- **2** → produce an alternative message, then show the numbered options again

## Rules

- **Never commit if nothing is staged.** Always base the message on `git diff --cached`, not `git status` or working tree.
- Do not stage or unstage files.
- Keep the generated message and commit within the caller-authorized staged scope; preserve and exclude unrelated staged work, including during autonomous or plan execution.
- Never amend unless the user explicitly asks.
- Do not add `Co-authored-by` or other trailers unless the user asks.
- If the user provides a hint, incorporate it but still derive type and scope from the actual diff.
