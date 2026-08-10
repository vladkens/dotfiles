---
name: plan-review
description: Review and revise an implementation plan in docs/plans. Use when the user invokes $plan-review or explicitly asks to improve a plan through review, not for read-only validation.
---

# Plan Review

Review an implementation plan against the actual project and revise the plan until it is ready for execution.

## Resolve The Plan

- Use the path supplied by the user.
- Otherwise use the plan clearly referenced by the conversation or the only active Markdown file in `docs/plans/`.
- If several plans match and context does not identify one, stop before making changes and list the candidates.
- Read the plan, its referenced research, relevant project files, project instructions, and optional planning rules from `.codex/planning-rules.md`, `.claude/planning-rules.md`, or the user-level planning rules used by `$planning`.
- Read `../planning/references/plan-template.md` when available.

## Independent Review

Launch two read-only subagents in parallel and wait for both:

1. **Correctness reviewer** — verify that the plan solves its stated problem, matches the existing architecture, names the right files and integration points, handles important edge cases, and contains an executable task sequence.
2. **Simplicity reviewer** — look for scope creep, unnecessary abstractions, premature compatibility work, vague tasks, missing tests, weak verification commands, and work that belongs under `Post-Completion`.

Give each reviewer the plan path, research path when present, repository root, and its review focus. Tell reviewers to inspect the relevant code, cite plan sections and project files, report only concrete findings, and never edit files.

If `claude` is available, run `claude -p` concurrently as a third independent reviewer. Use read-only plan permission mode, allow only read/search tools, disable session persistence, and ask it to review the same plan for correctness, missing work, and over-engineering. Never use a permission-bypass flag. If Claude is unavailable or fails, continue with the Codex reviewers instead of blocking the review.

## Reconcile And Revise

1. Validate every finding against the plan and project. Reject duplicates, preferences presented as defects, and claims unsupported by the code.
2. Prioritize issues that would make the plan incorrect, incomplete, unsafe, or impossible to execute. Fix important maintainability and testing gaps when they are concrete. Ignore cosmetic suggestions.
3. Revise the plan directly with the smallest changes that resolve confirmed findings. Preserve useful decisions and avoid expanding the implementation scope.
4. Launch one fresh read-only verification subagent after the revision. Ask only whether blocking or important problems remain.
5. Resolve confirmed verification findings once. Do not create an unbounded reviewer loop.

Do not modify implementation files, use the Git index, create commits, or start implementation during the review itself.

## Result

Report the reviewed plan path and a short summary of material changes. If no blocking decisions remain, offer to implement the plan in the current chat under normal interaction and Git permission rules, execute it autonomously with `$plan-exec <plan-path>`, or leave it ready for later. Do not select a mode without the user. If a product decision cannot be derived safely, leave it explicit in the plan and report that decision as the remaining blocker.
