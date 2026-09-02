"""
MarketHunter

Tests for tools/gil_trading_scanner_runtime/runtime.py - the scheduler
entry point. No live IBKR session exists in this environment
(build_ibkr_universe_source() always returns None today - see
trading_scanner/universe.py), so the only behavior this entry point
can actually exercise is its own fail-closed skip - and that is
exactly what must be proven: a missing universe source is a normal,
successful no-op, never a crash.
"""

from __future__ import annotations

import unittest

from tools.gil_trading_scanner_runtime.runtime import EXIT_OK, main


class GilTradingScannerRuntimeTests(unittest.TestCase):
    def test_main_exits_ok_when_no_ibkr_universe_source_is_configured(self):
        with self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, EXIT_OK)


if __name__ == "__main__":
    unittest.main()
