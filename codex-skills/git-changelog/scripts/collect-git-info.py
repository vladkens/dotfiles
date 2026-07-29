#!/usr/bin/env python3
"""
Collects git info needed for changelog generation.

Skips versions already present in changelog.md — no redundant API calls.
Detects external contributors via committer signatures and GitHub noreply emails.
Fetches GitHub usernames from API only when necessary.

Runs against the repository containing the current directory.
"""

import json
import os
import re
import subprocess
import sys

RELEASE_TAG_RE = re.compile(r"^v\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?$")


def run(cmd, required=True):
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        if required:
            message = res.stderr.strip() or res.stdout.strip()
            print(f"ERROR: {' '.join(cmd)} failed: {message}", file=sys.stderr)
            sys.exit(res.returncode)
        return ""
    return res.stdout.strip()


def run_json(cmd, required=False):
    out = run(cmd, required=required)
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        if required:
            print(f"ERROR: {' '.join(cmd)} returned invalid JSON", file=sys.stderr)
            sys.exit(1)
        return None


def gh_api(path, required=False):
    return run_json(["gh", "api", path], required=required)


def gh_pr_author(repo, pr_num, required=False):
    cmd = ["gh", "pr", "view", pr_num, "--repo", repo, "--json", "author"]
    data = run_json(cmd, required=required)
    author = (data or {}).get("author") or {}
    return author.get("login") or ""


def parse_repo(remote_url):
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    return m.group(1) if m else None


def parse_github_noreply(email):
    """Extract GitHub username from *@users.noreply.github.com email."""
    if not email.endswith("@users.noreply.github.com"):
        return None
    local = email.split("@")[0]
    return local.split("+", 1)[1] if "+" in local else local


def get_contributor(commit, repo):
    """Return GitHub username of external contributor, or empty string."""
    author_email = commit["author_email"]
    committer_email = commit["committer_email"]

    # GitHub noreply email → parse username directly, no API call
    username = parse_github_noreply(author_email)
    if username:
        return username

    if not repo:
        return ""

    # GitHub squash merge: committer is noreply@github.com
    if committer_email == "noreply@github.com":
        pr_nums = re.findall(r"#(\d+)", commit["subject"])
        for pr_num in pr_nums:
            username = gh_pr_author(repo, pr_num, required=True)
            if username:
                return username
        data = gh_api(f"repos/{repo}/commits/{commit['sha']}", required=True)
        if data and data.get("author"):
            return data["author"]["login"] or ""

    # Cherry-picked: author and committer differ
    if author_email != committer_email:
        data = gh_api(f"repos/{repo}/commits/{commit['sha']}", required=True)
        if data and data.get("author"):
            return data["author"]["login"] or ""

    return ""


def get_commits(range_ref):
    # Include merge commits — old-style GitHub PR merges have contributor info in subject
    out = run(["git", "log", range_ref, "--format=%H%x09%ae%x09%ce%x09%s"])
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append(
                {
                    "sha": parts[0],
                    "author_email": parts[1],
                    "committer_email": parts[2],
                    "subject": parts[3],
                }
            )
    return commits


def parse_merge_commit(subject):
    """For 'Merge pull request #N from user/branch' style commits.
    Returns (pr_number, username) or None."""
    m = re.match(r"Merge pull request #(\d+) from ([^/]+)/", subject)
    if m:
        return m.group(1), m.group(2)
    return None


def filter_version_bumps(commits):
    return [c for c in commits if not re.match(r"^v\d+\.\d+", c["subject"])]


def print_commits(commits, repo):
    for c in commits:
        subject = c["subject"]

        # Handle old-style GitHub PR merge commits
        merge_info = parse_merge_commit(subject)
        if merge_info:
            _, username = merge_info
            # Use the body of the merge commit as the actual subject
            body = run(["git", "log", "-1", "--format=%b", c["sha"]]).strip().splitlines()
            real_subject = body[0] if body else subject
            print(f"  COMMIT | {c['sha']} | {username} | {real_subject}")
            continue

        # Skip non-PR merge commits (e.g. "Merge branch 'main'")
        if subject.startswith("Merge "):
            continue

        author = get_contributor(c, repo)
        print(f"  COMMIT | {c['sha']} | {author} | {subject}")


def read_existing_versions(changelog_path):
    """Return set of version strings already in changelog.md, e.g. {'v0.6.1', 'v0.6.0'}."""
    if not os.path.exists(changelog_path):
        return set()
    versions = set()
    with open(changelog_path) as f:
        for line in f:
            m = re.match(r"^## (v[^\s]+)(?:\s|$)", line)
            if m:
                versions.add(m.group(1))
    return versions


def main():
    project_root = run(["git", "rev-parse", "--show-toplevel"])
    os.chdir(project_root)

    changelog_path = "changelog.md"
    existing_versions = read_existing_versions(changelog_path)

    remote_url = run(["git", "config", "--get", "remote.origin.url"], required=False)
    repo = parse_repo(remote_url)

    tags = []
    for t in run(["git", "tag", "--sort=version:refname"]).splitlines():
        tag = t.strip()
        if RELEASE_TAG_RE.fullmatch(tag):
            tags.append(tag)

    print(f"REPO={repo or ''}")
    print(f"EXISTING_VERSIONS={','.join(sorted(existing_versions))}")
    print()

    skipped = 0
    for i, tag in enumerate(tags):
        if tag in existing_versions:
            skipped += 1
            continue

        date = run(["git", "log", "-1", "--format=%as", tag])
        prev_ref = tags[i - 1] if i > 0 else ""
        range_ref = f"{prev_ref}..{tag}" if prev_ref else tag

        print(f"=== {tag} | {date} | prev={prev_ref} ===")
        print_commits(filter_version_bumps(get_commits(range_ref)), repo)
        print()

    if skipped:
        print(f"# Skipped {skipped} version(s) already in {changelog_path}")

    # Also output unreleased commits after the latest tag (for the upcoming version).
    if tags:
        latest_tag = tags[-1]
        range_ref = f"{latest_tag}..HEAD"
    else:
        latest_tag = ""
        range_ref = "HEAD"

    unreleased = filter_version_bumps(get_commits(range_ref))
    if unreleased:
        print(f"=== UNRELEASED | (HEAD) | prev={latest_tag} ===")
        print_commits(unreleased, repo)
        print()


if __name__ == "__main__":
    main()
