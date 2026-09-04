from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from trading_scanner.ibkr_readonly import (
    IbkrReadOnlyConfig,
    IbkrReadOnlyUniverseSource,
    IbkrSessionUnavailable,
    IbkrStaleEvidence,
)


class FakeIbkrClient:
    def __init__(self, *, fail_connect=False, stale=False):
        self.connected = False
        self.fail_connect = fail_connect
        self.stale = stale
        self.readonly_calls = []

    async def connect(self, host, port, client_id, *, readonly):
        self.readonly_calls.append(readonly)
        if self.fail_connect:
            raise ConnectionError("offline")
        self.connected = True

    async def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    async def resolve_contracts(self, symbols):
        return ({"conid": 265598, "symbol": "AAPL", "sec_type": "STK",
                 "exchange": "SMART", "currency": "USD", "primary_exchange": "NASDAQ"},)

    async def historical_bars(self, conid, *, duration, bar_size):
        ts = datetime.now(timezone.utc) - (timedelta(days=10) if self.stale else timedelta(minutes=5))
        return tuple({"timestamp": ts, "open": 100, "high": 102, "low": 99,
                      "close": 101, "volume": 1_000_000} for _ in range(20))


class IbkrReadOnlyFoundationTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return IbkrReadOnlyConfig("127.0.0.1", 4002, 71, ("AAPL",), pacing_seconds=0)

    async def test_contract_history_and_liquidity_are_real_adapter_evidence(self):
        client = FakeIbkrClient()
        source = IbkrReadOnlyUniverseSource(client, self.config())
        contracts = await source.resolve_universe()
        self.assertEqual(contracts[0].conid, 265598)
        data = await source.market_data_for(contracts[0])
        self.assertEqual(data.closes[-1], Decimal("101"))
        liquidity = await source.liquidity_context_for(contracts[0])
        self.assertEqual(liquidity.average_daily_volume, Decimal("1000000"))
        self.assertEqual(liquidity.average_daily_dollar_volume, Decimal("101000000"))
        self.assertTrue(all(client.readonly_calls))

    async def test_connection_failure_fails_closed(self):
        source = IbkrReadOnlyUniverseSource(FakeIbkrClient(fail_connect=True), self.config())
        with self.assertRaises(IbkrSessionUnavailable):
            await source.resolve_universe()

    async def test_stale_history_fails_closed(self):
        source = IbkrReadOnlyUniverseSource(FakeIbkrClient(stale=True), self.config())
        contract = (await source.resolve_universe())[0]
        with self.assertRaises(IbkrStaleEvidence):
            await source.market_data_for(contract)

    async def test_adapter_exposes_no_order_submission_capability(self):
        source = IbkrReadOnlyUniverseSource(FakeIbkrClient(), self.config())
        self.assertFalse(hasattr(source, "place_order"))
        self.assertFalse(hasattr(source, "submit_order"))


if __name__ == "__main__":
    unittest.main()
