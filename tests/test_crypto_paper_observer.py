import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.crypto_paper_observer import runtime


class CryptoPaperObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "crypto-paper.db"
        self.base = 1_800_000_000 - (1_800_000_000 % runtime.BAR_SECONDS)
        self.common = [self.base - runtime.BAR_SECONDS * i for i in range(599, -1, -1)]
        self.data = {ts: (100.0, 100.0) for ts in self.common}

    def _patch_common(self, *, current_signal):
        event = {
            "signal_ts": self.common[-1],
            "asset": "BTCUSDT",
            "side": "LONG",
        }
        return (
            patch.object(runtime, "DB_PATH", self.db_path),
            patch.object(runtime, "_fetch_universes", return_value=(list(runtime.ASSETS), ["BTCUSDT"])),
            patch.object(runtime, "_fetch_klines", side_effect=lambda _symbol: dict(self.data)),
            patch.object(runtime, "frozen_events", return_value=[event] if current_signal else []),
            patch.object(runtime, "_fetch_current_bar_open", return_value=(self.common[-1] + runtime.BAR_SECONDS, 101.0)),
            patch.object(runtime.time, "time", return_value=self.common[-1] + runtime.BAR_SECONDS + 60),
        )

    def test_signal_is_filled_once_and_replay_is_idempotent(self):
        patches = self._patch_common(current_signal=True)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            first = runtime.run_cycle()
            second = runtime.run_cycle()

        self.assertEqual(first["status"], "OK")
        self.assertEqual(first["paper_order_counts"], {"OPEN": 1})
        self.assertEqual(second["paper_order_counts"], {"OPEN": 1})
        with runtime.sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_scan_cycles").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_paper_orders").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_material_states").fetchone()[0], 2)

    def test_no_signal_compacts_to_one_material_state_per_bar(self):
        patches = self._patch_common(current_signal=False)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            runtime.run_cycle()
            runtime.run_cycle()

        with runtime.sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_scan_cycles").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_material_states WHERE state='NO-SIGNAL'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM crypto_paper_orders").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
