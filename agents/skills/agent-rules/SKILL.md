---
name: agent-rules
description: Create or revise concise AGENTS.md instructions with clear actions and preserved permission boundaries. Use when the user asks to write, simplify, audit, or reorganize agent instruction files.
---

# Agent Rules

Create compact instruction files that change concrete agent decisions without losing scope, permissions, or exceptions.

## Establish scope

Read the target file, applicable parent instructions, and directly related skills or local guidance. For a new file, inspect enough of the project to identify real conventions. Use current files unless the user explicitly asks for historical comparison or Git inspection.

Determine whether the user wants analysis, a draft, or file edits. Preserve existing policy when a boundary is unclear; ask one specific question only when the ambiguity prevents completion.

## Select and place rules

Keep a rule when it defines a durable preference, a permission boundary, or a non-obvious action for its scope. Ask: "Which concrete agent decision changes because of this rule?" Remove slogans, generic quality advice, stale workarounds, and details already available where the behavior is triggered.

Place each rule in the narrowest scope that covers every use:

- Global `AGENTS.md`: durable user preferences across projects.
- Repository `AGENTS.md`: project purpose and repository-wide conventions.
- Nested `AGENTS.md`: behavior specific to that directory or component.
- Skill: a procedure triggered by a distinct user intent.
- Formatter, test, or CI: mechanically enforceable requirements.
- Ordinary documentation: explanations and reference material.

Before removing a duplicate, verify that the remaining source is loaded whenever the rule is needed. Moving a rule to a skill changes when it is available; moving a check to CI does not preserve an agent permission boundary.

## Audit existing rules

Assign each rule one action:

- **Keep:** useful, precise, and correctly placed.
- **Rewrite:** useful but verbose or ambiguous.
- **Merge:** governs the same decision under compatible conditions.
- **Move:** belongs to another scope or triggered workflow.
- **Remove:** an accessible duplicate, obsolete rule, or text with no concrete effect.

Use the classification to guide the work. Show a full rule-by-rule audit only when requested or needed to make the proposed changes reviewable.

## Write concise directions

Use this shape when it fits:

```text
[When <condition>,] <action> <object> [within <scope>] [only with <authorization>].
```

Write one coherent decision per bullet. Keep its condition, material exception, and authorization boundary beside the action. Use direct verbs and short familiar headings.

State the preferred action positively when that preserves the policy. Keep `only`, `never`, or `do not` when they express a boundary more precisely. For example:

```text
Modify the Git index only with explicit authorization.
Prefer sensible defaults; add CLI flags only when requested or necessary for the task.
```

The second form is valid only when task-required flags are already allowed. Adding an exception while rewriting changes policy.

Remove repeated explanations, synonym lists, filler, and examples that do not clarify a real boundary. Merge rules only when they govern the same decision. Split unrelated conditions even if that increases the bullet count. Measure size consistently when comparison is useful, without optimizing for a fixed reduction target.

## Verify meaning

For every changed rule, compare its condition, action, object, scope, authorization, and exceptions with the source. Test the wording against a normal case, a case without permission, and a material exception.

Pay particular attention to `only`, `all`, `any`, `before`, `explicit`, and `unless`. Avoid these common semantic regressions:

- Replacing `Git index` with `staging` narrows the protected operations.
- Replacing `files` with `code` excludes configuration and documentation.
- Keeping a required path while dropping `only` weakens the restriction.
- Adding a plausible exception expands authority.
- Removing a skill reminder is safe only after verifying its trigger and availability.

Check parent instructions for conflicts and inspect the result for internal duplication. Distinguish editorial changes from behavioral changes.

## Deliver the result

For an edit request, update the target file and reread it. For an analysis or draft request, return the proposed text without editing files.

Briefly report meaningful merges, removals, changes in scope or permission, and size before and after when relevant. Do not create audit notes or supporting documents unless requested. Describe improvements as editorial judgments unless behavioral tests support a claim about agent performance.
