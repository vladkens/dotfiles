#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["tree-sitter>=0.26", "tree-sitter-bash>=0.25.1"]
# ///
"""A review gate for pushes in github.com/vladkens/* repositories.

  review                    review what changed since the last review, as much as it needs
  review --accept REASON …  reject the open findings, one reason per finding
  claim PR|BRANCH           this Claude Code session watches that PR's CI from now on
  release PR|BRANCH         nobody watches it any more
  status [--all]            what this session owns, or (--all) every owner in this repo

The pr-gate Claude Code mod (hooks/register.ts beside this script) gives the model these as its
review, claim, release and status tools; a person runs them by hand with
`uv run --script ~/.claude/skills/pr-gate/pr-gate.py <command>`. The mod feeds the hooks below one
JSON object on stdin. They fail open: on their own errors they exit 0.

  pre    {command, cwd} of a Bash call: when it is a `git push` of a branch whose changes pr-gate
         hasn't passed, prints why it is denied and exits 2
  post   {command, cwd, session_id, stdout, stderr} after that call went through: the session
         owns the branches it pushed
  stop   {session_id} at a Stop: while CI runs on an open PR this session owns, or once per pushed
         commit when it failed, prints why the turn goes on and exits 2, so nobody hears "done"
         before CI is green

What counts is the branch's own code changes against the default branch: the changed lines of
code files, without docs, lockfiles, tests, assets and whitespace. They are compared as a set of
lines, so a rebase that keeps them doesn't count as a change. Nothing changed since the last
review: no review. A lot of new code in the branch: a pass with the code-style skill of its
language first (STYLES; none for other languages), once. Otherwise a quick Codex review of the
delta (low effort) answers OK, FIX or DEEP. A deep review of the whole branch (high effort) runs
instead when the quick one says DEEP, the delta touches a risky path or adds `unsafe`, or the code
changed since the last deep review passed DEEP_LINES; at most DEEP_MAX per branch. A review that
can't run blocks, for the person to look at. State is kept per branch in <git common dir>/pr-gate/.

A session owns a branch when it pushed it or claimed it last (last one wins; subagents push for
their parent session), for OWN_TTL after that; only its owner's Stop waits for the branch's CI.
Owners of every repository are in OWNERS (PR_GATE_OWNERS overrides the path); a merged or closed
PR leaves it. Without a session id (Codex, a plain terminal) nothing is owned or gated.
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from itertools import takewhile
from pathlib import Path
from urllib.parse import quote

import tree_sitter_bash as tsbash
from tree_sitter import Language, Node, Parser

OWNER = re.compile(r"github\.com[:/]vladkens/")
# Commands that run the command after them, with their options that take a value.
WRAPPERS = {
    "env": {"-u", "-C"},
    "sudo": {"-u", "-g", "-p", "-r", "-t", "-C", "-D", "-R", "-T", "-U", "--user"},
    "xargs": {"-I", "-J", "-L", "-n", "-P", "-s", "-E", "-d", "-a", "-R", "-S"},
    "caffeinate": {"-t", "-w"},
    "command": set(),
    "exec": {"-a"},
    "time": set(),
    "nice": {"-n"},
    "nohup": set(),
    "timeout": {"-s", "-k"},
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Options of git and of git push that take the next word for their value.
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"}
PUSH_VALUED = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
# A push's argument that can't be known: the refspecs xargs adds, all of a command that won't parse.
UNKNOWN = "?"
HEADS = ("HEAD", "@")
BASH = Parser(Language(tsbash.language()))
EXEMPT = (
    "*.md",
    "*.markdown",
    "*.rst",
    "*.txt",
    "LICENSE*",
    "docs/*",
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "go.sum",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.webp",
    "*.ico",
)
TESTS = (
    "tests/*",
    "test/*",
    "tests.rs",
    "*_test.*",
    "*_tests.*",
    "*.test.*",
    "*.spec.*",
    "test_*",
)
RISKY = (
    "*migrat*",
    "auth/*",
    "auth.*",
    "*oauth*",
    "*secret*",
    "*credential*",
    "*crypto*",
    "*password*",
    ".github/workflows/*",
    "build.rs",
)
# Code-style skills in ~/.claude/skills/ by file extension; a script without one: by its shebang.
STYLES = {".rs": "code-style-rust", ".py": "code-style-python"}
STYLE_LINES = 300  # added code lines in the branch, mostly new rather than rewritten
DEEP_LINES = 400  # code lines changed since the last deep review
DEEP_MAX = 2
TIMEOUT = {"low": 5 * 60, "high": 9 * 60}  # below the 10 minutes an agent's command can run
OWNERS = Path(os.environ.get("PR_GATE_OWNERS") or Path.home() / ".cache/pr-gate/owners.json")
OWN_TTL = 12 * 3600  # a session stops watching a branch this long after its last push or claim

QUICK = """Quick review of a change. See it with: {diff}
Look only for real defects the change brings: bugs, wrong logic, unhandled errors, security
holes, data loss, races. Skip style, naming and nitpicks. Be brief.
{rejected}
List each finding as `- path:line: problem`. Then end with exactly one of these lines:
VERDICT: OK
VERDICT: FIX
VERDICT: DEEP <why>
OK when nothing is found. FIX when the findings above can each be fixed from what the diff
shows. DEEP when the change can't be judged from this diff alone: it relies on code elsewhere,
concurrency, data formats or a public API. If the change adds complexity it doesn't need, put a
line `COMPLEX: <why>` before the verdict."""

DEEP = """Thorough review of this branch's whole change. See it with: {diff}
Read the surrounding code as needed. Why it is reviewed in depth: {why}.
Look for real defects: bugs, wrong logic, invariants broken across files, unhandled errors,
security holes, data loss, races, broken APIs. Skip style and nitpicks.
{rejected}
List each finding as `- path:line: problem`. End with exactly one line: `VERDICT: OK` when
nothing is found, else `VERDICT: FIX`."""


def git(*args: str, cwd: str | Path | None = None) -> str:
    rs = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if rs.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {rs.stderr.strip()}")

    return rs.stdout.strip()


def matches(path: str, globs: tuple[str, ...]) -> bool:
    return any(fnmatchcase("/" + path, "*/" + g) for g in globs)


def fingerprint(changes: Counter) -> str:
    return hashlib.sha256(json.dumps(sorted(changes.items())).encode()).hexdigest()[:16]


def drift(a: Counter, b: Counter) -> Counter:
    """Changed lines in one set and not the other."""
    return (a - b) + (b - a)


def size(changes: Counter) -> int:
    return sum(changes.values())


@dataclass
class Repo:
    top: Path
    branch: str
    default: str  # origin/main
    head: str
    base: str  # merge base with the default branch
    state_file: Path
    st: dict

    @classmethod
    def open(
        cls, cwd: str | Path, fetch: bool = False, branch: str | None = None, head: str = "HEAD"
    ) -> "Repo | None":
        """The repository at cwd when the gate applies to it: ours, on a branch, not the default;
        with `branch`, that branch at commit `head` instead of the one checked out."""
        top = Path(git("rev-parse", "--show-toplevel", cwd=cwd))
        try:
            origin = git("config", "--get", "remote.origin.url", cwd=top)
        except RuntimeError:
            return None

        branch = git("branch", "--show-current", cwd=top) if branch is None else branch
        try:
            default = git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=top)
        except RuntimeError:
            default = "origin/main"

        if not OWNER.search(origin) or branch in ("", default.removeprefix("origin/")):
            return None

        if fetch:
            name = default.removeprefix("origin/")
            subprocess.run(["git", "fetch", "-q", "origin", name], cwd=top, capture_output=True)

        common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top))
        state_file = common / "pr-gate" / f"{quote(branch, safe='')}.json"
        st = json.loads(state_file.read_text()) if state_file.exists() else {}
        return cls(
            top=top,
            branch=branch,
            default=default,
            head=git("rev-parse", f"{head}^{{commit}}", cwd=top),
            base=git("merge-base", default, head, cwd=top),
            state_file=state_file,
            st=st,
        )

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.st, indent=2) + "\n")

    def snapshot(self) -> dict:
        return {"commit": self.head, "base": self.base}

    def exists(self, commit: str) -> bool:
        args = ["git", "cat-file", "-e", f"{commit}^{{commit}}"]
        return subprocess.run(args, cwd=self.top, capture_output=True).returncode == 0

    def changes(self, snap: dict | None = None) -> Counter:
        """The branch's own code changes at a snapshot (now when None), as counted lines."""
        base, head = (snap["base"], snap["commit"]) if snap else (self.base, self.head)
        if snap and not (self.exists(base) and self.exists(head)):
            return Counter()

        out = git(
            "diff",
            "-U0",
            "--no-renames",
            "--no-color",
            "--ignore-all-space",
            "--ignore-blank-lines",
            base,
            head,
            cwd=self.top,
        )
        rs, path = Counter(), None
        for line in out.splitlines():
            if line.startswith("+++ "):
                path = line[6:] if line != "+++ /dev/null" else path
            elif line.startswith("--- "):
                path = line[6:] if line != "--- /dev/null" else None
            elif line.startswith(("+", "-")) and path and not matches(path, EXEMPT + TESTS):
                rs[(path, line)] += 1

        return rs

    def since(self, key: str, cur: Counter) -> Counter:
        """What changed since the snapshot under key; everything when there is none."""
        snap = self.st.get(key)
        return drift(cur, self.changes(snap)) if snap else cur

    def rejected(self) -> str:
        items = self.st.get("rejected", [])
        if not items:
            return ""

        lines = "\n".join(f"- {x}" for x in items[-10:])
        return f"The author already rejected these findings; don't repeat them:\n{lines}\n"

    def styles(self, changes: Counter) -> str:
        """The code-style skills for the files the changes add lines to, as `/a and /b`; empty
        when no language of theirs has one."""
        exts = set()
        for path in {p for p, x in changes if x.startswith("+")}:
            file = self.top / path
            if file.suffix or not file.is_file():
                exts.add(file.suffix)
                continue

            with file.open("rb") as f:
                exts.add(".py" if re.match(rb"#!.*\b(python|uv run)", f.readline()) else "")

        return " and ".join(f"/{x}" for ext, x in STYLES.items() if ext in exts)


