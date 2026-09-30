"""Offline regression tests for prefetch lifecycle and legacy reconciliation."""
import json
import sqlite3
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import agent
import legacy_lifecycle_maintenance as legacy


SYM = "TESTUSDT"
SIGNAL_MS = 1_800_000_899_999
NOW_MS = SIGNAL_MS + agent.BAR_MS + 60_000


def seed(conn, *, symbol=SYM, signal_ms=SIGNAL_MS, expires_ms=None):
    conn.execute(
        """INSERT INTO active_breakouts
           (symbol,signal_candle_ms,range_high,expires_ms,status,direction,range_low)
           VALUES(?,?,?,?, 'ACTIVE','LONG',?)""",
        (symbol, signal_ms, 100.0,
         expires_ms if expires_ms is not None else signal_ms + agent.WINDOW_MS, 90.0),
    )
    conn.commit()


class PrefetchLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        agent.init(self.conn)
        seed(self.conn)

    def tearDown(self):
        self.conn.close()

    def run_cycle(self, *, bar_prices, when_ms=NOW_MS, prefetched=True, failed=False):
        bars = [
            {"end": SIGNAL_MS + (i + 1) * agent.BAR_MS, "close": price}
            for i, price in enumerate(bar_prices)
        ]
        prefetch = ({SYM: bars}, {}) if prefetched else ({}, {})
        if failed:
            prefetch = ({}, {SYM: RuntimeError("WEEX M15 unavailable")})
        with (
            patch.object(agent, "universe", return_value={SYM}),
            patch.object(agent, "snapshot", return_value={SYM: {"symbol": SYM}}),
            patch.object(agent, "eligible", return_value=True),
            patch.object(agent, "refresh_needed", return_value=False),
            patch.object(agent, "prefetch_m15", return_value=prefetch),
            patch.object(agent, "flush_notifications"),
            patch.object(agent, "analyze", return_value=None),
            patch.object(agent, "emit"),
            patch.object(agent.time, "time", return_value=when_ms / 1000),
            patch.object(agent, "candles", return_value=bars) as fallback,
        ):
            agent.cycle(self.conn, 120)
        return fallback

    def lifecycle(self):
        return [
            row[0] for row in self.conn.execute(
                "SELECT state FROM lifecycle_events ORDER BY state"
            )
        ]

    def test_successful_prefetch_confirms_first_closed_bar(self):
        fallback = self.run_cycle(bar_prices=[101.0])
        self.assertEqual(self.lifecycle(), ["BREAKOUT_CONFIRMED_PAPER"])
        self.assertEqual(
            self.conn.execute("SELECT status FROM active_breakouts").fetchone()[0],
            "ACTIVE",
        )
        fallback.assert_not_called()
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM notification_outbox").fetchone()[0],
            1,
        )

    def test_prefetched_first_bar_invalidates_without_confirmation(self):
        fallback = self.run_cycle(bar_prices=[99.0])
        self.assertEqual(self.lifecycle(), ["BREAKOUT_INVALIDATED"])
        self.assertEqual(
            self.conn.execute("SELECT status FROM active_breakouts").fetchone()[0],
            "BREAKOUT_INVALIDATED",
        )
        fallback.assert_not_called()

    def test_partial_current_candles_do_not_guess_outcome(self):
        self.run_cycle(
            bar_prices=[101.0],
            when_ms=SIGNAL_MS + 2 * agent.BAR_MS + 60_000,
        )
        self.assertEqual(self.lifecycle(), [])
        self.assertEqual(
            self.conn.execute("SELECT status FROM active_breakouts").fetchone()[0],
            "ACTIVE",
        )

    def test_fallback_uses_candles_when_prefetch_missing(self):
        fallback = self.run_cycle(bar_prices=[99.0], prefetched=False)
        fallback.assert_called_once_with(SYM)
        self.assertEqual(self.lifecycle(), ["BREAKOUT_INVALIDATED"])

    def test_failed_prefetch_does_not_manufacture_outcome(self):
        fallback = self.run_cycle(bar_prices=[], failed=True)
        fallback.assert_not_called()
        self.assertEqual(self.lifecycle(), [])
        self.assertEqual(
            self.conn.execute("SELECT status FROM active_breakouts").fetchone()[0],
            "ACTIVE",
        )

    def test_second_prefetched_cycle_does_not_duplicate_confirmation(self):
        self.run_cycle(bar_prices=[101.0])
        self.run_cycle(bar_prices=[101.0])
        self.assertEqual(self.lifecycle(), ["BREAKOUT_CONFIRMED_PAPER"])
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM notification_outbox").fetchone()[0],
            1,
        )


