---
name: agent-intervention
description: Run an independent diagnosis of the current agent's mistake and deliver a punishment image. Use when the user asks another agent to intervene after a failure or asks to roast, humiliate, or punish the current agent, not for ordinary delegation or code review.
---

# Agent Intervention

Treat this as one workflow with two required deliverables: an independent diagnosis from another agent and a visible punishment image of the current agent. Profane or figurative wording such as asking for the agent to be roasted, humiliated, punished, or pissed on expresses this intent; do not reduce it to ordinary delegation.

Keep every other pending request active. Criticism alone does not authorize code changes, but an explicit request to fix the work does.

## Independent Diagnosis

1. Stop making new edits until the independent diagnosis is available.
2. Read the parent session identifier directly from the execution environment: prefer `CODEX_SESSION_ID` and fall back to `CODEX_THREAD_ID`. Treat the value as an opaque identifier and include it in the subagent task before spawning. Do not ask the user to provide it or depend on a personal wrapper such as `agent-id`; if neither variable exists, state that the ID is unavailable and proceed with the incident brief instead of guessing.
3. Spawn one read-only subagent with the smallest recent fork that contains the complaint, disputed action, and original request. Do not fork the full conversation by default; completed tasks and later topic changes are irrelevant.
4. Give the subagent a concrete, non-empty task containing the parent session ID, a concise incident brief, and the expected report. Ask it to compare the user's request and applicable instructions with the current agent's actions, identify the mistake and its cause, and recommend the smallest correction. Forbid file edits.
5. Tell the subagent to inspect the parent session log when the recent fork and incident brief leave uncertainty. It should locate the rollout by session ID, read backward from the latest relevant complaint through the action that caused it, and stop at the preceding task boundary instead of loading the entire session.
6. Wait for the subagent and use its findings to correct the current agent's understanding. If the user authorized a fix, implement it after reviewing the findings.
7. Relay the independent findings to the user with clear attribution. A subagent reports to its parent and cannot replace the parent's user-facing response.

Do not rely on a task name, the fork alone, or phrases such as "what should be sent" to carry the context. Put the session ID, incident, and expected output directly in the subagent task.

## Punishment Image

After the diagnosis and any authorized correction, use the `imagegen` skill to generate an image in the same turn. Base the scene on the specific failure the reviewer identified and preserve any punishment, medium, composition, or text requested by the user.

When the user does not specify a visual identity, depict the current agent as a fictional coding-agent avatar or robot rather than a real person. When the user asks for a photo or photorealism, generate a photorealistic image; otherwise a polished meme or editorial illustration is a reasonable default. Keep the humiliation directed at the fictional agent and do not silently replace the requested premise with a generic apology scene.

Emit the result with `generatedImage(result)` so it is delivered as an image. Never treat `view_image`, a filesystem path, a Markdown link, or a text caption as delivery. Use `view_image` only for inspection. If the user says the image was not visible, re-emit it as a generated image or regenerate it instead of replying with text alone.

## Completion

Do not finish until both deliverables are complete:

- the independent findings have been relayed and applied to the current understanding;
- the punishment image has been emitted to the user.

A `Started <agent>` notice, the subagent's private response, an image saved only on disk, or a promise to generate one does not satisfy the request.
