---
name: task-exec
description: Execute a described coding task through an approved solution and user-reviewed implementation. Use only when the user explicitly invokes $task-exec, not for ordinary implementation requests.
---

# Task Exec

Implement an already described coding task collaboratively. Let the user approve the solution before editing code and review the first implementation before tests and verification begin.

## Workflow

- Read the task and inspect only the project context needed to understand the current behavior and existing implementation patterns. Do not edit code yet or investigate test infrastructure and verification commands.
- Ask concise questions when missing information could materially change the implementation. Wait for the answers instead of choosing an unapproved direction, but do not ask about facts that can be derived from the available context.
- If the solution was already discussed and approved earlier in the conversation, skip the proposal and approval steps below and proceed to implementation after inspecting the necessary project context.
- Once the task is clear, briefly explain what needs to change and how the proposed solution will work. Do not turn this into a file itinerary or include tests, linters, verification commands, and routine implementation steps.
- Ask whether the user agrees with the proposed solution and stop. The original implementation request is not approval of the proposed solution.
- After approval, write the smallest production-code implementation that solves the task and follows nearby project patterns. Avoid unapproved abstractions, refactors, compatibility work, and adjacent cleanup.
- Do not add tests or run formatters, linters, type checks, tests, or broad reviews during the first implementation pass.
- Stop after the first implementation and ask the user to review the code. Summarize only material behavior or decisions that help with that review.
- During review, answer questions and apply clear corrections directly without restarting the workflow. Ask before editing when feedback exposes a material ambiguity, and keep verification work deferred until the implementation is approved.
- After the user approves the implementation or asks to finish it, add or update tests required by the task, format the changed code, and run proportionate lint, type, and focused test checks. Fix failures caused by the change without polishing unrelated code.
- Finish with a concise summary of the implemented behavior, tests added or changed, and verification results.

Do not create a formal plan file or invoke an autonomous execution workflow unless the user explicitly asks for one.
