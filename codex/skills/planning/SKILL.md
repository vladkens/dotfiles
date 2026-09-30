---
name: planning
description: Create a concise implementation plan in docs/plans for a feature, bug fix, refactor, or migration. Use when the user asks for an implementation plan or wants to turn research into an actionable plan.
---

# Planning

Create `docs/plans/yyyymmdd-<task-name>.md` when the user asks for an implementation plan.

## Understand the Task

- Read any research the user references and verify details that affect the plan against the current project.
- Inspect the affected code, nearby patterns, call sites, and relevant tests. For bugs, trace the failure and current behavior; for features and refactors, identify integration points and affected references.
- Establish the desired behavior, acceptance criteria, scope, constraints, dependencies, and meaningful edge cases.
- Ask only about decisions that could materially change the solution. Compare approaches only when there is a real choice; recommend one and record the reason.

## Write the Plan

Give the plan a descriptive title and use these sections, omitting empty ones:

- `Goal`: the problem, intended behavior, and acceptance criteria.
- `Context`: current behavior, relevant files, constraints, and research source if any.
- `Approach`: the chosen solution, important decisions, and trade-offs that affected the choice.
- `Steps`: ordered, concrete changes with affected files and dependencies when known.
- `Verification`: meaningful tests or checks, with exact commands when known.
- `Open Questions`: unresolved decisions or risks.

Keep steps limited to the requested change. Use real paths and commands when known; identify unknowns instead of inventing details. Put manual or external follow-up outside the implementation steps when needed. Do not require a test or progress checkbox for every step.

Report the plan path. If the user asks to implement it, continue in the current conversation under the normal project and Git permission rules.
