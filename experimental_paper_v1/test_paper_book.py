"""Virtual trades in these tests use fabricated fixtures; never real market P&L."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from forward_gate import ForwardSignalGate
from paper_book import ExperimentalPaperBook,QuoteEvidence
from test_forward_gate import NOW,source_db,put

def q(when,price="100",symbol="AAPL",source="SYNTHETIC_TEST_FIXTURE"):
    return QuoteEvidence(symbol,D(price),when,source,"fixture-"+when.isoformat(),"USD",D("5"),D("5"))

class BookTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        src=root/"source.db"
        source_db(src)
        self.gate=ForwardSignalGate(src,root/"separate_paper.db")
        self.gate.arm(now=NOW)
        put(src,seen=NOW+timedelta(minutes=1),observed=NOW+timedelta(seconds=30))
        self.gate.collect(now=NOW+timedelta(minutes=2))
        self.book=ExperimentalPaperBook(self.gate)
        with self.gate._write_db() as db:
            self.signal=db.execute("SELECT signal_id FROM paper_signal_intake").fetchone()[0]

    def test_post_signal_quote_and_no_duplicate_fill(self):
        self.assertEqual(self.book.open_forward(self.signal,q(NOW),now=NOW+timedelta(minutes=2)),
                         "WAITING_FRESH_POST_SIGNAL_QUOTE")
        self.assertEqual(self.book.snapshot()["open_positions"],0)
        quote=q(NOW+timedelta(minutes=3))
        self.assertEqual(self.book.open_forward(self.signal,quote,now=NOW+timedelta(minutes=4)),"PAPER_OPENED")
        self.assertEqual(self.book.open_forward(self.signal,quote,now=NOW+timedelta(minutes=4)),"NO_ELIGIBLE_SIGNAL")
        self.assertEqual(self.book.snapshot()["open_positions"],1)

    def test_stop_gap_uses_observed_price_not_theoretical_stop(self):
        self.book.open_forward(self.signal,q(NOW+timedelta(minutes=3)),now=NOW+timedelta(minutes=4))
        self.assertEqual(self.book.tick(q(NOW+timedelta(minutes=5),"98.5"),now=NOW+timedelta(minutes=6)),"MARKED")
        self.assertEqual(self.book.tick(q(NOW+timedelta(minutes=7),"95"),now=NOW+timedelta(minutes=8)),"PAPER_CLOSED")
        snapshot=self.book.snapshot()
        self.assertEqual((snapshot["open_positions"],snapshot["closed_trades"]),(0,1))
        self.assertLess(D(snapshot["realized_pnl"]),0)

    def test_short_unsupported_and_no_borrow_fabrication(self):
        with self.gate._write_db() as db:
            db.execute("UPDATE paper_signal_intake SET direction='SHORT' WHERE signal_id=?",(self.signal,))
        self.assertEqual(self.book.open_forward(self.signal,q(NOW+timedelta(minutes=3)),now=NOW+timedelta(minutes=4)),
                         "BLOCKED_UNSUPPORTED_SHORT")
        self.assertEqual(self.book.snapshot()["open_positions"],0)

    def test_stale_quote_and_symbol_mismatch(self):
        self.assertEqual(self.book.open_forward(self.signal,q(NOW+timedelta(minutes=3),symbol="MSFT"),now=NOW+timedelta(minutes=4)),
                         "BLOCKED_SYMBOL_MISMATCH")
        self.assertEqual(self.book.open_forward(self.signal,q(NOW+timedelta(minutes=3)),now=NOW+timedelta(hours=1)),
                         "WAITING_FRESH_POST_SIGNAL_QUOTE")
        self.assertEqual(self.book.snapshot()["open_positions"],0)

if __name__=="__main__":
    unittest.main()
