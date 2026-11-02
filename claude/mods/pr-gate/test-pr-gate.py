#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = ["tree-sitter>=0.26", "tree-sitter-bash>=0.25.1"]
# ///

"""Tests for the stdin interface pr-gate.py gives its mod: pre, post and stop."""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("pr_gate", Path(__file__).with_name("pr-gate.py"))
pg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pg)

PUSHED = "To github.com:vladkens/x.git\n   1111111..2222222  feat -> feat\n"
# Pushes only mentioned in quoted text, comments, heredocs and arguments, or run on another host.
QUOTED = (
    'git commit -m "wip; git push later"',
    'git commit -m "docs (git push) flow"',
    'gh pr create --title x --body "Steps:\ngit push origin feat"',
    "ls # git push",
    "ls # don't git push",
    "echo $'a\\'b; git push '",
    "git commit -m \"$(cat <<'EOF'\nwip\ngit push later\nEOF\n)\"",
    "cat <<\\EOF\ngit push\nEOF",
    'cat <<-"EOF"\ngit push\n\tEOF',
    "ls # foo; git push later",
    "echo hi \\\ngit push x",
    "cat <<EOF\ngit push in body\nEOF",
    "git commit -m \"$(cat <<'EOF'\n…git push later…\nEOF\n)\"",
    "ssh host <<'EOF'\ngit push\nEOF",
)
# Real pushes: after text with a quote that doesn't open a string, behind a wrapper, in a
# compound command, a substitution or a script that a shell runs, or in a command that won't parse.
UNQUOTED = (
    "ls # don't\ngit push",
    'ls # say "hi\ngit push',
    "echo $'don\\'t' && git push",
    "echo $$'a\\' && git push #'",
    "cat <<'EOF'\ngit push\nEOF\ngit push",
    "git commit -m \"$(cat <<'EOF'\nit's\nEOF\n)\" && git push",
    "bash <<'EOF'\ngit push\nEOF",
    "sh <<'EOF'\ncd x && git push\nEOF",
    "git push  # not --tags",
    "git push origin feat  # -d not needed",
    "# a; git push --delete x\ngit push",
    "(true)# don't\ngit push",
    "ls \\\n# don't\ngit push",
    "echo `git push`",
    'echo "`git push`"',
    "FOO=1 git push",
    "if git push; then :; fi",
    "{ git push; }",
    "! git push",
    "time git push",
    "command git push",
    "env A=1 git push",
    "bash -c 'git push'",
    "eval 'git push'",
    "git push --delete origin old && git push -u origin feat",
    "git push origin feat --tags",
    "sudo git push",
    "sudo -u root -E git push",
    "/usr/bin/env git push",
    "env -C . git push",
    "caffeinate -i -t 60 git push",
    "echo feat | xargs git push origin",
    "cat >f <<'EOF'; git push\nx\nEOF",
)


