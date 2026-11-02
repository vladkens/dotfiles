## Layout

Personal dotfiles and agent extensions shared across machines: app and system configs in `dotfiles/<app>/`, Claude and Codex config and extensions in `claude/` and `codex/`, instructions and skills shared by both in `agents/agents.md` and `agents/skills/`. Changes under `agents/`, `claude/` and `codex/` change global agent behavior.

- Deploy everything through the modules in `config.py`: add each new config or tool to a module, link files via `files`, macOS settings via `defaults`, launchd jobs via `launchd`; never copy files in `setup`, and keep `setup` safe to repeat.

## Python scripts

- Name scripts in kebab-case, give them inline uv metadata (`uv run --script <path>`), and never use `from __future__ import annotations`.
- Exceptions: `config.py` and `dotsync/` run on the macOS system Python 3.9 before uv exists, so their runnable scripts start with `#!/usr/bin/python3`, have no uv metadata, use snake_case names and may use `from __future__`; `scripts/git-diff-codex-config.py` is Git's clean filter for `codex/config.toml`, so it uses `#!/usr/bin/env python3`, the standard library only and no uv metadata.

## Skills

Define each shared skill in `agents/skills/<name>/SKILL.md` without agent-specific syntax and without `agents/openai.yaml`. Its `description` is the action contract and trigger, matched to the user's intent rather than a keyword; workflow steps go in the body:

```yaml
description: <Action> <concrete object> [with/from/into <essential context or result>]. Use when the user [explicitly] asks to <matching intent> [or <equivalent intent>].
```

Add the nearest exclusion when it prevents a likely false trigger:

```yaml
description: <Action> <concrete object>. Use only when <positive trigger>, not when <nearest confusable intent>.
```
