---
name: code-style-python
description: Apply the user's established coding style to Python code. Use when the user asks to implement, refactor, or review Python code in their personal style, not for generic Python guidance.
---

# Python Code Style

Use these rules as a decision guide, not as a mechanical linter. Preserve explicit task requirements and established project conventions. Do not refactor unrelated code merely to make it match this style.

## Overall Character

- Prefer concrete, compact, operational code over framework-like architecture.
- Keep the implementation proportional to the problem. Add a layer only when it owns a stable responsibility or removes meaningful complexity.
- Make the actual data flow visible: load, normalize, filter, merge, save, retry, or report.
- Prefer ordinary functions, dictionaries, comprehensions, generators, and explicit state over elaborate object models.
- Accept small amounts of local duplication when a shared abstraction would hide meaningful differences or create indirect behavior.

## Packages, Modules, and Files

- Organize modules around stable responsibilities such as configuration, storage, parsing, API access, collection, or export.
- Keep the package tree shallow. Introduce a directory only for a genuine family of peer modules.
- Do not split a cohesive module because it has become long. Split it when parts have different responsibilities, dependencies, lifecycles, or reasons to change.
- Keep closely related data definitions, parsing logic, helpers, and workflow code together when they form one readable unit.
- Create a shared helper module only after multiple real consumers need the same behavior.
- Collapse or remove a module when its contents are meaningful only to one owner and the separate boundary no longer helps.
- For a sequential operational pipeline, filenames may encode execution order. Do not use numbered filenames in an ordinary reusable package.
- Keep executable entry points direct: parse arguments, initialize resources, select the operation, and call domain functions.
- Use `__init__.py` as a small public facade for a reusable library. Internal packages may leave it empty.

## Types and Function Placement

- Define a type beside the code that owns its meaning or conversion rules.
- Use `@dataclass` for transparent value objects and structured public results.
- Use `TypedDict` for dictionary-shaped records passed through ETL, SQL, or serialization boundaries.
- Use an ordinary `dict` for local transformations that do not need a reusable named contract.
- Preserve external field names when compatibility requires them. Use `snake_case` for new locally owned fields and APIs.
- Use a class when it owns state, a resource, an invariant, or a coherent group of operations.
- Prefer free functions when object state is unnecessary.
- Keep a private helper in the same module as its only consumer.
- Define a helper inside another function when it is meaningful only to that workflow and benefits from its local context.
- Order an executable module for top-down reading: constants and types, helpers, the main workflow, `main()`, then the `__main__` guard.

General choices:

```python
@dataclass
class Record:
    key: str
    count: int


class Row(TypedDict):
    key: str
    count: int
```

Use the dataclass when values have object behavior or form a stable public result. Use the `TypedDict` when the record remains dictionary-shaped throughout a data pipeline.

## Naming

- Use short, concrete module and type names that state the owned concept, such as `Config`, `Client`, `Record`, `Job`, or `Queue`.
- For operation functions, prefer direct action prefixes such as `get_`, `load_`, `fetch_`, `parse_`, `make_`, `save_`, `insert_`, `merge_`, `remove_`, `report_`, `export_`, `check_`, or `validate_`.
- Prefer a direct verb-object name over a vague noun or generic lifecycle term, but do not add an action prefix to a fixture, callback, nested helper, or established domain name whose role is already clear.
- Use `make_` only when a function constructs and returns a new value or resource.
- Prefix a module-level function with `_` only when it is a short implementation helper confined to that file.
- Do not prefix a nested or otherwise local function with `_`; its lexical scope already hides it.
- Never import or re-export an `_`-prefixed module helper. If another module needs it, move the responsibility or expose a deliberate non-underscored API.
- In a reusable library, `_` may additionally mark technically accessible internals that callers should not use. Do not apply that library-facing signal mechanically to application code.
- Preserve established domain acronyms instead of expanding them into unnatural names.
- Use familiar abbreviations in narrow scopes, especially `db`, `ctx`, `cfg`, `req`, `rep`, `res`, `obj`, `doc`, `cur`, `idx`, `uid`, and domain-specific IDs.
- Prefer descriptive names at module and API boundaries. Short names are appropriate only when their meaning is immediate from a small scope.
- Use `T`, `P`, and `R` only for narrow mechanical typing helpers. Give domain callbacks and records concrete names.
- Do not introduce verbose suffixes such as `Manager`, `Service`, `Factory`, `Processor`, or `Interface` unless the object genuinely represents that role.

