## Repository purpose

This repository is the source of truth for personal dotfiles and agent extensions installed across one or more computers. The instructions in this file apply to both Codex and Claude unless a section explicitly says otherwise.

Keep ordinary application and system configuration under `dotfiles/`, grouped by application. Keep larger, self-contained agent extensions in the dedicated top-level directories: `codex-skills/`, `codex-plugins/`, and `claude-skills/`. Treat changes to these files as changes to global tooling and behavior, not as configuration specific to this repository.

## Instruction writing

- Write each bullet as one coherent rule. Do not combine unrelated policies or split one policy into micro-directives.
- Use simple, concrete wording. Avoid padding rules with synonyms or lists that do not clarify a real boundary.
- Keep bullets concise, but include enough context to preserve the intended behavior. Do not turn a bullet into a paragraph.
- When simplifying existing instructions, preserve their approved structure and meaning unless the user asks to change them.

## Codex skills

Define each Codex skill in its `SKILL.md`. Do not create an `agents/openai.yaml` file for skills in this repository.

### Description format

A skill `description` is both its action contract and its trigger. Keep it short and use this structure:

```yaml
description: <Action> <concrete object> [with/from/into <essential context or result>]. Use when the user [explicitly] asks to <matching intent> [or <equivalent intent>].
```

For easily confused intents, define the nearest exclusion:

```yaml
description: <Action> <concrete object>. Use only when <positive trigger>, not when <nearest confusable intent>.
```

- Start with a direct action verb such as `Create`, `Review`, `Execute`, or `Translate`.
- Name the exact object and only the context that defines the skill.
- Match the user's intent, not an isolated keyword.
- Add an exclusion only for a likely false trigger.
- Keep workflow steps and detailed behavior in the `SKILL.md` body.
