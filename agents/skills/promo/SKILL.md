---
name: promo
description: Plan and log the user's publications across projects (posts, threads, articles, release announcements, comments, replies, list submissions on X, LinkedIn, Reddit, Discord, Slack, Telegram, Hacker News, the blog, GitHub lists) with the local promo.py, which enforces each channel's posting rules. Use when the user plans, drafts a date for, or schedules a post on any channel, says something was posted, published, sent or went out, asks what is planned or was done for a project, or when the session-start note lists due or unanswered publications.
---

# Promo

Use the bundled `scripts/promo.py` to plan and log every publication. Resolve `<skill-dir>` to the directory containing this `SKILL.md`, not the current working directory.

The data lives in the private notes repo `~/Code/notes`: `promo.jsonl` (one item per line) and `promo-channels.toml` (projects with their GitHub repo, channels with their numeric rules). Nuanced rules (one big launch a day, LinkedIn tone, blog reposts) are in `~/Code/notes/marketing.md`, each subreddit's own rules and what works there in `~/Code/notes/reddit.md`: read them before planning a post. The CLI requires `uv`; `gh` is optional, for star counts.

## Commands

Prefix each command below with `uv run --script <skill-dir>/scripts/promo.py`. Use `--help` on the CLI or a subcommand to check syntax.

| Task                                          | Command                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------ |
| Plan a post                                   | `add wavo x 2026-11-04 "Wavo 0.1 demo video" --draft wavo/x.md`          |
| Log a reply or comment that is already out    | `add wavo slack today "reply to Matan in the thread" --reply --link URL` |
| The user says it went out                     | `done ID --link URL` (add `--date` if not on the planned day)            |
| Record the response later                     | `edit ID --note "42 points, 34 comments, requests: …"`                   |
| Move or change a planned item                 | `edit ID --date 2026-11-05` (also `--channel --project --what --draft`)  |
| It is not going out                           | `drop ID`                                                                |
| Upcoming, unanswered and the last 14 days     | `list` (`--project P`, `--status check`, `--all`)                        |
| Per-project view: planned, done with links    | `show` or `show --project wavo`                                          |
| Today's and overdue items (SessionStart hook) | `check`                                                                  |

- Projects and channels must exist in `promo-channels.toml`; the error lists the known ids. Add a new subreddit or project there (and its numeric rules from reddit.md) when the user starts using it. A channel's rules are `max_per_day` (all projects together), `min_days_same_project` (days between posts about one project), `min_days_between` (days between posts of any project, a subreddit's per-developer cooldown: r/macapps 30), `weekdays`, and the informational `window` and `checked`.
- `--draft` is a path relative to `~/Code/notes`, where the text and media for the post live.
- `--reply` marks replies, comments, reminders in a thread and DMs: they are logged but never count toward or break a rule. Use it only for those, not to get around a rule.
- `done` and `add --link` record the repo's GitHub stars as `stars_after` (and `add` records `stars_before`); run `done ID` again a day or two later to refresh the count.
- `rm` is for mistakes only; use `drop` for posts that won't go out, so the history stays.

## Rules

- When `add` or `edit` refuses, it prints the broken rule and the first allowed date. Offer the user that date, or another that passes; pass `--force` only when the user asks for that date knowing the rule.
- Print the channel's posting window and its rules' `checked` date that `add` prints. If the date is old, recheck the platform's rules (the reddit skill's `rules` for a subreddit) and update `checked` in the config and the date in reddit.md (marketing.md for other channels).
- Log every publication, planned or done, including comments, replies and list submissions. When the user says something went out, run `done` with the link at once; if there is no link, ask for it.
- When the session-start note lists overdue or unanswered items, ask the user once, briefly, which went out (with links), which to move, and which to drop, then run `done`, `edit --date` or `drop`. Planned items more than 3 days overdue turn into status `check` by themselves.
- Keep `what` to one line. Answer in the conversation's language. The data is in the notes repo: commit it there by its `agents.md` once the result is finished.
