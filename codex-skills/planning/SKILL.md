---
name: planning
description: Create an executable implementation plan in docs/plans for a feature, bug fix, refactor, or migration. Use when the user asks for an implementation plan or wants to turn docs/research findings into one.
---

# Planning

Create a practical implementation plan file at `docs/plans/yyyymmdd-<task-name>.md`.

## Workflow

### Step 0: Load Planning Rules

Before planning, check for optional custom rules:

1. Project rules: `.codex/planning-rules.md`, then `.claude/planning-rules.md`.
2. User rules: `$CODEX_HOME/planning-rules.md` if `CODEX_HOME` is set, otherwise `~/.codex/planning-rules.md`.

Use the first non-empty file found. Treat rules as additional guidance for creating the plan; do not paste rules into the plan unless the user explicitly asks.

### Step 1: Gather Context

Inspect project context before writing the plan. Keep discovery focused:

- For prior research: read the referenced file in `docs/research/`; if no file is named, use a clear matching file or ask when multiple files could apply.
- For a feature: find 1-3 relevant files/directories and existing patterns.
- For a bug: search error messages, function names, and recent changes.
- For a refactor/migration: inspect references/imports and nearby tests.
- For vague requests: inspect the top-level structure and relevant recent commits.

Summarize findings briefly: relevant files, current behavior, constraints, and likely risks. Treat research as discovery context, verify details that affect the plan, and preserve its path for the plan's Context section.

### Step 2: Clarify Only What Matters

Ask one question at a time only when a real decision is missing.

Use `request_user_input` if available. If unavailable, ask a plain question and wait. Good clarification targets:

- main goal or acceptance criteria
- scope boundaries
- hard constraints
- testing preference: TDD or regular
- short plan title

Skip questions when context and user intent are already clear.

### Step 3: Explore Approaches When Useful

For non-obvious implementation choices, propose 2-3 approaches with tradeoffs and recommend one. Skip this for direct bug fixes or when the user already chose the approach.

Do not create the plan until the approach is clear enough to be executable.

### Step 4: Create The Plan File

Create `docs/plans/yyyymmdd-<task-name>.md` using the current date.

Use the structure in `references/plan-template.md`. Adapt it to the project and task:

- keep tasks concrete and small
- include a `Files:` block for each implementation task
- every code-changing task must include tests
- include exact verification commands when known
- put manual/external follow-up items under `Post-Completion`

If `docs/plans/` does not exist, create it. Do not move plans to `completed/` until implementation is complete.

### Step 5: Report Next Options

After creating the file, tell the user:

```text
created plan: `docs/plans/yyyymmdd-<task-name>.md`
```

Then ask what to do next:

- review it with `$plan-review <plan-path>`
- implement it in the current chat
- execute it autonomously with `$plan-exec <plan-path>`
- leave it as a draft
- adjust a section

Do not choose an execution mode automatically. If the user chooses implementation in the current chat, continue in the current checkout under the normal interaction and Git permission rules. If the user chooses autonomous execution, invoke `$plan-exec`; it uses a temporary worktree, removes it before returning, and leaves a feature branch containing the committed result.

## Plan Quality Rules

- Write plans for future execution, not as vague notes.
- Prefer concrete file paths and concrete commands.
- Keep scope tight; mark deferred work explicitly.
- Do not include unrelated refactors.
- Each task should be a logical unit that can be completed and tested before the next.
- Update the plan file if scope changes during implementation.
- Keep `Post-Completion` free of checkboxes; it is informational external/manual follow-up.

## Reference

Read `references/plan-template.md` when creating a plan file.
