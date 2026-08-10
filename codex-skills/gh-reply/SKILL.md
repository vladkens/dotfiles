---
name: gh-reply
description: Draft or post a concise reply to a GitHub comment. Use when the user asks to answer someone in an issue, pull request, or review thread, not to review the pull request itself.
---

# GitHub Reply

Write the next natural turn in an existing GitHub conversation.

## Gather Context

1. Resolve the issue, pull request, or review thread from the supplied URL, number, or current branch.
2. Read the title, body, and relevant discussion. For a pull request, include reviews and inline threads when they affect the reply.
3. Identify the comment being answered and what the user wants to communicate.
4. Inspect code, releases, or other project context only when needed to verify a claim.
5. If the intended comment or message remains ambiguous, ask one concise question.

## Write The Reply

- Default to one short paragraph of one to three sentences.
- Match the conversation's language, technical level, and tone.
- State the result, decision, or question early. Expand only when technical reasoning is needed to make the reply useful.
- Answer or acknowledge the relevant comment, then add only what the user wants to communicate.
- Treat the user's wording as a rough draft. Turn it into a natural public reply without adding information or intent.
- Preserve the user's directness. Do not add warmth, caution, or softening that changes the intended tone.
- Do not restate the issue, pull request, or comment being answered. Mention existing context only when the reply would otherwise be unclear.
- Do not invent facts, commitments, explanations, or next steps.
- Avoid headings, lists, generic thanks, and formal filler unless the content requires them.

## Examples

Use these as length and tone calibration, not as templates:

- `thanks, merged` → `Thanks for the PR — merged!`
- `regression, fixed in v0.8.2, ask them to test` → `This was a regression and should be fixed in v0.8.2. Please give it a try and let me know if it works for you.`
- `not a bug, this state is impossible and the panic is intentional` → `This isn't a bug: supported hardware cannot produce this state, and the panic is intentional.`
- Do not turn `thanks, merged` into a recap such as `Thanks for adding X and updating Y. I've reviewed these changes and have now merged the pull request.`

## Draft Or Publish

- For a draft, return only the proposed comment without a label, quotation marks, or explanation.
- Publish only when the user explicitly asks to post, send, leave, or reply on GitHub. Otherwise, draft only.
- Post exactly once in the discussion being answered. Check for an existing reply before posting or retrying after an uncertain failure.
- After publishing, return the comment link without repeating its text.
