#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["telethon==1.45.0", "rich>=13.9.4"]
# ///
"""Read Telegram channels and post comments from a single-file CLI.

Examples (prefix commands with `uv run --script tg-cli.py`):
  auth status
  feed --json                         Posts from subscriptions in the last 24 hours.
  feed --since 2026-10-01 --json        Posts from subscriptions since a given date.
  channel list --json
  channel view @channel
  message list @channel --since 2026-10-01 --until 2026-10-04 --json
  message search @channel "release" --json
  message view https://t.me/channel/123
  comment list https://t.me/channel/123 --json

Private channels accept their -100… ID from `channel list` or a t.me/c/… link.
Dates use UTC; --since is inclusive and --until is exclusive. Results are newest
first. Pass next_before as --before to continue the same query without overlap.
Every command reads the existing authorization from native Telegram for macOS
and uses it in memory. No login flow, session files or stored cursors are created.
If there is no active local session, the command fails with a clear error.
`feed` includes public and private subscriptions, including archived channels.
Its --limit applies per channel; truncated pages include next_before for use
with `message list CHANNEL --before ID` and the same --since/--until window.
New means published in the selected period, independent of read/unread status.

Privacy boundary: only broadcast channels and comments attached to their posts
are readable. DMs, Saved Messages, bots, standalone groups and channel inboxes
are rejected. Commands never send messages, join chats, or mark messages read.
Telegram's dialog listing includes private previews; these stay in memory and
are neither printed nor saved to disk. Authorization is kept only in memory.
The session itself still carries the account's full Telegram permissions.
"""

import argparse
import asyncio
import base64
import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NotRequired, TypedDict, TypeGuard
from urllib.parse import urlsplit

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from telethon import TelegramClient, errors, functions, types, utils
from telethon.crypto import AuthKey
from telethon.sessions import MemorySession

# The native macOS application profile, as used by the original tg-session.py.
API_ID = 2834
API_HASH = "68875f756c9b437a8b916ca3de215815"
MACOS_DATA = (
    Path.home()
    / "Library/Group Containers/6N38VWS5BX.ru.keepcoder.Telegram/stable/accounts-shared-data"
)


class CLIError(Exception):
    """An error safe to show without including Telegram response objects."""


class ChannelInfo(TypedDict):
    id: int
    title: str
    username: str | None
    link: str | None


class Author(TypedDict):
    id: int
    name: str
    username: str | None


class Message(TypedDict):
    id: int
    channel_id: int
    date: str
    text: str
    link: str
    author: Author | None
    signature: str | None
    reply_to_id: int | None
    views: int | None
    comments: int
    media_type: str | None
    album_id: int | None


class Page(TypedDict):
    channel: ChannelInfo
    messages: list[Message]
    has_more: bool
    next_before: int | None
    post_id: NotRequired[int]


class Feed(TypedDict):
    since: str
    until: str
    channels_checked: int
    complete: bool
    feed: list[Page]


def positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a positive integer") from None

    if result < 1:
        raise argparse.ArgumentTypeError("expected a positive integer")

    return result


