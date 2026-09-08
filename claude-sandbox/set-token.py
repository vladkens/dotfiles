#!/usr/bin/env python3
"""Store a Claude setup-token in the auth-only Docker volume."""

import getpass
from pathlib import Path
import subprocess


def store_token(token):
    if not token or any(char.isspace() for char in token):
        raise ValueError("Expected a nonempty token without whitespace")
    subprocess.run(
        ["docker", "--context", "colima", "build", "-t", "claude-dkr-auth:local",
         str(Path(__file__).parent / "auth")], check=True,
    )
    subprocess.run(
        ["docker", "--context", "colima", "run", "--rm", "-i",
         "--mount", "type=volume,source=claude-dkr-auth,target=/auth",
         "--entrypoint", "sh", "claude-dkr-auth:local", "-c",
         "umask 077; cat > /auth/token.new && mv /auth/token.new /auth/token"],
        input=token, text=True, check=True,
    )


if __name__ == "__main__":
    store_token(getpass.getpass("Claude token (from claude setup-token): "))
    print("Claude token saved. All projects use it through the auth container.")
