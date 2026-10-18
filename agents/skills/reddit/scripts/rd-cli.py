#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["curl-cffi>=0.16.3"]
# ///
"""Read Reddit listings, posts with comments, search results and rules as Markdown.

Examples (prefix commands with `uv run --script rd-cli.py`):
  auth
  feed --limit 50
  sub speechtech --sort top --time month --limit 50
  post https://www.reddit.com/r/rust/comments/abc123/title/ --limit 200
  search "wgpu" --sub rust --limit 10
  rules speechtech
  subs

Requests use the reddit.com session of a logged-in browser, read with `unjar`
(Chrome's default profile unless -b/-p choose another). macOS may ask to allow
Keychain access. The cookies stay in memory only. Without a session, or with
--rss, `sub` and `search` fall back to RSS: one request of at most 100 entries,
no scores or comment counts, and about one request per minute.

Read-only by construction: only GET requests, and only to an allowlist of
public subreddit listings, posts with comments, search, subreddit about and
rules, the account name (`auth`), its home feed (`feed`) and its subscribed
subreddits (`subs`). Inbox,
chat, messages, notifications, votes, saved or hidden items, settings and other
users' data are outside the allowlist and refused before any request.
"""

import argparse
import html
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

BASE = "https://www.reddit.com"
MAX_WAIT = 60  # seconds the CLI sleeps for a rate limit before giving up
ATOM = {"a": "http://www.w3.org/2005/Atom"}
SUB = r"[A-Za-z0-9_]{2,21}"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# Every request path must fully match one of these; anything else is refused.
ALLOWED = [
    re.compile(pattern)
    for pattern in (
        rf"/r/{SUB}/(hot|new|top|rising)/?\.(json|rss)",
        r"/(best|hot|new|top|rising)\.json",  # the account's home feed
        rf"(/r/{SUB})?/search\.(json|rss)",
        r"/comments/[a-z0-9]+\.json",
        rf"/r/{SUB}/about(/rules)?\.json",
        rf"/r/{SUB}/s/[A-Za-z0-9]+",  # share link, read only for its redirect target
        r"/api/me\.json",
        r"/subreddits/mine/subscriber\.json",
    )
]


# MARK: HTTP


