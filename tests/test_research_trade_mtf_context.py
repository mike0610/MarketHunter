"""
MarketHunter

Tests for MTF persistence and API contract v1: ResearchTrade.mtf_context
is populated from signal.metadata (mtf_*-prefixed keys only) at trade
creation, persisted/restored via SQLite, and exposed through the API as
a typed ResearchTradeMTFResponse.

Confirmation-logic itself (is_confirmed, score bonus, timestamp
alignment, etc) is already covered in tests/daily_levels/ - these tests
only exercise the copy/filter/persist/serialize path, not DailyLevels
strategy behavior.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.research_api import (
    ResearchTradeMTFResponse,
    ResearchTradeResponse,
)
from models.signal import Signal
from research.manager import ResearchManager
from research.models.trade import ResearchTrade
from research.storage.repository import ResearchRepository


def make_signal(
    *,
    metadata: dict,
    symbol: str = "BTCUSDT",
    strategy: str = "DailyLevels",
    direction: str = "LONG",
    market: str = "futures",
    score: float = 80.0,
) -> Signal:
    """
    Create a deterministic virtual signal carrying arbitrary metadata.
    """

    signal = Signal(
        symbol=symbol,
        market=market,
        timeframe="1d",
        strategy=strategy,
        direction=direction,
        score=score,
    )

    signal.metadata.update(metadata)

    return signal


CONFIRMED_MTF_METADATA = {
    "mtf_context_version": "v1",
    "mtf_primary_timeframe": "1d",
    "mtf_entry_timeframe": "1h",
    "mtf_entry_expected_pattern": "breakout_close",
    "mtf_entry_confirmation_type": "breakout_close",
    "mtf_entry_confirmation_is_confirmed": True,
    "mtf_entry_confirmation_applied": True,
    "mtf_entry_confirmation_base_score": 76,
    "mtf_entry_confirmation_score_delta": 4,
    "mtf_entry_confirmation_final_score": 80,
    "mtf_entry_raw_candle_count": 6,
    "mtf_entry_aligned_candle_count": 5,
    "mtf_entry_discarded_candle_count": 1,
    "mtf_entry_confirmation_analyzed_candles": 5,
    "mtf_entry_confirmation_candle_open_time": (
        "2026-07-10T01:00:00+00:00"
    ),
    "mtf_daily_signal_close_time": (
        "2026-07-09T23:59:59.999000+00:00"
    ),
}

NON_MTF_METADATA = {
    "risk_geometry_valid": True,
    "risk_geometry_summary": "OK",
    "risk_geometry_reasons": ["fine"],
    "stop_distance": 1.5,
    "target_rr": 3.0,
    "target_clear": True,
    "target_summary": "clear",
    "reaction_confirmed": True,
    "reaction_score": 2,
    "reaction_reasons": ["Bullish BOS"],
    "probability": 82,
    "confidence": "A",
    "probability_reasons": ["base"],
    "elite_signal": False,
    "research_group": "experimental",
    "experiment_tag": "daily_levels_v1",
}


class ResearchTradeMTFContextCreationTests(unittest.TestCase):
    """
    ResearchManager.create_from_signal() copies mtf_* metadata into
    ResearchTrade.mtf_context and nothing else.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        database_path = Path(
            self.temp_dir.name
        ) / "research.db"

        self.repository = ResearchRepository(
            path=str(database_path),
        )

        self.manager = ResearchManager(
            repository=self.repository,
            max_open_trades=10,
            max_open_trades_per_symbol=2,
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temp_dir.cleanup()

    def test_all_mtf_prefixed_keys_are_transferred(self) -> None:
        signal = make_signal(
            metadata={
                **CONFIRMED_MTF_METADATA,
                **NON_MTF_METADATA,
            },
        )

        result = self.manager.create_from_signal(
            signal=signal,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            probability=82,
        )

        self.assertTrue(result.created)

        for key, value in CONFIRMED_MTF_METADATA.items():
            self.assertIn(key, result.trade.mtf_context)
            self.assertEqual(
                result.trade.mtf_context[key],
                value,
            )

    def test_non_mtf_metadata_is_excluded(self) -> None:
        signal = make_signal(
            metadata={
                **CONFIRMED_MTF_METADATA,
                **NON_MTF_METADATA,
            },
        )

        result = self.manager.create_from_signal(
            signal=signal,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            probability=82,
        )

        self.assertTrue(result.created)

        for key in NON_MTF_METADATA:
            self.assertNotIn(
                key,
                result.trade.mtf_context,
            )

        self.assertEqual(
            len(result.trade.mtf_context),
            len(CONFIRMED_MTF_METADATA),
        )

    def test_trade_mtf_context_is_a_separate_copy(self) -> None:
        signal = make_signal(
            metadata=dict(CONFIRMED_MTF_METADATA),
        )

        result = self.manager.create_from_signal(
            signal=signal,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            probability=82,
        )

        self.assertTrue(result.created)

        signal.metadata["mtf_context_version"] = "mutated"
        result.trade.mtf_context["mtf_primary_timeframe"] = "mutated"

        self.assertEqual(
            signal.metadata["mtf_primary_timeframe"],
            "1d",
        )
        self.assertNotEqual(
            result.trade.mtf_context["mtf_context_version"],
            "mutated",
        )

    def test_signal_without_mtf_metadata_gets_empty_context(
        self,
    ) -> None:
        signal = make_signal(
            metadata=dict(NON_MTF_METADATA),
        )

        result = self.manager.create_from_signal(
            signal=signal,
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            probability=82,
        )

        self.assertTrue(result.created)
        self.assertEqual(
            result.trade.mtf_context,
            {},
        )


class ResearchTradeMTFContextPersistenceTests(unittest.TestCase):
    """
    ResearchRepository round-trips mtf_context through SQLite as JSON,
    and old rows created before this column existed stay compatible.
    """

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        self.database_path = Path(
            self.temp_dir.name
        ) / "research.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_repository_round_trips_full_mtf_context(self) -> None:
        repository = ResearchRepository(
            path=str(self.database_path),
        )

        try:
            trade = ResearchTrade(
                id="trade-1",
                signal_id="signal-1",
                symbol="BTCUSDT",
                market="futures",
                timeframe="1d",
                strategy="DailyLevels",
                direction="LONG",
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=115.0,
                probability=82,
                score=80.0,
                mtf_context=dict(CONFIRMED_MTF_METADATA),
            )

            repository.save(trade)

            restored = repository.get_by_id(
                trade_id="trade-1",
            )

            self.assertIsNotNone(restored)
            self.assertEqual(
                restored.mtf_context,
                CONFIRMED_MTF_METADATA,
            )
        finally:
            repository.close()

    def test_old_row_without_mtf_context_column_reads_as_empty(
        self,
    ) -> None:
        # Simulate a database created before this migration by
        # building the pre-MTF schema directly, bypassing
        # ResearchRepository.create_schema()/migrate_schema().
        connection = sqlite3.connect(str(self.database_path))

        try:
            connection.execute(
                """
                CREATE TABLE research_trades (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    probability INTEGER NOT NULL,
                    score REAL NOT NULL,
                    reasons TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    opened_at TEXT,
                    closed_at TEXT,
                    close_reason TEXT
                )
                """
            )

            connection.execute(
                """
                INSERT INTO research_trades (
                    id, signal_id, symbol, market, timeframe,
                    strategy, direction, entry_price, stop_loss,
                    take_profit, probability, score, reasons,
                    status, created_at, opened_at, closed_at,
                    close_reason
                ) VALUES (
                    'legacy-1', NULL, 'ETHUSDT', 'futures', '1d',
                    'DailyLevels', 'LONG', 100.0, 95.0, 115.0, 70,
                    76.0, '[]', 'waiting_entry',
                    '2026-01-01T00:00:00+00:00', NULL, NULL, NULL
                )
                """
            )

            connection.commit()
        finally:
            connection.close()

        # Opening a ResearchRepository against this pre-existing
        # database runs create_schema() (no-op, table already
        # exists) and migrate_schema() (adds mtf_context TEXT NOT
        # NULL DEFAULT '{}' via ALTER TABLE, backfilling the legacy
        # row automatically - no manual backfill needed).
        repository = ResearchRepository(
            path=str(self.database_path),
        )

        try:
            restored = repository.get_by_id(
                trade_id="legacy-1",
            )

            self.assertIsNotNone(restored)
            self.assertEqual(
                restored.mtf_context,
                {},
            )
        finally:
            repository.close()

    def test_trade_without_mtf_context_saves_and_restores_as_empty(
        self,
    ) -> None:
        repository = ResearchRepository(
            path=str(self.database_path),
        )

        try:
            trade = ResearchTrade(
                id="trade-2",
                signal_id=None,
                symbol="BTCUSDT",
                market="futures",
                timeframe="1d",
                strategy="FVG",
                direction="LONG",
                entry_price=100.0,
                stop_loss=95.0,
                take_profit=115.0,
                probability=70,
                score=70.0,
            )

            repository.save(trade)

            restored = repository.get_by_id(
                trade_id="trade-2",
            )

            self.assertIsNotNone(restored)
            self.assertEqual(
                restored.mtf_context,
                {},
            )
        finally:
            repository.close()


class ResearchTradeMTFResponseTests(unittest.TestCase):
    """
    API-layer mapping from ResearchTrade.mtf_context to the typed
    ResearchTradeMTFResponse, and its absence for legacy trades.
    """

    def _trade(self, **overrides) -> ResearchTrade:
        defaults = dict(
            id="trade-1",
            signal_id="signal-1",
            symbol="BTCUSDT",
            market="futures",
            timeframe="1d",
            strategy="DailyLevels",
            direction="LONG",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            probability=82,
            score=80.0,
        )

        defaults.update(overrides)

        return ResearchTrade(**defaults)

    def test_confirmed_context_maps_to_typed_response(self) -> None:
        trade = self._trade(
            mtf_context=dict(CONFIRMED_MTF_METADATA),
        )

        response = ResearchTradeResponse.from_trade(trade)

        self.assertIsInstance(
            response.mtf,
            ResearchTradeMTFResponse,
        )
        self.assertEqual(response.mtf.context_version, "v1")
        self.assertEqual(response.mtf.entry_timeframe, "1h")
        self.assertEqual(
            response.mtf.confirmation_type,
            "breakout_close",
        )
        self.assertTrue(response.mtf.confirmed)
        self.assertTrue(response.mtf.applied)
        self.assertEqual(response.mtf.base_score, 76)
        self.assertEqual(response.mtf.score_delta, 4)
        self.assertEqual(response.mtf.final_score, 80)
        self.assertEqual(response.mtf.aligned_candle_count, 5)
        self.assertEqual(
            response.mtf.confirmation_candle_open_time,
            "2026-07-10T01:00:00+00:00",
        )
        self.assertEqual(
            response.mtf.daily_signal_close_time,
            "2026-07-09T23:59:59.999000+00:00",
        )

    def test_base_score_plus_delta_equals_final_score(self) -> None:
        trade = self._trade(
            mtf_context=dict(CONFIRMED_MTF_METADATA),
        )

        response = ResearchTradeResponse.from_trade(trade)

        self.assertEqual(
            response.mtf.base_score + response.mtf.score_delta,
            response.mtf.final_score,
        )

    def test_legacy_trade_with_empty_context_returns_none(
        self,
    ) -> None:
        trade = self._trade(
            mtf_context={},
        )

        response = ResearchTradeResponse.from_trade(trade)

        self.assertIsNone(response.mtf)

        serialized = json.loads(
            response.model_dump_json(),
        )

        self.assertIsNone(serialized["mtf"])

    def test_trade_score_is_unaffected_by_mtf_serialization(
        self,
    ) -> None:
        trade = self._trade(
            score=80.0,
            mtf_context=dict(CONFIRMED_MTF_METADATA),
        )

        response = ResearchTradeResponse.from_trade(trade)

        self.assertEqual(response.score, trade.score)
        self.assertEqual(response.score, 80.0)


if __name__ == "__main__":
    unittest.main()
