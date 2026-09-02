"""
MarketHunter

Tests for api/trading_scanner_api.py - the read-only Trading Candidate
Queue API. This router never creates/mutates a candidate; every test
seeds the store directly (mirroring how a real scan cycle would) and
verifies only read behavior.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api.app import app
from trading_scanner.models import LiquidityContext, QueueState, SetupFamily, TradingCandidate, VolatilityContext
from trading_scanner.store import TradingScannerStore

NOW = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def _candidate(**overrides) -> TradingCandidate:
    data = dict(
        conid=1,
        symbol="AAPL",
        sec_type="STK",
        exchange="SMART",
        currency="USD",
        setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH,
        reason_stack=("close above SMA20",),
        liquidity=LiquidityContext(
            average_daily_volume=Decimal("1000000"), average_daily_dollar_volume=Decimal("10000000"), last_price=Decimal("150")
        ),
        volatility=VolatilityContext(realized_range_pct=Decimal("3.5")),
        evidence_status="OK",
        eligible=True,
        discovered_at=NOW,
        scan_cycle_id="cycle-1",
        dedupe_key="1:MOMENTUM_RELATIVE_STRENGTH:cycle-1",
        queue_state=QueueState.CANDIDATE,
    )
    data.update(overrides)
    return TradingCandidate(**data)


class TradingScannerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "trading_scanner.db"
        self.env_patch = mock.patch.dict("os.environ", {"TRADING_SCANNER_DB_PATH": str(self.db_path)})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)
        self.store = TradingScannerStore(self.db_path)

    def test_list_candidates_on_an_empty_store_returns_an_empty_list(self):
        response = self.client.get("/trading-scanner/candidates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["candidates"], [])

    def test_list_candidates_returns_a_seeded_candidate(self):
        self.store.record_candidate(_candidate())
        response = self.client.get("/trading-scanner/candidates")
        body = response.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["symbol"], "AAPL")
        self.assertTrue(body["simulation_only"])

    def test_filters_by_queue_state(self):
        self.store.record_candidate(_candidate(dedupe_key="k1", queue_state=QueueState.CANDIDATE))
        self.store.record_candidate(
            _candidate(dedupe_key="k2", queue_state=QueueState.REJECTED, reject_reason="stale")
        )
        response = self.client.get("/trading-scanner/candidates", params={"queue_state": "REJECTED"})
        body = response.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["dedupe_key"], "k2")

    def test_filters_by_setup_family(self):
        self.store.record_candidate(
            _candidate(dedupe_key="k1", setup_family=SetupFamily.MOMENTUM_RELATIVE_STRENGTH)
        )
        self.store.record_candidate(
            _candidate(dedupe_key="k2", setup_family=SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND)
        )
        response = self.client.get("/trading-scanner/candidates", params={"setup_family": "BREAKOUT_OR_PULLBACK_IN_TREND"})
        body = response.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["dedupe_key"], "k2")

    def test_filters_by_symbol(self):
        self.store.record_candidate(_candidate(dedupe_key="k1", symbol="AAPL"))
        self.store.record_candidate(_candidate(dedupe_key="k2", symbol="MSFT", conid=2))
        response = self.client.get("/trading-scanner/candidates", params={"symbol": "MSFT"})
        body = response.json()
        self.assertEqual(len(body["candidates"]), 1)
        self.assertEqual(body["candidates"][0]["symbol"], "MSFT")

    def test_get_a_single_candidate_by_dedupe_key(self):
        self.store.record_candidate(_candidate())
        response = self.client.get("/trading-scanner/candidates/1:MOMENTUM_RELATIVE_STRENGTH:cycle-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["symbol"], "AAPL")

    def test_get_an_unknown_dedupe_key_returns_404(self):
        response = self.client.get("/trading-scanner/candidates/does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_response_never_includes_an_executable_order_shape(self):
        self.store.record_candidate(_candidate())
        body = self.client.get("/trading-scanner/candidates").json()
        candidate = body["candidates"][0]
        for forbidden_key in ("action", "quantity", "leverage", "stop_loss", "take_profit", "order_intent_id"):
            self.assertNotIn(forbidden_key, candidate)


if __name__ == "__main__":
    unittest.main()
