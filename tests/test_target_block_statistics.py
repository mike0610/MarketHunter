"""
Tests for target-block statistics.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.storage.repository import ResearchRepository


class TargetBlockStatisticsTests(unittest.TestCase):
    def test_groups_target_block_records(self) -> None:
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
                        symbol TEXT,
                        strategy TEXT,
                        direction TEXT,
                        rejected_reason TEXT,
                        research_skipped TEXT,
                        metadata TEXT,
                        created_at TEXT
                    )
                    """
                )

                metadata = {
                    "target_rr": 3.0,
                    "target_price": 110.0,
                    "target_clear": False,
                    "target_summary": (
                        "TP 1:3 is blocked by resistance zone around 108.00000000."
                    ),
                    "target_blocking_zone_type": "resistance",
                    "target_blocking_zone_center": 108.0,
                    "target_blocking_zone_distance_to_entry_percent": 8.0,
                    "target_blocking_zone_distance_to_target_percent": 1.8,
                }

                repository.connection.execute(
                    """
                    INSERT INTO signal_records (
                        id,
                        symbol,
                        strategy,
                        direction,
                        rejected_reason,
                        research_skipped,
                        metadata,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "1",
                        "BTCUSDT",
                        "FVG",
                        "LONG",
                        None,
                        "Research trade blocked by target quality: TP 1:3 is blocked by resistance zone around 108.00000000.",
                        json.dumps(metadata),
                        "2026-07-09T00:00:00Z",
                    ),
                )

            stats = repository.get_target_block_statistics(
                limit=10,
            )

            self.assertEqual(
                stats["summary"]["records"],
                1,
            )
            self.assertEqual(
                stats["summary"]["resistance_blocks"],
                1,
            )
            self.assertEqual(
                stats["summary"]["long_blocks"],
                1,
            )
            self.assertEqual(
                stats["by_strategy"][0]["label"],
                "FVG",
            )
            self.assertEqual(
                stats["by_symbol"][0]["label"],
                "BTCUSDT",
            )

            repository.close()


if __name__ == "__main__":
    unittest.main()
