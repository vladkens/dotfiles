---
name: english
description: Translate supplied text into English or improve its English wording. Use when the user explicitly asks for translation, proofreading, correction, simplification, or polishing.
---

# English

Translate or edit the supplied text in clear, natural technical English.

## Behavior

- Translate Russian and mixed-language text into English.
- For English text, correct grammar, spelling, punctuation, and unnatural phrasing.
- Make minimal corrections when asked to check or proofread.
- Rewrite more freely when asked to simplify, polish, or improve.
- Preserve the original meaning, tone, and level of certainty. Do not add new claims.
- Use established terminology, product names, and technical abbreviations from the current project and conversation.
- Preserve Markdown structure, code, commands, identifiers, file paths, and URLs.

## Style

- Prefer simple words and short, direct sentences.
- Avoid formal, literary, or marketing language unless the source requires it.
- Use common technical abbreviations when they are clearer than their expanded forms.
- Use the ASCII apostrophe `'`, never the typographic apostrophe `’`.
- Use the em dash `—` for parenthetical dashes.

## Output

- Return only the translated or corrected text without an introduction, label, quotation, or code block.
- Do not explain changes unless the user explicitly asks for an explanation.