## Data Flow and Control Flow

- Express a transformation as a short sequence of visible stages, often by rebinding the same local variable.
- Use comprehensions for simple mapping, filtering, indexing, and collection.
- Use explicit loops for mutation, multiple accumulators, retries, side effects, and workflows with several exit conditions.
- Prefer early returns and `continue` over deep nesting.
- Use generators for streaming, pagination, chunking, file walking, and potentially large result sets.
- Treat local mutation as normal when a record is progressively normalized or enriched.
- Keep branching close to the data or response it interprets.
- Use a small local function for a callback or bounded job when moving it to module scope would remove useful context.
- Choose concurrency by workload: async I/O for network and server orchestration, a semaphore for bounded request concurrency, and multiprocessing for CPU-heavy batch work.

General transformation shape:

```python
items = load_items()
items = [item for item in items if is_valid(item)]
items = sorted(items, key=lambda item: item.key)
```

Do not replace a clear sequence like this with a generic pipeline abstraction.

## Blank Lines Around Control Flow

- Put one blank line after every completed multi-line `if` or `for` block before the next statement at the same indentation level.
- Do not put that blank line before `elif` or `else`, because they continue the same `if` statement.
- Do not add a trailing blank line when the `if` or `for` block is already the final statement in its enclosing scope.

Write:

```python
if len(row) != expected:
    raise ValueError(f"Invalid row: {row}")

return parse_row(row)
```

And:

```python
for item in items:
    process(item)

save_results(items)
```

## Abstractions and Dependencies

- Start with concrete functions and types.
- Introduce a wrapper when it owns a client, connection, cache, retry policy, configuration, or another persistent resource.
- Use a small local decorator for a repeated mechanical concern such as retry, caching, timing, or output grouping.
- Keep generics and protocols narrow. Do not make domain architecture generic in anticipation of hypothetical implementations.
- Use established packages for substantial capabilities such as HTTP, async database access, HTML parsing, CLI parsing, serialization, and data processing.
- Write local helpers for small glue operations such as chunking, nested lookup, simple caching, or file traversal.
- Prefer direct SQL and a thin connection helper when the query is important to understanding behavior.
- Do not add a repository or ORM layer that merely hides straightforward data access.
- Remove a dependency, service, or abstraction when the surrounding workflow becomes simpler and it no longer carries its weight.
- Do not unify similar integrations merely because they share a superficial shape. Keep concrete implementations separate when their data and failure modes differ.

## Error Handling

- Handle expected errors near the unstable operation that produces them.
- In reusable code, distinguish outcomes that require different recovery behavior, such as retrying, switching a resource, returning no result, or aborting the operation.
- Use a small custom exception only when callers handle it differently or it communicates a real boundary.
- Represent expected absence with `None`, an empty collection, or an explicit default.
- In batch processing, isolate item-level failures when later items remain useful. Log, dump, collect, or skip the failed item deliberately.
- Catch specific exceptions for expected failure modes. Catch `Exception` only at a deliberate batch, worker, CLI, or service boundary.
- Never silently swallow an unexpected exception in maintained code.
- Use `assert` for internal invariants, trusted data-shape assumptions, and executable checks, not for ordinary user input validation.
- Keep retry behavior next to the client, database, queue, or request that needs it. Bound retries unless the program is intentionally a long-running worker waiting for external recovery.
- Preserve useful diagnostic context such as the item identifier, response status, operation, or dump location.

