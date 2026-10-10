---
name: planning
description: Create an implementation plan in docs/plans for discussion or delegated execution. Use when the user asks for an implementation plan, an executable task checklist, or to turn research into an actionable plan, not merely to explore possible directions.
---

# Planning

Write `docs/plans/yyyymmdd-<task-name>.md`, adapting the detail to the user's intent. Read an existing plan before revising it; preserve user edits and completed work.

## Research

- Read applicable instructions, referenced research, affected code, callers, nearby patterns, and relevant tests/build commands. Verify facts against the current project.
- Establish the goal, observable acceptance criteria, scope, constraints, integration points, and important failure cases.
- Resolve material product or technical choices with the user when local evidence cannot answer them. Compare approaches only when there is a real trade-off; record the selected solution and reason. `brainstorm` is optional when choices need exploration.

## Plan

- For discussion, give a concise goal, context, approach, ordered steps, and verification. Include open questions only when they remain relevant.
- For delegated execution, use ordered logical tasks with concrete checkboxes, affected paths, current decisions, dependencies, and exact checks. Each task should be independently verifiable and understandable to a fresh executor without chat history; combine changes that cannot pass separately.
- Use the repository's existing checks and focused regression coverage for meaningful changed behavior. Do not add tests per checkbox or a separate final verification task merely to fill a template.
- Keep changes within the requested scope. Put manual, deployment, and external follow-up outside executable checkboxes; state missing prerequisites instead of promising unavailable checks.
- Executable plans schedule commits after validated tasks and review fixes unless explicit user instructions specify otherwise. Creating or reviewing a plan does not authorize implementation, staging, or commits; do not carry the interactive no-commit default into execution.

## Review and Handoff

- On request, or before a substantial autonomous change, give one fresh read-only native agent the plan, absolute project path, original goal, decisions, constraints, and relevant source paths. Ask it to inspect the real code for incorrect assumptions, missing integration, scope gaps, and unverifiable tasks. Use available tools with the current model/effort; wait for its terminal result.
- Record the review outcome in the plan or handoff. Resolve confirmed in-scope issues and assumptions that could invalidate the solution, or obtain explicit acceptance. A failed review is not approval; reuse earlier review when the plan and underlying assumptions remain valid.
- Report the plan path and essential decisions. If execution was already requested, continue without asking again, using `plan-exec` for delegated plan execution and the applicable Git rules. Otherwise stop at the plan.