def codex(repo: Repo, prompt: str, effort: str) -> tuple[str | None, str]:
    """The review's last message, or None and why it couldn't run."""
    with tempfile.NamedTemporaryFile(suffix=".md") as out:
        cmd = [
            "codex",
            "exec",
            "-C",
            str(repo.top),
            "-s",
            "read-only",
            "--ephemeral",
            "-c",
            f"model_reasoning_effort={effort}",
            "-o",
            out.name,
            prompt,
        ]
        try:
            rs = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=TIMEOUT[effort],
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, str(e)

        if rs.returncode:
            tail = "\n".join(rs.stderr.strip().splitlines()[-5:])
            return None, f"codex exited with {rs.returncode}:\n{tail}"

        return Path(out.name).read_text().strip(), ""


def verdict(text: str) -> tuple[str, str] | None:
    found = re.findall(r"^\W*VERDICT:\s*(OK|FIX|DEEP)\b\W*(.*)$", text, re.MULTILINE)
    return found[-1] if found else None


def findings(text: str) -> int:
    return len(re.findall(r"^\s*[-*]\s+`?\S+:\d+", text, re.MULTILINE))


# MARK: Outcomes


def passed(repo: Repo, fp: str, why: str) -> int:
    repo.st["passed"] = [*repo.st.get("passed", []), fp][-50:]
    repo.st["last"] = repo.snapshot()
    repo.st.pop("open", None)
    repo.save()
    print(f"pr-gate: passed ({why}). Push again.")
    return 0


