"""
MarketHunter

Tests for Outcome Intelligence runtime orchestration
(tools/outcome_intelligence/runtime.py).
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import httpx

from tools.outcome_intelligence.acquisition import (
    SETUP_REASONS_ENDPOINT,
    STATISTICS_ENDPOINT,
)
from tools.outcome_intelligence.analysis import PERSISTENCE_MIN_CONSECUTIVE_RUNS
from tools.outcome_intelligence.runtime import (
    ENV_API_BASE_URL,
    ENV_SLACK_WEBHOOK_URL,
    EXIT_CONFIG_ERROR,
    EXIT_FAILURE,
    EXIT_OK,
    run_daily_cycle,
    run_weekly_cycle,
)

STATISTICS_BODY = {"total": 10, "wins": 5, "losses": 5, "win_rate": 50.0}

SETUP_REASONS_BODY = {
    "by_strategy": [],
    "by_setup_reason": [],
    "by_close_reason": [],
    "by_status": [],
    "by_outcome": [],
    "by_outcome_group": [],
}


def _capture_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            STATISTICS_BODY
            if request.url.path == STATISTICS_ENDPOINT
            else SETUP_REASONS_BODY
        )
        return httpx.Response(
            200,
            content=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json"},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _failing_capture_client() -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )


def _slack_client(handler=None) -> tuple[httpx.Client, list]:
    calls: list = []

    def default_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    return httpx.Client(
        transport=httpx.MockTransport(handler or default_handler)
    ), calls


def _never_called_slack_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(
            "Slack should not have been called when nothing is applicable "
            "to report"
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


REQUIRED_ENV = {
    ENV_API_BASE_URL: "http://example.test",
    ENV_SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/T/B/X",
}


class RunDailyCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_dir = Path(self._tmp.name)

    def test_missing_env_fails_closed_with_config_error(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_CONFIG_ERROR)
        self.assertFalse((self.output_dir / "runs").exists())

    def test_missing_slack_webhook_only_fails_closed(self) -> None:
        with mock.patch.dict(
            "os.environ", {ENV_API_BASE_URL: "http://example.test"}, clear=True
        ):
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_CONFIG_ERROR)

    def test_capture_failure_returns_failure_and_writes_nothing(self) -> None:
        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_failing_capture_client(),
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_FAILURE)
        self.assertFalse((self.output_dir / "runs").exists())

    def test_first_run_ok_with_no_slack_delivery(self) -> None:
        # Only 1 run exists after this capture - nothing "applicable"
        # to report yet, so Slack must not be contacted.
        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=_never_called_slack_client(),
                now_utc=lambda: datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(list((self.output_dir / "runs").iterdir())), 1)

    def test_second_run_delivers_daily_report(self) -> None:
        slack_client, calls = _slack_client()

        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=_never_called_slack_client(),
                now_utc=lambda: datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc),
            )
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=slack_client,
                now_utc=lambda: datetime(2026, 8, 26, 6, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(calls), 1)
        self.assertIn(b"daily change", calls[0].content)

    def test_slack_delivery_failure_returns_failure_but_keeps_capture(self) -> None:
        failing_slack = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        )

        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=_never_called_slack_client(),
                now_utc=lambda: datetime(2026, 8, 25, 6, 0, tzinfo=timezone.utc),
            )
            code = run_daily_cycle(
                output_dir=self.output_dir,
                capture_client=_capture_client(),
                slack_client=failing_slack,
                now_utc=lambda: datetime(2026, 8, 26, 6, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(code, EXIT_FAILURE)
        # The second capture is already durably persisted despite the
        # Slack failure - delivery failure never loses data.
        self.assertEqual(len(list((self.output_dir / "runs").iterdir())), 2)


class RunWeeklyCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output_dir = Path(self._tmp.name)

    def _seed_runs(self, count: int) -> None:
        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            for i in range(count):
                run_daily_cycle(
                    output_dir=self.output_dir,
                    capture_client=_capture_client(),
                    slack_client=_slack_client()[0],
                    now_utc=lambda i=i: datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
                    + timedelta(days=i),
                )

    def test_missing_webhook_fails_closed_with_config_error(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            code = run_weekly_cycle(
                output_dir=self.output_dir,
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_CONFIG_ERROR)

    def test_weekly_cycle_does_not_require_api_base_url(self) -> None:
        self._seed_runs(PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1)

        with mock.patch.dict(
            "os.environ",
            {ENV_SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/T/B/X"},
            clear=True,
        ):
            slack_client, calls = _slack_client()
            code = run_weekly_cycle(
                output_dir=self.output_dir, slack_client=slack_client
            )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(calls), 1)

    def test_insufficient_history_is_ok_with_no_delivery(self) -> None:
        self._seed_runs(PERSISTENCE_MIN_CONSECUTIVE_RUNS)  # one short

        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            code = run_weekly_cycle(
                output_dir=self.output_dir,
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_OK)

    def test_enough_history_delivers_weekly_report(self) -> None:
        self._seed_runs(PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1)

        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            slack_client, calls = _slack_client()
            code = run_weekly_cycle(
                output_dir=self.output_dir, slack_client=slack_client
            )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(calls), 1)
        self.assertIn(b"weekly review", calls[0].content)

    def test_slack_delivery_failure_returns_failure(self) -> None:
        self._seed_runs(PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1)

        failing_slack = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        )

        with mock.patch.dict("os.environ", REQUIRED_ENV, clear=True):
            code = run_weekly_cycle(
                output_dir=self.output_dir, slack_client=failing_slack
            )

        self.assertEqual(code, EXIT_FAILURE)

    def test_weekly_never_captures(self) -> None:
        # No runs exist at all, and weekly is given no API base URL -
        # it must not attempt any capture (which would require it).
        with mock.patch.dict(
            "os.environ",
            {ENV_SLACK_WEBHOOK_URL: "https://hooks.slack.com/services/T/B/X"},
            clear=True,
        ):
            code = run_weekly_cycle(
                output_dir=self.output_dir,
                slack_client=_never_called_slack_client(),
            )

        self.assertEqual(code, EXIT_OK)
        self.assertFalse((self.output_dir / "runs").exists())


if __name__ == "__main__":
    unittest.main()
