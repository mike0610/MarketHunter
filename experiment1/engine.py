from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from experiment1.models import (
    AccountKind,
    AccountState,
    DecisionAction,
    FillRecord,
    IntentStatus,
    MarketQuote,
    OrderIntent,
    PositionState,
)


STARTING_CASH = {
    AccountKind.INVESTMENTS: Decimal("5000"),
    AccountKind.SPOT: Decimal("2000"),
    AccountKind.FUTURES: Decimal("2000"),
}

MAX_FUTURES_LEVERAGE = Decimal("3")


class Experiment1Error(Exception):
    pass


class Experiment1Engine:
    """Persistent, paper-only Experiment 1 execution core.

    The engine never fetches market data and never sends real orders. A fill can
    only occur from a caller-supplied MarketQuote carrying explicit provenance,
    fee and slippage assumptions.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()
        self._ensure_accounts()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS experiment1_accounts (
                    account TEXT PRIMARY KEY,
                    starting_cash TEXT NOT NULL,
                    cash TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    fees_paid TEXT NOT NULL,
                    peak_equity TEXT NOT NULL,
                    last_equity TEXT NOT NULL,
                    max_drawdown TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment1_intents (
                    intent_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    account TEXT NOT NULL,
                    action TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    stop_loss TEXT,
                    take_profit TEXT,
                    status TEXT NOT NULL,
                    status_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS experiment1_positions (
                    account TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    average_price TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    PRIMARY KEY(account, symbol)
                );
                CREATE TABLE IF NOT EXISTS experiment1_fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id TEXT NOT NULL UNIQUE,
                    account TEXT NOT NULL,
                    action TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    reference_price TEXT NOT NULL,
                    fill_price TEXT NOT NULL,
                    fee TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_reference TEXT NOT NULL
                );
                """
            )

    def _ensure_accounts(self) -> None:
        with self._connect() as conn:
            for account, cash in STARTING_CASH.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO experiment1_accounts
                    (account, starting_cash, cash, realized_pnl, fees_paid,
                     peak_equity, last_equity, max_drawdown)
                    VALUES (?, ?, ?, '0', '0', ?, ?, '0')
                    """,
                    (account.value, str(cash), str(cash), str(cash), str(cash)),
                )

    def submit_intent(self, intent: OrderIntent) -> IntentStatus:
        self._validate_intent_policy(intent)
        status = (
            IntentStatus.NO_ACTION
            if intent.action in (DecisionAction.WAIT, DecisionAction.HOLD)
            else IntentStatus.PENDING
        )
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM experiment1_intents WHERE intent_id = ?",
                (intent.intent_id,),
            ).fetchone()
            if existing is not None:
                if self._row_matches_intent(existing, intent):
                    return IntentStatus(existing["status"])
                raise Experiment1Error("intent_id already exists with different content")
            conn.execute(
                """
                INSERT INTO experiment1_intents
                (intent_id, created_at, account, action, symbol, quantity, reason,
                 leverage, stop_loss, take_profit, status, status_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    intent.intent_id,
                    intent.created_at.isoformat(),
                    intent.account.value,
                    intent.action.value,
                    intent.symbol,
                    str(intent.quantity),
                    intent.reason,
                    str(intent.leverage),
                    None if intent.stop_loss is None else str(intent.stop_loss),
                    None if intent.take_profit is None else str(intent.take_profit),
                    status.value,
                ),
            )
        return status

    def execute_pending(self, intent_id: str, quote: MarketQuote) -> FillRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM experiment1_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is None:
                raise Experiment1Error("unknown intent")
            status = IntentStatus(row["status"])
            if status is IntentStatus.FILLED:
                return self._load_fill(conn, intent_id)
            if status is not IntentStatus.PENDING:
                raise Experiment1Error(f"intent is not executable: {status.value}")

            intent = self._intent_from_row(row)
            if quote.symbol != intent.symbol:
                raise Experiment1Error("quote symbol does not match intent")
            if quote.observed_at <= intent.created_at:
                raise Experiment1Error("quote must be observed after intent creation")

            fill = self._build_fill(intent, quote)
            self._apply_fill(conn, fill)
            conn.execute(
                "UPDATE experiment1_intents SET status = ? WHERE intent_id = ?",
                (IntentStatus.FILLED.value, intent_id),
            )
            self._update_equity_after_fill(conn, fill, quote.price)
            return fill

    def _validate_intent_policy(self, intent: OrderIntent) -> None:
        if intent.account in (AccountKind.INVESTMENTS, AccountKind.SPOT):
            if intent.action not in (
                DecisionAction.BUY,
                DecisionAction.SELL,
                DecisionAction.WAIT,
                DecisionAction.HOLD,
            ):
                raise Experiment1Error("Investments/Spot only allow BUY/SELL/WAIT/HOLD")
            if intent.leverage != Decimal("1"):
                raise Experiment1Error("Investments/Spot leverage must be 1x")
        else:
            if intent.action not in (
                DecisionAction.LONG,
                DecisionAction.SHORT,
                DecisionAction.WAIT,
                DecisionAction.HOLD,
            ):
                raise Experiment1Error("Futures only allow LONG/SHORT/WAIT/HOLD")
            if intent.leverage > MAX_FUTURES_LEVERAGE:
                raise Experiment1Error("Futures leverage exceeds conservative 3x cap")

    def _build_fill(self, intent: OrderIntent, quote: MarketQuote) -> FillRecord:
        buy_like = intent.action in (DecisionAction.BUY, DecisionAction.LONG)
        slip = quote.slippage_bps / Decimal("10000")
        fill_price = quote.price * (Decimal("1") + slip if buy_like else Decimal("1") - slip)
        notional = fill_price * intent.quantity
        fee = notional * quote.fee_bps / Decimal("10000")
        return FillRecord(
            intent_id=intent.intent_id,
            account=intent.account,
            action=intent.action,
            symbol=intent.symbol,
            quantity=intent.quantity,
            reference_price=quote.price,
            fill_price=fill_price,
            fee=fee,
            leverage=intent.leverage,
            observed_at=quote.observed_at,
            source=quote.source,
            source_reference=quote.source_reference,
        )

    def _apply_fill(self, conn: sqlite3.Connection, fill: FillRecord) -> None:
        account = self._account_row(conn, fill.account)
        cash = Decimal(account["cash"])
        realized = Decimal(account["realized_pnl"])
        fees_paid = Decimal(account["fees_paid"])
        position = conn.execute(
            "SELECT * FROM experiment1_positions WHERE account = ? AND symbol = ?",
            (fill.account.value, fill.symbol),
        ).fetchone()
        old_qty = Decimal(position["quantity"]) if position else Decimal("0")
        old_avg = Decimal(position["average_price"]) if position else Decimal("0")

        if fill.account in (AccountKind.INVESTMENTS, AccountKind.SPOT):
            if fill.action is DecisionAction.BUY:
                cost = fill.fill_price * fill.quantity + fill.fee
                if cost > cash:
                    raise Experiment1Error("insufficient paper cash")
                new_qty = old_qty + fill.quantity
                new_avg = (
                    (old_avg * old_qty + fill.fill_price * fill.quantity) / new_qty
                    if new_qty > 0 else Decimal("0")
                )
                cash -= cost
            else:
                if fill.quantity > old_qty:
                    raise Experiment1Error("cannot paper-sell more than held quantity")
                realized += (fill.fill_price - old_avg) * fill.quantity
                cash += fill.fill_price * fill.quantity - fill.fee
                new_qty = old_qty - fill.quantity
                new_avg = old_avg if new_qty > 0 else Decimal("0")
        else:
            signed = fill.quantity if fill.action is DecisionAction.LONG else -fill.quantity
            if old_qty == 0 or (old_qty > 0 and signed > 0) or (old_qty < 0 and signed < 0):
                new_qty = old_qty + signed
                new_avg = (
                    (abs(old_qty) * old_avg + abs(signed) * fill.fill_price) / abs(new_qty)
                )
            else:
                close_qty = min(abs(old_qty), abs(signed))
                direction = Decimal("1") if old_qty > 0 else Decimal("-1")
                pnl = (fill.fill_price - old_avg) * close_qty * direction
                realized += pnl
                cash += pnl
                new_qty = old_qty + signed
                if new_qty == 0:
                    new_avg = Decimal("0")
                elif (old_qty > 0 > new_qty) or (old_qty < 0 < new_qty):
                    new_avg = fill.fill_price
                else:
                    new_avg = old_avg
            cash -= fill.fee

        fees_paid += fill.fee
        conn.execute(
            """
            INSERT INTO experiment1_positions(account, symbol, quantity, average_price, leverage)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account, symbol) DO UPDATE SET
              quantity=excluded.quantity,
              average_price=excluded.average_price,
              leverage=excluded.leverage
            """,
            (fill.account.value, fill.symbol, str(new_qty), str(new_avg), str(fill.leverage)),
        )
        conn.execute(
            "UPDATE experiment1_accounts SET cash=?, realized_pnl=?, fees_paid=? WHERE account=?",
            (str(cash), str(realized), str(fees_paid), fill.account.value),
        )
        conn.execute(
            """
            INSERT INTO experiment1_fills
            (intent_id, account, action, symbol, quantity, reference_price,
             fill_price, fee, leverage, observed_at, source, source_reference)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill.intent_id, fill.account.value, fill.action.value, fill.symbol,
                str(fill.quantity), str(fill.reference_price), str(fill.fill_price),
                str(fill.fee), str(fill.leverage), fill.observed_at.isoformat(),
                fill.source, fill.source_reference,
            ),
        )

    def _update_equity_after_fill(self, conn: sqlite3.Connection, fill: FillRecord, mark_price: Decimal) -> None:
        row = self._account_row(conn, fill.account)
        cash = Decimal(row["cash"])
        equity = cash
        positions = conn.execute(
            "SELECT * FROM experiment1_positions WHERE account = ?",
            (fill.account.value,),
        ).fetchall()
        for position in positions:
            qty = Decimal(position["quantity"])
            avg = Decimal(position["average_price"])
            if position["symbol"] != fill.symbol:
                continue
            if fill.account in (AccountKind.INVESTMENTS, AccountKind.SPOT):
                equity += qty * mark_price
            else:
                equity += (mark_price - avg) * qty
        peak = max(Decimal(row["peak_equity"]), equity)
        drawdown = Decimal("0") if peak == 0 else (peak - equity) / peak
        max_drawdown = max(Decimal(row["max_drawdown"]), drawdown)
        conn.execute(
            "UPDATE experiment1_accounts SET peak_equity=?, last_equity=?, max_drawdown=? WHERE account=?",
            (str(peak), str(equity), str(max_drawdown), fill.account.value),
        )

    def account_state(self, account: AccountKind) -> AccountState:
        with self._connect() as conn:
            row = self._account_row(conn, account)
            return AccountState(
                account=account,
                starting_cash=Decimal(row["starting_cash"]),
                cash=Decimal(row["cash"]),
                realized_pnl=Decimal(row["realized_pnl"]),
                fees_paid=Decimal(row["fees_paid"]),
                peak_equity=Decimal(row["peak_equity"]),
                last_equity=Decimal(row["last_equity"]),
                max_drawdown=Decimal(row["max_drawdown"]),
            )

    def positions(self, account: AccountKind) -> tuple[PositionState, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment1_positions WHERE account = ? AND quantity != '0' ORDER BY symbol",
                (account.value,),
            ).fetchall()
            return tuple(
                PositionState(
                    account=account,
                    symbol=row["symbol"],
                    quantity=Decimal(row["quantity"]),
                    average_price=Decimal(row["average_price"]),
                    leverage=Decimal(row["leverage"]),
                )
                for row in rows
                if Decimal(row["quantity"]) != 0
            )

    def _account_row(self, conn: sqlite3.Connection, account: AccountKind) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM experiment1_accounts WHERE account = ?", (account.value,)
        ).fetchone()
        if row is None:
            raise Experiment1Error("account not initialized")
        return row

    def _load_fill(self, conn: sqlite3.Connection, intent_id: str) -> FillRecord:
        row = conn.execute(
            "SELECT * FROM experiment1_fills WHERE intent_id = ?", (intent_id,)
        ).fetchone()
        if row is None:
            raise Experiment1Error("filled intent has no fill record")
        return FillRecord(
            intent_id=row["intent_id"], account=AccountKind(row["account"]),
            action=DecisionAction(row["action"]), symbol=row["symbol"],
            quantity=Decimal(row["quantity"]), reference_price=Decimal(row["reference_price"]),
            fill_price=Decimal(row["fill_price"]), fee=Decimal(row["fee"]),
            leverage=Decimal(row["leverage"]), observed_at=datetime.fromisoformat(row["observed_at"]),
            source=row["source"], source_reference=row["source_reference"],
        )

    def _intent_from_row(self, row: sqlite3.Row) -> OrderIntent:
        return OrderIntent(
            intent_id=row["intent_id"], created_at=datetime.fromisoformat(row["created_at"]),
            account=AccountKind(row["account"]), action=DecisionAction(row["action"]),
            symbol=row["symbol"], quantity=Decimal(row["quantity"]), reason=row["reason"],
            leverage=Decimal(row["leverage"]),
            stop_loss=None if row["stop_loss"] is None else Decimal(row["stop_loss"]),
            take_profit=None if row["take_profit"] is None else Decimal(row["take_profit"]),
        )

    def _row_matches_intent(self, row: sqlite3.Row, intent: OrderIntent) -> bool:
        return self._intent_from_row(row) == intent