## Visibility and Public API

- Treat a module-level `_name` as file-private implementation and keep every use of it in that file.
- Expose a small library facade instead of requiring callers to know the internal module tree.
- In library code, use `_name` to mark reachable internals that are not supported public API.
- In application code, do not add `_` merely to warn other modules away. Use it only for a helper intentionally confined to the file.
- For methods and fields, use `_` only when the class has a meaningful public/internal boundary; do not rename every implementation detail mechanically.
- Let transparent dataclasses and records expose their data directly.
- Do not add getters, abstract interfaces, or facade objects solely to hide a straightforward record.
- Keep raw and parsed API variants separate only when both are genuinely useful to callers; use a clear suffix such as `_raw`.

## Tests and Comments

- For reusable libraries, write focused pytest tests around parsing, resource lifecycle, retries, state transitions, and regression cases.
- Prefer realistic fixtures and small fakes over elaborate mock frameworks.
- Test observable behavior and invariants rather than the internal sequence of helper calls.
- Name regression tests after the behavior or bug they protect when that context is useful.
- For operational tools, a direct executable end-to-end checker with assertions is acceptable when the real boundary is a process, filesystem, database, or remote service.
- Keep test setup direct. Add factories or shared fixtures only when repetition is material.
- Comment protocol quirks, units, magic values, compatibility constraints, retry reasons, fallbacks, and non-obvious performance choices.
- Use short section comments to make a long cohesive module navigable.
- Do not narrate code that is already clear from its names and control flow.
- Use docstrings for public contracts and genuinely surprising behavior, not to restate every signature.
- Do not preserve abandoned alternatives, routine diagnostics, or temporary experiments as commented-out code.

## Code That Does Not Match

- Deep `domain/service/repository/adapter` layering for a small program.
- A class for every operation despite having no state.
- Abstract base classes, protocols, or dependency injection with one implementation.
- Pydantic or dataclass models for every temporary dictionary.
- Splitting a cohesive parser or workflow across many tiny files solely to limit file size.
- A repository or ORM layer that obscures important simple SQL.
- Long fluent pipelines that hide intermediate data and failure points.
- Avoiding local mutation when a record is naturally enriched in stages.
- Large custom exception taxonomies without distinct recovery behavior.
- A generic retry, cache, or provider framework for a small local concern.
- Verbose public names that avoid familiar domain abbreviations.
- Adding `_` to a nested helper whose scope is already local.
- Importing or re-exporting an `_`-prefixed helper from another module.
- Adding `make_` or another action prefix to a clear fixture, callback, or local name without changing what the name communicates.
- Broad exceptions swallowed without diagnostics.
- Tests dominated by mock scaffolding rather than behavior.
- Docstrings and comments that repeat the code.
- Stale commented-out code, hardcoded temporary switches, wildcard imports, and accidental shadowing treated as conventions.

## Final Check

Before returning new or revised Python code, verify that:

- Every package, module, class, decorator, and dependency has a concrete responsibility.
- Cohesive behavior remains together, while genuinely independent responsibilities are separated.
- Structured types live beside the code that owns their meaning.
- Dataclasses, `TypedDict`, and plain dictionaries are used for the roles they fit.
- Names are direct, compact, and understandable in their scope.
- Every module-level `_name` is confined to its file, and no local helper received a redundant `_` prefix.
- Transformations are visible as simple stages, comprehensions, generators, or explicit loops.
- Completed `if` and `for` blocks are followed by a blank line before the next sibling statement.
- Error handling distinguishes expected absence, recoverable failure, item-level failure, and internal invariants.
- Retries and resource ownership are located near the relevant boundary.
- Tests target behavior, regressions, and real integration boundaries without unnecessary scaffolding.
- Comments explain decisions or external constraints rather than restating syntax.
- The result looks like a direct solution to the current problem, not a reusable framework for imagined future work.
