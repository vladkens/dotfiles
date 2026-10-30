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
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location(
    "account_switch", Path(__file__).with_name("account-switch.py")
)
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)

SW = {"accountUuid": "a-sw", "organizationUuid": "o-sw", "emailAddress": "me@work"}
PERSONAL = {"accountUuid": "a-me", "organizationUuid": "o-me", "emailAddress": "me@home"}
FULL = [{"kind": "five_hour", "percentUsed": 97, "resetsAt": "2099-01-01T00:00:00Z"}]
LOW = [{"kind": kind, "percentUsed": 20, "resetsAt": "2099-01-01T00:00:00Z"} for kind in sw.WINDOWS]


def login(token: str) -> dict:
    oauth = {"accessToken": f"at-{token}", "refreshToken": f"rt-{token}"}
    return {"claudeAiOauth": oauth, "trustedDeviceToken": f"td-{token}"}


def windows(five_hour: float, seven_day: float) -> list[dict]:
    return [
        {"kind": kind, "percentUsed": used, "resetsAt": "2099-01-01T00:00:00Z"}
        for kind, used in (("five_hour", five_hour), ("seven_day", seven_day))
    ]


class Home(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        (home / ".claude").mkdir()
        self.keychain: dict[tuple[str, str], dict] = {}
        self.usage = LOW
        self.usage_by_token = {}
        patches = {
            "CLAUDE_DIR": home / ".claude",
            "CONFIG": home / ".claude.json",
            "STATE": home / ".claude/account-switch.json",
            "keychain_read": lambda service, account: self.keychain.get((service, account)),
            "keychain_write": self.keychain_write,
            "keychain_delete": lambda service, account: self.keychain.pop((service, account), None),
            "keychain_user": lambda: "me",
            "oauth_get": self.oauth_get,
        }
        for name, value in patches.items():
            patcher = mock.patch.object(sw, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def keychain_write(self, service: str, account: str, data: dict) -> None:
        self.keychain[(service, account)] = data

    def oauth_get(self, path: str, token: str) -> dict:
        if path == "usage":
            live = sw.access_token(self.keychain.get((sw.LIVE, "me"), {}))
            limits = self.usage_by_token.get(token, self.usage if token == live else LOW)
            return {
                limit["kind"]: {
                    "utilization": limit["percentUsed"],
                    "resets_at": limit.get("resetsAt"),
                }
                for limit in limits
            }

        for (service, _), data in self.keychain.items():
            if service == sw.SAVED and sw.access_token(data["login"]) == token:
                account = data["oauthAccount"]
                break
        else:
            account = self.live_account()

        return {
            "account": {"uuid": account["accountUuid"]},
            "organization": {"uuid": account["organizationUuid"]},
        }

    def log_in(self, account: dict, token: str) -> None:
        self.keychain[(sw.LIVE, "me")] = login(token) | {"mcpOAuth": {"server": "token"}}
        sw.CONFIG.write_text(json.dumps({"oauthAccount": account, "theme": "dark"}))

    def save(self, name: str, account: dict, token: str) -> None:
        self.keychain[(sw.SAVED, name)] = {"login": login(token), "oauthAccount": account}

    def set_plan(self, name: str, kind: str, tier: str) -> None:
        saved = self.keychain[(sw.SAVED, name)]
        metadata = {"subscriptionType": kind, "rateLimitTier": tier}
        saved["login"]["claudeAiOauth"].update(metadata)
        if sw.same_account(saved["oauthAccount"], self.live_account()):
            self.keychain[(sw.LIVE, "me")]["claudeAiOauth"].update(metadata)

    def measure(self, limits: list[dict]) -> int | None:
        with mock.patch("sys.stdin", io.StringIO(json.dumps(limits))):
            return sw.cmd_measure(None)

    def live_account(self) -> dict:
        return json.loads(sw.CONFIG.read_text())["oauthAccount"]


class PickTest(unittest.TestCase):
    def test_full_window_moves_to_the_next_account_with_room(self):
        full = {}
        limits = [{"kind": "five_hour", "percentUsed": 97.5, "resetsAt": "2026-10-18T15:00:00Z"}]
        self.assertEqual(sw.pick("sw", limits, ["sw", "personal"], full, 0), "personal")
        self.assertEqual(full["sw"], {"five_hour": 1792335600})

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

    def test_partial_reading_keeps_the_other_blocked_window(self):
        full = {"sw": {"five_hour": 2000}}
        weekly = [{"kind": "seven_day", "percentUsed": 20}]
        self.assertEqual(sw.pick("sw", weekly, ["sw", "personal"], full, 1000), "personal")
        self.assertEqual(full["sw"], {"five_hour": 2000})

    def test_only_a_reported_window_is_cleared(self):
        full = {"sw": {"five_hour": 2000, "seven_day": 3000}}
        limits = [{"kind": "five_hour", "percentUsed": 20}]
        self.assertEqual(sw.pick("sw", limits, ["sw", "personal"], full, 1000), "personal")
        self.assertEqual(full["sw"], {"seven_day": 3000})

    def test_partial_reading_does_not_shorten_another_windows_block(self):
        full = {"sw": {"seven_day": 3000}}
        limits = [{"kind": "five_hour", "percentUsed": 100, "resetsAt": "1970-01-01T00:33:20Z"}]
        sw.pick("sw", limits, ["sw", "personal"], full, 1000)
        self.assertEqual(sw.full_until(full["sw"]), 3000)

    def test_legacy_block_survives_partial_data_but_not_a_complete_verified_reading(self):
        full = {"sw": 2000}
        sw.pick("sw", LOW[:1], ["sw", "personal"], full, 1000)
        self.assertEqual(full["sw"], {"legacy": 2000})
        sw.pick("sw", LOW, ["sw", "personal"], full, 1000)
        self.assertNotIn("sw", full)

    def test_missing_window_expires_at_its_own_reset(self):
        full = {"sw": {"five_hour": 1000, "seven_day": 2000}}
        self.assertEqual(sw.pick("sw", [], ["sw", "personal"], full, 1001), "personal")
        self.assertEqual(full["sw"], {"seven_day": 2000})
        self.assertEqual(sw.pick("sw", [], ["sw", "personal"], full, 2001), "sw")

    def test_reserve_uses_plan_capacity_when_both_accounts_exceed_the_threshold(self):
        usage = {"sw": windows(95, 17), "personal": windows(14, 99)}
        full = {"personal": {"seven_day": 5000}}
        weights = {"sw": 1.25, "personal": 20}
        self.assertEqual(
            sw.pick("sw", usage["sw"], list(usage), full, 1000, usage, weights), "personal"
        )

    def test_normal_priority_wins_before_reserves_are_needed(self):
        usage = {"sw": windows(20, 20), "personal": windows(20, 20)}
        self.assertEqual(
            sw.pick("personal", usage["personal"], list(usage), {}, 1000, usage, {"personal": 20}),
            "sw",
        )

    def test_a_larger_plan_with_an_exhausted_window_has_no_reserve(self):
        for used in (windows(100, 97), windows(14, 100)):
            usage = {"sw": windows(99, 17), "personal": used}
            full = {"personal": {"seven_day": 5000}}
            self.assertEqual(
                sw.pick("sw", usage["sw"], list(usage), full, 1000, usage, {"personal": 20}),
                "sw",
            )

    def test_unknown_window_is_not_counted_as_reserve(self):
        usage = {"sw": windows(99, 17), "personal": windows(14, 97)[1:]}
        full = {"personal": {"seven_day": 5000}}
        self.assertEqual(
            sw.pick("sw", usage["sw"], list(usage), full, 1000, usage, {"personal": 20}), "sw"
        )

    def test_small_reserve_differences_do_not_make_accounts_oscillate(self):
        usage = {"sw": windows(95, 20), "personal": windows(94, 20)}
        full = {"personal": {"five_hour": 5000}}
        self.assertEqual(sw.pick("sw", usage["sw"], list(usage), full, 1000, usage), "sw")
        usage["personal"] = windows(93, 20)
        self.assertEqual(sw.pick("sw", usage["sw"], list(usage), full, 1000, usage), "personal")

    def test_equal_reserves_keep_the_current_account(self):
        usage = {"sw": windows(95, 20), "personal": windows(95, 20)}
        full = {"sw": {"five_hour": 5000}}
        self.assertEqual(
            sw.pick("personal", usage["personal"], list(usage), full, 1000, usage), "personal"
        )


class SubscriptionTest(unittest.TestCase):
    def test_capacity_comes_from_login_metadata(self):
        for kind, tier, expected in (
            ("pro", "default_claude_pro", ("Pro", 1)),
            ("max", "default_claude_max_5x", ("Max 5x", 5)),
            ("max", "default_claude_max_20x", ("Max 20x", 20)),
            ("team", "default_raven", ("Team", 1.25)),
            ("team", "default_claude_max_5x", ("Team Premium", 6.25)),
            ("max", "unknown_future_tier", ("Max", 1)),
        ):
            with self.subTest(kind=kind, tier=tier):
                data = {"claudeAiOauth": {"subscriptionType": kind, "rateLimitTier": tier}}
                self.assertEqual(sw.subscription(data), expected)


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
        self.usage = FULL

        self.assertEqual(self.measure(FULL), sw.RETRY)
        self.assertEqual(self.live_account(), PERSONAL)

        # A reading right after the switch may still be the old account's: it is ignored.
        self.assertEqual(self.measure([{"kind": "five_hour", "percentUsed": 99}]), sw.RETRY)
        state = json.loads(sw.STATE.read_text())
        self.assertEqual(list(state["full"]), ["sw"])

    def test_measure_skips_while_another_session_decides(self):
        self.log_in(SW, "sw")

        with sw.STATE.with_suffix(".lock").open("a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            self.assertEqual(self.measure(FULL), sw.RETRY)

        self.assertEqual(self.live_account(), SW)

    def test_same_hint_is_processed_after_settle_without_a_new_response(self):
        self.log_in(SW, "sw")
        self.usage = FULL
        sw.STATE.write_text(json.dumps({"switchedAt": 1000}))
        with mock.patch.object(sw.time, "time", return_value=1030):
            self.assertEqual(self.measure(FULL), sw.RETRY)

        with mock.patch.object(sw.time, "time", return_value=1061):
            self.assertEqual(self.measure(FULL), sw.RETRY)

        self.assertEqual(self.live_account(), PERSONAL)
        state = json.loads(sw.STATE.read_text())
        self.assertIn("five_hour", state["full"]["sw"])

    def test_a_delayed_sw_hint_does_not_block_personal(self):
        self.log_in(PERSONAL, "me")
        sw.STATE.write_text(json.dumps({"full": {"sw": 5000}, "switchedAt": 1000}))
        with mock.patch.object(sw.time, "time", return_value=1061):
            self.assertIsNone(self.measure(FULL))

        state = json.loads(sw.STATE.read_text())
        self.assertNotIn("personal", state["full"])
        self.assertEqual(self.live_account(), PERSONAL)

    def test_profile_mismatch_does_not_assign_usage_to_the_config_account(self):
        self.log_in(PERSONAL, "sw-old")
        with mock.patch.object(sw, "oauth_get", wraps=self.oauth_get) as request:
            self.assertEqual(self.measure(FULL), sw.RETRY)

        self.assertEqual(request.call_count, 1)
        self.assertNotIn("full", json.loads(sw.STATE.read_text()))
        self.assertEqual(self.live_account(), PERSONAL)

    def test_login_change_during_request_discards_the_result(self):
        self.log_in(SW, "sw")

        def change_login(account, token, state):
            self.log_in(PERSONAL, "me")
            return FULL

        with mock.patch.object(sw, "verified_usage", side_effect=change_login):
            self.assertEqual(self.measure(FULL), sw.RETRY)

        self.assertNotIn("full", json.loads(sw.STATE.read_text()))
        self.assertEqual(self.live_account(), PERSONAL)

    def test_switch_checks_expected_login_under_its_lock(self):
        self.log_in(PERSONAL, "me")
        self.assertFalse(sw.switch("sw", expected=(SW, "at-sw")))
        self.assertEqual(self.live_account(), PERSONAL)

    def test_usage_failure_preserves_full_and_retries_after_backoff(self):
        self.log_in(SW, "sw")
        before = {"personal": 5000}
        sw.STATE.write_text(json.dumps({"full": before}))
        with (
            mock.patch.object(sw.time, "time", return_value=1000),
            mock.patch.object(sw, "oauth_get", side_effect=sw.UsageUnavailable("throttled", 300)),
        ):
            self.assertEqual(self.measure(FULL), sw.RETRY)

        with (
            mock.patch.object(sw.time, "time", return_value=1299),
            mock.patch.object(sw, "oauth_get") as request,
        ):
            self.assertEqual(self.measure(FULL), sw.RETRY)
            request.assert_not_called()

        state = json.loads(sw.STATE.read_text())
        self.assertEqual(state["full"], before)
        self.assertEqual(state["usage"]["sw"]["usageRetryAt"], 1300)
        with mock.patch.object(sw.time, "time", return_value=1300):
            self.assertIsNone(self.measure(FULL))

    def test_rate_limits_back_off_silently_across_calls_without_switching(self):
        self.log_in(SW, "sw")
        before = {"personal": 50_000}
        sw.STATE.write_text(json.dumps({"full": before}))
        now = 1000
        for delay in (300, 450, 675, 1012.5, 1518.75, 1800, 1800):
            with (
                mock.patch.object(sw.time, "time", return_value=now),
                mock.patch.object(
                    sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
                ) as request,
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                self.assertEqual(self.measure(FULL), sw.RETRY)

            request.assert_called_once()
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")
            state = json.loads(sw.STATE.read_text())
            self.assertEqual(state["usage"]["sw"]["usageRetryAt"], now + delay)
            self.assertEqual(state["full"], before)
            self.assertEqual(self.live_account(), SW)

            # Another session waking just before the deadline must not request or grow backoff.
            with (
                mock.patch.object(sw.time, "time", return_value=now + delay - 1),
                mock.patch.object(sw, "oauth_get") as request,
            ):
                self.assertEqual(self.measure(FULL), sw.RETRY)
                request.assert_not_called()

            self.assertEqual(json.loads(sw.STATE.read_text()), state)
            now += delay

    def test_rate_limit_respects_a_server_delay_longer_than_the_backoff_cap(self):
        self.log_in(SW, "sw")
        sw.STATE.write_text(json.dumps({"usageBackoff": 1518.75}))
        with (
            mock.patch.object(sw.time, "time", return_value=1000),
            mock.patch.object(
                sw,
                "oauth_get",
                side_effect=sw.UsageUnavailable("HTTP 429", 3600, rate_limited=True),
            ),
        ):
            self.assertEqual(self.measure(FULL), sw.RETRY)

        state = json.loads(sw.STATE.read_text())
        self.assertEqual(state["usage"]["sw"]["usageRetryAt"], 4600)
        self.assertEqual(state["usage"]["sw"]["usageBackoff"], 1800)

    def test_success_clears_rate_limit_backoff_and_error(self):
        self.log_in(SW, "sw")
        sw.STATE.write_text(json.dumps({"usageBackoff": 1800, "usageError": "HTTP 429"}))
        with mock.patch.object(sw.time, "time", return_value=1000):
            self.assertIsNone(self.measure(LOW))

        state = json.loads(sw.STATE.read_text())["usage"]["sw"]
        self.assertNotIn("usageBackoff", state)
        self.assertNotIn("usageError", state)
        self.assertEqual(state["usageRetryAt"], 1060)

        with (
            mock.patch.object(sw.time, "time", return_value=1060),
            mock.patch.object(
                sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
            ),
        ):
            self.assertEqual(self.measure(LOW), sw.RETRY)

        self.assertEqual(json.loads(sw.STATE.read_text())["usage"]["sw"]["usageRetryAt"], 1360)

    def test_other_usage_errors_remain_visible_without_growing_backoff(self):
        self.log_in(SW, "sw")
        with (
            mock.patch.object(sw.time, "time", return_value=1000),
            mock.patch.object(sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 401")),
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(self.measure(LOW), sw.RETRY)

        self.assertEqual(stderr.getvalue(), "HTTP 401\n")
        state = json.loads(sw.STATE.read_text())["usage"]["sw"]
        self.assertNotIn("usageBackoff", state)
        self.assertEqual(state["usageRetryAt"], 1060)

    def test_status_shows_silent_rate_limit_and_when_it_can_retry(self):
        self.log_in(SW, "sw")
        with (
            mock.patch.object(sw.time, "time", return_value=1000),
            mock.patch.object(
                sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
            ),
        ):
            self.assertEqual(self.measure(LOW), sw.RETRY)

        for now in (1001, 1300):
            with (
                mock.patch.object(sw.time, "time", return_value=now),
                mock.patch.object(
                    sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
                ),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                sw.cmd_status(None)

            self.assertIn("HTTP 429", stdout.getvalue())
            self.assertIn("Next attempt after", stdout.getvalue())

    def test_verified_profile_is_reused_only_for_the_same_token(self):
        self.log_in(SW, "sw")
        state = {}
        with mock.patch.object(sw, "oauth_get", wraps=self.oauth_get) as request:
            sw.verified_usage(SW, "at-sw", state)
            sw.verified_usage(SW, "at-sw", state)
            sw.verified_usage(SW, "at-new", state)

        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            ["profile", "usage", "usage", "profile", "usage"],
        )
        self.assertNotIn("at-sw", json.dumps(state))
        self.assertNotIn("at-new", json.dumps(state))

    def test_malformed_profile_preserves_existing_blocks(self):
        self.log_in(SW, "sw")
        full = {"sw": {"five_hour": 5000}}
        for profile in ({}, {"account": []}, {"account": {"uuid": "a-sw"}, "organization": {}}):
            with self.subTest(profile=profile):
                sw.STATE.write_text(json.dumps({"full": full}))
                with mock.patch.object(sw, "oauth_get", return_value=profile):
                    self.assertEqual(self.measure(FULL), sw.RETRY)

                self.assertEqual(json.loads(sw.STATE.read_text())["full"], full)

    def test_malformed_usage_cannot_clear_a_block_or_switch_accounts(self):
        self.log_in(SW, "sw")
        full = {"sw": {"five_hour": 5000}}
        profile = self.oauth_get("profile", "at-sw")
        for usage in (
            {},
            {"five_hour": {"utilization": 20, "resets_at": "bad"}},
            {"five_hour": {"utilization": float("nan")}},
            {"five_hour": {"utilization": "20"}},
            {"five_hour": None},
        ):
            with self.subTest(usage=usage):
                sw.STATE.write_text(json.dumps({"full": full}))
                with mock.patch.object(sw, "oauth_get", side_effect=[profile, usage]):
                    self.assertEqual(self.measure(FULL), sw.RETRY)

                self.assertEqual(json.loads(sw.STATE.read_text())["full"], full)
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


class ReserveSwitchTest(Home):
    def setUp(self):
        super().setUp()
        self.save("sw", SW, "sw-old")
        self.save("personal", PERSONAL, "me")
        self.log_in(SW, "sw")
        self.set_plan("sw", "team", "default_raven")
        self.set_plan("personal", "max", "default_claude_max_20x")
        self.usage_by_token = {"at-sw": windows(99, 17), "at-me": windows(14, 97)}
        sw.STATE.write_text(
            json.dumps({"full": {"sw": {"five_hour": 5000}, "personal": {"seven_day": 6000}}})
        )

    def snapshot(self):
        with (
            mock.patch.object(sw.time, "time", return_value=1000),
            mock.patch("sys.stdout", io.StringIO()),
        ):
            sw.cmd_status(None)

    def test_switches_to_personal_reserve_and_returns_to_work_after_reset(self):
        with mock.patch.object(sw.time, "time", return_value=1000):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), PERSONAL)
        with mock.patch.object(sw.time, "time", return_value=1061):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), PERSONAL)
        self.usage_by_token["at-sw"] = windows(0, 17)
        with mock.patch.object(sw.time, "time", return_value=1122):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), SW)

    def test_status_cache_can_trigger_switch_without_another_usage_request(self):
        self.snapshot()
        with (
            mock.patch.object(sw.time, "time", return_value=1001),
            mock.patch.object(sw, "oauth_get") as request,
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        request.assert_not_called()
        self.assertEqual(self.live_account(), PERSONAL)

    def test_rate_limited_usage_does_not_prevent_using_recent_verified_reserve(self):
        self.snapshot()
        with (
            mock.patch.object(sw.time, "time", return_value=1061),
            mock.patch.object(
                sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
            ) as request,
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(request.call_count, 2)
        self.assertEqual(self.live_account(), PERSONAL)

    def test_old_current_reading_during_429_can_use_a_fresh_alternative(self):
        self.snapshot()
        original = self.oauth_get

        def request(path, token):
            if token == "at-sw":
                raise sw.UsageUnavailable("HTTP 429", rate_limited=True)

            return original(path, token)

        with (
            mock.patch.object(sw.time, "time", return_value=1400),
            mock.patch.object(sw, "oauth_get", side_effect=request),
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), PERSONAL)
        self.assertGreater(json.loads(sw.STATE.read_text())["full"]["sw"]["five_hour"], 1400)

    def test_legacy_429_cooldown_does_not_need_to_expire_before_failover(self):
        self.snapshot()
        state = json.loads(sw.STATE.read_text())
        state["usage"]["sw"].update(
            checkedAt=600,
            usageRetryAt=1300,
            usageError="Account usage check failed (HTTP 429); will retry",
        )
        sw.STATE.write_text(json.dumps(state))
        with (
            mock.patch.object(sw.time, "time", return_value=1001),
            mock.patch.object(sw, "oauth_get") as request,
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        request.assert_not_called()
        self.assertEqual(self.live_account(), PERSONAL)

    def test_alternative_with_an_authentication_error_is_not_used(self):
        self.snapshot()
        original = self.oauth_get

        def request(path, token):
            if token == "at-me":
                raise sw.UsageUnavailable("HTTP 401")

            return original(path, token)

        with (
            mock.patch.object(sw.time, "time", return_value=1061),
            mock.patch.object(sw, "oauth_get", side_effect=request),
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), SW)

    def test_exhausted_alternative_is_not_used(self):
        self.usage_by_token["at-me"] = windows(14, 100)
        with mock.patch.object(sw.time, "time", return_value=1000):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), SW)

    def test_an_expired_cached_reserve_is_not_used_during_api_cooldown(self):
        self.usage_by_token["at-me"] = [
            limit | {"resetsAt": "1970-01-01T00:20:00Z"} for limit in windows(14, 97)
        ]
        self.snapshot()
        original = self.oauth_get

        def request(path, token):
            if token == "at-me":
                raise sw.UsageUnavailable("HTTP 429", rate_limited=True)

            return original(path, token)

        with (
            mock.patch.object(sw.time, "time", return_value=1201),
            mock.patch.object(sw, "oauth_get", side_effect=request),
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        self.assertEqual(self.live_account(), SW)

    def test_cache_for_another_token_cannot_trigger_a_switch(self):
        self.snapshot()
        self.keychain[(sw.SAVED, "personal")]["login"]["claudeAiOauth"]["accessToken"] = "at-new"
        with (
            mock.patch.object(sw.time, "time", return_value=1001),
            mock.patch.object(sw, "oauth_get") as request,
        ):
            self.assertEqual(self.measure([]), sw.RETRY)

        request.assert_not_called()
        self.assertEqual(self.live_account(), SW)


class StatusTest(Home):
    def setUp(self):
        super().setUp()
        self.save("sw", SW, "sw-old")
        self.save("personal", PERSONAL, "me")
        self.log_in(SW, "sw-live")

    def status(self, now: float = 1000) -> str:
        with (
            mock.patch.object(sw.time, "time", return_value=now),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            sw.cmd_status(None)

        return stdout.getvalue()

    def test_status_reads_both_accounts_with_the_latest_live_token_without_switching(self):
        original = self.oauth_get

        def request(path, token):
            if path == "usage":
                return {
                    "seven_day": {
                        "utilization": 87.5 if token == "at-sw-live" else 100,
                        "resets_at": "1970-01-01T02:00:00Z",
                    },
                    "five_hour": {"utilization": 30, "resets_at": "1970-01-01T01:00:00Z"},
                }

            return original(path, token)

        before = dict(self.keychain)
        full = {"sw": {"seven_day": 7200}}
        sw.STATE.write_text(json.dumps({"full": full}))
        with mock.patch.object(sw, "oauth_get", side_effect=request) as get:
            output = self.status()

        self.assertIn("* sw: me@work [Unknown]\n    Weekly: 12.5% left, resets", output)
        self.assertIn("  personal: me@home [Unknown]\n    Weekly: 0% left, resets", output)
        self.assertIn("(in 1h 43m)", output)
        self.assertIn("5-hour: 70% left", output)
        self.assertEqual(
            [call.args[1] for call in get.call_args_list], ["at-sw-live"] * 2 + ["at-me"] * 2
        )
        self.assertEqual(self.keychain, before)
        self.assertEqual(self.live_account(), SW)
        state = json.loads(sw.STATE.read_text())
        self.assertEqual(state["full"], full)
        self.assertNotIn("at-sw-live", json.dumps(state))
        self.assertNotIn("at-me", json.dumps(state))

    def test_one_unavailable_account_does_not_hide_the_other(self):
        original = self.oauth_get

        def request(path, token):
            if token == "at-sw-live":
                raise sw.UsageUnavailable("HTTP 401")

            return original(path, token)

        with mock.patch.object(sw, "oauth_get", side_effect=request):
            output = self.status()

        self.assertIn("Weekly: remaining unknown", output)
        self.assertIn("HTTP 401", output)
        self.assertIn("  personal: me@home [Unknown]\n    Weekly: 80% left", output)

    def test_failed_refresh_keeps_the_last_reading_and_its_age(self):
        self.status()
        with mock.patch.object(
            sw, "oauth_get", side_effect=sw.UsageUnavailable("network unavailable")
        ):
            output = self.status(1120)

        self.assertIn("Weekly: 80% left", output)
        self.assertIn("(2m ago)", output)
        self.assertIn("network unavailable; showing saved data", output)
        self.assertIn("Next attempt after", output)
        state = json.loads(sw.STATE.read_text())
        self.assertEqual(state["usage"]["sw"]["checkedAt"], 1000)

    def test_status_and_measure_share_cache_and_retry_delays(self):
        with mock.patch.object(sw.time, "time", return_value=1000):
            self.assertIsNone(self.measure(LOW))

        with mock.patch.object(sw, "oauth_get", wraps=self.oauth_get) as get:
            output = self.status(1001)

        self.assertIn("Weekly: 80% left", output)
        self.assertEqual([call.args[1] for call in get.call_args_list], ["at-me", "at-me"])
        with (
            mock.patch.object(sw, "oauth_get") as get,
            mock.patch.object(sw.time, "time", return_value=1002),
        ):
            self.status(1002)
            self.assertEqual(self.measure(LOW), sw.RETRY)

        get.assert_not_called()

    def test_expired_window_is_unknown_until_a_successful_refresh(self):
        self.usage = [{"kind": "seven_day", "percentUsed": 99, "resetsAt": "1970-01-01T00:20:00Z"}]
        self.status()
        with mock.patch.object(
            sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 429", rate_limited=True)
        ):
            output = self.status(1300)

        self.assertIn("Weekly: remaining unknown, last reset", output)
        self.assertIn("(passed)", output)
        self.assertNotIn("1% left", output)
        self.assertNotIn("100% left", output)

    def test_old_state_keeps_reset_times_without_inventing_percentages(self):
        sw.STATE.write_text(
            json.dumps(
                {
                    "full": {"sw": {"seven_day": 7200}},
                    "verifiedLogin": SW,
                    "usageError": "HTTP 429",
                    "usageBackoff": 300,
                    "usageRetryAt": 1300,
                }
            )
        )
        with mock.patch.object(sw, "oauth_get", wraps=self.oauth_get) as get:
            output = self.status()

        self.assertIn("Weekly: remaining unknown, resets", output)
        self.assertIn("(last known)", output)
        self.assertIn("HTTP 429", output)
        self.assertEqual([call.args[1] for call in get.call_args_list], ["at-me", "at-me"])
        state = json.loads(sw.STATE.read_text())
        self.assertEqual(state["usage"]["sw"]["usageBackoff"], 300)
        self.assertNotIn("usageRetryAt", state)

    def test_a_replaced_saved_account_cannot_inherit_another_accounts_usage(self):
        self.status()
        replacement = PERSONAL | {"accountUuid": "a-new"}
        self.save("personal", replacement, "new")
        with mock.patch.object(sw, "oauth_get", side_effect=sw.UsageUnavailable("HTTP 401")):
            output = self.status(1001)

        personal = output.split("  personal:", 1)[1]
        self.assertIn("Weekly: remaining unknown", personal)
        self.assertNotIn("80% left", personal)
        self.assertNotIn("Checked", personal)

    def test_a_keychain_failure_does_not_hide_other_accounts(self):
        original = sw.keychain_read

        def read(service, account):
            if service == sw.SAVED and account == "personal":
                raise SystemExit("Keychain unavailable")

            return original(service, account)

        with mock.patch.object(sw, "keychain_read", side_effect=read):
            output = self.status()

        self.assertIn("Weekly: 80% left", output)
        self.assertIn("personal: Keychain unavailable", output)

    def test_a_missing_access_token_is_reported_per_account(self):
        self.keychain[(sw.SAVED, "personal")]["login"] = {}
        output = self.status()
        self.assertIn("Weekly: 80% left", output)
        self.assertIn("Account usage unavailable: no access token", output)

    def test_status_shows_subscription_and_normalized_reserve(self):
        self.set_plan("sw", "team", "default_raven")
        self.set_plan("personal", "max", "default_claude_max_20x")
        self.usage_by_token = {"at-sw-live": windows(99, 17), "at-me": windows(14, 97)}
        output = self.status()
        self.assertIn("[Team]", output)
        self.assertIn("Reserve: ~1.25 Pro units (estimate)", output)
        self.assertIn("[Max 20x]", output)
        self.assertIn("Reserve: ~60 Pro units (estimate)", output)


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


class UsageTest(unittest.TestCase):
    def test_api_contract(self):
        response = mock.MagicMock()
        response.__enter__.return_value = io.StringIO('{"five_hour":{"utilization":97}}')
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(sw, "build_opener", return_value=opener):
            self.assertEqual(sw.oauth_get("usage", "secret")["five_hour"]["utilization"], 97)

        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/api/oauth/usage")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("Anthropic-beta"), "oauth-2025-04-20")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 5)

    def test_http_errors_preserve_retry_after_and_identify_rate_limits(self):
        for code, delay in ((429, 600), (403, 600), (401, 60), (500, 60)):
            error = HTTPError(
                "https://api.anthropic.com", code, "failed", {"Retry-After": "600"}, None
            )
            opener = mock.Mock()
            opener.open.side_effect = error
            with (
                self.subTest(code=code),
                mock.patch.object(sw, "build_opener", return_value=opener),
                self.assertRaises(sw.UsageUnavailable) as raised,
            ):
                sw.oauth_get("usage", "secret")

            self.assertEqual(raised.exception.retry_after, delay)
            self.assertEqual(raised.exception.rate_limited, code == 429)
            self.assertNotIn("secret", str(raised.exception))

    def test_retry_after_supports_seconds_dates_and_invalid_values(self):
        self.assertEqual(sw.retry_delay("120", 0), 120)
        self.assertEqual(sw.retry_delay("Thu, 01 Jan 1970 00:05:00 GMT", 60), 240)
        self.assertEqual(sw.retry_delay(None, 0), 300)
        self.assertEqual(sw.retry_delay("garbage", 0), 300)
        self.assertEqual(sw.retry_delay("nan", 0), 300)


if __name__ == "__main__":
    unittest.main()
