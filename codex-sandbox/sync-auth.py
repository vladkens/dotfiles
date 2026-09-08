#!/usr/bin/env python3
"""Copy only the current ChatGPT access token into the gateway volume."""
import json
from pathlib import Path
import subprocess

credentials = json.loads((Path.home() / ".codex/auth.json").read_text())
tokens = credentials.get("tokens") or {}
if not tokens.get("access_token") or not tokens.get("account_id"):
    raise SystemExit("Sign in with ChatGPT on the host first: codex login")
payload = json.dumps({key: tokens[key] for key in ("access_token", "account_id")})
subprocess.run([
    "docker", "--context", "colima", "run", "--rm", "-i",
    "--mount", "type=volume,source=codex-dkr-auth,target=/auth",
    "--entrypoint", "sh", "codex-dkr-auth:local", "-c",
    "umask 077; cat > /auth/credentials.new && mv /auth/credentials.new /auth/credentials.json",
], input=payload, text=True, check=True)
