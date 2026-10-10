---
name: plan-exec
description: Execute an implementation plan sequentially with fresh task agents, validation, and independent review. Use when the user asks to run a plan autonomously task by task or explicitly invokes plan-exec, not merely to write or discuss a plan.
---

# Plan Exec

Act as the manager: delegate implementation and fixes, inspect evidence, and keep the plan current. Do not implement or fix the work yourself.

## Boundaries

- Use the native collaboration/subagent tools available in this session, inheriting the current model and effort unless the user specifies otherwise. If delegation is unavailable, report the blocker. A fresh context shares the filesystem, so allow only one writer and no review concurrent with implementation/fixes.
- Keep every child in the exact absolute project directory under applicable instructions and permissions. Preserve unrelated edits and staged work; record run-owned paths/changes and a review baseline before the first task commit. Use the current checkout unless isolation was requested; follow project worktree rules when it was.
- A user's request to execute the plan, including an explicit plan-exec skill invocation, authorizes staging and committing verified run-owned changes after each task and review fix. Follow explicit user or approved-plan commit instructions; a newer user clarification supersedes an older restriction. Do not import the interactive no-commit default. Broader Git operations and publishing need separate authorization.

## Prepare and Resume

- Read the supplied plan and project context. If no path was supplied, use the only unfinished plan in `docs/plans/`, excluding progress files; ask only when selection or scope is genuinely ambiguous. If no plan exists, report that and offer `planning`.
- Adapt a clear approved roadmap into dependency-ordered, verifiable tasks without asking about its headings. Derive paths/checks from the actual project and preserve scope, completed work, and explicit instructions; resolve only material decisions that remain unclear.
- For substantial autonomous work or on request, require one independent read-only plan review against relevant code before implementation. Reuse a valid earlier review; otherwise supply a fresh reviewer the goal, plan, decisions, constraints, and project paths. Resolve confirmed in-scope issues or material assumptions, or obtain explicit acceptance; a failed review does not pass this gate.
- Keep a short `<plan-stem>.progress.md` beside the plan with scope, working directory, commit policy/source, task status, exact check results, commits, review findings, and the next step. Preserve existing evidence on resume; only one agent writes the plan/progress at a time.
- Reconcile checkboxes with current files, recorded checks, and due commits. Finish a missing commit checkpoint using still-valid evidence; do not redo unchanged verified work. Confirm an earlier child is terminal before replacing it. Interrupted work and skipped checks remain incomplete.

## Execute

1. Give a fresh executor exactly the next unfinished logical task, absolute project/plan/progress paths, original goal, decisions, affected paths, checks, relevant prior evidence, permissions, and resolved commit policy with its source. Do not rely on inherited history; children do not delegate or start another task.
2. The executor reads the relevant files, completes that task, runs appropriate repository checks and meaningful regressions, marks only verified items complete, records a concise result, commits task-owned changes under the supplied policy, and stops. Preserve unrelated index contents; if ownership cannot be separated safely, report the blocker.
3. Wait for the terminal result. Check the changed work, exact validation evidence, remaining items, and due commit identifier before advancing. A failed required check or commit blocks completion; unavailable, manual, and external checks must not be marked passed. Reuse passing evidence for unchanged work and avoid empty commits.
4. Repeat sequentially until tasks are complete. On user feedback, steer the active child and update affected decisions/tasks at a safe boundary; reopen only invalidated work. Report concrete permission, environment, or decision blockers instead of restarting the whole workflow.

## Review and Finish

1. Give one fresh independent read-only reviewer the whole run-owned implementation, original goal, current plan/decisions, absolute paths, changed files/baseline, and validation evidence. Ask it to inspect actual source for goal coverage, integration, real defects, and sufficient checks. It does not edit files or Git state; commands with write side effects belong to an executor/fixer. Wait for its terminal report; silence or failure is not clean review.
2. If the reviewer returns actionable findings, send them to a separate fresh fixer with the same scope, context, permissions, and commit policy. It verifies evidence, fixes only confirmed in-scope issues, records false positives/unrelated findings separately, runs focused checks, and commits verified fixes. If needed, use one focused read-only recheck of corrected behavior and affected integration; unresolved issues remain visible and block a clean finish. A successful review with no actionable findings goes directly to step 3.
3. The manager compares acceptance criteria with delivered behavior and check/review evidence, records completion and any due final commit checkpoint under the policy, then reports tasks, changed paths, commits, checks, and remaining manual/external limitations. Do not claim completion while a required check, review, or commit is unresolved.