def utc_date(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD or an ISO 8601 timestamp") from None

    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def parse_target(value: str) -> tuple[str | int, int | None]:
    value = value.strip()
    message_id = None
    if value.startswith(("https://", "http://", "t.me/")):
        parsed = urlsplit(value if "://" in value else f"https://{value}")
        if parsed.netloc != "t.me" or parsed.fragment or parsed.query not in ("", "single"):
            raise CLIError("Use a plain t.me channel or post link.")

        parts = parsed.path.strip("/").split("/")
        if parts[0] == "s":
            parts = parts[1:]

        if parts and parts[0] == "c":
            if len(parts) not in (2, 3) or not parts[1].isdigit() or int(parts[1]) < 1:
                raise CLIError("Invalid private channel link.")

            value = str(utils.get_peer_id(types.PeerChannel(int(parts[1]))))
            parts = [value, *parts[2:]]

        if len(parts) not in (1, 2) or not parts[0]:
            raise CLIError("Use a channel link or a link to a single post.")

        if len(parts) == 2:
            if not parts[1].isdigit() or int(parts[1]) < 1:
                raise CLIError("Invalid post ID in link.")

            message_id = int(parts[1])

        value = parts[0]

    if re.fullmatch(r"-?\d+", value):
        peer_id, peer_type = utils.resolve_id(int(value))
        if peer_type is not types.PeerChannel or peer_id < 1:
            raise CLIError("Only channel IDs are allowed; use the -100… ID from `channel list`.")

        return int(value), message_id

    username = value.removeprefix("@")
    if username.casefold() in ("me", "self") or not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9_]{0,31}", username
    ):
        raise CLIError("Only channel usernames, channel IDs and t.me channel links are allowed.")

    return username, message_id


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    groups = parser.add_subparsers(dest="group", required=True)
    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="Print structured JSON to stdout.")

    auth = groups.add_parser("auth", help="Check the local Telegram session.").add_subparsers(
        dest="command", required=True
    )
    auth.add_parser(
        "status", parents=[output], help="Check authorization without displaying account details."
    )
    feed = groups.add_parser(
        "feed", parents=[output], help="Read recent posts from subscriptions (default: last 24h)."
    )
    feed.set_defaults(command="list", before=None)

    channels = groups.add_parser(
        "channel", help="List or inspect broadcast channels."
    ).add_subparsers(dest="command", required=True)
    channels.add_parser(
        "list",
        parents=[output],
        help="List subscribed public and private channels, including archived ones.",
    )
    channel_view = channels.add_parser(
        "view", parents=[output], help="Show a channel's description and metadata."
    )
    channel_view.add_argument("target", help="Channel username, -100… ID, or t.me link.")

    messages = groups.add_parser("message", help="Read or search channel posts.").add_subparsers(
        dest="command", required=True
    )
    message_list = messages.add_parser(
        "list", parents=[output], help="Read channel history, newest first."
    )
    message_search = messages.add_parser(
        "search", parents=[output], help="Search within one channel, newest first."
    )
    message_view = messages.add_parser(
        "view", parents=[output], help="Read a post by link or channel and message ID."
    )
    comments = groups.add_parser(
        "comment", help="Read comments attached to a channel post."
    ).add_subparsers(dest="command", required=True)
    comment_list = comments.add_parser(
        "list", parents=[output], help="Read a post's discussion thread, newest first."
    )

    for command in (message_list, message_search, message_view, comment_list):
        command.add_argument("target", help="Channel username, -100… ID, or t.me link.")

    message_search.add_argument("query", help="Telegram text search query within this channel.")
    for command in (message_view, comment_list):
        command.add_argument(
            "message_id", nargs="?", type=positive_int, help="Post ID, unless included in the link."
        )

    for command in (message_list, message_search, comment_list):
        command.add_argument(
            "--before", type=positive_int, help="Exclusive message ID cursor from next_before."
        )

    for command in (message_list, message_search, comment_list, feed):
        command.add_argument(
            "--limit",
            type=positive_int,
            default=50,
            help="Maximum results per channel/page (default: 50; max: 1000).",
        )
        command.add_argument(
            "--since", type=utc_date, help="Inclusive start date/time (UTC by default)."
        )
        command.add_argument(
            "--until", type=utc_date, help="Exclusive end date/time (UTC by default)."
        )

    args = parser.parse_args(argv)
    if args.group == "feed":
        args.until = args.until or datetime.now(UTC)
        args.since = args.since or args.until - timedelta(days=1)

    if getattr(args, "limit", 0) > 1000:
        parser.error("--limit must not exceed 1000; use `message list --before` to paginate")

    if getattr(args, "since", None) and args.until and args.since >= args.until:
        parser.error("--since must be earlier than --until")

    if getattr(args, "query", None) is not None and not args.query.strip():
        parser.error("search query must not be empty")

    if not hasattr(args, "target"):
        return args

    try:
        args.selector, linked_id = parse_target(args.target)
        if hasattr(args, "message_id"):
            if linked_id and args.message_id and linked_id != args.message_id:
                raise CLIError("The post link and message ID refer to different posts.")

            args.message_id = args.message_id or linked_id
            if not args.message_id:
                raise CLIError("Provide a post link or a channel and message ID.")
        elif args.group == "message" and linked_id:
            raise CLIError("Use a channel as the target, or `message view` for a post link.")
    except CLIError as error:
        parser.error(str(error))

    return args


def is_broadcast(entity: object) -> TypeGuard[types.Channel]:
    return (
        isinstance(entity, types.Channel)
        and bool(entity.broadcast)
        and not entity.megagroup
        and not entity.gigagroup
        and not entity.monoforum
    )


def require_broadcast(entity: object) -> types.Channel:
    if not is_broadcast(entity):
        raise CLIError(
            "Access denied: only broadcast channels and their post comments are allowed."
        )

    return entity


