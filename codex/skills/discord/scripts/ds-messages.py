#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["cryptography>=50.0.1", "curl-cffi>=0.16.3"]
# ///
"""Read Discord messages, newest first, without restarting the client.

Examples (prefix commands with `uv run --script ds-messages.py`):
  get https://discord.com/channels/123/456 --limit 100
  auth

Reads the local Discord profile and its macOS Keychain encryption password.
Authorization stays in memory. macOS may ask to allow Keychain access.
Message links select their channel, not the individual linked message.
"""

import argparse
import base64
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

PROFILE = Path.home() / "Library/Application Support/discord/Local Storage/leveldb"
ENCRYPTED = re.compile(rb"dQw4w9WgXcQ:([A-Za-z0-9+/=]+)")
TOKEN = re.compile(r"[\w-]{24,}\.[\w-]{6,}\.[\w-]{27,}|mfa\.[\w-]{40,}")
API = "https://discord.com/api/v10"


def decrypt_token(encoded: bytes, key: bytes) -> str:
    data = base64.b64decode(encoded, validate=True)
    if not data.startswith(b"v10"):
        raise ValueError("Unsupported encryption version")

    decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
    data = decryptor.update(data[3:]) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(data) + unpadder.finalize()).decode()


def local_tokens() -> list[str]:
    if sys.platform != "darwin" or not PROFILE.is_dir():
        raise RuntimeError("Expected an authorized Discord.app profile on macOS")

    encrypted: set[bytes] = set()
    for path in PROFILE.iterdir():
        if path.suffix in {".ldb", ".log"}:
            encrypted.update(ENCRYPTED.findall(path.read_bytes()))

    if not encrypted:
        raise RuntimeError("No encrypted session found in Discord Local Storage")

    result = subprocess.run(
        ["security", "find-generic-password", "-s", "discord Safe Storage", "-w"],
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(
            f"Cannot read discord Safe Storage (exit {result.returncode}); "
            "allow access in macOS Keychain"
        )

    # Electron's macOS v10 format uses Chromium's PBKDF2 and AES-CBC scheme.
    key = hashlib.pbkdf2_hmac("sha1", result.stdout.rstrip(b"\n"), b"saltysalt", 1003, 16)
    tokens: set[str] = set()
    for encoded in encrypted:
        try:
            token = decrypt_token(encoded, key)
        except (ValueError, UnicodeError):
            continue

        if TOKEN.fullmatch(token):
            tokens.add(token)

    if not tokens:
        raise RuntimeError("Cannot decrypt a Discord session with the current storage format")
    if len(tokens) > 10:
        raise RuntimeError("Too many stored sessions; refusing to probe historical accounts")

    return sorted(tokens)


def api_get(client: requests.Session, path: str, **params: Any) -> Any:
    for attempt in range(4):
        response = client.get(f"{API}{path}", params=params, timeout=20, allow_redirects=False)
        if response.status_code == 429:
            delay = float(response.json().get("retry_after", 1))
            if attempt == 3 or not 0 <= delay <= 30:
                raise RuntimeError("Discord rate limit reached; try again later")

            time.sleep(delay)
            continue

        if response.status_code == 401:
            return None
        if response.status_code == 403:
            raise RuntimeError("The account cannot read this channel")
        if response.status_code != 200:
            raise RuntimeError(f"Discord returned HTTP {response.status_code}")

        return response.json()

    raise RuntimeError("Discord request failed")


def authorize(client: requests.Session) -> None:
    valid: list[str] = []
    for token in local_tokens():
        client.headers["Authorization"] = token
        user = api_get(client, "/users/@me")
        if isinstance(user, dict) and user.get("id"):
            valid.append(token)

    if len(valid) != 1:
        raise RuntimeError(f"Expected one valid local Discord session, found {len(valid)}")

    client.headers["Authorization"] = valid[0]


def channel_ids(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    match = re.fullmatch(r"/channels/(@me|\d+)/(\d+)(?:/\d+)?/?", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "discord.com" or not match:
        raise ValueError("Expected https://discord.com/channels/SERVER/CHANNEL")

    return match.group(1), match.group(2)


def author(message: dict) -> str:
    user = message.get("author", {})
    return user.get("global_name") or user.get("username") or "unknown"


def format_message(message: dict, guild: str, channel: str) -> str:
    link = f"https://discord.com/channels/{guild}/{channel}/{message['id']}"
    lines = [f"## {message.get('timestamp', '')} — {author(message)}", "", f"[Message]({link})"]
    reference = message.get("referenced_message")
    if reference:
        lines.extend(["", f"> Reply to {author(reference)}"])
        lines.extend(f"> {line}" for line in reference.get("content", "").splitlines())

    if message.get("content"):
        lines.extend(["", message["content"]])

    for embed in message.get("embeds", []):
        for field in ("title", "description", "url"):
            if embed.get(field):
                lines.extend(["", str(embed[field])])

        for field in embed.get("fields", []):
            lines.extend(["", f"{field.get('name', '')}: {field.get('value', '')}"])

    for attachment in message.get("attachments", []):
        lines.extend(["", f"[{attachment.get('filename', 'Attachment')}]({attachment['url']})"])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Check authorization from the local Discord session")
    get = commands.add_parser("get", help="Print recent messages as Markdown, newest first")
    get.add_argument("url")
    get.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    guild, channel = "", ""
    if args.command == "get":
        guild, channel = channel_ids(args.url)
        if args.limit < 1:
            parser.error("--limit must be positive")

    with requests.Session(impersonate="chrome") as client:
        authorize(client)
        if args.command == "auth":
            print("authorization: verified from local Discord storage")
            return

        messages: dict[str, dict] = {}
        before = None
        while len(messages) < args.limit:
            params: dict[str, str | int] = {"limit": min(100, args.limit - len(messages))}
            if before:
                params["before"] = before

            page = api_get(client, f"/channels/{channel}/messages", **params)
            if not isinstance(page, list):
                raise TypeError("Discord session expired or messages response is invalid")
            if not page:
                break

            previous_count = len(messages)
            messages.update((item["id"], item) for item in page)
            if len(messages) == previous_count:
                raise RuntimeError("Discord pagination made no progress")

            before = str(min(int(item["id"]) for item in page))

        print(f"# Discord channel {channel}")
        for message in sorted(messages.values(), key=lambda item: int(item["id"]), reverse=True):
            print("\n" + format_message(message, guild, channel))

        print(f"messages: {len(messages)}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (
        RuntimeError,
        ValueError,
        OSError,
        subprocess.TimeoutExpired,
        RequestException,
        TypeError,
    ) as error:
        raise SystemExit(str(error)) from None
