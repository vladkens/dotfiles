---
name: git-changelog
description: Generate user-facing release notes from Git history and update changelog.md for v-prefixed releases. Use when the user asks to create, update, backfill, or prepare a changelog or release notes.
---

# Changelog Generator

Generate user-facing release entries and update `changelog.md`.

The file is consumed by CI release pipelines via awk — format must be exact.

> **IMPORTANT: ALWAYS CHECK CHANGELOG CONSISTENCY BEFORE WRITING ANYTHING.** Compare all v-prefixed release tags against all `## v...` headers in `changelog.md`. If ANY tags are missing from the file — generate entries for ALL of them, not just the current version. A changelog that skips releases is broken. Every tag must have an entry.

## Workflow

### Step 1: Detect project type and version

Check for these files in order to detect project type and current version:

- `Cargo.toml` — Rust; read `version` under `[package]`
- `package.json` — Node.js; read the top-level `version`
- `pyproject.toml` — Python; read `version` under `[project]` or `[tool.poetry.project]`
- None of the above — treat the repository as generic and ask the user for the version

If the user passed a version argument, use that instead (normalise: add `v` prefix if missing).

### Step 2: Determine which versions are missing

Get all existing tags sorted newest-first:

```bash
git tag --list 'v*' --sort=-version:refname
```

Read `changelog.md` if it exists and collect all version headers already present (lines matching `## vX.Y.Z`).

Compare the two lists and the current project version:

1. Collect every tagged version that has no changelog entry.
2. Add the current project version if it has no entry. Do not add it twice when it is already one of the missing tags.
3. If no versions are missing, tell the user and stop.
4. If versions are missing, report how many and generate entries for all of them.

Never stop only because the current version already has an entry: backfill any older tagged versions that are still missing.

### Step 3: Run the collection script

Run the bundled script from the project root. It collects tags, dates, commits, and contributor usernames in one shot, using the GitHub API only where necessary:

```bash
<skill-dir>/scripts/collect-git-info.py
```

Contributor detection logic:

- Author email ends with `@users.noreply.github.com` → parse username directly from email, no API call
- Committer = `noreply@github.com` (GitHub squash merge) → call `gh pr view {N} --repo <owner/repo> --json author` for the PR author
- Author ≠ committer (cherry-picked patch) → call `gh api .../commits/{sha}` for the author

Output format:

```
REPO=vladkens/macmon

=== v0.6.1 | 2025-06-02 | prev=v0.6.0 ===
  COMMIT | <sha> | aliasaria | Only show soc info if --soc-info argument is passed
  COMMIT | <sha> |  | maintenance
  COMMIT | <sha> | aliasaria | adds soc info to pipe json

=== v0.6.0 | 2025-02-26 | prev=v0.5.1 ===
  COMMIT | <sha> |  | feat: smooth temp if no sensor value on m3/m4 chips #12
```

Fields: `COMMIT | sha | github_username_or_empty | commit subject`

The script also outputs an `UNRELEASED` block for commits after the latest tag (the upcoming version).

> **IMPORTANT: The script output already contains all contributor usernames. Do NOT make any additional `gh api` or `git` calls to look up PR authors or committer info. Use only what the script printed.**

Use the script output to generate entries for all missing versions. If the username field is non-empty, append `(by @username)` to the relevant changelog item.

### Step 4: Write the entry

Analyse the commits and produce a user-facing changelog entry.

Changelog entries describe the **net user-visible difference between the previous released version and the version being released**. Commits are evidence, not one-to-one changelog items.

Before writing sections:

- Identify the final behavior shipped in the release range, not every intermediate state.
- If one unreleased commit adds behavior and a later unreleased commit fixes, reverts, or refines that same behavior, describe only the final behavior.
- Do not write a `### Fixes` item for a bug that only existed in unreleased work inside the same release range. Fold that correction into the feature/improvement wording instead.
- A `### Fixes` item must fix a problem present in the previous released version.

**Include:**

- New features visible to the user (new commands, flags, options, UI elements, outputs, endpoints)
- Bug fixes that affected the user experience or correctness of output
- Breaking changes or removed features
- Notable performance improvements the user would notice
- New installation methods or platform support

**Exclude:**

- CI/CD and build system changes
- Code refactoring with no user-visible effect
- Dependency version bumps without user-visible effect, unless the release would otherwise have no notes; in that case group notable dependency/runtime/data updates under `### Maintenance`
- Formatting, linting, chores, typo fixes in code
- Internal tooling, developer experience improvements
- Test additions
- Documentation updates that only describe code changes in the same release
- README-only wording, formatting, badge, sponsor, donation, marketing, or attribution changes unless the user explicitly asks to include them

Special cases:

- Optional backends, install extras, platform support, public APIs, CLI commands, and user-selectable runtime modes are Features when they are new in the release.
- Use `### Maintenance` for release-worthy upkeep that is not a feature, bug fix, docs deliverable, or user-facing improvement, such as updated external service operation IDs, compatibility data, generated metadata, or dependency refreshes included as the main release content.
- Telemetry, analytics, and internal instrumentation are not Features. Mention them only when the release note is important for users, and place opt-out/privacy wording under Improvements or Docs as appropriate.
- Use `### Docs` only for substantial documentation deliverables users would care about on their own, such as a new migration guide, tutorial, reference page, or policy users must understand. Do not add `### Docs` for README-only cleanup, sponsor blocks, badges, funding links, marketing copy, wording changes, typo fixes, or docs added to explain another item already listed above.

**Sections — use the sections that match the release content, even if a section has only one item:**

```markdown
### Features

- Added X

### Fixes

- Fixed Y

### Docs

- Updated Z
```

Available sections (use only what's needed, in this order): `### Breaking Changes`, `### Features`, `### Fixes`, `### Improvements`, `### Maintenance`, `### Docs`. Add `### Breaking Changes` at the top if any exist.

**Style rules:**

- Plain English, no jargon or implementation details
- Past tense: "Added", "Fixed", "Improved", "Updated", "Removed"
- Each item starts with a capital letter
- If the commit message contains a `#NNN` reference (issue or PR number), append it at the end of the item in parentheses
- If the item also has an external contributor, combine both: `(#123, by @username)`
- Format: `- Added something useful (#28)` or `- Fixed a bug (#42, by @someone)`
- Extract `#NNN` directly from the commit message — no API calls needed for this

### Step 5: Write all entries to changelog.md

Write release blocks in descending version order. Put the current unreleased version first. Insert backfilled historical versions at their correct position instead of prepending them above newer existing releases. If the file does not exist, create it.

Exact format (spacing matters for the awk extractor):

```markdown
## v<version> – YYYY-MM-DD

### Features

- Added X (#12, by @contributor)

### Fixes

- Fixed Y (#19)

**Full Changelog**: https://github.com/<owner>/<repo>/compare/<prev_tag>...v<version>
```

When another release block follows, separate the blocks exactly like this:

```markdown
**Full Changelog**: https://github.com/<owner>/<repo>/compare/<prev_tag>...v<version>

---

## v<previous-version> – YYYY-MM-DD
```

Do not add a trailing `---` after the final release block.

Format rules:

- `–` is an en-dash (U+2013), not a hyphen.
- For past releases use the **tag date** (from `git log -1 --format=%as`), not today's date.
- For the current unreleased version use **today's date**.
- Full Changelog uses three dots `...` (GitHub compare syntax).
- If no previous tag: use `.../commits/v<version>` instead.
- If remote is not GitHub: omit Full Changelog line.
- One blank line between the `##` header and the first `###` section.
- Put one blank line around the `---` separator between release blocks.

## Rules

1. File name is always `changelog.md` — all lowercase.
2. Version header: `## v<version> – YYYY-MM-DD` (en-dash). The awk extractor matches as prefix so the date does not break it.
3. Always use `###` sections. Never write a flat list without a section header.
4. No separate Contributors section. Attribution goes inline as `(by @username)` on the relevant item only.
5. Write in English only.
6. If no user-facing or release-worthy maintenance changes are found, say so and ask the user what to include.

## CI integration note

The release pipeline skips the `##` header line and strips the `---` separator:

```bash
VERSION="${GITHUB_REF_NAME}"   # e.g. v1.2.0
NOTES=$(awk "/^## ${VERSION}/{found=1; next} /^## /{found=0} found" changelog.md | sed '/^---$/d')
echo "$NOTES" > release_notes.txt
```

The awk pattern `/^## ${VERSION}/` matches as a prefix — the date suffix in the header (`## v1.2.0 – 2026-04-01`) does not break extraction. GitHub release title is the tag name set automatically. Body contains sections + Full Changelog link.

## Example

User says: `/changelog`

1. Detects `Cargo.toml` → `v0.7.0`
2. No existing entry → proceed
3. git log since `v0.6.1`: 6 unreleased commits; today's date is `2026-04-01`
4. Commit messages contain: `feat: add --interval flag #16`, `feat: gpu temp display #12` (PR by `@contributor1`), `fix: memory usage on M3 #19`
5. Updates `changelog.md`:

```markdown
## v0.7.0 – 2026-04-01

### Features

- Added `--interval` flag to control the refresh rate (#16)
- Added GPU temperature display (#12, by @contributor1)

### Fixes

- Fixed incorrect memory usage reported on M3 chips (#19)

**Full Changelog**: https://github.com/vladkens/macmon/compare/v0.6.1...v0.7.0
```

Take your time with Step 4 — accuracy matters more than speed. When in doubt about whether a commit is user-facing, lean toward excluding it.