def serialize_channel(channel: types.Channel) -> ChannelInfo:
    require_broadcast(channel)
    return {
        "id": utils.get_peer_id(channel),
        "title": channel.title,
        "username": channel.username,
        "link": f"https://t.me/{channel.username}" if channel.username else None,
    }


async def list_channels(
    client: TelegramClient, since: datetime | None = None
) -> list[types.Channel]:
    # getDialogs necessarily returns mixed previews. Never expose its messages,
    # drafts, users or raw objects, and never persist the client's entity cache.
    channels = []
    async for dialog in client.iter_dialogs(ignore_migrated=True):
        channel = dialog.entity
        if not is_broadcast(channel) or channel.left:
            continue

        if since and dialog.date and dialog.date < since:
            continue

        channels.append(channel)

    return sorted(channels, key=lambda channel: (channel.title.casefold(), channel.id))


async def resolve_channel(client: TelegramClient, selector: str | int) -> types.Channel:
    if isinstance(selector, int):
        for channel in await list_channels(client):
            if utils.get_peer_id(channel) == selector:
                return require_broadcast(channel)

        raise CLIError("Channel ID not found among subscribed channels. Use `channel list`.")

    resolved = await client(functions.contacts.ResolveUsernameRequest(selector))
    if not isinstance(resolved.peer, types.PeerChannel):
        raise CLIError("Access denied: this username does not identify a broadcast channel.")

    for channel in resolved.chats:
        if channel.id == resolved.peer.channel_id:
            return require_broadcast(channel)

    raise CLIError("Telegram did not return the requested channel.")


def get_channel_peer(channel: types.Channel) -> types.InputPeerChannel:
    require_broadcast(channel)
    return utils.get_input_peer(channel)


def require_message_peer(message: object, channel_id: int) -> None:
    peer = getattr(message, "peer_id", None)
    if not isinstance(peer, types.PeerChannel) or peer.channel_id != channel_id:
        raise CLIError(
            "Access denied: Telegram returned a message outside the requested channel or thread."
        )


def serialize_message(message: types.Message, channel_id: int, username: str | None) -> Message:
    require_message_peer(message, channel_id)
    base = f"https://t.me/{username}" if username else f"https://t.me/c/{channel_id}"
    sender = message.sender
    author: Author | None = None
    if isinstance(sender, types.User):
        author = {
            "id": sender.id,
            "name": utils.get_display_name(sender),
            "username": sender.username,
        }
    elif isinstance(sender, types.Channel):
        author = {
            "id": utils.get_peer_id(sender),
            "name": sender.title,
            "username": sender.username,
        }

    return {
        "id": message.id,
        "channel_id": utils.get_peer_id(types.PeerChannel(channel_id)),
        "date": message.date.astimezone(UTC).isoformat(),
        "text": message.message or "",
        "link": f"{base}/{message.id}",
        "author": author,
        "signature": message.post_author,
        "reply_to_id": message.reply_to.reply_to_msg_id if message.reply_to else None,
        "views": message.views,
        "comments": message.replies.replies if message.replies and message.replies.comments else 0,
        "media_type": type(message.media).__name__ if message.media else None,
        "album_id": message.grouped_id,
    }


async def get_post(
    client: TelegramClient, channel: types.Channel, message_id: int
) -> types.Message:
    message = await client.get_messages(get_channel_peer(channel), ids=message_id)
    if message is None or isinstance(message, types.MessageEmpty):
        raise CLIError("Post not found or not accessible.")

    require_message_peer(message, channel.id)
    if not isinstance(message, types.Message):
        raise CLIError("This ID refers to a service event, not a channel post.")

    if message.id != message_id:
        raise CLIError("Telegram returned a different post than requested.")

    return message


async def get_discussion_root(
    client: TelegramClient, channel: types.Channel, post: types.Message
) -> int:
    discussion = await client(
        functions.messages.GetDiscussionMessageRequest(get_channel_peer(channel), post.id)
    )
    for message in discussion.messages:
        forwarded = getattr(message, "fwd_from", None)
        if (
            isinstance(message, types.Message)
            and isinstance(message.peer_id, types.PeerChannel)
            and message.peer_id.channel_id == post.replies.channel_id
            and forwarded
            and isinstance(forwarded.from_id, types.PeerChannel)
            and forwarded.from_id.channel_id == channel.id
            and forwarded.channel_post == post.id
        ):
            return message.id

    raise CLIError("Could not verify the discussion thread attached to this post.")


