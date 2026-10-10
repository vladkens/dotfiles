---
name: brainstorm
description: Explore open-ended product or technical decisions and their trade-offs. Use when the user asks to explore or choose a direction before planning or implementation, not for a bounded review of existing content.
---

# Brainstorm

Think through ideas and changes in collaborative dialogue before planning or implementation.

## Core Intent

Build a shared understanding of the idea, goal, constraints, unknowns, and decisions. Use project context when it exists. Adapt the depth to the task; do not force ceremony when the context is already clear.

## Process

### Phase 1: Understand

1. Inspect relevant project context when it exists.
2. Summarize the available context, what is known, and what remains uncertain.
3. Ask at most one question at a time, only when a high-impact unknown blocks progress.
4. Focus on purpose, constraints, success criteria, affected workflows, integration points, user expectations, and risks.

Do not propose approaches, APIs, config, abstractions, or implementation steps before inspecting the available context. If local context answers a question, state the assumption and continue.

The first substantive response should usually be a discovery summary. If the user explicitly asks for a proposal and the context is sufficient, move directly to Phase 2.

### Phase 2: Explore Approaches

Enter this phase only when the context and key constraints are clear enough to evaluate options. Propose alternatives only when there is a real choice.

1. Compare 2-3 approaches only when they have materially different trade-offs.
2. Lead with the recommended option and explain the reasoning.
3. Tie each option to concrete project facts when available.
4. Compare only the trade-offs that matter for the user's goal.

If one approach is clearly project-native, recommend it instead of inventing alternatives. If the user corrects an assumption, update the model and continue from the corrected facts.

### Phase 3: Present Design

After the approach is selected, present the design incrementally.

1. Break larger designs into decision-sized sections.
2. Cover only relevant concerns: architecture, components, data flow, interfaces, error handling, testing, migration, and rollout.
3. Keep each section short and scannable.
4. Pause for confirmation only when the answer could materially change the design.
5. Backtrack when new information invalidates an assumption.

### Phase 4: Continue or Save

Continue the conversation without creating files unless the user explicitly asks to save the findings or write a plan.

- When asked to save the findings, use the requested path or `docs/research/yyyymmdd-<task-name>.md` by default. Create the directory if needed. Give the note a descriptive title and use the sections below, omitting empty ones.
- When asked for an implementation plan, continue in this conversation with the planning skill.
- When asked to implement, continue in this conversation under the normal project and Git permission rules.

Structure a saved research note with these `##` headings:

- `Goal`: what is being explored and why.
- `Context`: relevant files, components, constraints, and existing behavior.
- `Findings`: verified facts and meaningful alternatives with trade-offs.
- `Decisions`: decisions made and their rationale.
- `Open Questions`: unresolved questions or risks.
- `Recommendation`: the preferred direction and why.

Do not start implementation merely because the discussion reaches a recommendation.

## Response Style

Keep responses practical and conversational. Lead with known facts, state the recommendation and meaningful trade-off, and ask one concrete question only when a real decision blocks progress.

## Rules

- One question at a time.
- Prefer multiple-choice questions when the options are known.
- Inspect context before proposing architecture.
- YAGNI ruthlessly: deliver the smallest complete solution to the user's request; do not invent MVPs, phases, or deferred follow-up work unless the user asks for staged delivery.
- Prefer project conventions and existing extension points when they exist.
- When code would repeat, ask whether to keep duplication or add an abstraction, with the trade-off.
- Explore alternatives only when alternatives are real.
- If a question blocks progress, ask it before presenting a full proposal.
- Accept user corrections instead of defending invalid assumptions.
- Surface assumptions and risks explicitly.
