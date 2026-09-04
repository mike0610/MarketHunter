from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from market_data.foundation import LiquidityEvidence, MarketBar, MarketInstrument, MarketSeries
from trading_scanner.market_data_adapter import MarketDataScannerAdapter
from trading_scanner.scan import run_scan_cycle
from trading_scanner.store import TradingScannerStore


class FakeProvider:
    def __init__(self):
        self.instrument = MarketInstrument("TEST", "US_STOCK_OR_ETF", "USD", "NASDAQ")
        self.now = datetime(2026, 9, 4, 20, 0, tzinfo=timezone.utc)

    async def universe(self):
        return (self.instrument,)

    async def history(self, instrument, *, timeframe="1d", limit=120):
        bars = tuple(
            MarketBar(
                self.now,
                Decimal(100 + i),
                Decimal(101 + i),
                Decimal(99 + i),
                Decimal(100 + i),
                Decimal("2000000"),
            )
            for i in range(60)
        )
        return MarketSeries(
            instrument, timeframe, bars[-limit:], "FAKE_REAL_PROVIDER",
            "provider://TEST/1d", self.now, self.now,
        )

    async def liquidity(self, instrument):
        return LiquidityEvidence(
            instrument, Decimal("2000000"), Decimal("318000000"),
            Decimal("159"), "FAKE_REAL_PROVIDER", self.now, "provider://TEST/1d",
        )


class ScannerMarketDataAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_provider_boundary_drives_durable_candidates_only(self):
        adapter = MarketDataScannerAdapter(FakeProvider())
        contracts = await adapter.resolve_universe()
        self.assertEqual(contracts[0].symbol, "TEST")

        with tempfile.TemporaryDirectory() as tmp:
            store = TradingScannerStore(Path(tmp) / "scanner.db")
            result = await run_scan_cycle(
                adapter, store, scan_cycle_id="cycle-1",
                now=datetime(2026, 9, 4, 20, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(result.contracts_seen, 1)
            self.assertEqual(len(store.list_candidates()), 3)

            # Exact same cycle is idempotent: no duplicate durable rows.
            await run_scan_cycle(
                adapter, store, scan_cycle_id="cycle-1",
                now=datetime(2026, 9, 4, 20, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(len(store.list_candidates()), 3)

    async def test_adapter_has_zero_execution_surface(self):
        adapter = MarketDataScannerAdapter(FakeProvider())
        for forbidden in ("place_order", "submit_order", "fill", "order_intent"):
            self.assertFalse(hasattr(adapter, forbidden))


if __name__ == "__main__":
    unittest.main()