async def fetch_messages(
    client: TelegramClient,
    channel: types.Channel,
    *,
    limit: int = 50,
    before: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    query: str | None = None,
    post_id: int | None = None,
) -> Page:
    peer = get_channel_peer(channel)
    expected_id, username = channel.id, channel.username
    reply_to = None
    thread_id = None
    if post_id is not None:
        post = await get_post(client, channel, post_id)
        if not post.replies or not post.replies.comments or not post.replies.channel_id:
            return {
                "channel": serialize_channel(channel),
                "post_id": post_id,
                "messages": [],
                "has_more": False,
                "next_before": None,
            }

        expected_id, username = post.replies.channel_id, None
        reply_to = post.id
        thread_id = await get_discussion_root(client, channel, post)

    messages: list[Message] = []
    async for message in client.iter_messages(
        peer,
        limit=None,
        offset_id=before or 0,
        offset_date=until,
        search=query,
        reply_to=reply_to,
    ):
        require_message_peer(message, expected_id)
        if not isinstance(message, types.Message):
            continue

        if thread_id:
            reply = message.reply_to
            if not reply or (reply.reply_to_top_id or reply.reply_to_msg_id) != thread_id:
                raise CLIError("Access denied: a comment belongs to a different discussion thread.")

        if since and message.date < since:
            break

        if until and message.date >= until:
            continue

        messages.append(serialize_message(message, expected_id, username))
        if len(messages) > limit:
            break

    has_more = len(messages) > limit
    messages = messages[:limit]
    page: Page = {
        "channel": serialize_channel(channel),
        "messages": messages,
        "has_more": has_more,
        "next_before": messages[-1]["id"] if has_more else None,
    }
    if reply_to:
        page["post_id"] = reply_to

    return page


async def fetch_feed(
    client: TelegramClient, *, since: datetime, until: datetime, limit: int = 50
) -> Feed:
    channels = await list_channels(client, since=since)
    pages: list[Page] = []
    for channel in channels:
        page = await fetch_messages(client, channel, since=since, until=until, limit=limit)
        if page["messages"]:
            pages.append(page)

    pages.sort(key=lambda page: page["messages"][0]["date"], reverse=True)
    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "channels_checked": len(channels),
        "complete": not any(page["has_more"] for page in pages),
        "feed": pages,
    }


def make_client(session: MemorySession) -> TelegramClient:
    return TelegramClient(
        session,
        API_ID,
        API_HASH,
        device_model="MacBook Pro",
        system_version="macOS",
        app_version="12.10",
        receive_updates=False,
        flood_sleep_threshold=0,
        request_retries=1,
        connection_retries=2,
    )


def read_macos_auth() -> tuple[int, bytes]:
    try:
        data = json.loads(MACOS_DATA.read_bytes())
    except FileNotFoundError:
        raise CLIError("No active session found in local Telegram for macOS.") from None
    except (OSError, ValueError):
        raise CLIError("Could not read local Telegram for macOS authorization.") from None

    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        raise CLIError("Unsupported Telegram for macOS account format.")

    if not accounts:
        raise CLIError("No active session found in local Telegram for macOS.")

    if len(accounts) != 1:
        raise CLIError("Several local Telegram accounts found; cannot determine the active one.")

    account = accounts[0]
    if not isinstance(account, dict) or account.get("isTestingEnvironment") is not False:
        raise CLIError("Expected a production Telegram account.")

    dc_id, datacenters = account.get("primaryId"), account.get("datacenters")
    if not isinstance(dc_id, int) or not isinstance(datacenters, list) or len(datacenters) % 2:
        raise CLIError("Unsupported Telegram for macOS account format.")

    key = None
    try:
        for index in range(0, len(datacenters), 2):
            if datacenters[index] == dc_id:
                key = base64.b64decode(datacenters[index + 1]["masterKey"]["data"], validate=True)
                break
    except (KeyError, TypeError, ValueError):
        raise CLIError("Telegram account authorization key is missing or invalid.") from None
    if key is None or len(key) != 256:
        raise CLIError("Telegram account authorization key is missing or invalid.")

    return dc_id, key


async def load_session() -> MemorySession:
    dc_id, key = read_macos_auth()
    client = make_client(MemorySession())
    try:
        await client.connect()
        config = await client(functions.help.GetConfigRequest())
    finally:
        await client.disconnect()

    endpoints = [
        item
        for item in config.dc_options
        if item.id == dc_id and not (item.ipv6 or item.media_only or item.tcpo_only or item.cdn)
    ]
    if not endpoints:
        raise CLIError("Telegram did not return a usable data center endpoint.")

    endpoint = next((item for item in endpoints if item.static), endpoints[0])
    session = MemorySession()
    session.set_dc(dc_id, endpoint.ip_address, endpoint.port)
    session.auth_key = AuthKey(key)
    return session


