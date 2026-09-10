# Plan Template

Use this template for `docs/plans/yyyymmdd-<task-name>.md`.

```markdown
# [Plan Title]

## Overview

- clear description of the feature/change being implemented
- problem it solves and key benefits
- how it integrates with the existing system

**Acceptance criteria**:

- [requirement 1]
- [requirement 2]
- [requirement 3]

## Context (from discovery)

- research source: [`docs/research/...`, if applicable]
- files/components involved: [list]
- related patterns found: [patterns]
- dependencies identified: [dependencies]
- risks or unknowns: [risks]

## Development Approach

- **testing approach**: [TDD / Regular]
- complete each task fully before moving to the next
- make small, focused changes
- every code-changing task must include new or updated tests
- all tests for a task must pass before starting the next task
- update this plan file when scope changes during implementation
- maintain backward compatibility unless the plan explicitly says otherwise

## Testing Strategy

- **unit tests**: [what to test]
- **integration/e2e tests**: [if applicable]
- **regression tests**: [existing behavior to preserve]
- **commands**:
  - `[test command]`
  - `[lint/typecheck command]`

## Progress Tracking

- mark completed items with `[x]` immediately when done
- add newly discovered tasks with a `+` prefix
- document issues/blockers with a `!` prefix
- keep this plan in sync with actual implementation decisions

## Solution Overview

- high-level approach and architecture chosen
- key design decisions and rationale
- how it fits into the existing system

## Technical Details

- data structures and changes
- parameters and formats
- processing flow
- error handling

## What Goes Where

- **Implementation Steps**: tasks achievable within this codebase
- **Post-Completion**: manual or external follow-up without checkboxes

## Implementation Steps

### Task 1: [specific name]

**Files:**

- Create: `path/to/new_file`
- Modify: `path/to/existing_file`

- [ ] [specific implementation action]
- [ ] [specific implementation action]
- [ ] write tests for success cases
- [ ] write tests for error/edge cases
- [ ] run tests - must pass before next task

### Task 2: [specific name]

**Files:**

- Modify: `path/to/existing_file`
- Modify: `tests/path/to/test_file`

- [ ] [specific implementation action]
- [ ] [specific implementation action]
- [ ] update tests for changed behavior
- [ ] run tests - must pass before next task

### Task N-1: Verify acceptance criteria

- [ ] verify all requirements from Overview are implemented
- [ ] verify edge cases are handled
- [ ] run full test suite: `[command]`
- [ ] run lint/typecheck: `[command]`

### Task N: Final documentation

- [ ] update README or project docs if needed
- [ ] update this plan if actual implementation differs
- [ ] move this plan to `docs/plans/completed/` when done

## Post-Completion

_Items requiring manual intervention or external systems - no checkboxes, informational only_

**Manual verification**:

- [scenario]

**External system updates**:

- [deployment/config/third-party follow-up]
```
