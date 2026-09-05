from __future__ import annotations

import sqlite3
from pathlib import Path


class Stage10TestOnlyProvenance:
    """Minimal durable marker for system-test artifacts.

    This is not strategy evidence. It exists only so Stage 10 E2E proof
    records can traverse the real durable pipeline without contaminating
    normal strategy analytics.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                """create table if not exists stage10_test_only_provenance(
                   position_id text primary key,
                   marker text not null check(marker='TEST_ONLY')
                )"""
            )

    def mark_position(self, position_id: str) -> None:
        if not position_id:
            raise ValueError("position_id is required")
        with sqlite3.connect(self.db_path) as c:
            c.execute(
                "insert or ignore into stage10_test_only_provenance(position_id,marker) values (?,'TEST_ONLY')",
                (position_id,),
            )

    def is_test_only(self, position_id: str) -> bool:
        with sqlite3.connect(self.db_path) as c:
            row = c.execute(
                "select marker from stage10_test_only_provenance where position_id=?",
                (position_id,),
            ).fetchone()
        return row is not None and row[0] == "TEST_ONLY"
