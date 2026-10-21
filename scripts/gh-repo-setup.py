#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Usage: scripts/gh-repo-setup.py [--apply] [REPO...]

Sets up vladkens' public GitHub repos the same way. Without REPO it checks the repos in REPOS
below; name any other repo (a new one, say) to check that. Prints what differs and changes
nothing; --apply makes the changes. Safe to repeat: what already matches stays untouched.

What a set-up repo has:
- Features: Issues only; no Wiki, Projects tab or Discussions.
- Merging: squash only, the commit titled by the PR; the branch deleted after merge; an
  "Update branch" button on PRs.
- main: changed only through PRs; no force-push, no deletion, nobody bypasses (you included);
  every review thread resolved before merge; Copilot reviews each push; the CI jobs in REPOS
  green before merge.
- Release tags vX.Y.Z: never deleted or moved (CI can still create them; `v1` can move).
- Safety: Dependabot alerts about vulnerable dependencies (no PRs); secret scanning that also
  blocks pushes with secrets; a private way to report vulnerabilities; CI's token read-only
  and unable to approve PRs. CI on fork PRs keeps GitHub's default: only a first-time
  contributor's PR waits for your approval.
"""

import json
import subprocess
import sys
from collections.abc import Callable

OWNER = "vladkens"

# The repos worth keeping in shape, each with the CI jobs its PRs must pass. Name only a job that
# runs on every PR under that exact name: a required job that never runs blocks merging forever
# (a matrix job is named per version, e.g. "test (3.12)", so leave those out).
REPOS = {
    "wavo": ["test"],
    "nimbo": ["test"],
    "macmon": ["test"],  # from pull.yml
    "cctrail": ["test"],
    "clankr": ["ubuntu-latest", "macos-latest"],  # matrix by OS
    "unjar": ["test"],  # from pull.yml
    "badgelib": ["test"],  # from pull.yml
    "twscrape": [],  # matrix
    "ghstats": ["build"],
    "apigen-ts": [],  # matrix
}

ACTIONS_APP = 15368  # GitHub Actions, the app CI check runs come from

# Repo settings: (API field, wanted value, what it means).
SETTINGS = [
    ("has_issues", True, "Issues"),
    ("has_wiki", False, "Wiki"),
    ("has_projects", False, "Projects tab"),
    ("has_discussions", False, "Discussions"),
    ("allow_squash_merge", True, "squash merge"),
    ("allow_merge_commit", False, "merge commits"),
    ("allow_rebase_merge", False, "rebase merge"),
    ("squash_merge_commit_title", "PR_TITLE", None),
    ("squash_merge_commit_message", "BLANK", None),
    ("delete_branch_on_merge", True, "deleting the branch after merge"),
    ("allow_update_branch", True, '"Update branch" button on PRs'),
]
TOKEN = {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}

# Rule parameters in plain words, for reporting a changed ruleset.
RULE_WORDS = {
    "required_review_thread_resolution": "review threads resolved before merge",
    "allowed_merge_methods": "allowed merge methods",
    "required_approving_review_count": "required approvals",
    "review_on_push": "Copilot review on each push",
    "review_draft_pull_requests": "Copilot review of drafts",
    "required_status_checks": "required CI jobs",
}


def main_rules(checks: list[str]) -> dict:
    rules = [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": True,
                "allowed_merge_methods": ["squash"],
            },
        },
        {
            "type": "copilot_code_review",
            "parameters": {"review_on_push": True, "review_draft_pull_requests": False},
        },
    ]
    if checks:
        rules.append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": False,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": c, "integration_id": ACTIONS_APP} for c in checks
                    ],
                },
            }
        )

    return ruleset("main", "branch", "~DEFAULT_BRANCH", rules)


def ruleset(name: str, target: str, ref: str, rules: list[dict]) -> dict:
    return {
        "name": name,
        "target": target,
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [ref], "exclude": []}},
        "rules": rules,
    }


# Only v*.*.*, so a moving major tag like vladkens/actions' `v1` stays movable.
TAGS = ruleset(
    "release tags", "tag", "refs/tags/v*.*.*", [{"type": "deletion"}, {"type": "update"}]
)


def api(path: str, method: str = "GET", body: dict | None = None, missing_ok: bool = False):
    """`gh api`: the parsed JSON ({} when empty), or None for a 404 with missing_ok."""
    args = ["gh", "api", "-X", method, path]
    if body is not None:
        args += ["--input", "-"]

    p = subprocess.run(
        args,
        input=None if body is None else json.dumps(body),
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        if missing_ok and "HTTP 404" in p.stderr:
            return None

        sys.exit(f"gh api -X {method} {path}: {(p.stderr or p.stdout).strip()}")

    return json.loads(p.stdout) if p.stdout.strip() else {}


def onoff(on: bool, what: str) -> str:
    return f"turn {'on' if on else 'off'}: {what}"


def ruleset_diff(have: dict, want: dict) -> list[str]:
    """How `have` differs in what `want` sets, in plain words (GitHub adds other parameters)."""
    if any(have.get(k) != want[k] for k in ("target", "enforcement", "conditions")):
        return ["rewrite it: it is off or covers other branches/tags"]

    diff = []
    if have.get("bypass_actors"):
        diff.append("remove its bypass list: nobody skips the rule")

    have_rules = {r["type"]: r.get("parameters", {}) for r in have.get("rules", [])}
    want_rules = {r["type"]: r.get("parameters", {}) for r in want["rules"]}
    diff += [f"add rule: {t}" for t in want_rules.keys() - have_rules.keys()]
    diff += [f"drop rule: {t}" for t in have_rules.keys() - want_rules.keys()]
    for t in want_rules.keys() & have_rules.keys():
        for k, v in want_rules[t].items():
            if have_rules[t].get(k) == v:
                continue

            if k == "required_status_checks":
                v = [c["context"] for c in v]

            diff.append(f"{RULE_WORDS.get(k, k)}: {have_rules[t].get(k)} → {v}")

    return diff


class Repo:
    def __init__(self, name: str, checks: list[str]):
        self.full, self.checks = f"{OWNER}/{name}", checks
        self.changes: list[tuple[list[str], Callable]] = []  # (what, how to make it)

    def change(self, what: str | list[str], apply: Callable) -> None:
        self.changes.append(([what] if isinstance(what, str) else what, apply))

    def plan(self) -> list[str]:
        """Collects the changes; returns warnings."""
        r = api(f"repos/{self.full}")
        if r["archived"]:
            return ["archived: skipped"]

        if r["private"]:
            return ["private: skipped (rulesets and secret scanning need a paid plan there)"]

        body = {key: want for key, want, _ in SETTINGS if r.get(key) != want}
        shown = [onoff(want, what) for key, want, what in SETTINGS if key in body and what]
        if {"squash_merge_commit_title", "squash_merge_commit_message"} & body.keys():
            body |= {key: want for key, want, _ in SETTINGS if key.startswith("squash_merge_commit")}
            shown.append("squash commit: the PR title only")

        sa = r.get("security_and_analysis") or {}
        security = {
            key: {"status": "enabled"}
            for key in ("secret_scanning", "secret_scanning_push_protection")
            if sa.get(key, {}).get("status") != "enabled"
        }
        if security:
            body["security_and_analysis"] = security
            shown.append(onoff(True, "secret scanning, blocking pushes with secrets"))

        if body:
            self.change(shown, lambda: api(f"repos/{self.full}", "PATCH", body))

        token = api(f"repos/{self.full}/actions/permissions/workflow")
        if any(token.get(k) != v for k, v in TOKEN.items()):
            self.change(
                "CI token: read-only, can't approve PRs",
                lambda: api(f"repos/{self.full}/actions/permissions/workflow", "PUT", TOKEN),
            )

        if api(f"repos/{self.full}/vulnerability-alerts", missing_ok=True) is None:
            self.change(
                onoff(True, "Dependabot alerts about vulnerable dependencies (no PRs)"),
                lambda: api(f"repos/{self.full}/vulnerability-alerts", "PUT"),
            )

        if not api(f"repos/{self.full}/private-vulnerability-reporting").get("enabled"):
            self.change(
                onoff(True, "private vulnerability reports to you"),
                lambda: api(f"repos/{self.full}/private-vulnerability-reporting", "PUT"),
            )

        existing = {
            s["name"]: s for s in api(f"repos/{self.full}/rulesets?includes_parents=false") or []
        }
        main = main_rules(self.checks)
        self.plan_ruleset(
            existing.pop("main", None),
            main,
            "add rule for main: PRs only (squash), no force-push or deletion, threads resolved, "
            + "Copilot review"
            + (f", CI jobs {', '.join(self.checks)} green" if self.checks else ""),
        )
        self.plan_ruleset(
            existing.pop("release tags", None),
            TAGS,
            "add rule: release tags vX.Y.Z can't be deleted or moved",
        )
        return [f"extra rule '{n}' kept: delete it if it only repeats the main rule" for n in existing]

    def plan_ruleset(self, summary: dict | None, want: dict, created: str) -> None:
        if summary is None:
            self.change(created, lambda: api(f"repos/{self.full}/rulesets", "POST", want))
            return

        have = api(f"repos/{self.full}/rulesets/{summary['id']}")
        if diff := ruleset_diff(have, want):
            self.change(
                [f"rule '{want['name']}': {d}" for d in diff],
                lambda: api(f"repos/{self.full}/rulesets/{have['id']}", "PUT", want),
            )


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    names = [a for a in args if a != "--apply"]
    if any(a.startswith("-") for a in names):
        sys.exit(__doc__)

    dirty = 0
    for name in names or REPOS:
        repo = Repo(name, REPOS.get(name, []))
        warnings = repo.plan()
        status = "ok" if not repo.changes else ("changed" if apply else "to change")
        print(f"{name}: {status}")
        for what, do in repo.changes:
            for line in what:
                print(f"  - {line}")

            if apply:
                do()

        for w in warnings:
            print(f"  ! {w}")

        dirty += bool(repo.changes)

    if dirty and not apply:
        print(f"\n{dirty} repo(s) to change; run again with --apply to change them")
        sys.exit(1)


if __name__ == "__main__":
    main()
