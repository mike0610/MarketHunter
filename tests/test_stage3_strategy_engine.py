from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from strategies.registry_foundation import StrategyUsability, StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from strategy_engine.models import StrategyDecisionOutcome
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import (
    LiquidityContext, QueueState, SetupFamily, TradingCandidate, VolatilityContext,
)


NOW = datetime(2026, 9, 5, 1, 30, tzinfo=timezone.utc)


def candidate(state=QueueState.CANDIDATE, family=SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND):
    return TradingCandidate(
        conid=1, symbol="SPY", sec_type="STK", exchange="SMART", currency="USD",
        setup_family=family, reason_stack=("BREAKOUT confirmed",),
        liquidity=LiquidityContext(Decimal("1000000"), Decimal("500000000"), Decimal("500")),
        volatility=VolatilityContext(Decimal("1.2")), evidence_status="OK", eligible=True,
        discovered_at=NOW, scan_cycle_id="cycle-1",
        dedupe_key=f"1:{family.value}:cycle-1", queue_state=state,
    )


USABLE = StrategyVersionAssessment(StrategyUsability.USABLE, ())


class Stage3StrategyEngineTests(unittest.TestCase):
    def test_candidate_produces_deterministic_long_without_execution_fields(self):
        result = validate_candidate(candidate(), strategy_assessment=USABLE, decided_at=NOW)
        self.assertEqual(result.outcome, StrategyDecisionOutcome.LONG)
        for forbidden in ("quantity", "leverage", "stop_loss", "take_profit", "order_intent", "fill", "position"):
            self.assertFalse(hasattr(result, forbidden))

    def test_non_candidate_is_rejected(self):
        result = validate_candidate(candidate(QueueState.WATCH), strategy_assessment=USABLE, decided_at=NOW)
        self.assertEqual(result.outcome, StrategyDecisionOutcome.REJECTED)

    def test_family_without_directional_rule_is_no_trade(self):
        result = validate_candidate(candidate(family=SetupFamily.ABNORMAL_VOLUME_CATALYST), strategy_assessment=USABLE, decided_at=NOW)
        self.assertEqual(result.outcome, StrategyDecisionOutcome.NO_TRADE)

    def test_store_is_idempotent_and_creates_no_execution_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "stage3.db"
            store = StrategyDecisionStore(db)
            result = validate_candidate(candidate(), strategy_assessment=USABLE, decided_at=NOW)
            self.assertEqual(store.record(result), result)
            self.assertEqual(store.record(result), result)
            self.assertEqual(len(store.list_all()), 1)
            con = sqlite3.connect(db)
            tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
            con.close()
            self.assertEqual(tables, {"strategy_decisions"})


if __name__ == "__main__":
    unittest.main()