def sanitize_text(value: str) -> str:
    # Channel text must not execute terminal escape sequences.
    return "".join(
        char
        for char in value
        if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159)
    )


def print_channels(channels: list[ChannelInfo]) -> None:
    table = Table(
        title=f"Subscribed channels ({len(channels)})",
        title_justify="left",
        box=box.SIMPLE,
        header_style="bold",
    )
    table.add_column("Channel")
    table.add_column("Username", style="cyan", no_wrap=True)
    table.add_column("ID", style="dim", justify="right", no_wrap=True)
    for channel in channels:
        username = (
            Text("@" + channel["username"], style=f"link https://t.me/{channel['username']}")
            if channel["username"]
            else Text("No username", style="dim")
        )
        table.add_row(Text(sanitize_text(channel["title"])), username, str(channel["id"]))

    Console().print(table)


def print_result(result: Mapping[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if "authorized" in result:
        print(f"Authorized\nSource: {result['source']}\nCLI scope: {result['scope']}")
        return

    if "feed" in result:
        print(f"Subscription posts: {result['since']} to {result['until']}")
        for page in result["feed"]:
            print()
            print_result(page, False)

        if not result["feed"]:
            print("No posts found in this period.")

        return

    if "channels" in result:
        print_channels(result["channels"])
        return

    channel = result["channel"]
    print(sanitize_text(f"{channel['title']} ({channel['id']})"))
    if "description" in channel:
        print(sanitize_text(channel["description"] or ""))
        print(f"Subscribers: {channel['subscribers']}")
        return

    messages = [result["message"]] if "message" in result else result["messages"]
    for message in messages:
        print(f"\n{message['date']} | {message['link']}")
        if message["author"]:
            print(sanitize_text(message["author"]["name"]))

        print(sanitize_text(message["text"]))
        if message["media_type"]:
            print(f"[{message['media_type']}]")

    if not messages:
        print("No messages found.")

    if result.get("has_more"):
        print(f"\nMore results: repeat with --before {result['next_before']}")


async def run_command(args: argparse.Namespace) -> Mapping[str, Any]:
    session = await load_session()
    client = make_client(session)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise CLIError("No active session found in local Telegram for macOS.")

        if args.group == "auth":
            return {
                "authorized": True,
                "source": "Telegram for macOS",
                "scope": "channels-and-post-comments",
            }

        if args.group == "feed":
            return await fetch_feed(client, since=args.since, until=args.until, limit=args.limit)

        if args.group == "channel" and args.command == "list":
            return {
                "channels": [serialize_channel(channel) for channel in await list_channels(client)]
            }

        channel = await resolve_channel(client, args.selector)
        if args.group == "channel":
            full = await client(functions.channels.GetFullChannelRequest(get_channel_peer(channel)))
            return {
                "channel": {
                    **serialize_channel(channel),
                    "description": full.full_chat.about,
                    "subscribers": full.full_chat.participants_count,
                }
            }

        if args.group == "message" and args.command == "view":
            post = await get_post(client, channel, args.message_id)
            return {
                "channel": serialize_channel(channel),
                "message": serialize_message(post, channel.id, channel.username),
            }

        return await fetch_messages(
            client,
            channel,
            limit=args.limit,
            before=args.before,
            since=args.since,
            until=args.until,
            query=args.query if args.command == "search" else None,
            post_id=args.message_id if args.group == "comment" else None,
        )
    finally:
        await client.disconnect()


def main() -> int:
    args = parse_args()
    # Library error logs may contain raw Telegram objects. Emit only our own errors.
    logging.getLogger("telethon").setLevel(logging.CRITICAL + 1)
    try:
        result = asyncio.run(run_command(args))
        print_result(result, args.json)
        return 0
    except errors.FloodWaitError as error:
        message, code = f"Telegram rate limit: retry in {error.seconds} seconds.", 3
    except CLIError as error:
        message, code = str(error), 1
    except errors.RPCError as error:
        message, code = f"Telegram request failed ({type(error).__name__}).", 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 130
    except BrokenPipeError:
        return 0
    except Exception as error:
        # No traceback or raw exception text: either can contain private API data.
        message, code = f"Operation failed ({type(error).__name__}).", 1

    if args.json:
        print(json.dumps({"error": message, "exit_code": code}), file=sys.stderr)
    else:
        print(f"Error: {message}", file=sys.stderr)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