class Repo(unittest.TestCase):
    """A repository of github.com/vladkens on branch feat with one new code file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        patches = [mock.patch.dict(os.environ, env), mock.patch.object(pg, "OWNERS", self.owners)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", "git@github.com:vladkens/x.git")
        (self.top / "readme.md").write_text("x\n")
        self.git("add", ".")
        self.git("commit", "-qm", "init")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("switch", "-qc", "feat")
        (self.top / "app.py").write_text("print('hi')\n")
        self.git("add", ".")
        self.git("commit", "-qm", "app")

    @property
    def top(self) -> Path:
        return Path(self.tmp.name).resolve()

    @property
    def owners(self) -> Path:
        return Path(self.tmp.name) / "owners.json"

    def git(self, *args: str) -> str:
        cfg = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        cmd = ["git", *cfg, *args]
        rs = subprocess.run(cmd, cwd=self.top, check=True, capture_output=True, text=True)

        return rs.stdout.strip()

    def call(self, fn, stdin: dict | str) -> tuple[int, str]:
        text = stdin if isinstance(stdin, str) else json.dumps(stdin)
        out = io.StringIO()
        with (
            mock.patch("sys.stdin", io.StringIO(text)),
            redirect_stdout(out),
            redirect_stderr(io.StringIO()),
        ):
            code = fn()

        return code, out.getvalue()


class PreTest(Repo):
    def test_denies_an_unreviewed_push(self):
        code, out = self.call(pg.pre, {"command": "git push -u origin feat", "cwd": str(self.top)})

        self.assertEqual(code, 2)
        self.assertIn("review tool", out)
        self.assertIn(str(self.top), out)

    def test_follows_cd_and_git_c_to_the_repository(self):
        name = self.top.name
        for cmd in (f"cd {name} && git push", f"git -C {name} push", f"git -C '{name}' push"):
            code, _ = self.call(pg.pre, {"command": cmd, "cwd": str(self.top.parent)})
            self.assertEqual(code, 2, cmd)

    def test_denies_a_push_after_a_message(self):
        (self.top / "x").mkdir()
        msg = "git commit -m \"$(cat <<'EOF'\nDon't\nEOF\n)\" && git push"
        for cmd in ("git push", "git commit -m 'x; y' && git push", msg, *UNQUOTED):
            code, _ = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
            self.assertEqual(code, 2, cmd)

    def test_follows_cd_after_a_comment(self):
        cmd = f"# it's fine\ncd {self.top.name} && git push"
        code, _ = self.call(pg.pre, {"command": cmd, "cwd": str(self.top.parent)})

        self.assertEqual(code, 2)

    def test_allows_a_push_whose_changes_passed(self):
        repo = pg.Repo.open(self.top)
        repo.st["passed"] = [pg.fingerprint(repo.changes())]
        repo.save()

        code, out = self.call(pg.pre, {"command": "git push", "cwd": str(self.top)})

        self.assertEqual((code, out), (0, ""))

    def test_denies_a_push_of_another_branch(self):
        self.git("switch", "-qc", "other", "main")
        (self.top / "lib.py").write_text("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "lib")
        repo = pg.Repo.open(self.top)
        repo.st["passed"] = [pg.fingerprint(repo.changes())]
        repo.save()
        self.git("tag", "v1", "feat")

        cases = {
            "other": ("git push origin feat", "git push origin other feat", "git push --all"),
            "main": ("git push -u origin feat", "git push origin feat:main"),
            "--detach": ("git push origin HEAD:feat",),
        }
        allowed = (
            "git push",
            "git push origin other",
            "git push origin main",
            "git push origin v1",
        )
        for at, cmds in cases.items():
            self.git("switch", "-q", at, *(["feat"] if at == "--detach" else []))
            for cmd in cmds:
                code, _ = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
                self.assertEqual(code, 2, f"{at}: {cmd}")

        self.git("switch", "-q", "other")
        for cmd in allowed:
            code, out = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
            self.assertEqual((code, out), (0, ""), cmd)

    def test_takes_at_for_head(self):
        repo = pg.Repo.open(self.top)
        repo.st["passed"] = [pg.fingerprint(repo.changes())]
        repo.save()

        for cmd in ("git push origin @", "git push origin @:feat"):
            code, out = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
            self.assertEqual((code, out), (0, ""), cmd)

        pld = {"command": "git push origin @", "cwd": str(self.top), "session_id": "s1"}
        self.call(pg.post, {**pld, "stdout": "", "stderr": PUSHED})
        self.assertEqual(list(pg.owners()[str(self.top / ".git")]), ["feat"])

    def test_names_a_branch_that_is_not_checked_out(self):
        _, out = self.call(pg.pre, {"command": "git push", "cwd": str(self.top)})
        self.assertNotIn("check out", out)

        self.git("switch", "-q", "main")
        _, out = self.call(pg.pre, {"command": "git push origin feat", "cwd": str(self.top)})
        self.assertIn("check out feat", out)

        self.git("switch", "-q", "--detach", "feat")
        _, out = self.call(pg.pre, {"command": "git push origin HEAD:feat", "cwd": str(self.top)})
        self.assertIn("check out feat", out)

    def test_allows_a_dry_run(self):
        for cmd in ("git push -n origin feat", "git push --all -n", "git push --dry-run --mirror"):
            code, out = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
            self.assertEqual((code, out), (0, ""), cmd)

    def test_allows_what_is_no_push(self):
        cmds = ("git status", "git commit -m 'git push later'", "git push --delete origin x")
        for cmd in (*cmds, *QUOTED):
            code, out = self.call(pg.pre, {"command": cmd, "cwd": str(self.top)})
            self.assertEqual((code, out), (0, ""), cmd)

    def test_parses_broken_commands(self):
        for cmd in ("x $'a\\", "x <<'E'\nb", 'x "$(y # )', 'git push "'):
            self.assertIsInstance(pg.pushes(cmd, self.top), list, cmd)

    def test_fails_open_on_its_own_errors(self):
        for stdin in ("not json", {"cwd": str(self.top)}):
            code, out = self.call(pg.pre, stdin)
            self.assertEqual((code, out), (0, ""))


class PostTest(Repo):
    def pushed(self, **extra) -> dict:
        pld = {"command": "git push", "cwd": str(self.top), "session_id": "s1"}
        self.assertEqual(self.call(pg.post, {**pld, "stdout": "", "stderr": PUSHED, **extra})[0], 0)
        return pg.owners()

    def test_owns_the_pushed_branch(self):
        st = self.pushed()

        common = str(self.top / ".git")
        entry = st[common]["feat"]
        self.assertEqual(entry["session_id"], "s1")
        self.assertEqual(entry["sha"], self.git("rev-parse", "HEAD"))

    def test_owns_what_every_push_pushed(self):
        for cmd in ("FOO=1 git push", "bash -c 'git push'", "git push -d origin x && git push"):
            self.owners.unlink(missing_ok=True)
            self.assertEqual(list(self.pushed(command=cmd)[str(self.top / ".git")]), ["feat"], cmd)

    def test_owns_nothing_after_a_failed_push(self):
        self.assertEqual(self.pushed(stderr=" ! [rejected]  feat -> feat (fetch first)\n"), {})

    def test_owns_nothing_after_a_push_in_a_message(self):
        for cmd in QUOTED:
            self.assertEqual(self.pushed(command=cmd), {}, cmd)

    def test_owns_nothing_after_a_command_that_wont_parse(self):
        self.assertEqual(self.pushed(command="cat >f <<'EOF'; git push\nx\nEOF"), {})

    def test_owns_nothing_without_a_session(self):
        self.assertEqual(self.pushed(session_id=None), {})


class PushesTest(unittest.TestCase):
    def test_finds_the_directory(self):
        cwd, home = Path("/w"), Path.home()
        cases = {
            "(cd /tmp && ls) && git push": cwd,
            'cd "$HOME" && git push': home,
            "cd ~/x; git push": home / "x",
            "git -C 'a b' push": cwd / "a b",
            "cd 'a b' && cd c && git -C d push origin HEAD:feat": cwd / "a b/c/d",
            "sh <<'EOF'\ncd x && git push\nEOF": cwd / "x",
            "cd $(git rev-parse --show-toplevel) && git push": cwd,
            "git -c a=b -C x --git-dir=y/.git push": cwd / "x",
            "env -C x A=1 git push": cwd / "x",
            "cat >f <<'EOF'; git push\nx\nEOF": cwd,
        }
        for cmd, path in cases.items():
            self.assertEqual([p for _, p in pg.pushes(cmd, cwd)], [path], cmd)

    def test_finds_the_arguments(self):
        cases = {
            "git push --delete origin old && git push -u origin feat": [["-u", "origin", "feat"]],
            "git push origin feat --tags": [["origin", "feat", "--tags"]],
            "git push 2>&1 origin feat | tail": [["origin", "feat"]],
            "timeout 60 nice -n 5 git push origin 'a b'": [["origin", "a b"]],
            "git push x; git push y": [["x"], ["y"]],
            '"git" push x; \\git push y; /usr/bin/git push z': [["x"], ["y"], ["z"]],
            "git push --tags; git push origin --tags; git push -d origin x": [],
            "sudo -u root /usr/bin/env A=1 caffeinate -i git push x": [["x"]],
            "echo feat | xargs -n 1 git push origin": [["origin", pg.UNKNOWN]],
            "cat >f <<'EOF'; git push\nx\nEOF": [[pg.UNKNOWN]],
            "ssh host <<'EOF'\ngit push\nEOF": [],
        }
        for cmd, args in cases.items():
            self.assertEqual([a for a, _ in pg.pushes(cmd, Path("/w"))], args, cmd)


class StopTest(Repo):
    def own(self, at: float) -> None:
        with pg.owners_locked() as st:
            st[str(self.top / ".git")] = {"feat": {"session_id": "s1", "at": at, "sha": "abc"}}

    def look(self, state: str):
        def look(x, timeout=15):
            x.state, x.waiting, x.slug = state, ["test"], "vladkens/x"
            x.pr = {"number": 1, "headRefOid": "abc"}
            return x

        return mock.patch.object(pg.Owned, "look", look)

    def test_blocks_while_ci_runs(self):
        self.own(time.time())
        with self.look("running"):
            code, out = self.call(pg.stop, {"session_id": "s1"})

        self.assertEqual(code, 2)
        self.assertIn("CI is still running (vladkens/x#1 in", out)
        self.assertIn("release tool", out)

    def test_lets_another_session_stop(self):
        self.own(time.time())
        with self.look("running"):
            self.assertEqual(self.call(pg.stop, {"session_id": "s2"}), (0, ""))

    def test_lets_a_green_pr_stop(self):
        self.own(time.time())
        with self.look("green"):
            self.assertEqual(self.call(pg.stop, {"session_id": "s1"}), (0, ""))

    def test_fails_open_on_its_own_errors(self):
        self.assertEqual(self.call(pg.stop, "not json"), (0, ""))


if __name__ == "__main__":
    unittest.main()
