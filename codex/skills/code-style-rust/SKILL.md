---
name: code-style-rust
description: Apply the user's established coding style to Rust code. Use when the user asks to implement, refactor, or review Rust code in their personal style, not for generic Rust guidance.
---

# Rust Code Style

Use these rules as a decision guide, not as a mechanical linter. Preserve explicit task requirements and established project conventions. Do not refactor unrelated code merely to make it match this style.

## Overall Character

- Prefer concrete, compact, operational code over framework-like architecture.
- Keep the design proportional to the problem. Add a layer only when it owns a stable responsibility or removes meaningful complexity.
- Optimize for code that can be read locally: ordinary structs and enums, explicit state, direct control flow, and visible data transformations.
- Accept small amounts of local duplication when the alternative is a generic framework with indirect behavior.

## Crates, Modules, and Files

- Create a separate crate only for a real reusable boundary with its own coherent API, not merely to reduce file size.
- Organize modules around stable responsibilities such as configuration, storage, protocol parsing, rendering, or transport.
- Keep the module tree shallow. Introduce a directory only for a genuine family of peer modules, such as several routes or service integrations.
- Do not split a cohesive module because it has become long. Split it when parts have distinct responsibilities, lifecycles, dependencies, or reasons to change.
- Keep closely related types, parsing logic, helpers, and tests together when they form one readable unit.
- Use `main.rs` as the composition root. It may parse arguments, initialize resources, connect components, and run the top-level workflow, but reusable domain behavior belongs in modules.
- Keep `lib.rs` small. Declare internal modules there and re-export only the intended crate API.

General shape:

```text
src/
├── main.rs
├── config.rs
├── client.rs
└── routes/
    ├── mod.rs
    ├── api.rs
    └── html.rs
```

Use the directory only when `api` and `html` are peers under one stable `routes` responsibility. Otherwise prefer flat files.

## Placement of Types and Functions

- Define a type in the module that owns its behavior or interpretation.
- Keep protocol, database-row, and serialization types next to the code that reads or writes them unless they form a shared public model.
- Treat generated and third-party data as an external compatibility boundary even when it is embedded. Inspect its updater before changing the consumer, preserve generated keys, and use serialization renames when local Rust names should differ.
- Keep private helper structs and enums in the same file as their sole consumer.
- Put broadly shared domain types in a small dedicated module only after multiple modules genuinely depend on them.
- Place CLI argument types near the executable entry point unless another module owns their semantics.
- Order a module for local comprehension: primary public type or entry function first, its implementation next, private helpers afterward, and tests last.
- Prefer free private helper functions when no object state is needed. Use methods when behavior naturally belongs to a value or resource owner.

For a one-off response shape, prefer a local private type:

```rust
#[derive(Deserialize)]
struct Data {
    count: u64,
}
```

Do not create a shared `models` hierarchy for a type used by one parser.

## Naming

- Treat naming as part of correctness and make a deliberate naming pass before structural cleanup or final validation.
- Use short, concrete module and type names that state the owned concept: `Config`, `Client`, `Record`, `Sampler`, `AppState`.
- Name functions with direct verb-object phrases such as `load_config`, `read_record`, `insert_stats`, `render_image`, or `run_server`.
- Module context may shorten a concrete name, but it does not replace the action in a function name. Avoid noun-only or vague function names when a direct operation can be stated.
- Use short generic names such as `Data` or `Kind` for local types and values when the surrounding module supplies the missing context. Qualify the name when several related variants coexist.
- Preserve established domain acronyms in type names instead of expanding them into unnatural prose.
- Use familiar abbreviations in narrow scopes, especially for protocol fields, buffers, indexes, requests, and responses.
- In short closures, use the shortest familiar parameter made obvious by the expression, such as `|x|`, `|t|`, `|ts|`, `|p|`, `|e|`, or `|i|`. Reserve full words for multi-line closures or scopes where several similar values must be distinguished.
- Prefer descriptive names at module and API boundaries. Short names such as `req`, `res`, `buf`, `idx`, `cfg`, or `cur` are appropriate only when their meaning is immediate.
- Use compact result aliases when they remove repeated boilerplate and the error model is uniform, for example `type Res<T> = anyhow::Result<T>`.
- Do not introduce verbose suffixes such as `Manager`, `Service`, `Factory`, `Processor`, or `Interface` unless the type genuinely represents that role.

## Control Flow

- Use iterator chains for stateless mapping, filtering, aggregation, and collection.
- Use explicit loops for parsers, retry logic, ordered state transitions, channel processing, and workflows with mutation or multiple exit conditions.
- Prefer early returns for invalid input, empty cases, cache hits, and completed special cases.
- Use `match` when variants drive different behavior. Prefer exhaustive matching over boolean flags and scattered conditionals.
- Use match guards when a condition belongs to a particular variant.
- Treat local mutation and variable shadowing as normal tools when they make a sequential transformation easier to read.
- Keep branching close to the data it interprets. Avoid routing simple behavior through callbacks, trait objects, or generic dispatch.
- Choose concurrency that matches the work: async tasks for network and server orchestration, threads or data parallelism for blocking and CPU-heavy work.
- In ordinary application paths, prefer clarity over eliminating every allocation or clone. In measured hot paths, use explicit capacities, specialized collections, and tighter representations.

