---
name: git-commit-msg
description: Generate a commit message from staged Git changes using the repository's existing style. Use when the user asks to write, suggest, regenerate, or commit a message for staged changes.
---

# Commit Message Generator

Generate a commit message for staged changes, calibrated to the project's own commit style.

## Step 1: Gather context

```bash
<skill-dir>/scripts/collect-context.py
```

The script returns the staged stat, bounded per-file patch excerpts, and recent commit subjects in one response.

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
- Uses `<type>/<scope>: <description>` for scoped changes only when typed messages are established but the scope syntax is unclear
- Uses lowercase for type and scope
- Matches the project's capitalization; otherwise starts the description with a lowercase verb
- Is concise: subject line ≤ 72 characters
- Matches the style and verbosity observed in Step 2

If the changes span multiple concerns, pick the dominant one for the subject. Do not add a body unless the change is genuinely non-obvious. Inspect recent commit bodies separately before adding one.

## Step 4: Output

Always respond with a plain text message. Do not use Codex interactive `request_user_input`
menus for this skill, even when they are available.

Show the generated commit message first, then always end the response with numbered
options. The user must be able to reply with a number.

Use this format:

```text
<generated commit message>

Options:
1. Commit with this message.
2. Regenerate another message.
```

Wait for an explicit answer before committing.

Based on the answer:

- **1** → run `git commit -m "<the message>"`
- **2** → produce an alternative message, then show the numbered options again

## Rules

- **Never commit if nothing is staged.** Always base the message on `git diff --cached`, not `git status` or working tree.
- Do not stage or unstage files.
- Never amend unless the user explicitly asks.
- Do not add `Co-authored-by` or other trailers unless the user asks.
- If the user provides a hint, incorporate it but still derive type and scope from the actual diff.