def fix(repo: Repo, fp: str, text: str, style: str) -> int:
    repo.st["last"] = repo.snapshot()
    repo.st["open"] = {"fp": fp, "findings": text}
    repo.save()
    return open_findings(repo, style)


def open_findings(repo: Repo, style: str = "") -> int:
    print(repo.st["open"]["findings"])
    print(
        "\npr-gate: findings to handle. Check each one against the code. Fix the real ones,"
        " commit and call the pr-gate review tool again; that review covers only your fixes. To"
        " reject findings without changing code, call it with `accept`, one reason per finding:"
        ' `["<finding>: <why it is wrong>", …]`.'
    )
    if style:
        print(
            f"Before that, review the branch's changes (`git diff {repo.default}...HEAD`) against"
            f" {style}, fix what doesn't match and commit."
        )

    return 1


def broken(why: str) -> int:
    print(
        f"pr-gate: the review couldn't run: {why}\nThe push stays blocked. Tell the person;"
        " don't work around it.",
        file=sys.stderr,
    )
    return 1


def review(repo: Repo) -> int:
    if git("status", "--porcelain", "--untracked-files=no", cwd=repo.top):
        print("pr-gate: uncommitted changes are not reviewed; commit them first.", file=sys.stderr)

    cur = repo.changes()
    fp = fingerprint(cur)
    if fp in repo.st.get("passed", []):
        print("pr-gate: these changes have passed already. Push again.")
        return 0

    if repo.st.get("open", {}).get("fp") == fp:
        return open_findings(repo)

    delta = repo.since("last", cur)
    if not delta:
        return passed(repo, fp, "no code changed since the last review")

    added = sum(n for (_, line), n in cur.items() if line.startswith("+"))
    deleted = size(cur) - added
    big = added > STYLE_LINES and added > 3 * deleted
    style = repo.styles(cur) if big and not repo.st.get("style") else ""
    if style:
        repo.st["style"] = True
        repo.save()
        print(
            f"pr-gate: this branch adds {added} lines of new code. Review its changes"
            f" (`git diff {repo.default}...HEAD`) against {style}, fix what doesn't match,"
            " commit, then call the pr-gate review tool again."
        )
        return 1

    files = sorted({path for path, _ in delta})
    why = [f"touches {x}" for x in files if matches(x, RISKY)]
    why += [f"adds unsafe in {p}" for p, x in delta if x.startswith("+") and "unsafe" in x][:1]
    since_deep = size(repo.since("deep_at", cur))
    if since_deep > DEEP_LINES:
        why.append(f"{since_deep} lines of code changed since the last deep review")

    style = ""
    if not why:
        # After a rebase the last reviewed commit isn't an ancestor: show the delta's files whole.
        last = repo.st.get("last")
        on_top = (
            last
            and repo.exists(last["commit"])
            and subprocess.run(
                ["git", "merge-base", "--is-ancestor", last["commit"], "HEAD"], cwd=repo.top
            ).returncode
            == 0
        )
        rng = f"{last['commit']} HEAD" if on_top else f"{repo.default}...HEAD"
        diff = f"git diff {rng} -- {' '.join(files)}"
        print(f"pr-gate: quick review of {size(delta)} changed lines…", file=sys.stderr)
        text, err = codex(repo, QUICK.format(diff=diff, rejected=repo.rejected()), "low")
        found = text and verdict(text)
        if not found:
            return broken(err or f"no verdict in the quick review:\n{text}")

        complex_ = re.search(r"^\W*COMPLEX:", text, re.MULTILINE)
        style = repo.styles(delta) if complex_ and not repo.st.get("style") else ""
        repo.st["style"] = repo.st.get("style") or bool(style)
        match found:
            case ("OK", _) if style:
                return fix(repo, fp, text, style)
            case ("OK", _):
                return passed(repo, fp, "quick review found nothing")
            case ("FIX", _):
                return fix(repo, fp, text, style)
            case ("DEEP", reason):
                why.append(f"the quick review asked for it: {reason or 'no reason given'}")

    if repo.st.get("deep", 0) >= DEEP_MAX:
        print(
            f"pr-gate: a deep review is due ({'; '.join(why)}), but this branch had {DEEP_MAX}"
            " already. Tell the person instead of starting another."
        )
        return passed(repo, fp, "deep review limit reached")

    print(f"pr-gate: deep review of the branch ({'; '.join(why)})…", file=sys.stderr)
    diff = f"git diff {repo.default}...HEAD"
    prompt = DEEP.format(diff=diff, why="; ".join(why), rejected=repo.rejected())
    text, err = codex(repo, prompt, "high")
    found = text and verdict(text)
    if not found:
        return broken(err or f"no verdict in the deep review:\n{text}")

    repo.st["deep"] = repo.st.get("deep", 0) + 1
    repo.st["deep_at"] = repo.snapshot()
    if found[0] == "OK":
        return passed(repo, fp, "deep review found nothing")

    return fix(repo, fp, text, style)


