---
name: agent-benchmark
description: Compare independent Codex model runs on one task and generate a shareable HTML report of time, token usage, results, and work logs. Use when the user asks to benchmark agents on the same prompt or compare saved Codex sessions, not for ordinary task delegation or model recommendations.
---

# Agent Benchmark

Turn one task into independent model runs and an inspectable comparison. Use the bundled report template: model columns, sticky visibility controls and names, and one results/work-log switch. Do not invent quality scores or rewrite answers to make them look better.

## Choose inputs

- Use the task, project, attachments, models, and effort already provided. Ask for the task only if it is missing; clarify a decision only when it materially changes what the participants may do.
- Default model order: `gpt-5.6-sol`, `gpt-6-luna`, `gpt-6-sol`, `gpt-6-astra`, with `xhigh`. Allow 1–4 user-selected model IDs. Unavailable models stay visible as failures; never silently substitute another model.
- A request to run this comparison authorizes the selected independent runs and their ordinary model usage. State the model count and timeout before starting. Default timeout is 30 minutes per model, not a token or money cap; shared account limits and host load can affect timing.
- Default to read-only analysis. Use `--write` for an explicitly requested coding task; edits stay in independent copies and appear as a diff in the report. Tasks requiring external mutations, deployments, trades, or interactive authorization need a separately scoped workflow.
- Put necessary external files under `--input`; refer to supplied inputs by relative name in the task. Each participant receives the same prompt and the same snapshot. The snapshots exclude Git internals, dependency caches, common credential files, and symlinks; inspect the recorded exclusions if required project files are missing. Dependencies must be available in the benchmark environment; do not loosen sandbox permissions just to make a participant succeed.

## Run

Resolve bundled paths relative to this skill directory. The runner needs Python 3.11+, `uv`, and an installed, authenticated Codex CLI. Markdown dependencies are declared inline; the HTML template requires no Node build or remote resources. The process runner targets macOS/Linux.

```bash
uv run --script scripts/benchmark.py run --project /path/to/project --prompt-file /path/to/task.txt --background
```

For a different comparison, add `--models model-a model-b`, `--effort high`, or `--timeout 600`. Use `--input /path/to/file` for each additional file or directory. `--output` must name a new directory outside the source project; by default the runner creates a temporary directory. Use a persistent location when the user wants to retain reports beyond temporary-directory cleanup.

The runner launches separate `codex exec --json` processes, keeps normal Codex permissions and rules, and disables nested multi-agent delegation so each participant's reported usage refers to its own run. It does not inherit this conversation as a prompt. Global skills, project instructions, tools, and account configuration can still influence every run.

The printed benchmark directory contains `private/` (raw JSONL, metadata, stderr, snapshot, and separate working copies) and `public/index.html` (the shareable report). The HTML embeds its styles, scripts, and sanitized data; share that single file or publish only `public/`. No server or companion files are needed to open it. Reports are updated at run completion; refresh an already-open page to see updates.

```bash
uv run --script scripts/benchmark.py status /path/to/benchmark
uv run --script scripts/benchmark.py stop /path/to/benchmark
```

For a request to finish the comparison, keep monitoring until every participant has a terminal status, then open the report. A failed model does not stop the others. Do not automatically rerun failed participants: preserve their first result and explain the failure. If the user only requests a background launch, return the directory and status command.

## Import completed sessions

```bash
uv run --script scripts/benchmark.py import /path/to/run-a.jsonl /path/to/run-b.jsonl --turn 1
```

Accept Codex rollout JSONL, `codex exec --json` logs, or the timestamped event logs produced by this runner. Preserve input order. For exec logs without model labels or a prompt, supply `--models model-a model-b` and `--prompt 'Task description'`. Missing timestamps or usage stay unknown. Importing does not run a model or alter the source logs.

Use the selected turn's completion usage for exec streams. For cumulative rollout counters, subtract the last counters before that turn rather than adding repeated total-usage events. `total = input + output`; cached input and reasoning output are subsets, never additional charges. Uncached input is not a count of unique source text, and token totals are not a monetary bill.

## Public report

- Publish final answers, elapsed time, reported usage, agent comments, command/tool descriptions, completion status, and optional code diffs. Raw tool outputs, system/developer instructions, authentication data, and raw hidden reasoning are excluded by field selection. Include only already-exposed CLI reasoning summaries when available; label these as summaries.
- The renderer removes common secret formats, personal filesystem paths, emails, and session IDs from all public text, strips unsafe HTML, and escapes embedded JSON. This is a best-effort filter; inspect `public/index.html` before sharing, especially for proprietary source or task-specific personal data. Preserve technical facts needed to assess the answers.
- Open the generated HTML locally. Publishing is optional: when the user requests a URL, use `html-share` if installed, or their chosen static host. That skill is not required to run a benchmark or share the HTML file itself.
- Report which runs completed, where to open the page, and any missing metrics or failures. Distinguish the wall-clock duration of the parallel batch from the sum of individual durations.

Never bundle personal logs, account tokens, machine paths, or a particular project's results with this skill.
