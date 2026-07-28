---
name: gh-review
description: Review a GitHub pull request with gh, including its diff, checks, discussion, project context, tests, and independent read-only reviewers. Use when the user asks to review, inspect, or check a GitHub PR.
---

# GitHub PR Review

Review a pull request as a project maintainer and report only actionable findings.

## Resolve And Gather

1. Require a Git repository, `gh`, and valid GitHub authentication.
2. Resolve the PR from a supplied number or URL, or from the current branch with `gh pr view`. If no PR can be identified unambiguously, stop and say what is missing.
3. Fetch the PR title, body, author, base and head commits, changed files, commits, reviews, review decision, mergeability, and check results.
4. Read general discussion comments and inline review comments. Identify the current GitHub user and track which concerns they already raised.
5. Read project instructions and the relevant surrounding code. Compare what the PR actually changes with what its description claims.
6. Treat successful required checks as existing validation. Do not repeat green CI commands locally without a concrete reason.

## Independent Review

1. Launch two read-only subagents in parallel and wait for both:
   - **Correctness reviewer** — inspect behavior, regressions, edge cases, error handling, security, and concurrency.
   - **Quality reviewer** — inspect tests, maintainability, project conventions, over-engineering, and scope creep.
2. Give reviewers the PR metadata, discussion summary, diff, relevant project context, check results, and their review focus. Require concrete findings with file and line references and forbid file edits.

## Targeted Local Validation

Do not fetch or check out the PR, create a worktree, install dependencies, or run local checks by default.

Run a local command only when it can resolve a concrete uncertainty that the diff, surrounding code, discussion, and CI results cannot resolve. State the uncertainty and the smallest relevant command before running it.

- Prefer one focused test or reproduction over a full suite.
- Run lint, formatting, type checks, or broad tests only when the suspected issue directly requires them or the corresponding CI check is missing or failing.
- Never rerun a successful CI command merely to confirm the same result.
- If validation requires the PR files, use the exact head commit in a detached temporary worktree without creating a branch or changing the original checkout.
- Keep setup proportional to the uncertainty. If dependencies, generated files, services, credentials, or environment configuration require substantial setup, report the limitation instead of expanding the review automatically.
- Remove any temporary worktree before returning. If it is not clean, leave it intact and report its path.

## Reconcile Findings

- Verify each finding against the changed code and surrounding implementation.
- Prioritize bugs, security problems, behavioral regressions, missing error handling, and meaningful test gaps.
- Report style or naming only when it violates project rules or hides a concrete maintenance problem.
- Classify changed files as core, supporting, related cleanup, or unrelated. Report unrelated changes as scope creep.
- Exclude findings already raised by the current user unless the issue remains unresolved after a claimed fix.
- Exclude resolved discussion, duplicates, speculative concerns, and preferences without technical impact.
- Mention failed checks separately even when they are unrelated to a code finding.

## Output

Lead with findings ordered by severity. Include file and line references, impact, and a concise suggested direction. Then summarize CI status, any targeted local validation actually performed, and material scope concerns. If no actionable findings remain, say so directly.

The review is read-only by default. Do not modify PR code or automatically draft or publish a formal GitHub review. If the current user message explicitly requests posting, use `gh pr review` with the requested disposition and the verified findings. Never approve, request changes, comment, or merge based only on a general review request.
