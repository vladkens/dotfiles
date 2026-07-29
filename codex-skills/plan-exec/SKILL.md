---
name: plan-exec
description: Execute a specific docs/plans implementation plan autonomously in a temporary worktree on a new branch, with task commits and review passes. Use when the user invokes $plan-exec or explicitly asks for autonomous plan execution with commits.
---

# Plan Exec

Execute the selected plan without routine user interaction and leave a reviewed implementation on a dedicated branch.

## Authorization Boundary

Invoking `$plan-exec` for a plan explicitly authorizes creating and removing a temporary worktree, creating a `codex/<plan-name>` branch, staging files changed for that plan inside the worktree, and creating focused commits on that branch.

This authorization does not include changing the original checkout or its index, staging unrelated local changes, amending or rewriting existing commits, bypassing hooks, rebasing, merging, pushing, tagging, releasing, deploying, or modifying external systems.

## Resolve And Check

1. Resolve the plan from the supplied path, clear conversation context, or the only active Markdown file in `docs/plans/`. If the plan is ambiguous, stop before any Git mutation and list the candidates.
2. Read the whole plan, referenced research, project instructions, relevant implementation files, and available planning rules.
3. Confirm that the plan contains concrete implementation tasks and verification commands. Treat `Post-Completion` as informational and never execute those external or manual actions.
4. Record the original checkout's branch, commit, and complete `git status --short`. The worktree isolates execution, so existing local changes may remain, but never copy or modify them.
5. Record the current commit as the prospective base for a new run. If resuming an interrupted run, recover its base from the existing branch history instead of replacing it with the current checkout's `HEAD`.

## Create Or Resume The Worktree

1. Derive a lowercase slug from the plan filename without its date prefix. Use branch `codex/<slug>` and candidate path `~/.worktrees/<repository>--<slug>`, where `<repository>` is the main worktree directory name.
2. Before any Git mutation, inspect `git worktree list --porcelain`, the candidate branch, the candidate path, and any worktree already attached to that branch.
3. If the branch is attached to a worktree, inspect its complete status, plan, and commits. Resume at its registered path only when it is clearly an incomplete execution of the selected plan. Preserve its index, working files, commits, and original review base, then continue from the first incomplete task. If its purpose is unclear, stop and report the recoverable state instead of creating a suffixed replacement.
4. If the branch exists without a registered worktree, inspect its history and plan state. When it is clearly an incomplete execution of the selected plan and the candidate path is free, recreate the worktree at that path from the existing branch and resume its committed progress. If the branch belongs to a completed or independent run, treat it as a genuine collision.
5. If the candidate path exists but is not its expected registered worktree, stop and report it instead of overwriting, deleting, or bypassing it.
6. Add the same next available numeric suffix to the branch and path only after confirming a genuine collision. Verify that both suffixed targets are unused.
7. For a new run, create `~/.worktrees` if needed and create the branch with `git worktree add -b <branch> <path> HEAD`. Never create worktrees in `/tmp`, `$TMPDIR`, or inside `.git`, and never switch branches in the original checkout.
8. For a new run, recreate the selected plan and referenced research file at the same relative paths inside the worktree and commit them if they differ from `HEAD`. When resuming, never overwrite the recovered plan or working state.
9. Perform every later file edit, command, test, Git operation, and subagent task inside the selected worktree.

## Execute Tasks

Create one task for each plan task and process them in order. Do not run write-capable task agents in parallel because later tasks may depend on earlier changes.

For each task:

1. Re-read the plan and select the first incomplete task.
2. Spawn one worker subagent with the worktree path, the complete task, relevant project rules, and the required verification commands. Tell it to implement only that task, update tests, run focused checks, and avoid Git staging or commits.
3. Inspect the resulting diff and run the task's relevant tests. If the task is incomplete or checks fail, send the concrete failure back to the worker or retry once with a fresh worker.
4. Resolve ordinary implementation details from the plan, repository conventions, and the smallest safe solution. Do not ask the user routine questions.
5. Update the plan checkboxes and record only material deviations or judgment calls.
6. Stage explicit task files and the updated plan. Never use `git add .` or `git add -A`.
7. Create one focused commit matching the repository's commit-message style. Never use `--no-verify`.

Continue until every implementation task and acceptance criterion is complete. Stop only for a hard blocker such as missing credentials, required destructive or external authority, contradictory requirements, or repeated verification failure. Before reporting a blocker, revert only the failed worker's uncommitted changes with `apply_patch`, preserve verified commits, and run the mandatory worktree cleanup.

## Review And Fix

After implementation, launch two read-only subagents in parallel:

1. **Implementation reviewer** — compare the branch with its base and the plan, checking correctness, regressions, error handling, and acceptance criteria.
2. **Quality reviewer** — check tests, maintainability, project conventions, unnecessary complexity, and scope creep.

Require concrete findings with file and line references. Validate each finding against the code, reject false positives, and fix confirmed issues with a single write-capable worker. Run affected checks and commit the fixes. Then run one fresh critical-only review pass and fix any confirmed blocking issues. Do not create an unbounded review loop.

## Complete

1. Run the full verification commands from the plan and confirm the acceptance criteria.
2. Mark the plan complete, add concise execution notes for material deviations, and move it to `docs/plans/completed/` using `apply_patch`.
3. Commit the completed plan and any final verified changes if the worktree is dirty.
4. Confirm that `git status --short` is empty.
5. Remove the temporary worktree without force and verify that its path no longer appears in `git worktree list`. Do this before the final response for completed, blocked, and failed runs.
6. Confirm that the feature branch still exists and the original checkout's branch, commit, index, and working-tree status are unchanged.
7. Report the branch name, base commit, commits, verification results, and material decisions or deviations. The user must be able to run `git switch <branch>` immediately after cleaning any pre-existing changes in their checkout.
