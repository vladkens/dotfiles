#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///

"""Tests for account-switch.py with a fake Keychain and a temporary home."""

import argparse
import fcntl
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "account_switch", Path(__file__).with_name("account-switch.py")
)
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)

SW = {"accountUuid": "a-sw", "organizationUuid": "o-sw", "emailAddress": "me@work"}
PERSONAL = {"accountUuid": "a-me", "organizationUuid": "o-me", "emailAddress": "me@home"}
FULL = [{"kind": "five_hour", "percentUsed": 97, "resetsAt": "2099-01-01T00:00:00Z"}]


def login(token: str) -> dict:
    oauth = {"accessToken": f"at-{token}", "refreshToken": f"rt-{token}"}
    return {"claudeAiOauth": oauth, "trustedDeviceToken": f"td-{token}"}


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        (home / ".claude").mkdir()
        self.keychain: dict[tuple[str, str], dict] = {}
        patches = {
            "CLAUDE_DIR": home / ".claude",
            "CONFIG": home / ".claude.json",
            "STATE": home / ".claude/account-switch.json",
            "keychain_read": lambda service, account: self.keychain.get((service, account)),
            "keychain_write": self.keychain_write,
            "keychain_delete": lambda service, account: self.keychain.pop((service, account), None),
            "keychain_user": lambda: "me",
        }
        for name, value in patches.items():
            patcher = mock.patch.object(sw, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def keychain_write(self, service: str, account: str, data: dict) -> None:
        self.keychain[(service, account)] = data

    def log_in(self, account: dict, token: str) -> None:
        self.keychain[(sw.LIVE, "me")] = login(token) | {"mcpOAuth": {"server": "token"}}
        sw.CONFIG.write_text(json.dumps({"oauthAccount": account, "theme": "dark"}))

    def save(self, name: str, account: dict, token: str) -> None:
        self.keychain[(sw.SAVED, name)] = {"login": login(token), "oauthAccount": account}

    def measure(self, limits: list[dict]) -> None:
        with mock.patch("sys.stdin", io.StringIO(json.dumps(limits))):
            sw.cmd_measure(None)

    def live_account(self) -> dict:
        return json.loads(sw.CONFIG.read_text())["oauthAccount"]


class PickTest(unittest.TestCase):
    def test_full_window_moves_to_the_next_account_with_room(self):
        full = {}
        limits = [{"kind": "five_hour", "percentUsed": 97.5, "resetsAt": "2026-10-18T15:00:00Z"}]
        self.assertEqual(sw.pick("sw", limits, ["sw", "personal"], full, 0), "personal")
        self.assertEqual(full["sw"], 1792335600)

    def test_weekly_window_counts_and_other_kinds_do_not(self):
        weekly = [{"kind": "seven_day", "percentUsed": 99, "resetsAt": "2026-10-20T00:00:00Z"}]
        spend = [{"kind": "spend_limit", "percentUsed": 100}]
        self.assertEqual(sw.pick("sw", weekly, ["sw", "personal"], {}, 0), "personal")
        self.assertEqual(sw.pick("sw", spend, ["sw", "personal"], {}, 0), "sw")

    def test_stays_when_no_other_account_has_room(self):
        full = {"personal": 2000}
        limits = [{"kind": "five_hour", "percentUsed": 98, "resetsAt": "2026-10-18T15:00:00Z"}]
        self.assertEqual(sw.pick("sw", limits, ["sw", "personal"], full, 1000), "sw")

    def test_returns_to_the_first_account_once_its_window_reset(self):
        full = {"sw": 1000}
        limits = [{"kind": "five_hour", "percentUsed": 40}]
        self.assertEqual(sw.pick("personal", limits, ["sw", "personal"], full, 999), "personal")
        self.assertEqual(sw.pick("personal", limits, ["sw", "personal"], full, 1001), "sw")


class SwitchTest(Home):
    def setUp(self):
        super().setUp()
        self.save("sw", SW, "sw-old")
        self.save("personal", PERSONAL, "me")

    def test_switch_keeps_the_rotated_login_and_the_shared_fields(self):
        self.log_in(SW, "sw-rotated")

        self.assertTrue(sw.switch("personal"))

        self.assertEqual(self.keychain[(sw.SAVED, "sw")]["login"], login("sw-rotated"))
        live = self.keychain[(sw.LIVE, "me")]
        self.assertEqual(live, login("me") | {"mcpOAuth": {"server": "token"}})
        self.assertEqual(
            json.loads(sw.CONFIG.read_text()), {"oauthAccount": PERSONAL, "theme": "dark"}
        )
        self.assertFalse(sw.switch("personal"))

    def test_switch_refuses_an_unsaved_live_login(self):
        self.log_in({"accountUuid": "a-qh", "organizationUuid": "o-qh"}, "qh")

        with self.assertRaises(SystemExit):
            sw.switch("personal")

        self.assertEqual(
            self.keychain[(sw.LIVE, "me")]["claudeAiOauth"], login("qh")["claudeAiOauth"]
        )

    def test_switch_refuses_tokens_of_another_account_than_the_config_names(self):
        self.log_in(SW, "me")  # ~/.claude.json says sw, the Keychain holds personal's tokens

        with self.assertRaises(SystemExit):
            sw.switch("personal")

        self.assertEqual(self.keychain[(sw.SAVED, "sw")]["login"], login("sw-old"))
        self.assertEqual(self.live_account(), SW)

    def test_failed_switch_restores_the_live_login(self):
        self.log_in(SW, "sw")
        before = self.keychain[(sw.LIVE, "me")]

        with (
            mock.patch.object(sw, "set_config_account", side_effect=[SystemExit("disk"), None]),
            self.assertRaises(SystemExit),
        ):
            sw.switch("personal")

        self.assertEqual(self.keychain[(sw.LIVE, "me")], before)

    def test_measure_switches_and_then_waits_for_sessions_to_follow(self):
        self.log_in(SW, "sw")

        self.measure(FULL)
        self.assertEqual(self.live_account(), PERSONAL)

        # A reading right after the switch may still be the old account's: it is ignored.
        self.measure([{"kind": "five_hour", "percentUsed": 99}])
        state = json.loads(sw.STATE.read_text())
        self.assertEqual(list(state["full"]), ["sw"])

    def test_measure_skips_while_another_session_decides(self):
        self.log_in(SW, "sw")

        with sw.STATE.with_suffix(".lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self.measure(FULL)

        self.assertEqual(self.live_account(), SW)

    def test_other_profiles_are_left_alone(self):
        self.log_in(SW, "sw")

        for argv in (["x", "measure"], ["x", "use", "personal"]):
            env = {"CLAUDE_CONFIG_DIR": "/elsewhere"}
            with (
                mock.patch.dict(os.environ, env),
                mock.patch("sys.argv", argv),
                mock.patch("sys.stdin", io.StringIO(json.dumps(FULL))),
            ):
                if argv[1] == "measure":
                    sw.main()
                else:
                    self.assertRaises(SystemExit, sw.main)

        self.assertEqual(self.live_account(), SW)


class AddTest(Home):
    def test_add_from_a_profile_moves_its_login(self):
        profile = Path(self.tmp.name) / ".claude-sw"
        profile.mkdir()
        (profile / ".claude.json").write_text(json.dumps({"oauthAccount": SW}))
        item = sw.profile_item(profile)
        self.keychain[(item, "me")] = login("sw") | {"mcpOAuth": {"server": "token"}}

        sw.cmd_add(argparse.Namespace(name="sw", source=str(profile)))
        self.assertEqual(
            self.keychain[(sw.SAVED, "sw")], {"login": login("sw"), "oauthAccount": SW}
        )
        self.assertNotIn((item, "me"), self.keychain)
        self.assertEqual(list(profile.iterdir()), [profile / ".claude.json"])

    def test_profile_item_matches_claude_code(self):
        # The name Claude Code 2.1.292 gives ~/.claude-sw's login, seen in the Keychain.
        item = sw.profile_item(Path("/Users/user/.claude-sw"))
        self.assertEqual(item, "Claude Code-credentials-4f691c5c")


class LockTest(Home):
    def test_stale_lock_is_taken_and_a_live_one_waited_for(self):
        lock = sw.CLAUDE_DIR / ".oauth_refresh.lock"
        lock.mkdir()
        os.utime(lock, (time.time() - 120, time.time() - 120))
        with sw.dir_lock(lock, time.monotonic() + 1):
            self.assertTrue(lock.is_dir())

        self.assertFalse(lock.exists())

        lock.mkdir()
        with self.assertRaises(SystemExit), sw.dir_lock(lock, time.monotonic() + 0.3):
            pass

        self.assertTrue(lock.exists())


if __name__ == "__main__":
    unittest.main()