def accept(repo: Repo, reasons: list[str]) -> int:
    fp = fingerprint(repo.changes())
    if fp in repo.st.get("passed", []):
        print("pr-gate: these changes have passed already.")
        return 0

    item = repo.st.get("open", {})
    if item.get("fp") != fp:
        print(
            "pr-gate: no findings are open for these changes; call the review tool without"
            " `accept`.",
            file=sys.stderr,
        )
        return 1

    need = max(1, findings(item["findings"]))
    if len(reasons) < need:
        print(
            f"pr-gate: {need} findings are open; give a reason for each (one `accept` entry per"
            " finding), or fix them and call the review tool again.",
            file=sys.stderr,
        )
        return 1

    repo.st["rejected"] = [*repo.st.get("rejected", []), *reasons][-20:]
    return passed(repo, fp, "findings rejected")


# MARK: Shell


def word(n: Node, loose: bool = False) -> str | None:
    """A word's value after quote removal; None when it depends on an expansion other than $HOME,
    or with `loose` the expansion's own text."""
    text = n.text.decode()
    match n.type:
        case "word" | "number":
            return re.sub(r"\\(.)", r"\1", text, flags=re.DOTALL)
        case "raw_string":
            return text[1:-1]
        case "ansi_c_string":
            esc = {"n": "\n", "t": "\t"}
            return re.sub(r"\\(.)", lambda m: esc.get(m[1], m[1]), text[2:-1], flags=re.DOTALL)
        case "string_content":
            return re.sub(r'\\([$`"\\])', r"\1", text)
        case "string" | "concatenation":
            parts = [word(c, loose) for c in n.named_children]
            return None if None in parts else "".join(parts)
        case "simple_expansion" | "expansion" if text in ("$HOME", "${HOME}"):
            return str(Path.home())

    return text if loose else None


def into(cwd: Path, n: Node) -> Path:
    """The directory `cd <n>` moves to from `cwd`; `cwd` when it can't be known."""
    to = word(n)
    if to is None or to == "-":
        return cwd

    return cwd / (Path(to).expanduser() if n.text.startswith(b"~") else Path(to))


def positional(args: list[str]) -> list[str]:
    """A push's arguments that aren't options: the remote, then the refspecs."""
    return [
        w
        for i, w in enumerate(args)
        if not w.startswith("-") and (i == 0 or args[i - 1] not in PUSH_VALUED)
    ]


def pushes(cmd: str, cwd: Path, guess: bool = True) -> list[tuple[list[str], Path]]:
    """Every `git push` a Bash command runs, as its arguments and the directory it runs in; not
    one that only deletes or pushes tags. With `guess`, an unknown push for a command that won't
    parse but mentions one."""
    found, tree = [], BASH.parse(cmd.encode())
    walk(tree.root_node, cwd, found)
    broken = tree.root_node.has_error and re.search(r"\bgit\b[\s\S]*\bpush\b", cmd)
    if guess and not found and broken:
        found.append(([UNKNOWN], cwd))

    return found


def walk(n: Node, cwd: Path, found: list) -> Path:
    """Adds the pushes `n` runs from `cwd` to `found`; the directory it leaves the shell in."""
    if n.type == "command":
        return command(n, cwd, found)

    alone = n.type == "pipeline"  # each command of a pipeline runs in its own subshell
    d = cwd
    for c in n.children:
        d = walk(c, cwd if alone else d, found)

    scoped = ("subshell", "command_substitution", "process_substitution", "function_definition")
    return cwd if alone or n.type in scoped else d