## Abstractions and Dependencies

- Start with concrete types and functions. Introduce a wrapper when it owns state, a resource, an invariant, or a coherent group of operations.
- Implement traits at real ecosystem or protocol boundaries, such as serialization, conversion, iteration, formatting, response conversion, or resource cleanup.
- Keep generics narrow and mechanical. Do not make domain behavior generic in anticipation of hypothetical implementations.
- Prefer enums for a closed set of modes or variants. Use trait objects only when runtime extensibility is an actual requirement.
- Use established crates for substantial, well-solved capabilities such as async I/O, HTTP, serialization, CLI parsing, database access, and parallel execution.
- Write a local implementation when the behavior is small glue, central to the product, performance-sensitive, unsupported by a suitable crate, or easier to understand directly.
- Remove a dependency or abstraction when the surrounding workflow becomes simpler and it no longer carries its weight.
- Do not unify similar integrations merely because they share a shape. Keep separate concrete modules when their APIs and failure modes differ.

## Error Handling

- Use one concise application-level `Result` alias when most operations share the same error strategy.
- Preserve specific error types in reusable parsers and libraries when callers can act on them.
- Add a small error wrapper at a framework boundary only when conversion changes behavior, such as mapping errors into HTTP responses.
- Use `?` for propagation and implement `From` when a conversion is stable and removes repeated mapping code.
- Represent expected absence, optional data, and unsupported input with `Option`, defaults, skips, or an explicit branch rather than treating them as exceptional failures.
- For a private input field with one consumer, prefer keeping `Option` and applying its fallback at the use site over adding a Serde default helper that only returns a literal.
- Use `unwrap`, `expect`, assertions, and `unreachable!` only for internal invariants made clear by nearby construction or control flow.
- In batch work, isolate item-level failures when later items remain useful. Log or collect the failure and continue deliberately.
- Avoid large custom error enums when callers do not distinguish the variants.

## Visibility and Public API

- Keep items private by default.
- Use `pub(crate)` only when it creates a meaningful boundary. In a small binary crate with private modules, ordinary `pub` for cross-module access is usually clearer than repeating `pub(crate)` throughout the code.
- Descendants can already access private items from a parent module. In small private module trees, prefer private items for descendant access and ordinary `pub` for parent access instead of `pub(super)` annotations.
- Re-export a small, curated library API from the crate root instead of exposing the internal module tree.
- Make fields public for transparent data records whose fields are the API. Keep fields private for stateful objects, builders, and values with invariants.
- Do not add getters, traits, or facade types solely to hide a straightforward record.
- Treat visibility as an architectural boundary, not as a convenience for making the compiler accept a call.

## Tests and Comments

- Put focused unit tests in an inline `tests` module beside the pure logic they verify.
- Prioritize parsing boundaries, filtering rules, conversions, and behavior with easy-to-miss edge cases.
- Add integration tests only when behavior genuinely crosses module, process, filesystem, database, or network boundaries.
- Keep test setup direct. Avoid mock frameworks and test-only abstraction layers unless interaction behavior cannot be checked more simply.
- Comment reasons, protocol details, units, magic values, compatibility constraints, fallbacks, and non-obvious performance choices.
- Do not narrate code that is already clear from its names and control flow.
- Use Rustdoc for public contracts and surprising behavior, not to restate every signature.
- Do not preserve abandoned alternatives or routine diagnostics as commented-out code.

## Code That Does Not Match

- Deep `domain/service/repository/adapter` layering for a small program.
- A trait and generic implementation for every component despite having one implementation.
- Splitting cohesive logic across many tiny files solely to enforce file-size limits.
- A global `models` module filled with types used by only one feature.
- Generic provider frameworks that obscure small differences between concrete integrations.
- Noun-only or vague function names when the operation can be stated directly.
- Public-by-default modules, fields, and helpers.
- Long iterator chains that hide state transitions or error handling.
- Hand-written loops for simple stateless transformations when a short iterator expression is clearer.
- Custom error taxonomies without caller-visible recovery behavior.
- Defensive clones, allocations, or abstractions introduced without a concrete need.
- Comments that repeat syntax, stale commented-out code, and broad lint suppressions used instead of fixing local issues.

## Final Check

Before returning new or revised Rust code, verify that:

- Every crate, module, file, wrapper, trait, and dependency has a concrete responsibility.
- Cohesive behavior remains together, while genuine peer responsibilities are separated.
- Types live beside the code that owns their meaning.
- A deliberate naming pass found concrete function actions, compact local names, and abbreviated parameters in short closures.
- Iterators handle stateless transformations and loops handle stateful workflows.
- Errors distinguish propagation, expected absence, item-level failure, and internal invariants.
- Visibility exposes only the API required by actual callers.
- Tests target rules and boundaries rather than implementation ceremony.
- Comments explain decisions or external constraints rather than restating the code.
- The result looks like a direct solution to the current problem, not a reusable framework for imagined future work.