class HttpErrorDiagnosticsTests(unittest.TestCase):
    def test_http_error_logs_safe_status_and_timeframe_only(self):
        error = HTTPError("https://example.test/secret/never-log", 400, "Bad request", {}, None)
        with patch.object(agent, "fetch_raw", side_effect=error), patch.object(agent, "emit") as emit:
            with self.assertRaises(HTTPError):
                agent._bg_candles("BADUSDT", "1d", 21, agent.DAY_MS)
        emit.assert_called_once_with(
            type="MTF_REFRESH_HTTP_ERROR", symbol="BADUSDT", interval="1d", status_code=400
        )
        self.assertNotIn("never-log", str(emit.call_args))


class LegacyReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        agent.init(self.conn)
        self.as_of_ms = 2_000_000_000_000
        self.old_ms = self.as_of_ms - 72 * 60 * 60 * 1000
        self.recent_ms = self.as_of_ms - 8 * 60 * 60 * 1000
        seed(
            self.conn, symbol="OLDUSDT", signal_ms=self.old_ms,
            expires_ms=self.old_ms + agent.WINDOW_MS,
        )
        seed(
            self.conn, symbol="FRESHUSDT", signal_ms=self.recent_ms,
            expires_ms=self.recent_ms + agent.WINDOW_MS,
        )

    def tearDown(self):
        self.conn.close()

    def test_retire_only_genuinely_stale_preserves_history_sends_no_telegram(self):
        with self.conn:
            result = legacy.retire_legacy_overdue(
                self.conn, as_of_ms=self.as_of_ms,
            )
        self.assertEqual(result["retired"], 1)
        self.assertFalse(result["telegram_queued"])
        self.assertEqual(
            dict(self.conn.execute("SELECT symbol,status FROM active_breakouts")),
            {"OLDUSDT": "BREAKOUT_UNVERIFIED", "FRESHUSDT": "ACTIVE"},
        )
        lifecycle = self.conn.execute(
            "SELECT symbol,state,payload_json FROM lifecycle_events"
        ).fetchall()
        self.assertEqual(len(lifecycle), 1)
        self.assertEqual(lifecycle[0][:2], ("OLDUSDT", "BREAKOUT_UNVERIFIED"))
        self.assertTrue(json.loads(lifecycle[0][2])["historical_reconciliation"])
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM notification_outbox").fetchone()[0],
            0,
        )
        with self.conn:
            again = legacy.retire_legacy_overdue(
                self.conn, as_of_ms=self.as_of_ms + 24 * 60 * 60 * 1000,
            )
        self.assertTrue(again["already_applied"])
        self.assertEqual(again["retired"], 0)
        self.assertEqual(
            self.conn.execute("SELECT count(*) FROM lifecycle_events").fetchone()[0],
            1,
        )

    def test_preserves_existing_terminal_record_for_review(self):
        self.conn.execute(
            """INSERT INTO lifecycle_events
               (symbol,signal_candle_ms,state,candle_close_ms,observed_at_utc,payload_json)
               VALUES (?,?,?,?,?,?)""",
            ("OLDUSDT", self.old_ms, "BREAKOUT_INVALIDATED", self.old_ms + agent.BAR_MS,
             "2026-09-01T00:00:00+00:00", "{}"),
        )
        with self.conn:
            result = legacy.retire_legacy_overdue(self.conn, as_of_ms=self.as_of_ms)
        self.assertEqual(result["skipped_conflicting"], 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM active_breakouts WHERE symbol='OLDUSDT'"
            ).fetchone()[0],
            "ACTIVE",
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT count(*) FROM lifecycle_events WHERE symbol='OLDUSDT'"
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