def command(n: Node, cwd: Path, found: list) -> Path:
    """walk() of a simple command."""
    for c in n.children:  # the `$( )` in its words and assignments
        walk(c, cwd, found)

    name = n.child_by_field_name("name")
    if name is None:
        return cwd

    up = n.parent if n.parent.type == "redirected_statement" else None
    redirects = [*n.children_by_field_name("redirect")]
    redirects += up.children_by_field_name("redirect") if up else []
    # tree-sitter-bash takes the words after `2>&1` for more targets of the redirect.
    extra = [d for r in redirects for d in r.children_by_field_name("destination")[1:]]
    ns = [name.named_child(0), *n.children_by_field_name("argument"), *extra]
    w = [word(c, True) for c in ns]

    i, here, fed = 0, cwd, False
    while i < len(w) and Path(w[i]).name in WRAPPERS:
        wrapper, i = Path(w[i]).name, i + 1
        fed = fed or wrapper == "xargs"
        while i < len(w) and (w[i].startswith("-") or wrapper in ("env", "sudo") and "=" in w[i]):
            if wrapper == "env" and w[i] == "-C" and i + 1 < len(w):
                here = into(here, ns[i + 1])

            i += 1 + (w[i] in WRAPPERS[wrapper])

        i += wrapper == "timeout"  # its duration

    ns, w = ns[i:], w[i:]
    prog = Path(w[0]).name if w else ""
    if prog in ("cd", "pushd"):
        to = [c for c, x in zip(ns[1:], w[1:]) if x == "-" or not x.startswith("-")]
        return into(cwd, to[0]) if to else Path.home()

    if prog == "git":
        i, path = 1, here
        while i < len(w) and w[i].startswith("-"):
            if w[i] == "-C" and i + 1 < len(w):
                path = into(path, ns[i + 1])

            i += 1 + (w[i] in GIT_VALUED)

        args = w[i + 1 :]
        tags = "--tags" in args and len(positional(args)) < 2
        if w[i : i + 1] == ["push"] and not tags and not {"--delete", "-d"} & set(args):
            found.append(([*args, UNKNOWN] if fed else args, path))

        return cwd

    if prog == "eval":
        return walk(BASH.parse(" ".join(w[1:]).encode()).root_node, cwd, found)

    # Text another shell runs: `sh -c` its script, a shell without one its stdin.
    opts = len(list(takewhile(lambda x: x.startswith("-"), w[1:])))
    scripts = []
    if prog in SHELLS and any(re.fullmatch(r"-[a-z]*c[a-z]*", x) for x in w[1 : 1 + opts]):
        scripts = w[1 + opts : 2 + opts]
    elif prog in SHELLS and len(w) == 1 + opts:
        for r in redirects:
            if r.type == "heredoc_redirect":
                scripts += [c.text.decode() for c in r.named_children if c.type == "heredoc_body"]
            elif r.type == "herestring_redirect":
                scripts.append(word(r.named_children[-1], True))

    for s in scripts:
        walk(BASH.parse(s.encode()).root_node, here, found)

    return cwd


def pre() -> int:
    """Denies a `git push` of a branch whose changes pr-gate hasn't passed. Fails open on its own
    errors, so a broken gate doesn't stop the work."""
    try:
        pld = json.load(sys.stdin)
        found = pushes(pld["command"], Path(pld.get("cwd") or "."))
    except Exception as e:
        print(f"pr-gate: pre hook error, not blocking: {e}", file=sys.stderr)
        return 0

    for args, path in found:
        try:
            top = Path(git("rev-parse", "--show-toplevel", cwd=path))
            todo = sources(args, top)
        except Exception as e:
            print(f"pr-gate: pre hook error, not blocking: {e}", file=sys.stderr)
            continue

        for branch, head in todo:
            try:
                repo = Repo.open(top, branch=branch, head=head)
                cur = repo.changes() if repo else None
                if not cur or fingerprint(cur) in repo.st.get("passed", []):
                    continue

                at = (git("branch", "--show-current", cwd=top), git("rev-parse", "HEAD", cwd=top))
            except Exception as e:
                print(f"pr-gate: pre hook error, not blocking: {e}", file=sys.stderr)
                continue

            if at == (branch, repo.head):
                print(
                    f"pr-gate: this push needs a review first. Call the pr-gate review tool with"
                    f" path {repo.top}, do what it says, then push again."
                )
            else:
                print(
                    f"pr-gate: this push sends branch {branch}, which needs a review first. The"
                    f" review tool reviews only the checked-out branch: check out {branch} at the"
                    f" commit you push, call the pr-gate review tool with path {repo.top}, do what"
                    " it says, then push again."
                )

            return 2

    return 0


def sources(args: list[str], top: Path) -> list[tuple[str, str]]:
    """What a push sends, as (branch whose review counts, commit): a local branch by its name, a
    detached HEAD or another commit by the branch it updates; not a tag. With --all or --mirror:
    every local branch."""

    def ref(name: str) -> bool:
        cmd = ["git", "rev-parse", "--verify", "--quiet", name]
        return subprocess.run(cmd, cwd=top, capture_output=True).returncode == 0

    if dry(args):
        return []

    if {"--all", "--branches", "--mirror"} & set(args):
        out = git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=top)
        return [(b, f"refs/heads/{b}") for b in out.splitlines()]

    cur = git("branch", "--show-current", cwd=top)
    rs = []
    for dst, src in refs(args, cur):
        src = src.removeprefix("refs/heads/")
        if src in HEADS:
            rs.append((cur or dst, "HEAD"))
        elif ref(f"refs/heads/{src}"):
            rs.append((src, f"refs/heads/{src}"))
        elif not src.startswith("refs/tags/") and not ref(f"refs/tags/{src}") and ref(src):
            rs.append((dst, src))

    return rs


def post() -> int:
    """Makes the session the owner of what the pushes that went through pushed. Fails open."""
    try:
        pld = json.load(sys.stdin)
        found = pushes(pld["command"], Path(pld.get("cwd") or "."), guess=False)
    except Exception as e:
        print(f"pr-gate: post hook error, not recording: {e}", file=sys.stderr)
        return 0

    for args, path in found:
        try:
            pushed(pld, args, path)
        except Exception as e:
            print(f"pr-gate: post hook error, not recording: {e}", file=sys.stderr)

    return 0


