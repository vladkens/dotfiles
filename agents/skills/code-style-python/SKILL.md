---
name: code-style-python
description: Apply the user's established coding style to Python code. Use when the user asks to implement, refactor, or review Python code in their personal style, not for generic Python guidance.
---

## Names and Structure

- Follow the project's formatter settings; the usual default is Ruff with a 100-column target.
- Use compact domain names and familiar locals such as `cfg`, `rep`, `rs`, `qs`, `pld`, and `x`. Name operations directly without forcing a verb prefix onto an already clear name.
- Keep packages shallow and related records, transformations, and helpers together. A helper for one workflow can stay nested in it.
- Follow the module's public/internal naming distinction; do not automatically prefix every helper or field with `_`.
- Leave a blank line after a completed block of checks before the following code.

## Types and Logic

- Prefer dataclasses with direct fields for plain records; keep their conversion methods and computed properties on the record.
- Use plain dictionaries for payloads and intermediate values, and `TypedDict` for named dictionary contracts. Follow existing Pydantic models where the project uses runtime validation.
- Use free functions for transformations and workflows; use classes for client state, resources, or a group of related operations.
- Use builtin collection annotations such as `list[T]` and unions such as `T | None`, within the project's supported Python version.
- Write transformations as successive assignments and comprehensions. Reusing the same local name for successive representations and mutating records during normalization are normal.
- Use comprehensions and generator expressions for mapping, filtering, and aggregation; use ordinary loops for multiple accumulators, side effects, retries, and state changes.
- Handle empty input, completed cases, and loop skips with early returns or `continue`, keeping the main workflow at the outer indentation level.

## Dependencies and Integrations

- Keep HTTP payload construction and response conversion together in the client or integration module.
- For SQL-backed tools, prefer direct SQL with thin connection or query helpers; keep queries beside the operation that uses them.

## Tests and Comments

- Write pytest tests as functions with direct assertions. Use `parametrize` for cases and fixtures or local helpers for shared setup.
- Keep comments brief: source/API links, units, and non-obvious behavior. Use `# MARK: ...` to separate groups in long cohesive files.
