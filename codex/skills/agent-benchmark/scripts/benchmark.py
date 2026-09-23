#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-it-py>=3,<5", "nh3>=0.2,<1"]
# ///

"""Run independent Codex sessions or import existing logs into a shareable report."""

import argparse
import asyncio
import difflib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import nh3
from markdown_it import MarkdownIt

DEFAULT_MODELS = ["gpt-5.6-sol", "gpt-6-luna", "gpt-6-sol", "gpt-6-astra"]
EXCLUDED = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    ".DS_Store",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".netlify",
    ".agent-benchmarks",
}


TOKEN_FIELDS = {
    "input": "input_tokens",
    "cached_input": "cached_input_tokens",
    "output": "output_tokens",
    "reasoning": "reasoning_output_tokens",
}
MARKDOWN = MarkdownIt("commonmark", {"html": False}).enable("table")
SECRET_PATTERNS = [
    (r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----", "[private-key]"),
    (r"\b(?:sk-|gh[pousr]_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{8,}", "[secret]"),
    (r"\bAKIA[A-Z0-9]{16}\b", "[secret]"),
    (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[jwt]"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [secret]"),
    (
        r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)[\"']?\s*[:=]\s*)([\"']?)[^\s,;\"'}]+\2",
        r"\1[secret]",
    ),
    (r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[credentials]@"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[email]"),
    (r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", "[session-id]"),
    (r"(?:file://)?(?:/Users/|/home/)[^\s\"'`<>\)\]]+", "[local-path]"),
    (
        r"(?:file://)?(?:/private/(?:tmp|var/folders)|/tmp|/var/folders)/[^\s\"'`<>\)\]]+",
        "[temporary-path]",
    ),
    (r"[A-Za-z]:\\(?:Users|Documents and Settings)\\[^\s\"'`<>]+", "[local-path]"),
    (r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?[^\s\"'`<>]*", "[local-url]"),
]


def redact(text, replacements=()):
    text = str(text or "")
    for private, public in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        if private:
            text = text.replace(str(private), public)

    for pattern, replacement in SECRET_PATTERNS:
        text = re.sub(pattern, replacement, text)

    return text


def markdown_html(text):
    # External images and embedded content are deliberately excluded from public reports.
    return nh3.clean(
        MARKDOWN.render(text),
        tags={
            "p",
            "br",
            "hr",
            "strong",
            "em",
            "s",
            "a",
            "code",
            "pre",
            "blockquote",
            "ul",
            "ol",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
        },
        attributes={"a": {"href", "title"}},
        url_schemes={"http", "https"},
        link_rel="noopener noreferrer",
    )


def tokens_from_usage(usage, baseline=None):
    result = {}
    for key, field in TOKEN_FIELDS.items():
        value = usage.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            value = None

        if baseline is not None:
            previous = baseline.get(field)
            value = value - previous if value is not None and isinstance(previous, int) else None
            if value is not None and value < 0:
                value = None

        result[key] = value

    result["total"] = (
        result["input"] + result["output"]
        if result["input"] is not None and result["output"] is not None
        else None
    )
    return result


def timestamp(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def message_text(payload):
    return "\n".join(
        item.get("text", "") for item in payload.get("content", []) if isinstance(item, dict)
    )


def load_events(path):
    records = []
    with Path(path).open() as stream:
        for line in stream:
            if not line.strip():
                continue

            record = json.loads(line)
            event = record.get("event", record)
            records.append((event, timestamp(record.get("recorded_at") or event.get("timestamp"))))

    return records


def parse_events(path, turn=1):
    records = load_events(path)
    rollout = any(event.get("type") == "event_msg" for event, _ in records)

    def started(event):
        return (
            (
                event.get("type") == "event_msg"
                and event.get("payload", {}).get("type") == "task_started"
            )
            if rollout
            else event.get("type") == "turn.started"
        )

    starts = [index for index, (event, _) in enumerate(records) if started(event)]
    if turn < 1 or turn > len(starts):
        raise ValueError(f"Turn {turn} missing; found {len(starts)} turn(s) in {path.name}")

    start_index = starts[turn - 1]
    end_index = starts[turn] if turn < len(starts) else len(records)
    start_time = records[start_index][1]
    selected = records[start_index:end_index]
    baseline = dict.fromkeys(TOKEN_FIELDS.values(), 0) if turn == 1 else {}
    for event, _ in records[:start_index]:
        usage = (event.get("payload", {}).get("info") or {}).get("total_token_usage")
        if usage:
            baseline = usage

    result = {
        "model": "unknown",
        "effort": "unknown",
        "status": "incomplete",
        "error": None,
        "duration_seconds": None,
        "tokens": tokens_from_usage({}),
        "final_answer": "",
        "prompt": "",
        "timeline": [],
    }
    seen = set()
    for event, at in selected:
        payload = event.get("payload", {})
        kind = event.get("type")
        offset = (
            round(max(0, at - start_time), 3) if at is not None and start_time is not None else None
        )
        if kind == "turn_context":
            result["model"] = payload.get("model", "unknown")
            result["effort"] = payload.get("effort", "unknown")

        if kind == "event_msg" and payload.get("type") == "user_message":
            result["prompt"] = payload.get("message", "")

        if kind == "event_msg" and payload.get("type") == "token_count":
            usage = (payload.get("info") or {}).get("total_token_usage")
            if usage:
                result["tokens"] = tokens_from_usage(usage, baseline)

        complete = kind == "turn.completed" or (
            kind == "event_msg" and payload.get("type") == "task_complete"
        )
        if complete:
            result["status"] = "completed"
            result["duration_seconds"] = offset
            if kind == "turn.completed":
                result["tokens"] = tokens_from_usage(event.get("usage") or {})

            break

        if kind in {"error", "turn.failed"} or (
            kind == "event_msg" and payload.get("type") in {"task_aborted", "error"}
        ):
            result["status"] = "failed"
            error = (
                event.get("error")
                or event.get("message")
                or payload.get("message")
                or payload.get("reason")
            )
            result["error"] = (
                error.get("message", str(error))
                if isinstance(error, dict)
                else str(error or "Run failed")
            )
            result["duration_seconds"] = offset

        item = (
            event.get("item", {})
            if kind == "item.completed"
            else payload
            if kind == "response_item"
            else {}
        )
        item_type = item.get("type")
        public_kind, title, detail = None, "", ""
        if kind == "item.completed" and item_type == "agent_message":
            detail = item.get("text", "")
            result["final_answer"] = detail
            public_kind, title = "update", "Комментарий агента"
        elif kind == "response_item" and item_type == "message" and item.get("role") == "assistant":
            detail = message_text(item)
            if item.get("phase") in {"final_answer", "final"} or item.get("channel") == "final":
                result["final_answer"] = detail
            elif item.get("phase") == "commentary" or item.get("channel") == "commentary":
                public_kind, title = "update", "Комментарий агента"
        elif kind == "item.completed" and item_type == "reasoning":
            # Only the CLI's already-exposed summary, never raw rollout reasoning payloads.
            public_kind, title, detail = "summary", "Краткая сводка", item.get("text", "")
        elif item_type in {"command_execution", "mcp_tool_call", "web_search", "file_change"}:
            public_kind, title = (
                "tool",
                {
                    "command_execution": "Команда",
                    "mcp_tool_call": "Инструмент",
                    "web_search": "Поиск",
                    "file_change": "Изменение файлов",
                }[item_type],
            )
            detail = (
                item.get("command")
                or item.get("query")
                or item.get("tool")
                or ", ".join(str(change.get("path", "")) for change in item.get("changes", []))
            )
            if item.get("exit_code") is not None:
                detail += f"\nExit code: {item['exit_code']}"
        elif item_type in {"function_call", "custom_tool_call"}:
            public_kind, title = "tool", str(item.get("name", "Инструмент"))
            detail = item.get("arguments") or item.get("input") or ""

        if public_kind and detail:
            key = item.get("id") or item.get("call_id")
            if key and key in seen:
                continue

            if key:
                seen.add(key)

            result["timeline"].append(
                {"at_seconds": offset, "kind": public_kind, "title": title, "detail": str(detail)}
            )

    if (
        not rollout
        and result["timeline"]
        and result["timeline"][-1]["detail"] == result["final_answer"]
    ):
        result["timeline"].pop()

    return result


def public_run(run, index, replacements):
    def clean(value):
        return redact(value, replacements)

    result = {
        "id": f"run-{index + 1}",
        "label": f"Запуск {index + 1:02d}",
        "model": clean(run.get("model", "unknown")),
        "effort": clean(run.get("effort", "unknown")),
        "status": run.get("status", "incomplete"),
        "error": clean(run.get("error")) or None,
        "duration_seconds": run.get("duration_seconds"),
        "tokens": {key: run.get("tokens", {}).get(key) for key in [*TOKEN_FIELDS, "total"]},
        "final_html": markdown_html(clean(run.get("final_answer", ""))),
        "timeline": [
            {
                "at_seconds": item.get("at_seconds"),
                "kind": clean(item.get("kind", "tool")),
                "title": clean(item.get("title")),
                "detail": clean(item.get("detail")),
            }
            for item in run.get("timeline", [])
        ],
    }
    if run.get("patch"):
        result["patch_html"] = markdown_html("```diff\n" + clean(run["patch"]) + "\n```")

    return result


def write_report(root, manifest):
    replacements = [(path, label) for path, label in manifest.get("redact_paths", [])]
    report = {
        "title": "Один запрос. Несколько агентов.",
        "prompt": redact(manifest.get("prompt", ""), replacements),
        "created_at": manifest.get("created_at", datetime.now(UTC).isoformat()),
        "wall_seconds": manifest.get("wall_seconds"),
        "methodology": "Независимые запуски Codex. Время запуска включает ожидание модели и инструментов. "
        "Токены взяты из usage; неизвестные значения обозначены прочерком. "
        "Вход включает повторный контекст; кеш входит во вход, reasoning входит в выход. "
        "Системные инструкции и сырые ответы инструментов не публикуются. "
        "Ход работы показывает доступные события и краткие сводки, а не полную внутреннюю цепочку рассуждений.",
        "runs": [
            public_run(run, index, replacements) for index, run in enumerate(manifest["runs"])
        ],
    }
    assets = Path(__file__).resolve().parents[1] / "assets"
    data = (
        json.dumps(report, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    template = (assets / "report.html").read_text()
    page = template.replace("__REPORT_DATA__", data)
    public = Path(root) / "public"
    public.mkdir(exist_ok=True)
    destination = public / "index.html"
    temporary = public / "index.html.tmp"
    temporary.write_text(page)
    temporary.replace(destination)
    return destination


def now():
    return datetime.now(UTC).isoformat()


def save_manifest(root, manifest):
    target = root / "private" / "manifest.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(target)
    write_report(root, manifest)


def create_output(path):
    if path:
        root = path.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=False)
    else:
        root = Path(tempfile.mkdtemp(prefix="agent-benchmark-"))

    (root / "private").mkdir(mode=0o700)
    return root


def copy_snapshot(source, target, excluded):
    def ignore(directory, names):
        ignored = []
        for name in names:
            path = Path(directory) / name
            if (
                name in EXCLUDED
                or name.startswith(".env.")
                or path.is_symlink()
                or path.suffix.lower() in {".pem", ".key"}
            ):
                ignored.append(name)
                excluded.append(str(path.relative_to(source)))

        return ignored

    shutil.copytree(source, target, ignore=ignore)


def changed_files(snapshot, workspace):
    names = {path.relative_to(snapshot) for path in snapshot.rglob("*") if path.is_file()}
    names.update(path.relative_to(workspace) for path in workspace.rglob("*") if path.is_file())
    patches = []
    for name in sorted(names):
        before, after = snapshot / name, workspace / name
        if before.is_symlink() or after.is_symlink():
            continue

        if any(path.exists() and path.stat().st_size > 1_000_000 for path in (before, after)):
            continue

        left = before.read_bytes() if before.is_file() else b""
        right = after.read_bytes() if after.is_file() else b""
        if left == right:
            continue

        try:
            patch = "".join(
                difflib.unified_diff(
                    left.decode().splitlines(keepends=True),
                    right.decode().splitlines(keepends=True),
                    fromfile=f"a/{name}",
                    tofile=f"b/{name}",
                )
            )
        except UnicodeDecodeError:
            patch = f"Binary file changed: {name}\n"

        patches.append(patch)
        if sum(map(len, patches)) > 200_000:
            patches.append("\n[Diff truncated; complete files remain in the private workspace.]\n")
            break

    return "\n".join(patches)


async def stop_process(process):
    if process.returncode is not None:
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    try:
        await asyncio.wait_for(process.wait(), 5)
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        await process.wait()


async def execute_run(root, manifest, run):
    workspace = root / "private" / "workspaces" / run["id"]
    raw = root / "private" / run["id"]
    raw.mkdir()
    start = time.monotonic()
    run["status"] = "running"
    run["started_at"] = now()
    save_manifest(root, manifest)
    command = [
        "codex",
        "-a",
        "never",
        "exec",
        "--json",
        "--color",
        "never",
        "--model",
        run["model"],
        "-c",
        f'model_reasoning_effort="{run["effort"]}"',
        "--disable",
        "multi_agent",
        "--sandbox",
        "workspace-write" if manifest["write"] else "read-only",
        "--skip-git-repo-check",
        "--cd",
        str(workspace),
        "-o",
        str(raw / "final.md"),
        "-",
    ]
    run["command"] = command
    process = None
    stream_task = None
    outcome = None
    events_path = raw / "events.jsonl"
    try:
        with (raw / "stderr.log").open("w") as stderr, events_path.open("w") as events:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr,
                start_new_session=True,
                limit=16 * 1024 * 1024,
            )
            run["pid"] = process.pid
            process.stdin.write(manifest["execution_prompt"].encode())
            await process.stdin.drain()
            process.stdin.close()

            async def capture():
                async for line in process.stdout:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        # Diagnostics never enter the public event stream.
                        stderr.write(line.decode(errors="replace"))
                        continue

                    events.write(
                        json.dumps({"recorded_at": now(), "event": event}, ensure_ascii=False)
                        + "\n"
                    )
                    events.flush()

            stream_task = asyncio.create_task(capture())
            try:
                await asyncio.wait_for(asyncio.shield(stream_task), manifest["timeout_seconds"])
                await asyncio.wait_for(process.wait(), 10)
            finally:
                # Finish the reader while its files are still open, including on timeout/stop.
                await stop_process(process)
                if not stream_task.done():
                    stream_task.cancel()

                await asyncio.gather(stream_task, return_exceptions=True)

            run["exit_code"] = process.returncode
            if process.returncode:
                outcome = "failed"
                run["error"] = (
                    f"Codex exited with code {process.returncode}; see private stderr.log."
                )
    except TimeoutError:
        outcome = "timed_out"
        run["error"] = f"Time limit: {manifest['timeout_seconds']} seconds."
    except asyncio.CancelledError:
        outcome = "cancelled"
        run["error"] = "Run stopped."
    except (OSError, ValueError, RuntimeError) as error:
        outcome = "failed"
        run["error"] = str(error)
    finally:
        if process:
            await stop_process(process)

        if stream_task:
            if not stream_task.done():
                stream_task.cancel()

            await asyncio.gather(stream_task, return_exceptions=True)

        try:
            parsed = parse_events(events_path)
            for field in ("tokens", "timeline", "final_answer"):
                run[field] = parsed[field]

            if outcome == "failed" and parsed["error"]:
                run["error"] = parsed["error"]

            if not outcome:
                outcome = parsed["status"]
                run["error"] = parsed["error"]
        except (OSError, ValueError) as error:
            outcome = outcome or "failed"
            run["error"] = run.get("error") or f"Cannot read events: {error}"

        if (raw / "final.md").is_file():
            run["final_answer"] = (raw / "final.md").read_text()

        run["status"] = outcome
        run["duration_seconds"] = round(time.monotonic() - start, 3)
        run["finished_at"] = now()
        if manifest["write"]:
            run["patch"] = changed_files(root / "private" / "snapshot", workspace)

        save_manifest(root, manifest)
        print(f"{run['model']}: {run['status']} ({run['duration_seconds']:.1f}s)", flush=True)


async def run_worker(root):
    manifest = json.loads((root / "private" / "manifest.json").read_text())
    manifest["pid"] = os.getpid()
    manifest["status"] = "running"
    save_manifest(root, manifest)
    start = time.monotonic()
    group = asyncio.gather(*(execute_run(root, manifest, run) for run in manifest["runs"]))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, group.cancel)

    try:
        await group
    except asyncio.CancelledError:
        pass
    finally:
        manifest["status"] = (
            "completed"
            if all(run["status"] == "completed" for run in manifest["runs"])
            else "finished_with_errors"
        )
        manifest["wall_seconds"] = round(time.monotonic() - start, 3)
        manifest["finished_at"] = now()
        save_manifest(root, manifest)

    print(root / "public" / "index.html", flush=True)
    return 0 if manifest["status"] == "completed" else 1


def prepare_run(args):
    if not shutil.which("codex"):
        raise ValueError(
            "Codex CLI is missing; install and authenticate it before running benchmarks."
        )

    source = args.project.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Project is not a directory: {source}")

    if args.output and args.output.expanduser().resolve().is_relative_to(source):
        raise ValueError("Output must be outside the project being copied.")

    prompt = args.prompt or (args.prompt_file.read_text() if args.prompt_file else "")
    if not prompt.strip():
        raise ValueError("Provide --prompt or --prompt-file.")

    models = args.models or DEFAULT_MODELS
    if len(models) > 4 or len(set(models)) != len(models):
        raise ValueError("Choose 1–4 distinct model names.")

    if args.timeout <= 0:
        raise ValueError("Timeout must be positive.")

    root = create_output(args.output)
    if root.is_relative_to(source):
        raise ValueError("Temporary output is inside the source; specify --output outside it.")

    snapshot = root / "private" / "snapshot"
    excluded = []
    copy_snapshot(source, snapshot, excluded)
    replacements = [(str(source), "[project]"), (str(root), "[benchmark]")]
    inputs = []
    for supplied in args.input:
        supplied = supplied.expanduser().resolve()
        target = snapshot / "_benchmark_inputs" / supplied.name
        if target.exists() or not supplied.exists():
            raise ValueError(f"Missing or duplicate input: {supplied}")

        target.parent.mkdir(exist_ok=True)
        if supplied.is_dir():
            copy_snapshot(supplied, target, excluded)
        else:
            shutil.copy2(supplied, target)

        inputs.append(str(target.relative_to(snapshot)))
        replacements.append((str(supplied), f"[input]/{supplied.name}"))

    execution_prompt = prompt
    if inputs:
        execution_prompt += "\n\nProvided input files (relative to your workspace):\n" + "\n".join(
            inputs
        )

    execution_prompt += (
        "\n\nBenchmark conditions: solve independently in this workspace. Do not spawn other agents "
        "or inspect sibling benchmark runs. Do not publish results or perform external mutations. "
        "Do not ask follow-up questions; report any missing prerequisites in the final answer."
    )
    version = subprocess.run(
        ["codex", "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    manifest = {
        "created_at": now(),
        "status": "prepared",
        "prompt": prompt,
        "execution_prompt": execution_prompt,
        "project": str(source),
        "cli_version": version,
        "write": args.write,
        "timeout_seconds": args.timeout,
        "redact_paths": replacements,
        "excluded": excluded,
        "wall_seconds": None,
        "runs": [],
    }
    for index, model in enumerate(models):
        run = {
            "id": f"run-{index + 1}",
            "model": model,
            "effort": args.effort,
            "status": "pending",
            "tokens": tokens_from_usage({}),
            "timeline": [],
            "final_answer": "",
        }
        workspace = root / "private" / "workspaces" / run["id"]
        shutil.copytree(snapshot, workspace)
        manifest["runs"].append(run)

    save_manifest(root, manifest)
    print(f"Benchmark: {root}", flush=True)
    print(
        f"Models: {', '.join(models)}; effort: {args.effort}; timeout per model: {args.timeout}s",
        flush=True,
    )
    print(
        f"Copied project snapshot; excluded {len(excluded)} cache, credential or symlink paths.",
        flush=True,
    )
    return root


def start_background(root):
    with (root / "private" / "worker.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "_worker", str(root)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )

    print(f"Background worker PID: {process.pid}\nReport: {root / 'public' / 'index.html'}")


def import_logs(args):
    if not 1 <= len(args.logs) <= 4:
        raise ValueError("Import 1–4 logs at a time.")

    if args.models and len(args.models) != len(args.logs):
        raise ValueError("--models must name each imported log in the same order.")

    runs = []
    for index, path in enumerate(args.logs):
        run = parse_events(path.expanduser(), args.turn)
        if args.models:
            run["model"] = args.models[index]

        runs.append(run)

    prompt = args.prompt or next(
        (run["prompt"] for run in runs if run["prompt"]), "Prompt not recorded in these logs."
    )
    root = create_output(args.output)
    manifest = {
        "created_at": now(),
        "status": "imported",
        "prompt": prompt,
        "runs": runs,
        "wall_seconds": None,
        "redact_paths": [],
        "turn": args.turn,
    }
    save_manifest(root, manifest)
    print(root / "public" / "index.html")
    return 0


def status_or_stop(args):
    root = args.directory.expanduser().resolve()
    manifest = json.loads((root / "private" / "manifest.json").read_text())
    if args.command == "stop":
        pid = manifest.get("pid")
        if manifest["status"] != "running" or not pid:
            print("Worker is not running.")
            return 0

        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True
        ).stdout
        if (
            "_worker" not in command
            or str(root) not in command
            or str(Path(__file__).resolve()) not in command
        ):
            raise ValueError(
                "Recorded PID does not match this benchmark worker; refusing to signal it."
            )

        os.kill(pid, signal.SIGTERM)
        print("Stop requested; partial results will remain in the report.")
        return 0

    print(f"{manifest['status']}\n{root / 'public' / 'index.html'}")
    for run in manifest["runs"]:
        usage = run.get("tokens", {}).get("total")
        print(
            f"  {run['model']}: {run['status']}; tokens={usage if usage is not None else 'unknown'}"
        )

    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Start independent model runs from the same snapshot")
    prompt = run.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file", type=Path)
    run.add_argument("--project", type=Path, default=Path.cwd())
    run.add_argument(
        "--input",
        type=Path,
        action="append",
        default=[],
        help="Copy an additional input file or directory",
    )
    run.add_argument("--models", nargs="+", help="1–4 model IDs in display order")
    run.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], default="xhigh")
    run.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Seconds per model, including waiting (default: 1800)",
    )
    run.add_argument(
        "--write", action="store_true", help="Allow edits inside separate project copies"
    )
    run.add_argument(
        "--background", action="store_true", help="Detach the runner; inspect it with status/stop"
    )
    run.add_argument("--output", type=Path, help="New output directory outside the source project")
    imports = commands.add_parser(
        "import", help="Build a report from existing Codex exec or rollout JSONL"
    )
    imports.add_argument("logs", type=Path, nargs="+")
    imports.add_argument(
        "--turn", type=int, default=1, help="1-based turn to compare (default: first)"
    )
    imports.add_argument(
        "--models", nargs="+", help="Model labels when CLI logs lack model metadata"
    )
    imports.add_argument("--prompt", help="Public task description when logs lack the prompt")
    imports.add_argument("--output", type=Path)
    for action in ("status", "stop", "_worker"):
        commands.add_parser(
            action, help=argparse.SUPPRESS if action == "_worker" else action
        ).add_argument("directory", type=Path)

    args = parser.parse_args()
    try:
        if args.command == "run":
            root = prepare_run(args)
            if args.background:
                start_background(root)
                return 0

            return asyncio.run(run_worker(root))

        if args.command == "_worker":
            return asyncio.run(run_worker(args.directory))

        if args.command == "import":
            return import_logs(args)

        return status_or_stop(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