# MARK: Owners

SLUG = re.compile(r"github\.com[:/](vladkens/[^/\s]+?)(?:\.git)?/?$")
# What a push prints when it didn't go through.
PUSH_FAILED = re.compile(r"\[(?:remote )?rejected\]|error: failed to push|^fatal:", re.MULTILINE)
PR_FIELDS = "number,state,isDraft,headRefName,headRefOid,closedAt,statusCheckRollup"
# A check still running, and one that ended badly (check runs' conclusions, statuses' states).
WAITING = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED", "EXPECTED"}
BAD = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "ERROR"}
STUCK = 2 * 3600  # CI still waiting this long after the last push or claim won't finish: no gate
STOP_TIME = 10  # seconds the Stop hook may take, gh calls and the lock included


def gh(*args: str, timeout: float = 15):
    rs = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    if rs.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])}: {rs.stderr.strip()}")

    return json.loads(rs.stdout)


def fresh(entry: dict) -> bool:
    return time.time() - entry["at"] < OWN_TTL


def owners() -> dict:
    """{git common dir: {branch: {session_id, at, sha, reported}}}, where at is the last push or
    claim and reported the head whose failed CI the owner was told about; empty when the file is
    missing or broken."""
    try:
        st = json.loads(OWNERS.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"pr-gate: ignoring the broken {OWNERS}: {e}", file=sys.stderr)
        return {}

    if not isinstance(st, dict):
        return {}

    def ok(e) -> bool:
        return (
            isinstance(e, dict)
            and isinstance(e.get("session_id"), str)
            and isinstance(e.get("at"), (int, float))
        )

    return {
        repo: {b: e for b, e in brs.items() if ok(e)}
        for repo, brs in st.items()
        if isinstance(brs, dict)
    }


@contextmanager
def owners_locked(wait: float = 3):
    """The owners to change in place; saved atomically, without expired entries, on exit. Several
    sessions write at once, so it holds a lock for as long, waiting for it up to `wait` seconds."""
    OWNERS.parent.mkdir(parents=True, exist_ok=True)
    with open(OWNERS.with_suffix(".lock"), "w") as lock:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{OWNERS} stays locked")

                time.sleep(0.05)

        st = owners()
        yield st

        st = {r: x for r, brs in st.items() if (x := {b: e for b, e in brs.items() if fresh(e)})}
        with tempfile.NamedTemporaryFile("w", dir=OWNERS.parent, delete=False) as f:
            try:
                f.write(json.dumps(st, indent=2) + "\n")
                f.close()
                os.replace(f.name, OWNERS)
            except BaseException:
                Path(f.name).unlink(missing_ok=True)
                raise


def dry(args: list[str]) -> bool:
    return any(w == "--dry-run" or re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", w) for w in args)


def refs(args: list[str], cur: str) -> list[tuple[str, str]]:
    """The branches a push's arguments update, as (remote branch, local ref); the current branch
    when they name none or some can't be known; nothing for a dry run."""
    if dry(args):
        return []

    pos = positional([w for w in args if w != UNKNOWN])
    rs = []
    for spec in pos[1:]:
        src, _, dst = spec.lstrip("+").partition(":")
        name = (dst or src).removeprefix("refs/heads/")
        if src and not name.startswith("refs/"):  # `:branch` deletes, refs/tags/… isn't a branch
            rs.append((cur if name in HEADS else name, src))

    rs = rs if pos[1:] else [(cur, "HEAD")]
    return [*rs, (cur, "HEAD")] if UNKNOWN in args and (cur, "HEAD") not in rs else rs


def pushed(pld: dict, args: list[str], cwd: Path) -> int:
    """After a push that looks done (the command succeeded; a push in the background prints
    nothing yet): this session owns the local branches it pushed."""
    sid = pld.get("session_id")
    out = f"{pld.get('stdout') or ''}\n{pld.get('stderr') or ''}"
    if not sid or PUSH_FAILED.search(out):
        return 0

    # A `cd` in the command may have moved the session's cwd already.
    cwd = cwd if cwd.is_dir() else Path(pld.get("cwd") or ".")
    top = Path(git("rev-parse", "--show-toplevel", cwd=cwd))
    if not OWNER.search(git("config", "--get", "remote.origin.url", cwd=top)):
        return 0

    try:
        default = git("rev-parse", "--abbrev-ref", "origin/HEAD", cwd=top).removeprefix("origin/")
    except RuntimeError:
        default = "main"

    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top)
    cur = git("branch", "--show-current", cwd=top)
    branches = []
    for branch, src in refs(args, cur):
        src = cur if src in HEADS else src.removeprefix("refs/heads/")
        if branch in ("", default) or not src:
            continue

        try:  # only a local branch: not a tag, a commit or a word the parsing got wrong
            sha = git("rev-parse", "--verify", "--quiet", f"refs/heads/{src}", cwd=top)
        except RuntimeError:
            continue

        branches.append((branch, sha))

    if branches:
        with owners_locked() as st:
            for branch, sha in branches:
                entry = {"session_id": sid, "at": int(time.time()), "sha": sha}
                st.setdefault(common, {})[branch] = entry

    return 0


