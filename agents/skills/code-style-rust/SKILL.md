---
name: code-style-rust
description: Apply the user's established coding style to Rust code. Use when the user asks to implement, refactor, or review Rust code in their personal style, not for generic Rust guidance.
---

## Names and Structure

- Follow the project's rustfmt settings; the usual defaults are `tab_spaces = 2`, `max_width = 100`, and `use_small_heuristics = "Max"`.
- Use compact names supplied by domain or module context, such as `Config`, `Data`, `req`, `rep`, `dat`, and `cur`. Short closure parameters such as `x` or `e` are fine when their meaning is clear.
- Keep the module layout shallow and related records, parsing, implementations, and helpers together; group peer integrations in their own modules.

## Types and Logic

- Access plain record fields directly. Shared records often have public fields; module-local response structs can stay private, as can client or builder state. Follow the module's existing visibility boundaries.
- Keep construction and conversion beside the type in its `impl`; use traits such as `From`, `TryFrom`, `Display`, and `IntoResponse` for their corresponding operations.
- Use borrowed `&str` and slices for input-only helpers; keep owned values where the resource or result stores them.
- Use successive `let` bindings to transform a value under the same name; local mutation is normal.
- Use iterator chains for mapping, filtering, aggregation, and collection; use explicit loops for parsers, retries, multiple accumulators, and state changes.
- Handle special cases with early returns. Keep variant-dependent decisions in `match`, using guards when the condition belongs to a particular variant.
- Propagate fallible operations with `?` and reuse the project's compact result aliases, such as `Res` or `WithError`, while preserving its underlying error types.

## Dependencies and Integrations

- Keep request construction and response parsing visible in small client methods or service modules.
- Model the response fields an operation consumes with a small local Serde struct or `serde_json::Value`. Use Serde attributes for differences between the wire representation and local types.

## Tests and Comments

- Put unit tests beside the implementation in an inline `#[cfg(test)] mod tests`. Use direct assertions and tables or loops for repeated cases; keep file, database, or network fixtures close to the tests that need them.
- Use `// MARK: ...` for groups in long cohesive files and brief comments with source/spec links, units, or protocol details.
