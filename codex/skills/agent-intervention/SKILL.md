---
name: agent-intervention
description: Review the current agent's reported failure with an independent agent and deliver a punishment image. Use when the user asks another agent to analyze, explain, or correct the current agent after a reported failure, or asks to roast, humiliate, or punish it, not for ordinary delegation or code review.
---

# Agent Intervention

Treat this as one workflow with two required deliverables: an independent diagnosis from another agent and a visible punishment image of the current agent. A request to have another agent analyze or explain the current agent's failure triggers this workflow even when the user does not repeat the image requirement. Profane or figurative wording such as asking for the agent to be roasted, humiliated, punished, or pissed on expresses the same intent.

Keep every other pending request active. Criticism alone does not authorize file edits; an explicit request to fix authorizes an in-scope correction subject to normal permission boundaries.

## Independent Diagnosis

1. Stop making new edits until the independent diagnosis is available.
2. Read the parent session identifier directly from the execution environment: prefer `CODEX_SESSION_ID` and fall back to `CODEX_THREAD_ID`. Treat the value as an opaque identifier and include it in the subagent task before spawning. Do not ask the user to provide it or depend on a personal wrapper such as `agent-id`; if neither variable exists, mark the ID unavailable in the task and proceed with the incident brief instead of guessing.
3. Spawn one read-only subagent with a small recent fork, normally three to five turns. Include the complaint and disputed action when possible; do not enlarge the fork merely to reach an older request or completed task.
4. Give the subagent a concrete, non-empty task containing the parent session ID when available, a concise incident brief, and the expected report. Ask it to compare the user's request and applicable instructions with the current agent's actions, establish whether a mistake occurred, separate observed facts from possible causes, and recommend the smallest supported correction. Require it to state when evidence is insufficient. Forbid file edits.
5. Tell the subagent to inspect the relevant end of the parent session log if it can locate and access it, starting at the latest complaint and reading backward only until the current task began. If the log is inaccessible, use the incident brief and available fork and state what could not be verified. The small fork is context, not a substitute for checking the disputed actions when the log is available.
6. Wait for the subagent, use its findings to update the current agent's understanding, and relay them to the user with clear attribution. A subagent reports to its parent and cannot replace the parent's user-facing response.
7. Apply the smallest supported correction when the current task authorizes it. Do not expand the task or perform an external, destructive, or separately controlled action without its normal authorization.

Do not rely on a task name, the fork alone, or phrases such as "what should be sent" to carry the context. Put the available session ID, incident, and expected output directly in the subagent task.

## Punishment Image

After the diagnosis and any authorized correction, use the `imagegen` skill to generate an image in the same turn. Base the scene on the disputed action and the reviewer's findings without presenting an unverified mistake as fact; preserve any punishment, medium, composition, or text requested by the user.

When the user does not specify a visual identity, depict the current agent as a fictional coding-agent avatar or robot rather than a real person. Keep the humiliation directed at the fictional agent and do not silently replace the requested premise with a generic apology scene.

When the user does not specify a style, randomly choose one fitting treatment, such as a crude MS Paint meme, newspaper cartoon, pixel art, clay stop-motion scene, courtroom sketch, photoreal tabletop miniature, or watercolor. Use one coherent style per image. Do not inspect earlier punishment images to choose a style or mechanically default to the same dark robot scene. The user's requested medium or style always takes precedence; if they ask for a photo or photorealism, make the image photorealistic.

Emit the result with `generatedImage(result)` so it is delivered as an image. Never treat `view_image`, a filesystem path, a Markdown link, or a text caption as delivery. Use `view_image` only for inspection. If the user says the image was not visible, re-emit it as a generated image or regenerate it instead of replying with text alone.

## Completion

Finish when the workflow is complete:

- the independent findings have been relayed and applied to the current understanding;
- any correction authorized for the current task has been applied;
- the punishment image has been emitted to the user.

A `Started <agent>` notice, the subagent's private response, an image saved only on disk, or a promise to generate one does not satisfy the request.

If the subagent or image tool remains unavailable after a reasonable attempt, report which deliverables were completed and what blocked the rest. Do not invent findings, claim completion, or bypass the `imagegen` skill's fallback rules.