def checks(pr: dict) -> tuple[list[str], list[str]]:
    """The PR's checks still running, and those that ended badly."""
    waiting, bad = [], []
    for c in pr.get("statusCheckRollup") or []:
        name = c.get("name") or c.get("context") or "?"
        state = c.get("status") if c.get("status") != "COMPLETED" else c.get("conclusion")
        state = state or c.get("state")
        if state in WAITING:
            waiting.append(name)
        elif state in BAD:
            bad.append(name)

    return waiting, bad


@dataclass
class Owned:
    """A branch a session owns, and (after look) its PR and CI now."""

    repo: str  # git common dir
    branch: str
    entry: dict
    slug: str = ""
    pr: dict | None = None
    state: str = ""  # no PR, merged, closed, draft, running, failed, green, no checks
    waiting: list[str] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        repo = self.slug or Path(self.repo).parent.name
        return f"{repo}#{self.pr['number']}" if self.pr else f"{repo} {self.branch}"

    @property
    def done(self) -> bool:
        return self.state in ("merged", "closed")

    @property
    def reported(self) -> bool:
        return self.entry.get("reported") == (self.pr or {}).get("headRefOid")

    def look(self, timeout: float = 15) -> "Owned":
        m = SLUG.search(git("config", "--get", "remote.origin.url", cwd=self.repo))
        if m is None:
            self.state = "not ours"
            return self

        self.slug = m[1]
        args = ["--head", self.branch, "--state", "all", "--limit", "5", "--json", PR_FIELDS]
        prs = gh("pr", "list", "-R", self.slug, *args, timeout=timeout)
        pr = next((x for x in prs if x["state"] == "OPEN"), prs[0] if prs else None)
        if pr and pr["state"] != "OPEN":
            # An older PR of a reused branch name is not this push's.
            closed = datetime.fromisoformat(pr["closedAt"]).timestamp() if pr.get("closedAt") else 0
            if pr["headRefOid"] != self.entry.get("sha") and closed < self.entry["at"]:
                pr = None

        self.pr = pr
        if pr is None:
            self.state = "no PR"
        elif pr["state"] != "OPEN":
            self.state = pr["state"].lower()
        elif pr["isDraft"]:
            self.state = "draft"
        else:
            self.waiting, self.bad = checks(pr)
            ok = "green" if pr.get("statusCheckRollup") else "no checks"
            self.state = "running" if self.waiting else "failed" if self.bad else ok

        return self


def stop() -> int:
    """Blocks the end of a turn while an open, non-draft PR this session owns has CI running, or
    once per pushed head when it failed: prints why and exits 2. Fails open on its own errors."""
    try:
        pld = json.load(sys.stdin)
        sid = pld.get("session_id")
        mine = [
            Owned(repo, branch, e)
            for repo, brs in owners().items()
            for branch, e in brs.items()
            if sid and e["session_id"] == sid and fresh(e)
        ]
        deadline = time.monotonic() + STOP_TIME
        for x in mine:
            left = deadline - time.monotonic()
            if left < 1:
                break

            try:
                x.look(timeout=left)
            except Exception as e:
                print(f"pr-gate: stop hook skips {x.branch}: {e}", file=sys.stderr)

        now = time.time()
        running = [x for x in mine if x.state == "running" and now - x.entry["at"] < STUCK]
        failed = [x for x in mine if x.state == "failed" and not x.reported and not running]
        done = [x for x in mine if x.done]
    except Exception as e:
        print(f"pr-gate: stop hook error, not blocking: {e}", file=sys.stderr)
        return 0

    if failed or done:
        try:
            with owners_locked(wait=max(0.5, deadline - time.monotonic())) as st:
                for x in failed + done:
                    brs = st.get(x.repo, {})
                    if brs.get(x.branch) != x.entry:  # pushed or claimed again meanwhile
                        continue

                    if x.done:
                        del brs[x.branch]
                    else:
                        brs[x.branch]["reported"] = x.pr["headRefOid"]
        except Exception as e:
            print(f"pr-gate: stop hook can't save, not blocking on red CI: {e}", file=sys.stderr)
            failed = []

    if running:
        names = ", ".join(
            f"{x.name} in {Path(x.repo).parent} ({', '.join(x.waiting)})" for x in running
        )
        reason = (
            f"pr-gate: CI is still running ({names}). Wait for it with `gh pr checks <number>"
            " -R <repo> --watch` (10-minute timeout) and report the result, or, if it can't"
            " finish, call the pr-gate release tool with its number and its repository's"
            " directory as path; don't call the work done before CI is green."
        )
    elif failed:
        names = ", ".join(f"{x.name} ({', '.join(x.bad)})" for x in failed)
        reason = (
            f"pr-gate: CI failed ({names}). Look at it (`gh run view -R <repo> --log-failed`), fix"
            " it, or tell the person plainly that CI is red."
        )
    else:
        return 0

    print(reason)
    return 2


# MARK: Commands


def here() -> tuple[Path, str, str]:
    """This repository's top, git common dir and github.com slug."""
    top = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()))
    try:
        m = SLUG.search(git("config", "--get", "remote.origin.url", cwd=top))
    except RuntimeError:
        m = None

    if m is None:
        raise RuntimeError("not a github.com/vladkens repository")

    return top, git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=top), m[1]


