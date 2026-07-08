"""
MarketHunter

Tests for scan journal persistence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from models.signal import Signal
from research.storage.scan_journal_repository import (
    ScanJournalRepository,
)


class ScanJournalRepositoryTests(unittest.TestCase):
    """
    Test scan runs and signal records.
    """

    def test_creates_and_finishes_scan_run(self) -> None:
        """
        Scan run stores lifecycle counters.
        """

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            journal = ScanJournalRepository(
                path=str(database_path),
            )

            try:
                scan_run = journal.create_scan_run(
                    timeframe="1h",
                    candle_limit=500,
                    symbol_limit=20,
                    min_quote_volume_usdt=10_000_000.0,
                    research_minimum_probability=40,
                    elite_minimum_probability=80,
                )

                journal.finish_scan_run(
                    scan_run_id=scan_run.id,
                    status="completed",
                    symbols_scanned=20,
                    candidate_signals=12,
                    research_trades_created=3,
                    elite_signals_found=1,
                )

                latest = journal.get_latest_scan_run()

                self.assertIsNotNone(latest)
                self.assertEqual(
                    latest.id,
                    scan_run.id,
                )
                self.assertEqual(
                    latest.status,
                    "completed",
                )
                self.assertEqual(
                    latest.symbols_scanned,
                    20,
                )
                self.assertEqual(
                    latest.candidate_signals,
                    12,
                )
                self.assertEqual(
                    latest.research_trades_created,
                    3,
                )
                self.assertEqual(
                    latest.elite_signals_found,
                    1,
                )

            finally:
                journal.close()

    def test_saves_research_signal_from_context(self) -> None:
        """
        SignalContext-like object is converted into research record.
        """

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            journal = ScanJournalRepository(
                path=str(database_path),
            )

            try:
                scan_run = journal.create_scan_run(
                    timeframe="1h",
                    candle_limit=500,
                    symbol_limit=20,
                    min_quote_volume_usdt=10_000_000.0,
                    research_minimum_probability=40,
                    elite_minimum_probability=80,
                )

                signal = Signal(
                    symbol="BTCUSDT",
                    market="futures",
                    timeframe="1h",
                    strategy="FVG",
                    direction="LONG",
                    score=55.0,
                    reasons=[
                        "Bullish FVG detected.",
                    ],
                    metadata={
                        "research_trade_id": "trade-1",
                    },
                )

                context = SimpleNamespace(
                    signal=signal,
                    accepted=False,
                    rejected_reason=(
                        "Probability 55% is below elite threshold 80%."
                    ),
                    metadata={
                        "research_skipped": None,
                    },
                    probability=SimpleNamespace(
                        probability=55,
                        confidence="medium",
                        reasons=[
                            "Trend is bullish.",
                        ],
                    ),
                    risk=SimpleNamespace(
                        entry=100.0,
                        stop_loss=98.0,
                        take_profit=104.0,
                        risk_reward=2.0,
                    ),
                )

                record = journal.save_signal_record_from_context(
                    scan_run_id=scan_run.id,
                    context=context,
                )

                self.assertEqual(
                    record.status,
                    "research",
                )
                self.assertEqual(
                    record.research_trade_id,
                    "trade-1",
                )
                self.assertEqual(
                    record.probability,
                    55,
                )
                self.assertFalse(
                    record.is_elite,
                )

                records = journal.list_signal_records(
                    scan_run_id=scan_run.id,
                )

                self.assertEqual(
                    len(records),
                    1,
                )
                self.assertEqual(
                    records[0].symbol,
                    "BTCUSDT",
                )
                self.assertEqual(
                    records[0].status,
                    "research",
                )

                summary = journal.get_signal_record_summary(
                    scan_run_id=scan_run.id,
                )

                self.assertEqual(
                    summary,
                    {
                        "total": 1,
                        "rejected": 0,
                        "research": 1,
                        "elite": 0,
                    },
                )

            finally:
                journal.close()

    def test_saves_rejected_and_elite_records(self) -> None:
        """
        Journal separates rejected and elite signal records.
        """

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "research.db"

            journal = ScanJournalRepository(
                path=str(database_path),
            )

            try:
                scan_run = journal.create_scan_run(
                    timeframe="1h",
                    candle_limit=500,
                    symbol_limit=20,
                    min_quote_volume_usdt=10_000_000.0,
                    research_minimum_probability=40,
                    elite_minimum_probability=80,
                )

                journal.save_signal_record(
                    scan_run_id=scan_run.id,
                    symbol="ETHUSDT",
                    market="futures",
                    timeframe="1h",
                    strategy="OrderBlock",
                    direction="LONG",
                    score=30.0,
                    probability=20,
                    confidence="low",
                    entry_price=None,
                    stop_loss=None,
                    take_profit=None,
                    risk_reward=None,
                    status="rejected",
                    rejected_reason=(
                        "Probability is below research threshold."
                    ),
                    research_trade_id=None,
                    research_skipped=(
                        "Probability is below research threshold."
                    ),
                    is_elite=False,
                    reasons=[
                        "Weak setup.",
                    ],
                    probability_reasons=[],
                    metadata={},
                )

                journal.save_signal_record(
                    scan_run_id=scan_run.id,
                    symbol="SOLUSDT",
                    market="futures",
                    timeframe="1h",
                    strategy="Breaker",
                    direction="LONG",
                    score=91.0,
                    probability=84,
                    confidence="high",
                    entry_price=100.0,
                    stop_loss=98.0,
                    take_profit=104.0,
                    risk_reward=2.0,
                    status="elite",
                    rejected_reason=None,
                    research_trade_id="trade-2",
                    research_skipped=None,
                    is_elite=True,
                    reasons=[
                        "Strong setup.",
                    ],
                    probability_reasons=[
                        "Trend and momentum aligned.",
                    ],
                    metadata={},
                )

                summary = journal.get_signal_record_summary(
                    scan_run_id=scan_run.id,
                )

                self.assertEqual(
                    summary["total"],
                    2,
                )
                self.assertEqual(
                    summary["rejected"],
                    1,
                )
                self.assertEqual(
                    summary["research"],
                    0,
                )
                self.assertEqual(
                    summary["elite"],
                    1,
                )

                elite_records = journal.list_signal_records(
                    scan_run_id=scan_run.id,
                    status="elite",
                )

                self.assertEqual(
                    len(elite_records),
                    1,
                )
                self.assertEqual(
                    elite_records[0].symbol,
                    "SOLUSDT",
                )

            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()