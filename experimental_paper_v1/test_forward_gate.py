"""Offline tests; synthetic signals never count as real performance."""
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest

from forward_gate import ForwardSignalGate

NOW = datetime(2026,9,24,13,0,tzinfo=timezone.utc)

@contextmanager
def write_source(path):
    con = sqlite3.connect(path)
    try:
        with con:
            yield con
    finally:
        con.close()

def source_db(path):
    with write_source(path) as db:
        db.execute("""CREATE TABLE research_strategy_signals(
           symbol TEXT,strategy TEXT,direction TEXT,observed_at TEXT,
           first_seen_at TEXT,last_seen_at TEXT,observations INTEGER)""")

def put(path,*,symbol="AAPL",strategy="Breakout",direction="LONG",observed=None,seen=None,observations=1):
    observed=observed or NOW-timedelta(hours=2)
    seen=seen or NOW-timedelta(hours=1)
    with write_source(path) as db:
        db.execute("INSERT INTO research_strategy_signals VALUES(?,?,?,?,?,?,?)",
            (symbol,strategy,direction,observed.isoformat(),seen.isoformat(),seen.isoformat(),observations))

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/"research_strategy_signals.db"
        self.sandbox=Path(self.tmp.name)/"experimental_paper.db"
        source_db(self.source)
        self.gate=ForwardSignalGate(self.source,self.sandbox)

    def test_existing_96_stay_historical_after_reobserved(self):
        for i in range(96):
            put(self.source,symbol=f"OLD{i}",observations=13)
        self.gate.arm(now=NOW)
        self.assertEqual(self.gate.collect(now=NOW+timedelta(minutes=1)).new_waiting_evidence,0)
        with write_source(self.source) as db:
            db.execute("UPDATE research_strategy_signals SET observations=observations+1,last_seen_at=?",
                       ((NOW+timedelta(minutes=2)).isoformat(),))
        self.assertEqual(self.gate.collect(now=NOW+timedelta(minutes=3)).new_waiting_evidence,0)
        self.assertFalse(self.gate.snapshot()["by_status"])

    def test_new_forward_signal_only_once(self):
        self.gate.arm(now=NOW)
        put(self.source,seen=NOW+timedelta(minutes=1),observed=NOW+timedelta(seconds=30))
        self.assertEqual(self.gate.collect(now=NOW+timedelta(minutes=2)).new_waiting_evidence,1)
        self.assertEqual(self.gate.collect(now=NOW+timedelta(minutes=3)).previously_seen,1)
        self.assertEqual(self.gate.snapshot()["by_status"],{"WAITING_EVIDENCE":1})

    def test_invalid_stale_future_fail_closed(self):
        self.gate.arm(now=NOW)
        put(self.source,symbol="NO",strategy="Unknown",seen=NOW+timedelta(minutes=1))
        put(self.source,symbol="STALE",observed=NOW-timedelta(days=7),seen=NOW+timedelta(minutes=1))
        put(self.source,symbol="FUTURE",observed=NOW+timedelta(days=1),seen=NOW+timedelta(minutes=1))
        result=self.gate.collect(now=NOW+timedelta(minutes=2))
        self.assertEqual((result.invalid_ignored,result.new_waiting_evidence),(3,0))

    def test_source_bytes_unchanged_and_arm_fixed(self):
        self.gate.arm(now=NOW)
        original=self.source.read_bytes()
        self.assertEqual(self.gate.arm(now=NOW+timedelta(days=2)),NOW.isoformat())
        self.gate.collect(now=NOW+timedelta(minutes=1))
        self.assertEqual(original,self.source.read_bytes())

    def test_no_same_source_and_output(self):
        with self.assertRaises(ValueError):
            ForwardSignalGate(self.source,self.source)

if __name__=="__main__":
    unittest.main()
