import subprocess
from collections.abc import Mapping
from pathlib import Path


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    input: str | None = None,
    capture: bool = False,
    check: bool = True,
    stdout: int | None = None,
    stderr: int | None = None,
    error: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input,
            capture_output=capture,
            text=True,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    except FileNotFoundError:
        raise SystemExit(f"{command[0]} is required") from None

    if check and result.returncode != 0:
        message = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise SystemExit(message or error or f"{command[0]} failed")

    return result


def output(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    error: str | None = None,
) -> str:
    result = run(command, cwd=cwd, capture=True, check=check, error=error)
    return result.stdout.strip()
