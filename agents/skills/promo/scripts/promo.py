#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Plan and log social publications across projects and enforce per-channel posting rules.

Examples (prefix commands with `uv run --script promo.py`):
  add wavo x 2026-11-04 "Wavo 0.1 demo video" --draft wavo/launch-post.md
  add wavo slack today "reply to Matan in the thread" --reply --link URL
  edit k3f9 --date 2026-11-05
  done k3f9 --link https://x.com/uid127/status/123
  drop k3f9
  list --project wavo --all
  show --project wavo
  check

Data lives in the private notes repo (PROMO_DIR overrides it, for tests):
  promo.jsonl           one item per line, sorted by date then id
  promo-channels.toml   projects (GitHub repo for stars) and channels with their rules

`add` and `edit` refuse a post that breaks a channel rule and print the rule and the first
allowed date; --force adds it anyway. Replies and comments (--reply) are logged but never
count toward or break a rule. `check` is for the SessionStart hook: no network, silent when
nothing is due, never fails.
"""

import argparse
import contextlib
import fcntl
import json
import os
import random
import subprocess
import sys
import tempfile
import tomllib
from datetime import date, timedelta
from pathlib import Path

DIR = Path(os.environ.get("PROMO_DIR", Path.home() / "Code" / "notes"))
DATA = DIR / "promo.jsonl"
CHANNELS = DIR / "promo-channels.toml"
LOCK = DIR / ".promo.lock"

STATUSES = ("planned", "done", "dropped", "check")
FIELDS = ("id", "date", "project", "channel", "status", "reply", "what", "draft", "link", "note")
FIELDS += ("stars_before", "stars_after")
REQUIRED = {"id", "date", "project", "channel", "status", "what"}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
OVERDUE_DAYS = 3  # planned items older than this become status check
RECENT_DAYS = 14  # `list` shows this many past days by default
WHAT_WIDTH = 60


class Fail(Exception):
    pass


# MARK: Storage


def load_cfg() -> dict:
    if not CHANNELS.exists():
        raise Fail(f"no channels config at {CHANNELS}")

    cfg = tomllib.loads(CHANNELS.read_text())
    cfg.setdefault("projects", {})
    cfg.setdefault("channels", {})
    return cfg


def load() -> list[dict]:
    if not DATA.exists():
        return []

    items = []
    for n, line in enumerate(DATA.read_text().splitlines(), 1):
        if not line.strip():
            continue

        try:
            x = json.loads(line)
        except json.JSONDecodeError:
            x = None

        if not isinstance(x, dict) or not REQUIRED <= x.keys():
            raise Fail(f"bad line {n} in {DATA.name}")

        items.append(x)

    return items


def save(items: list[dict]):
    items = sorted(items, key=lambda x: (x["date"], x["id"]))
    rows = []
    for x in items:
        x = {k: x[k] for k in FIELDS if x.get(k) is not None and x[k] != "" and x[k] is not False}
        rows.append(json.dumps(x, ensure_ascii=False))

    # A unique temp file in the same dir, synced, then renamed: a crash never leaves half a file.
    opts = {"encoding": "utf-8", "dir": DIR, "prefix": ".promo-", "suffix": ".tmp", "delete": False}
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", **opts) as f:
            tmp = f.name
            os.fchmod(f.fileno(), DATA.stat().st_mode & 0o777 if DATA.exists() else 0o644)
            f.write("".join(f"{x}\n" for x in rows))
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp, DATA)
    except BaseException:
        if tmp:
            Path(tmp).unlink(missing_ok=True)

        raise


@contextlib.contextmanager
def locked(wait: bool = True):
    """Hold the exclusive data lock around load-modify-save; yields False if busy and not wait."""
    with LOCK.open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return

        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def find(items: list[dict], id: str) -> dict:
    for x in items:
        if x["id"] == id:
            return x

    raise Fail(f"no item {id}")


def new_id(items: list[dict]) -> str:
    used = {x["id"] for x in items}
    chars = "abcdefghjkmnpqrstuvwxyz23456789"
    while True:
        id = "".join(random.choices(chars, k=4))
        if id not in used:
            return id


def parse_date(s: str) -> str:
    words = {"today": 0, "tomorrow": 1, "yesterday": -1}
    if s in words:
        return (date.today() + timedelta(days=words[s])).isoformat()

    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        raise Fail(f"bad date {s!r}, want YYYY-MM-DD, today, tomorrow or yesterday") from None


def validate(cfg: dict, project: str | None = None, channel: str | None = None):
    if project is not None and project not in cfg["projects"]:
        names = ", ".join(cfg["projects"])
        raise Fail(f"unknown project {project!r}; known: {names} (add it to {CHANNELS})")

    if channel is not None and channel not in cfg["channels"]:
        names = ", ".join(cfg["channels"])
        raise Fail(f"unknown channel {channel!r}; known: {names} (add it to {CHANNELS})")


def check_draft(path: str | None):
    if path and not (DIR / path).exists():
        print(f"warning: draft {path} not found under {DIR}")


def stars(cfg: dict, project: str) -> int | None:
    repo = cfg["projects"].get(project, {}).get("repo")
    if not repo:
        return None

    cmd = ["gh", "api", f"repos/{repo}", "--jq", ".stargazers_count"]
    try:
        rep = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
        return int(rep.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# MARK: Rules


def dow(s: str) -> str:
    return DAYS[date.fromisoformat(s).weekday()]


def label(x: dict) -> str:
    return f"{x['id']} {x['date']} {x['project']}: {short(x['what'], 40)}"


def short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def violations(cfg: dict, items: list[dict], it: dict) -> list[str]:
    if it.get("reply") or it["status"] == "dropped":
        return []

    ch = cfg["channels"][it["channel"]]
    name = ch.get("name", it["channel"])
    day = date.fromisoformat(it["date"])
    others = [x for x in items if x["id"] != it["id"] and x["channel"] == it["channel"]]
    others = [x for x in others if x["status"] != "dropped" and not x.get("reply")]
    rs = []

    days = ch.get("weekdays")
    if days and dow(it["date"]) not in days:
        rs.append(
            f"{name} allows only {' '.join(days)} (weekdays); {it['date']} is {dow(it['date'])}"
        )

    n = ch.get("max_per_day")
    same = [x for x in others if x["date"] == it["date"]]
    if n and len(same) >= n:
        rs.append(f"{name} allows {n} post a day (max_per_day), taken by {label(same[0])}")

    n = ch.get("min_days_same_project")
    near = [x for x in others if x["project"] == it["project"]]
    near = [x for x in near if abs((date.fromisoformat(x["date"]) - day).days) < n] if n else []
    if near:
        rs.append(
            f"{name} needs {n} days between {it['project']} posts (min_days_same_project),"
            f" near {label(near[0])}"
        )

    n = ch.get("min_days_between")
    near = [x for x in others if abs((date.fromisoformat(x["date"]) - day).days) < n] if n else []
    if near:
        rs.append(
            f"{name} needs {n} days between posts of any project (min_days_between),"
            f" near {label(near[0])}"
        )

    return rs


def first_allowed(cfg: dict, items: list[dict], it: dict) -> str | None:
    day = date.fromisoformat(it["date"])
    for i in range(1, 400):
        x = it | {"date": (day + timedelta(days=i)).isoformat()}
        if not violations(cfg, items, x):
            return x["date"]

    return None


def enforce(cfg: dict, items: list[dict], it: dict, force: bool):
    rs = violations(cfg, items, it)
    if not rs:
        return

    if force:
        for r in rs:
            print(f"forced past a rule: {r}")

        return

    lines = [f"refused: {r}" for r in rs]
    lines.append(f"first allowed date: {first_allowed(cfg, items, it) or 'none within 400 days'}")
    lines.append("pick that date, or pass --force only if the user asked for this date")
    raise Fail("\n".join(lines))


def channel_info(cfg: dict, it: dict):
    ch = cfg["channels"][it["channel"]]
    info = [f"window {ch['window']}" if ch.get("window") else ""]
    info.append(f"rules checked {ch['checked']}" if ch.get("checked") else "")
    info = "; ".join(x for x in info if x)
    if info and not it.get("reply") and it["status"] == "planned":
        print(f"{ch.get('name', it['channel'])}: {info}")


# MARK: Commands


def cmd_add(args):
    cfg = load_cfg()
    validate(cfg, args.project, args.channel)
    check_draft(args.draft)

    # Stars before the lock: gh may take seconds.
    n = None if args.reply else stars(cfg, args.project)

    with locked():
        items = load()
        it = {"id": new_id(items), "date": parse_date(args.date), "project": args.project}
        it |= {"channel": args.channel, "status": "planned", "reply": args.reply}
        it |= {"what": args.what, "draft": args.draft}
        if args.link:
            it |= {"status": "done", "link": args.link, "stars_after": n}
        else:
            enforce(cfg, items, it, args.force)
            it["stars_before"] = n

        save([*items, it])

    print(
        f"{it['status']}: {it['id']} {it['date']} {dow(it['date'])} {it['project']} {it['channel']}"
    )
    channel_info(cfg, it)


def cmd_edit(args):
    cfg = load_cfg()
    validate(cfg, args.project, args.channel)
    check_draft(args.draft)

    with locked():
        items = load()
        it = find(items, args.id)
        old = dict(it)
        for k in ("project", "channel", "what", "draft", "note"):
            if getattr(args, k) is not None:
                it[k] = getattr(args, k)

        if args.date is not None:
            it["date"] = parse_date(args.date)
            if it["status"] == "check":
                it["status"] = "planned"

        moved = any(it[k] != old[k] for k in ("date", "channel", "project"))
        if moved and it["status"] in ("planned", "check"):
            enforce(cfg, items, it, args.force)

        save(items)

    print(f"edited: {it['id']} {it['date']} {dow(it['date'])} {it['project']} {it['channel']}")
    if moved:
        channel_info(cfg, it)


def cmd_done(args):
    cfg = load_cfg()
    it = find(load(), args.id)

    # Stars before the lock: gh may take seconds.
    n = None if it.get("reply") else stars(cfg, it["project"])

    with locked():
        items = load()
        it = find(items, args.id)
        it["status"] = "done"
        if args.link:
            it["link"] = args.link

        if args.date:
            it["date"] = parse_date(args.date)

        if n is not None:
            it["stars_after"] = n

        save(items)

    msg = f"done: {it['id']} {it['date']} {it['project']} {it['channel']}"
    msg += f" {it['link']}" if it.get("link") else " (no link: ask the user for it)"
    msg += f" ★{it['stars_after']}" if it.get("stars_after") is not None else ""
    print(msg)


def cmd_drop(args):
    with locked():
        items = load()
        it = find(items, args.id)
        it["status"] = "dropped"
        save(items)

    print(f"dropped: {label(it)}")


def cmd_rm(args):
    with locked():
        items = load()
        it = find(items, args.id)
        save([x for x in items if x is not it])

    print(f"removed: {label(it)}")


def row(x: dict) -> str:
    what = short(x["what"], WHAT_WIDTH) + (" [reply]" if x.get("reply") else "")
    cols = [x["date"], dow(x["date"]), x["id"], f"{x['status']:<7}", f"{x['project']:<9}"]
    cols += [f"{x['channel']:<24}", what]
    return "  ".join(cols)


def cmd_list(args):
    cfg, items = load_cfg(), load()
    validate(cfg, args.project)
    since = (date.today() - timedelta(days=RECENT_DAYS)).isoformat()

    if args.project:
        items = [x for x in items if x["project"] == args.project]

    if args.status:
        items = [x for x in items if x["status"] == args.status]
    elif not args.all:
        items = [x for x in items if x["date"] >= since or x["status"] in ("planned", "check")]

    for x in items:
        link = f"  {x['link']}" if x.get("link") else ""
        print(row(x) + link)

    if not items:
        print("nothing")


def show_line(x: dict) -> str:
    reply = " [reply]" if x.get("reply") else ""
    what = short(x["what"], WHAT_WIDTH)
    return f"    {x['date']} {dow(x['date'])}  {x['id']}  {x['channel']:<24}  {what}{reply}"


def show_stars(x: dict) -> str:
    sb, sa = x.get("stars_before"), x.get("stars_after")
    if sb is not None and sa is not None:
        return f"★ {sb} → {sa}"

    if sb is not None or sa is not None:
        return f"★ {sa if sa is not None else sb}"

    return ""


def cmd_show(args):
    cfg, items = load_cfg(), load()
    validate(cfg, args.project)
    today = date.today().isoformat()
    names = [args.project] if args.project else list(cfg["projects"])
    names += sorted({x["project"] for x in items} - set(names)) if not args.project else []
    pad = " " * 24

    for name in names:
        its = [x for x in items if x["project"] == name]
        if not its and not args.project:
            continue

        repo = cfg["projects"].get(name, {}).get("repo")
        print(f"{name}  github.com/{repo}" if repo else name)

        late = [x for x in its if x["status"] == "planned" and x["date"] < today]
        ahead = [x for x in its if x["status"] == "planned" and x["date"] >= today]
        ask = [x for x in its if x["status"] == "check"] + late
        done = [x for x in its if x["status"] == "done"]
        done = sorted(done, key=lambda x: x["date"], reverse=True)
        dropped = [x for x in its if x["status"] == "dropped"]

        for title, group in (("planned", ahead), ("needs the user's answer", ask)):
            if not group:
                continue

            print(f"  {title}")
            for x in group:
                print(show_line(x))

        if done:
            print("  done")

        for x in done:
            print(show_line(x))
            extra = "  ".join(s for s in (x.get("link", ""), show_stars(x)) if s)
            if extra:
                print(f"{pad}{extra}")

            if x.get("note"):
                print(f"{pad}note: {x['note']}")

        if dropped:
            print(f"  dropped: {len(dropped)} ({', '.join(x['id'] for x in dropped)})")

        if not its:
            print("  nothing yet")

        print()


def cmd_check(_args):
    if not DATA.exists():
        return

    today = date.today()
    stale = (today - timedelta(days=OVERDUE_DAYS)).isoformat()

    # Never wait for the lock at session start: if it is busy, skip the aging write.
    with locked(wait=False) as ok:
        items = load()
        old = [x for x in items if x["status"] == "planned" and x["date"] < stale]
        for x in old:
            x["status"] = "check"

        if ok and old:
            save(items)

    now = [x for x in items if x["status"] == "planned" and x["date"] == today.isoformat()]
    late = [x for x in items if x["status"] == "planned" and x["date"] < today.isoformat()]
    ask = [x for x in items if x["status"] == "check"]
    if not (now or late or ask):
        return

    def brief(x: dict) -> str:
        return f"{x['id']} {x['project']}/{x['channel']} {short(x['what'], 40)}"

    lines = []
    if now:
        lines.append("promo today: " + "; ".join(brief(x) for x in now))

    if late:
        late = "; ".join(f"{brief(x)} ({x['date']})" for x in late)
        lines.append(f"promo overdue (ask the user whether it went out and for the link): {late}")

    if ask:
        ids = short(", ".join(f"{x['id']} {x['project']}/{x['channel']}" for x in ask), 600)
        lines.append(
            f"promo: {len(ask)} old items need the user's answer (out? link? or drop): {ids}"
        )

    lines.append("use the promo skill: `promo list`, `promo done ID --link URL`, `promo drop ID`")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="plan a publication, or log one that is out (--link)")
    p.add_argument("project")
    p.add_argument("channel")
    p.add_argument("date", help="YYYY-MM-DD, today, tomorrow or yesterday")
    p.add_argument("what", help="one line: what goes out")
    p.add_argument("--draft", help="path relative to the notes repo")
    p.add_argument("--reply", action="store_true", help="a reply or comment: logged, no rules")
    p.add_argument("--link", help="already out: log it as done with this link")
    p.add_argument("--force", action="store_true", help="add even if it breaks a rule")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("edit", help="change an item; date or channel changes re-check the rules")
    p.add_argument("id")
    p.add_argument("--date")
    p.add_argument("--project")
    p.add_argument("--channel")
    p.add_argument("--what")
    p.add_argument("--draft")
    p.add_argument("--note", help="the response: reactions, comments, outcome")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_edit)

    p = sub.add_parser("done", help="mark as published; records GitHub stars")
    p.add_argument("id")
    p.add_argument("--link")
    p.add_argument("--date", help="when it actually went out")
    p.set_defaults(fn=cmd_done)

    p = sub.add_parser("drop", help="mark as dropped (not going out)")
    p.add_argument("id")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("rm", help="delete an item (mistakes only; use drop otherwise)")
    p.add_argument("id")
    p.set_defaults(fn=cmd_rm)

    p = sub.add_parser(
        "list", help=f"upcoming and unanswered items plus the last {RECENT_DAYS} days"
    )
    p.add_argument("--project")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--all", action="store_true", help="every item")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", help="per project: planned, unanswered, done with links and notes")
    p.add_argument("--project")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("check", help="for the SessionStart hook: today's and overdue items")
    p.set_defaults(fn=cmd_check)

    args = ap.parse_args()

    if args.cmd == "check":
        # The SessionStart hook must never fail a session, whatever the data looks like.
        with contextlib.suppress(Exception):
            cmd_check(args)

        return

    try:
        args.fn(args)
    except Fail as e:
        print(f"promo: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