def session() -> str:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        raise RuntimeError("no Claude Code session here (CLAUDE_CODE_SESSION_ID is unset)")

    return sid


def ago(at: float) -> str:
    s = int(time.time() - at)
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m"


def target_pr(slug: str, target: str) -> tuple[str, dict | None]:
    """The branch a PR number or a branch name stands for, and its PR (the open one by name)."""
    if re.fullmatch(r"#?\d+", target):
        pr = gh("pr", "view", target.lstrip("#"), "-R", slug, "--json", PR_FIELDS)
        return pr["headRefName"], pr

    prs = gh("pr", "list", "-R", slug, "--head", target, "--state", "open", "--json", PR_FIELDS)
    return target, prs[0] if prs else None


def claim(target: str) -> int:
    sid = session()
    top, common, slug = here()
    branch, pr = target_pr(slug, target)
    if pr and pr["state"] != "OPEN":
        print(f"pr-gate: #{pr['number']} is {pr['state'].lower()}; nothing to watch.")
        return 1

    sha = pr["headRefOid"] if pr else ""
    for ref in [] if sha else [f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"]:
        try:
            sha = git("rev-parse", "--verify", "-q", ref, cwd=top)
            break
        except RuntimeError:
            pass

    with owners_locked() as st:
        prev = st.get(common, {}).get(branch)
        st.setdefault(common, {})[branch] = {"session_id": sid, "at": int(time.time()), "sha": sha}

    name = f"{branch} (#{pr['number']})" if pr else f"{branch} (no open PR yet)"
    was = f", not {prev['session_id'][:8]}" if prev and prev["session_id"] != sid else ""
    print(f"pr-gate: this session owns {name} now{was}.")
    return 0


def release(target: str) -> int:
    _, common, slug = here()
    branch = target_pr(slug, target)[0] if re.fullmatch(r"#?\d+", target) else target
    with owners_locked() as st:
        prev = st.get(common, {}).pop(branch, None)

    if prev is None:
        print(f"pr-gate: nobody owns {branch}.")
        return 1

    who = prev["session_id"]
    who = "this session" if who == os.environ.get("CLAUDE_CODE_SESSION_ID") else who[:8]
    print(f"pr-gate: released {branch} (owned by {who}); nobody owns it now.")
    return 0


def status(every: bool) -> int:
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    st = owners()
    if every:
        common = here()[1]
        rows = [Owned(common, b, e) for b, e in st.get(common, {}).items()]
    else:
        sid = session()
        own = [(r, b, e) for r, brs in st.items() for b, e in brs.items()]
        rows = [Owned(r, b, e) for r, b, e in own if e["session_id"] == sid]

    if not rows:
        print(f"pr-gate: {'nobody owns a branch here' if every else 'this session owns nothing'}.")
        return 0

    for x in sorted(rows, key=lambda x: -x.entry["at"]):
        ci = "expired, not watched"
        if fresh(x.entry):
            try:
                x.look()
                ci = x.state
            except Exception as e:
                ci = f"unknown ({e})"

        if x.state == "running":
            ci = f"CI running: {', '.join(x.waiting)}"
        elif x.state == "failed":
            ci = f"CI failed: {', '.join(x.bad)}" + (", told once" if x.reported else "")

        cols = [Path(x.repo).parent.name, x.branch, f"#{x.pr['number']}" if x.pr else "-"]
        if every:
            who = x.entry["session_id"]
            cols.append("this session" if who == sid else who[:8])

        print("  ".join([*cols, f"{ago(x.entry['at'])} ago", ci]))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Thresholds: style over {}, deep over {} lines, at most {} deep reviews; owners"
        " watch for {} h.".format(STYLE_LINES, DEEP_LINES, DEEP_MAX, OWN_TTL // 3600),
    )
    cmds = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    cmd = cmds.add_parser("review", help="review what changed since the last review")
    cmd.add_argument(
        "--accept", metavar="REASON", action="append", help="reject one open finding with a reason"
    )
    cmd = cmds.add_parser("claim", help="this session watches that PR's CI from now on")
    cmd.add_argument("target", metavar="PR|BRANCH")
    cmd = cmds.add_parser("release", help="nobody watches that PR's CI any more")
    cmd.add_argument("target", metavar="PR|BRANCH")
    cmd = cmds.add_parser("status", help="what this session owns")
    cmd.add_argument("--all", action="store_true", help="every owner in this repository")
    cmds.add_parser("pre", help="mod hook before a Bash call: deny an unreviewed push")
    cmds.add_parser("post", help="mod hook after a Bash call: own the pushed branches")
    cmds.add_parser("stop", help="mod Stop hook: keep the turn going while CI runs")
    args = parser.parse_args()
    match args.cmd:
        case "pre":
            return pre()
        case "post":
            return post()
        case "stop":
            return stop()

    try:
        match args.cmd:
            case "claim":
                return claim(args.target)
            case "release":
                return release(args.target)
            case "status":
                return status(args.all)

        repo = Repo.open(Path.cwd(), fetch=True)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
        print(f"pr-gate: {e}", file=sys.stderr)
        return 1

    if repo is None:
        print("pr-gate: nothing to gate here (not a github.com/vladkens branch).")
        return 0

    if args.accept:
        return accept(repo, args.accept)

    return review(repo)


if __name__ == "__main__":
    sys.exit(main())
