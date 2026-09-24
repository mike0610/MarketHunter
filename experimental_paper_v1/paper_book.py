"""Isolated research-only paper ledger with externally supplied post-signal quotes.

No network, exchange/broker client, canonical Experiment1 import or live trading.
An explicit audited adapter must produce genuinely fresh USD QuoteEvidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN

from forward_gate import ForwardSignalGate, _parse_utc

D = Decimal
UTC = timezone.utc
MAX_QUOTE_AGE = timedelta(minutes=5)
START_CASH = D("2000")
STOP_PCT = D("0.02")
TAKE_PCT = D("0.04")
RISK_FRACTION = D("0.005")
MAX_EXPOSURE = D("0.20")
MAX_OPEN = 3
FEE_BPS_FLOOR = D("5")
SLIPPAGE_BPS_FLOOR = D("5")


@dataclass(frozen=True)
class QuoteEvidence:
    symbol: str
    price: Decimal
    observed_at: datetime
    source: str
    source_reference: str
    currency: str
    fee_bps: Decimal
    slippage_bps: Decimal

    def __post_init__(self):
        if (not self.symbol or not self.source or not self.source_reference
            or self.currency != "USD" or self.price <= 0
            or self.fee_bps < 0 or self.slippage_bps < 0
            or self.observed_at.tzinfo is None):
            raise ValueError("Missing/invalid USD quote evidence")


def _quote_fresh(quote: QuoteEvidence, now: datetime, after: datetime) -> bool:
    ts = quote.observed_at.astimezone(UTC)
    return (bool(quote.source_reference.strip()) and after < ts <= now
            and now - ts <= MAX_QUOTE_AGE)


def _price_after_cost(price: Decimal, quote: QuoteEvidence, side: str) -> Decimal:
    bps = max(quote.slippage_bps, SLIPPAGE_BPS_FLOOR)
    return price * (D("1") + bps/D("10000")*(D("1") if side=="BUY" else D("-1")))


def _fee(notional: Decimal, quote: QuoteEvidence) -> Decimal:
    return notional * max(quote.fee_bps, FEE_BPS_FLOOR) / D("10000")


class ExperimentalPaperBook:
    """Virtual 2000 USD LONG-only book, independent from SPOT/FUTURES runtime."""

    def __init__(self, gate: ForwardSignalGate):
        self.gate = gate
        self._init()

    def _init(self):
        with self.gate._write_db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS paper_book_account (
               account TEXT PRIMARY KEY, starting_cash TEXT NOT NULL, cash TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS paper_book_trades (
                trade_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, strategy TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED')),
                entry_at TEXT NOT NULL, entry_reference TEXT NOT NULL,
                entry_price TEXT NOT NULL, quantity TEXT NOT NULL, entry_fee TEXT NOT NULL,
                stop_price TEXT NOT NULL, target_price TEXT NOT NULL,
                latest_mark TEXT NOT NULL, latest_mark_at TEXT NOT NULL,
                exit_at TEXT, exit_reference TEXT, exit_price TEXT, exit_fee TEXT,
                exit_reason TEXT, net_pnl TEXT)""")
            db.execute("""INSERT OR IGNORE INTO paper_book_account(account,starting_cash,cash)
                VALUES('EXPERIMENTAL_RESEARCH_LONG_ONLY','2000','2000')""")

    def open_forward(self, signal_id: str, quote: QuoteEvidence, *, now: datetime | None = None) -> str:
        """Open once, only with a fresh price observed AFTER the signal was first seen."""
        clock = (now or datetime.now(UTC)).astimezone(UTC)
        with self.gate._write_db() as db:
            signal = db.execute("SELECT * FROM paper_signal_intake WHERE signal_id=?", (signal_id,)).fetchone()
            if signal is None or signal["status"] != "WAITING_EVIDENCE":
                return "NO_ELIGIBLE_SIGNAL"
            if quote.symbol != signal["symbol"]:
                return "BLOCKED_SYMBOL_MISMATCH"
            if signal["direction"] != "LONG":
                db.execute("UPDATE paper_signal_intake SET status='BLOCKED',reason=? WHERE signal_id=?",
                    ("SHORT requires separate executable instrument/borrow evidence", signal_id))
                return "BLOCKED_UNSUPPORTED_SHORT"
            first_seen = _parse_utc(signal["first_seen_at"])
            if not _quote_fresh(quote, clock, first_seen):
                return "WAITING_FRESH_POST_SIGNAL_QUOTE"
            if clock - first_seen > timedelta(days=1):
                db.execute("UPDATE paper_signal_intake SET status='EXPIRED',reason=? WHERE signal_id=?",
                    ("no valid quote within one day", signal_id))
                return "EXPIRED"
            open_rows = db.execute("SELECT * FROM paper_book_trades WHERE status='OPEN'").fetchall()
            if len(open_rows) >= MAX_OPEN or any(x["symbol"] == quote.symbol for x in open_rows):
                return "WAITING_CAPACITY"
            cash = D(db.execute(
                "SELECT cash FROM paper_book_account WHERE account='EXPERIMENTAL_RESEARCH_LONG_ONLY'"
            ).fetchone()[0])
            equity = cash + sum((D(r["quantity"])*D(r["latest_mark"]) for r in open_rows), D("0"))
            entry = _price_after_cost(quote.price, quote, "BUY")
            qty = min(cash*MAX_EXPOSURE/entry, equity*RISK_FRACTION/(entry*STOP_PCT))
            qty = qty.quantize(D("0.00000001"), rounding=ROUND_DOWN)
            fee = _fee(qty*entry, quote)
            if qty <= 0 or qty*entry+fee > cash:
                return "WAITING_CAPACITY"
            stop, target = entry*(D("1")-STOP_PCT), entry*(D("1")+TAKE_PCT)
            db.execute("""INSERT INTO paper_book_trades
               (trade_id,symbol,strategy,status,entry_at,entry_reference,entry_price,
                quantity,entry_fee,stop_price,target_price,latest_mark,latest_mark_at)
               VALUES(?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)""",
               (signal_id, quote.symbol, signal["strategy"], quote.observed_at.isoformat(),
                quote.source+"|"+quote.source_reference, str(entry), str(qty), str(fee),
                str(stop), str(target), str(quote.price), quote.observed_at.isoformat()))
            db.execute("UPDATE paper_book_account SET cash=? WHERE account='EXPERIMENTAL_RESEARCH_LONG_ONLY'",
                       (str(cash-qty*entry-fee),))
            db.execute("UPDATE paper_signal_intake SET status='OPENED',reason=? WHERE signal_id=?",
                       ("paper entry recorded in separate virtual book", signal_id))
            return "PAPER_OPENED"

    def tick(self, quote: QuoteEvidence, *, now: datetime | None = None) -> str:
        """Reprice or stop/target-close from a NEW observed quote, never fabricate stop fill."""
        clock = (now or datetime.now(UTC)).astimezone(UTC)
        with self.gate._write_db() as db:
            row = db.execute(
                "SELECT * FROM paper_book_trades WHERE status='OPEN' AND symbol=?",
                (quote.symbol,)
            ).fetchone()
            if row is None:
                return "NO_OPEN_POSITION"
            if not _quote_fresh(quote, clock, _parse_utc(row["latest_mark_at"])):
                return "WAITING_FRESH_MARK"
            raw = quote.price
            stop_hit = raw <= D(row["stop_price"])
            target_hit = raw >= D(row["target_price"])
            if not stop_hit and not target_hit:
                db.execute("UPDATE paper_book_trades SET latest_mark=?,latest_mark_at=? WHERE trade_id=?",
                           (str(raw), quote.observed_at.isoformat(), row["trade_id"]))
                return "MARKED"
            exit_price = _price_after_cost(raw, quote, "SELL")
            qty = D(row["quantity"])
            exit_fee = _fee(qty*exit_price, quote)
            proceeds = qty*exit_price-exit_fee
            net = proceeds - qty*D(row["entry_price"]) - D(row["entry_fee"])
            cash = D(db.execute(
                "SELECT cash FROM paper_book_account WHERE account='EXPERIMENTAL_RESEARCH_LONG_ONLY'"
            ).fetchone()[0])
            db.execute("UPDATE paper_book_account SET cash=? WHERE account='EXPERIMENTAL_RESEARCH_LONG_ONLY'",
                       (str(cash+proceeds),))
            db.execute("""UPDATE paper_book_trades SET status='CLOSED',
                latest_mark=?,latest_mark_at=?,exit_at=?,exit_reference=?,
                exit_price=?,exit_fee=?,exit_reason=?,net_pnl=? WHERE trade_id=?""",
                (str(raw), quote.observed_at.isoformat(), quote.observed_at.isoformat(),
                 quote.source+"|"+quote.source_reference, str(exit_price), str(exit_fee),
                 "STOP_LOSS" if stop_hit else "TAKE_PROFIT", str(net), row["trade_id"]))
            return "PAPER_CLOSED"

    def snapshot(self) -> dict:
        with self.gate._write_db() as db:
            cash = D(db.execute("SELECT cash FROM paper_book_account WHERE account='EXPERIMENTAL_RESEARCH_LONG_ONLY'").fetchone()[0])
            rows = db.execute("SELECT * FROM paper_book_trades ORDER BY entry_at,trade_id").fetchall()
            opened = [x for x in rows if x["status"] == "OPEN"]
            realized = sum((D(x["net_pnl"]) for x in rows if x["status"] == "CLOSED"), D("0"))
            equity = cash + sum((D(x["quantity"])*D(x["latest_mark"]) for x in opened), D("0"))
            return {
                "simulation_only": True,
                "account": "EXPERIMENTAL_RESEARCH_LONG_ONLY",
                "cash": str(cash), "last_mark_equity": str(equity),
                "realized_pnl": str(realized), "open_positions": len(opened),
                "closed_trades": len(rows)-len(opened),
                "mark_is_stale_until_new_quote": True
            }
