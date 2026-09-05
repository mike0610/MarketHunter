from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from strategy_engine.models import StrategyDecisionOutcome, StrategyDecisionRecord
from trading_scanner.models import SetupFamily


class StrategyDecisionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS strategy_decisions (
                    decision_id TEXT PRIMARY KEY,
                    candidate_dedupe_key TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    setup_family TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    reason_stack TEXT NOT NULL,
                    candidate_scan_cycle_id TEXT NOT NULL,
                    candidate_discovered_at TEXT NOT NULL,
                    candidate_evidence_status TEXT NOT NULL,
                    candidate_freshness_note TEXT
                )"""
            )
            columns={row[1] for row in conn.execute("PRAGMA table_info(strategy_decisions)").fetchall()}
            for name,ddl in (
                ("reference_price","TEXT"),
                ("structural_stop_price","TEXT"),
                ("structural_stop_source","TEXT"),
            ):
                if name not in columns:
                    conn.execute(f"ALTER TABLE strategy_decisions ADD COLUMN {name} {ddl}")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_strategy_decision_candidate_version "
                "ON strategy_decisions(candidate_dedupe_key, strategy_id, strategy_version)"
            )

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record(self, item: StrategyDecisionRecord) -> StrategyDecisionRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM strategy_decisions WHERE decision_id=?", (item.decision_id,)).fetchone()
            if row:
                existing = self._from_row(row)
                if existing == item:
                    return existing
                raise ValueError("decision_id collision")
            conn.execute(
                """INSERT INTO strategy_decisions (
                    decision_id,candidate_dedupe_key,symbol,setup_family,strategy_id,strategy_version,outcome,
                    decided_at,reason_stack,candidate_scan_cycle_id,candidate_discovered_at,candidate_evidence_status,
                    candidate_freshness_note,reference_price,structural_stop_price,structural_stop_source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item.decision_id,item.candidate_dedupe_key,item.symbol,item.setup_family.value,
                    item.strategy_id,item.strategy_version,item.outcome.value,item.decided_at.isoformat(),
                    "\x1f".join(item.reason_stack),item.candidate_scan_cycle_id,
                    item.candidate_discovered_at.isoformat(),item.candidate_evidence_status,
                    item.candidate_freshness_note,
                    None if item.reference_price is None else str(item.reference_price),
                    None if item.structural_stop_price is None else str(item.structural_stop_price),
                    item.structural_stop_source,
                ),
            )
        return item

    def list_all(self) -> tuple[StrategyDecisionRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM strategy_decisions ORDER BY decided_at, decision_id").fetchall()
        return tuple(self._from_row(r) for r in rows)

    @staticmethod
    def _from_row(row) -> StrategyDecisionRecord:
        return StrategyDecisionRecord(
            decision_id=row["decision_id"],
            candidate_dedupe_key=row["candidate_dedupe_key"],
            symbol=row["symbol"],
            setup_family=SetupFamily(row["setup_family"]),
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            outcome=StrategyDecisionOutcome(row["outcome"]),
            decided_at=datetime.fromisoformat(row["decided_at"]),
            reason_stack=tuple(row["reason_stack"].split("\x1f")),
            candidate_scan_cycle_id=row["candidate_scan_cycle_id"],
            candidate_discovered_at=datetime.fromisoformat(row["candidate_discovered_at"]),
            candidate_evidence_status=row["candidate_evidence_status"],
            candidate_freshness_note=row["candidate_freshness_note"],
            reference_price=None if "reference_price" not in row.keys() or row["reference_price"] is None else Decimal(row["reference_price"]),
            structural_stop_price=None if "structural_stop_price" not in row.keys() or row["structural_stop_price"] is None else Decimal(row["structural_stop_price"]),
            structural_stop_source=None if "structural_stop_source" not in row.keys() else row["structural_stop_source"],
        )