def session_cookies(browser: str | None, profile: str | None) -> dict[str, str]:
    unjar = shutil.which("unjar")
    if not unjar:
        raise RuntimeError("unjar is not installed; see https://github.com/vladkens/unjar")

    options = [*(["-b", browser] if browser else []), *(["-p", profile] if profile else [])]
    result = subprocess.run(
        [unjar, "-f", "header", *options, "reddit.com"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        reason = result.stderr.strip().splitlines()[-1:] or [f"exit {result.returncode}"]
        raise RuntimeError(f"unjar could not read browser cookies: {reason[0][:200]}")

    cookies = dict(item.split("=", 1) for item in result.stdout.strip().split("; ") if "=" in item)
    return cookies if "reddit_session" in cookies else {}


class Reddit:
    def __init__(self, browser: str | None, profile: str | None, rss: bool):
        cookies = {} if rss else session_cookies(browser, profile)
        self.mode = "session" if cookies else "anonymous"
        # Reddit blocks anonymous requests with an impersonated Chrome TLS fingerprint, but
        # serves RSS to curl's own fingerprint with a browser user agent.
        self.client = (
            requests.Session(impersonate="chrome")
            if cookies
            else requests.Session(headers={"User-Agent": USER_AGENT})
        )
        self.not_before = 0.0
        for name, value in cookies.items():
            self.client.cookies.set(name, value, domain=".reddit.com")

    def request(self, path: str, redirect: bool = False, **params: Any) -> requests.Response:
        if not any(pattern.fullmatch(path) for pattern in ALLOWED):
            raise RuntimeError(f"Refused: {path} is outside the read-only allowlist")

        params = {key: value for key, value in params.items() if value is not None}
        for attempt in range(3):
            wait = self.not_before - time.monotonic()
            if wait > MAX_WAIT:
                raise RuntimeError(f"Reddit rate limit reached; retry in {wait:.0f} s")
            if wait > 0:
                print(f"rate limit: waiting {wait:.0f} s", file=sys.stderr)
                time.sleep(wait)

            rs = self.client.get(f"{BASE}{path}", params=params, timeout=30, allow_redirects=False)
            remaining = float(rs.headers.get("x-ratelimit-remaining") or 1)
            reset = float(rs.headers.get("x-ratelimit-reset") or 0)
            if remaining < 1:
                self.not_before = time.monotonic() + reset

            if rs.status_code == 429:
                delay = float(rs.headers.get("retry-after") or reset or MAX_WAIT)
                self.not_before = time.monotonic() + max(delay, 1)
                if attempt == 2 or delay > MAX_WAIT:
                    raise RuntimeError(f"Reddit rate limit (HTTP 429); retry in {delay:.0f} s")
                continue

            if rs.status_code == 200 or (redirect and 300 <= rs.status_code < 400):
                return rs
            if rs.status_code == 403 and b"blocked by network security" in rs.content:
                raise RuntimeError(
                    "Reddit blocks anonymous requests from this network; "
                    "log in to reddit.com in Chrome"
                )
            if 300 <= rs.status_code < 400:
                raise RuntimeError(f"Reddit redirected {path}: missing, banned or private?")
            if rs.status_code == 404:
                raise RuntimeError(f"Not found: {path}")

            reason = ""
            if rs.headers.get("content-type", "").startswith("application/json"):
                body = rs.json()
                reason = (
                    (body.get("reason") or body.get("message") or "")
                    if isinstance(body, dict)
                    else ""
                )

            raise RuntimeError(f"Reddit returned HTTP {rs.status_code} {reason}".rstrip())

        raise RuntimeError("Reddit request failed")

    def json(self, path: str, **params: Any) -> Any:
        return self.request(f"{path}.json", raw_json=1, **params).json()

    def listing(self, path: str, limit: int, **params: Any) -> tuple[list[dict], bool]:
        items: dict[str, dict] = {}
        after = None
        while len(items) < limit:
            page = self.json(path, limit=min(100, limit - len(items)), after=after, **params)
            data = page["data"]
            before = len(items)
            items.update((child["data"]["name"], child) for child in data["children"])
            after = data.get("after")
            if not after or len(items) == before:
                return list(items.values())[:limit], True

        return list(items.values())[:limit], False

    def rss(self, path: str, **params: Any) -> list[dict]:
        root = ET.fromstring(self.request(f"{path}.rss", **params).content)
        entries = []
        for entry in root.findall("a:entry", ATOM):
            category = entry.find("a:category", ATOM)
            link = entry.find("a:link", ATOM)
            entries.append(
                {
                    "title": entry.findtext("a:title", "", ATOM),
                    "author": entry.findtext("a:author/a:name", "", ATOM).removeprefix("/u/"),
                    "link": link.get("href", "") if link is not None else "",
                    "date": entry.findtext("a:published", "", ATOM)
                    or entry.findtext("a:updated", "", ATOM),
                    "sub": category.get("label", "") if category is not None else "",
                    "content": entry.findtext("a:content", "", ATOM),
                }
            )

        return entries


# MARK: Formatting


def clean(value: str) -> str:
    # Reddit text must not execute terminal escape sequences.
    return "".join(
        char
        for char in value
        if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159)
    )


def date(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%MZ")


def truncate(text: str, size: int) -> str:
    text = text.strip()
    return text if len(text) <= size else text[:size].rstrip() + " …"


def format_post(post: dict, text_size: int | None) -> str:
    meta = [
        f"r/{post['subreddit']}",
        f"u/{post['author']}",
        date(post["created_utc"]),
        f"score {post['score']}",
        f"{post['num_comments']} comments",
    ]
    if post.get("link_flair_text"):
        meta.append(f"flair: {post['link_flair_text']}")

    lines = [f"## {post['title']}", "", " · ".join(meta), f"{BASE}{post['permalink']}"]
    if not post.get("is_self") and post.get("url"):
        lines.append(f"Link: {post['url']}")

    text = post.get("selftext", "")
    if text_size is not None:
        text = truncate(text, text_size)

    if text:
        lines.extend(["", blockquote(text)])

    return clean("\n".join(lines))


def blockquote(text: str) -> str:
    # Quoted, so headings inside a post cannot break the output's own structure.
    return "\n".join(f"> {line}".rstrip() for line in text.strip().splitlines())


def format_comment(comment: dict, op: str, depth: int, limit: int, shown: list[int]) -> list[str]:
    pad = "  " * depth
    if comment["kind"] == "more":
        count = comment["data"].get("count", 0)
        return [f"{pad}- … {count} more replies not loaded"] if count else []

    if shown[0] >= limit:
        return []

    data = comment["data"]
    shown[0] += 1
    score = "score hidden" if data.get("score_hidden") else f"{data.get('score', 0)} points"
    tags = " (OP)" if data.get("author") == op else ""
    tags += " (mod)" if data.get("distinguished") == "moderator" else ""
    lines = [f"{pad}- u/{data.get('author')}{tags} · {date(data['created_utc'])} · {score}"]
    lines.extend(f"{pad}  {line}" if line else "" for line in data.get("body", "").splitlines())
    replies = data.get("replies")
    if isinstance(replies, dict):
        for reply in replies["data"]["children"]:
            lines.extend(format_comment(reply, op, depth + 1, limit, shown))

    return lines


def print_posts(header: str, items: list[dict], limit: int, ended: bool) -> None:
    stamps = [item["data"]["created_utc"] for item in items]
    span = f", created {date(min(stamps))} to {date(max(stamps))}" if stamps else ""
    end = "the listing ended" if ended else f"stopped at --limit {limit}"
    print(f"# {header}\n")
    print(f"Coverage: {len(items)} posts{span}; {end}.")
    for item in items:
        print("\n" + format_post(item["data"], 500))


def print_rss(header: str, entries: list[dict]) -> None:
    stamps = sorted(entry["date"][:16].replace("T", " ") + "Z" for entry in entries)
    span = f", published {stamps[0]} to {stamps[-1]}" if stamps else ""
    print(f"# {header}\n")
    print(
        f"Coverage: {len(entries)} posts{span} via RSS (one request, at most 100 entries; "
        "no scores or comment counts; Reddit allows about one RSS request per minute)."
    )
    for entry in entries:
        text = re.sub(r"</(p|h\d|li|pre|blockquote)>|<br\s*/?>", "\n", entry["content"])
        text = re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", "", text)))
        text = re.sub(r"\s*\n\s*", "\n", text).replace("[link] [comments]", "")
        text = re.sub(r"submitted by /u/\S+", "", text).strip()
        lines = [
            f"## {entry['title']}",
            "",
            f"{entry['sub']} · u/{entry['author']} · {entry['date'][:16].replace('T', ' ')}Z",
            entry["link"],
        ]
        if text:
            lines.extend(["", blockquote(truncate(text, 500))])

        print("\n" + clean("\n".join(lines)))


# MARK: Commands


def sub_name(value: str) -> str:
    value = value.strip().rstrip("/")
    if value.startswith(("https://", "http://")):
        value = urlsplit(value).path.rstrip("/")

    value = value.removeprefix("/").removeprefix("r/")
    if not re.fullmatch(SUB, value):
        raise argparse.ArgumentTypeError(f"invalid subreddit name: {value!r}")

    return value


def post_link(reddit: Reddit, value: str) -> tuple[str, str | None]:
    """Return the post ID and, for a comment permalink, the comment ID."""
    value = value.strip()
    if value.startswith(("https://", "http://", "www.", "old.", "reddit.com", "redd.it")):
        parts = urlsplit(value if "://" in value else f"https://{value}")
        path = parts.path.rstrip("/")
        if re.fullmatch(rf"/r/{SUB}/s/[A-Za-z0-9]+", path):
            # Share links redirect to the canonical comments URL.
            path = urlsplit(reddit.request(path, redirect=True).headers.get("location", "")).path

        match = re.search(r"/comments/([a-z0-9]+)(?:/[^/]+/([a-z0-9]+))?", path)
        if parts.hostname == "redd.it":
            match = re.fullmatch(r"/([a-z0-9]+)()", path)

        if not match:
            raise ValueError(f"Not a Reddit post link: {value}")

        return match.group(1), match.group(2) or None

    value = value.removeprefix("t3_")
    if not re.fullmatch(r"[a-z0-9]{4,10}", value):
        raise ValueError(f"Expected a post link or ID, got {value!r}")

    return value, None


def cmd_auth(reddit: Reddit, args: argparse.Namespace) -> None:
    if reddit.mode != "session":
        print("No Reddit session in the browser profile; log in to reddit.com there.")
        return

    me = reddit.json("/api/me")
    name = me.get("data", {}).get("name") if isinstance(me, dict) else None
    if not name:
        raise RuntimeError("The browser's Reddit session is expired or not logged in")

    print(f"Logged in as u/{name}")


def cmd_sub(reddit: Reddit, args: argparse.Namespace) -> None:
    params = {"t": args.time} if args.sort == "top" else {}
    header = f"r/{args.name} — {args.sort}" + (f" ({args.time})" if params else "")
    if reddit.mode != "session":
        entries = reddit.rss(f"/r/{args.name}/{args.sort}/", limit=min(args.limit, 100), **params)
        print_rss(header, entries)
        return

    items, ended = reddit.listing(f"/r/{args.name}/{args.sort}", args.limit, **params)
    print_posts(header, items, args.limit, ended)


def cmd_feed(reddit: Reddit, args: argparse.Namespace) -> None:
    if reddit.mode != "session":
        raise RuntimeError("`feed` needs a Reddit session; log in to reddit.com in the browser")

    params = {"t": args.time} if args.sort == "top" else {}
    header = f"Home feed — {args.sort}" + (f" ({args.time})" if params else "")
    items, ended = reddit.listing(f"/{args.sort}", args.limit, **params)
    print_posts(header, items, args.limit, ended)


def cmd_search(reddit: Reddit, args: argparse.Namespace) -> None:
    path = f"/r/{args.sub}/search" if args.sub else "/search"
    params = {"q": args.query, "sort": args.sort, "t": args.time, "type": "link"}
    if args.sub:
        params["restrict_sr"] = 1

    scope = f"r/{args.sub}" if args.sub else "all of Reddit"
    header = f"Search {args.query!r} in {scope} — {args.sort} ({args.time})"
    if reddit.mode != "session":
        print_rss(header, reddit.rss(path, limit=min(args.limit, 100), **params))
        return

    items, ended = reddit.listing(path, args.limit, **params)
    print_posts(header, items, args.limit, ended)


def cmd_post(reddit: Reddit, args: argparse.Namespace) -> None:
    post_id, comment_id = post_link(reddit, args.post)
    # A comment permalink narrows the tree to that comment, its replies and 3 parents.
    focus = {"comment": comment_id, "context": 3} if comment_id else {}
    page = reddit.json(f"/comments/{post_id}", limit=args.limit, depth=args.depth, **focus)
    post = page[0]["data"]["children"][0]["data"]
    shown = [0]
    lines = []
    for comment in page[1]["data"]["children"]:
        lines.extend(format_comment(comment, post["author"], 0, args.limit, shown))

    scope = f", only around comment {comment_id} with up to 3 parents" if comment_id else ""
    print(format_post(post, None).replace("## ", "# ", 1))
    print(
        f"\nCoverage: {shown[0]} comments shown of {post['num_comments']} reported{scope} "
        f"(--limit {args.limit}, --depth {args.depth}; the reported count includes "
        "removed comments).\n"
    )
    print(clean("\n".join(lines)) or "No comments.")


def cmd_rules(reddit: Reddit, args: argparse.Namespace) -> None:
    about = reddit.json(f"/r/{args.name}/about")["data"]
    rules = reddit.json(f"/r/{args.name}/about/rules").get("rules", [])
    lines = [
        f"# r/{about['display_name']} — {about.get('title', '')}",
        "",
        f"{about.get('subscribers', 0)} members · created {date(about['created_utc'])}"
        f" · type {about.get('subreddit_type')} · submissions {about.get('submission_type')}"
        + (" · NSFW" if about.get("over18") else ""),
        "",
        "## Description",
        "",
        about.get("public_description") or "(none)",
        "",
        "## Rules",
    ]
    for index, rule in enumerate(rules, 1):
        lines.extend(["", f"{index}. **{rule['short_name']}** (applies to {rule.get('kind')})"])
        if rule.get("description"):
            lines.extend(f"   {line}" if line else "" for line in rule["description"].splitlines())

    if not rules:
        lines.extend(["", "(no rules listed)"])

    lines.extend(["", "## Sidebar", "", about.get("description") or "(empty)"])
    print(clean("\n".join(lines)))


def cmd_subs(reddit: Reddit, args: argparse.Namespace) -> None:
    if reddit.mode != "session":
        raise RuntimeError("`subs` needs a Reddit session; log in to reddit.com in the browser")

    items, ended = reddit.listing("/subreddits/mine/subscriber", 1000)
    print(f"# Subscribed subreddits ({len(items)}{'' if ended else ', truncated at 1000'})\n")
    for item in sorted(items, key=lambda item: item["data"]["display_name"].casefold()):
        data = item["data"]
        about = truncate(data.get("public_description", "").replace("\n", " "), 160)
        print(clean(f"- r/{data['display_name']} ({data.get('subscribers', 0)} members) {about}"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-b", "--browser", help="Browser for unjar (default: chrome).")
    parser.add_argument("-p", "--profile", help="Browser profile for unjar (see `unjar list`).")
    parser.add_argument(
        "--rss", action="store_true", help="Skip the browser session; read listings from RSS."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth", help="Show whether a logged-in session works, and as whom.")
    commands.add_parser("subs", help="List the account's subscribed subreddits.")

    times = ["hour", "day", "week", "month", "year", "all"]
    sub = commands.add_parser("sub", help="List a subreddit's posts.")
    sub.add_argument("name", type=sub_name, help="Subreddit name, r/NAME or link.")
    sub.add_argument("--sort", choices=["hot", "new", "top", "rising"], default="hot")
    sub.add_argument("--time", choices=times, default="week", help="Window for --sort top.")
    sub.add_argument("--limit", type=int, default=25, help="Maximum posts (default: 25).")

    feed = commands.add_parser("feed", help="List posts from the account's home feed.")
    feed.add_argument("--sort", choices=["best", "hot", "new", "top", "rising"], default="new")
    feed.add_argument("--time", choices=times, default="week", help="Window for --sort top.")
    feed.add_argument("--limit", type=int, default=25, help="Maximum posts (default: 25).")

    post = commands.add_parser("post", help="Read a post with its comment tree.")
    post.add_argument("post", help="Post or comment link, redd.it or share link, or post ID.")
    post.add_argument("--limit", type=int, default=200, help="Maximum comments (max: 500).")
    post.add_argument("--depth", type=int, default=8, help="Maximum reply depth (default: 8).")

    search = commands.add_parser("search", help="Search posts, optionally in one subreddit.")
    search.add_argument("query")
    search.add_argument("--sub", type=sub_name, help="Restrict to one subreddit.")
    search.add_argument(
        "--sort", choices=["relevance", "top", "new", "comments"], default="relevance"
    )
    search.add_argument("--time", choices=times, default="all")
    search.add_argument("--limit", type=int, default=25, help="Maximum posts (default: 25).")

    rules = commands.add_parser("rules", help="Show a subreddit's description, rules and sidebar.")
    rules.add_argument("name", type=sub_name, help="Subreddit name, r/NAME or link.")

    args = parser.parse_args()
    if not 1 <= getattr(args, "limit", 1) <= (500 if args.command == "post" else 1000):
        parser.error("--limit must be between 1 and 1000 (500 for post)")
    if getattr(args, "depth", 1) < 1:
        parser.error("--depth must be positive")
    if args.command == "search" and not args.query.strip():
        parser.error("search query must not be empty")

    reddit = Reddit(args.browser, args.profile, args.rss)
    globals()[f"cmd_{args.command}"](reddit, args)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
    except (
        RuntimeError,
        ValueError,
        KeyError,
        OSError,
        ET.ParseError,
        subprocess.TimeoutExpired,
        RequestException,
    ) as error:
        raise SystemExit(f"Error: {error}") from None
