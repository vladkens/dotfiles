## Repository scope

This repository is the source of truth for personal dotfiles and agent extensions installed across one or more computers. The instructions in this file apply to both Codex and Claude unless a section explicitly says otherwise.

- Store ordinary application and system configuration under `dotfiles/`, grouped by application; store agent configuration and extensions under the top-level `claude/` and `codex/` directories.
- Treat changes under `claude/` and `codex/` as changes to global tooling and behavior.

## Writing instructions

- Write one coherent rule per bullet; separate unrelated policies and combine fragments that govern the same decision.
- Use concise, concrete wording with only enough context to preserve behavior and clarify real boundaries.
- Preserve approved structure and meaning when simplifying instructions unless the user asks to change them.

## Codex skills

Define each Codex skill in its `SKILL.md`; omit `agents/openai.yaml` in this repository.

### Description format

A skill `description` is its action contract and trigger. Use this structure:

```yaml
description: <Action> <concrete object> [with/from/into <essential context or result>]. Use when the user [explicitly] asks to <matching intent> [or <equivalent intent>].
```

Add the nearest exclusion when it prevents a likely false trigger:

```yaml
description: <Action> <concrete object>. Use only when <positive trigger>, not when <nearest confusable intent>.
```

- Start with a direct action verb and name the exact object plus only essential context.
- Match the user's intent rather than an isolated keyword.
- Keep workflow steps and detailed behavior in the `SKILL.md` body.
