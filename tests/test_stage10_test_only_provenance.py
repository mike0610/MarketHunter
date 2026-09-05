from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from reports.stage7_repository import Stage7ClosedTradeReader
from stage10.test_only_provenance import Stage10TestOnlyProvenance


class Stage10TestOnlyProvenanceTests(unittest.TestCase):
    def test_marker_survives_restart_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "x.db"
            Stage10TestOnlyProvenance(db).mark_position("p-test")
            Stage10TestOnlyProvenance(db).mark_position("p-test")
            self.assertTrue(Stage10TestOnlyProvenance(db).is_test_only("p-test"))
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute("select count(*) from stage10_test_only_provenance").fetchone()[0], 1)

    def test_reports_exclude_test_only_closed_trade_but_keep_normal_trade(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "x.db"
            now = datetime(2026, 9, 5, tzinfo=timezone.utc).isoformat()
            with sqlite3.connect(db) as c:
                c.execute("""create table stage6_closed_trades(
closed_trade_id text primary key,position_id text unique,symbol text,direction text,entry_price text,exit_price text,
quantity text,gross_pnl text,entry_fees text,exit_fees text,realized_pnl text,opened_at text,closed_at text,
exit_reason text,strategy_id text,strategy_version text,strategy_decision_id text,candidate_dedupe_key text)""")
                rows = [
                    ("ct-test","p-test","SPY","LONG","100","101","1","1","0","0","1",now,now,"TIME_EXIT","SYSTEM_TEST","1","d-test","c-test"),
                    ("ct-real","p-real","SPY","LONG","100","101","1","1","0","0","1",now,now,"TIME_EXIT","strategy-1","1","d-real","c-real"),
                ]
                c.executemany("insert into stage6_closed_trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            Stage10TestOnlyProvenance(db).mark_position("p-test")
            samples = Stage7ClosedTradeReader(db).read_all()
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0].position_id, "p-real")
            self.assertEqual(samples[0].strategy_id, "strategy-1")


if __name__ == "__main__":
    unittest.main()
