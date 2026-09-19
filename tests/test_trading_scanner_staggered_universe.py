from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.gil_trading_scanner_runtime.runtime import _commit_universe_cursor, _select_universe_batch


class StaggeredUniverseTests(unittest.TestCase):
    def test_round_robin_batches_persist_cursor_and_wrap(self):
        symbols = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "META")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "cursor.txt"
            env = {
                "TRADING_SCANNER_UNIVERSE_BATCH_SIZE": "5",
                "TRADING_SCANNER_UNIVERSE_BATCH_STATE_PATH": str(state),
            }
            with patch.dict(os.environ, env, clear=False):
                first, pending = _select_universe_batch(symbols)
                self.assertEqual(first, symbols[:5])
                self.assertFalse(state.exists())
                retry, _ = _select_universe_batch(symbols)
                self.assertEqual(retry, first)
                _commit_universe_cursor(pending)
                second, pending = _select_universe_batch(symbols)
                self.assertEqual(second, ("AMD", "META", "SPY", "QQQ", "AAPL"))
                _commit_universe_cursor(pending)
                third, _ = _select_universe_batch(symbols)
                self.assertEqual(third, ("MSFT", "NVDA", "AMD", "META", "SPY"))

    def test_disabled_batching_keeps_full_universe(self):
        symbols = ("SPY", "QQQ")
        with patch.dict(os.environ, {"TRADING_SCANNER_UNIVERSE_BATCH_SIZE": "0"}, clear=False):
            self.assertEqual(_select_universe_batch(symbols), (symbols, None))


if __name__ == "__main__":
    unittest.main()
