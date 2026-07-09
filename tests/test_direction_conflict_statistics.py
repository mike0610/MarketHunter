"""
Tests for direction-conflict statistics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.storage.repository import ResearchRepository


class DirectionConflictStatisticsTests(unittest.TestCase):
    def test_groups_direction_conflict_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "research.db"
            repository = ResearchRepository(
                str(db_path),
            )

            with repository.connection:
                repository.connection.execute(
                    """
                    CREATE TABLE signal_records (
                        id TEXT PRIMARY KEY,
                        scan_run_id TEXT,
                        symbol TEXT,
                        strategy TEXT,
                        direction TEXT,
                        status TEXT,
                        rejected_reason TEXT,
                        research_skipped TEXT,
                        metadata TEXT,
                        created_at TEXT
                    )
                    """
                )

                metadata = {
                    "direction_conflict": True,
                    "conflict_symbol": "BTCUSDT",
                    "conflict_long_score": 80.0,
                    "conflict_short_score": 60.0,
                    "conflict_score_delta": 20.0,
                    "conflict_min_score_delta": 15.0,
                    "conflict_long_signal_count": 1,
                    "conflict_short_signal_count": 1,
                    "conflict_long_strategies": ["FVG"],
                    "conflict_short_strategies": ["OrderBlock"],
                    "conflict_winner_direction": "LONG",
                }

                winner_metadata = {
                    **metadata,
                    "conflict_resolution": "winner_selected",
                    "conflict_signal_outcome": "winner",
                }

                loser_metadata = {
                    **metadata,
                    "conflict_resolution": "loser_rejected",
                    "conflict_signal_outcome": "loser_rejected",
                }

                repository.connection.execute(
                    """
                    INSERT INTO signal_records (
                        id,
                        scan_run_id,
                        symbol,
                        strategy,
                        direction,
                        status,
                        rejected_reason,
                        research_skipped,
                        metadata,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "1",
                        "scan-1",
                        "BTCUSDT",
                        "FVG",
                        "LONG",
                        "research",
                        None,
                        None,
                        json.dumps(winner_metadata),
                        "2026-07-09T00:00:00Z",
                    ),
                )

                repository.connection.execute(
                    """
                    INSERT INTO signal_records (
                        id,
                        scan_run_id,
                        symbol,
                        strategy,
                        direction,
                        status,
                        rejected_reason,
                        research_skipped,
                        metadata,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2",
                        "scan-1",
                        "BTCUSDT",
                        "OrderBlock",
                        "SHORT",
                        "rejected",
                        "Direction conflict: weaker direction rejected",
                        None,
                        json.dumps(loser_metadata),
                        "2026-07-09T00:00:01Z",
                    ),
                )

            stats = repository.get_direction_conflict_statistics(
                limit=10,
            )

            self.assertEqual(
                stats["summary"]["records"],
                2,
            )
            self.assertEqual(
                stats["summary"]["events"],
                1,
            )
            self.assertEqual(
                stats["summary"]["resolved"],
                1,
            )
            self.assertEqual(
                stats["summary"]["long_winner"],
                1,
            )

            self.assertEqual(
                stats["by_symbol"][0]["label"],
                "BTCUSDT",
            )

            pair_label = stats["by_strategy_pair"][0]["label"]

            self.assertIn(
                "FVG",
                pair_label,
            )
            self.assertIn(
                "OrderBlock",
                pair_label,
            )

            repository.close()


if __name__ == "__main__":
    unittest.main()
