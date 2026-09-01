from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.models import (
    AccountKind,
    AccountState,
    ClosedTrade,
    ContributionRecord,
    DecisionAction,
    FillRecord,
    IntentStatus,
    MarketQuote,
    OrderIntent,
    PositionState,
)

# The legacy single AccountKind.INVESTMENTS is intentionally absent here -
# it is never (re)created for a fresh deployment. Any pre-existing row
# under that key is left untouched (see AccountKind's own docstring);
# going forward the canonical Investments model is these three
# independent ledgers.
STARTING_CASH = {
    AccountKind.INVESTMENTS_DEFENSIVE: Decimal("5000"),
    AccountKind.INVESTMENTS_BALANCED: Decimal("5000"),
    AccountKind.INVESTMENTS_GROWTH: Decimal("5000"),
    AccountKind.SPOT: Decimal("2000"),
    AccountKind.FUTURES: Decimal("2000"),
}

# Canonical monthly contribution per ledger. Applied only via the
# on-demand contribute() method below - this engine schedules nothing
# itself; an external caller (operator or a future scheduled job,
# analogous to the Outcome Intelligence systemd timers) decides when to
# call it for a given period.
MONTHLY_CONTRIBUTION = {
    AccountKind.INVESTMENTS_DEFENSIVE: Decimal("2000"),
    AccountKind.INVESTMENTS_BALANCED: Decimal("2000"),
    AccountKind.INVESTMENTS_GROWTH: Decimal("2000"),
}

# Accounts that trade with BUY/SELL semantics, no leverage, and are
# valued as qty * mark (as opposed to FUTURES' LONG/SHORT, leveraged,
# (mark - avg) * qty valuation). AccountKind.INVESTMENTS (legacy) is
# included only so any pre-existing row keeps its original behavior.
NO_LEVERAGE_ACCOUNTS = (
    AccountKind.INVESTMENTS,
    AccountKind.INVESTMENTS_DEFENSIVE,
    AccountKind.INVESTMENTS_BALANCED,
    AccountKind.INVESTMENTS_GROWTH,
    AccountKind.SPOT,
)

MAX_FUTURES_LEVERAGE = Decimal("3")


class Experiment1Error(Exception):
    pass


class Experiment1Engine:
    """Persistent paper-only engine for GIL Experiment 1."""

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
                    margin TEXT NOT NULL DEFAULT '0',
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
                    source_reference TEXT NOT NULL,
                    realized_pnl_delta TEXT NOT NULL DEFAULT '0'
                );
                CREATE TABLE IF NOT EXISTS experiment1_contributions (
                    account TEXT NOT NULL,
                    period TEXT NOT NULL,
                    amount TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    PRIMARY KEY(account, period)
                );
                """
            )
            # Migration guards for a database created before these columns
            # existed - CREATE TABLE IF NOT EXISTS above is a no-op against
            # an already-existing table, so an old file needs each column
            # added explicitly. Never touches any existing row's other
            # columns. A pre-migration position's margin defaults to '0'
            # (not fabricated - see _used_margin()'s note on this).
            fills_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(experiment1_fills)").fetchall()
            }
            if "realized_pnl_delta" not in fills_columns:
                conn.execute(
                    "ALTER TABLE experiment1_fills ADD COLUMN realized_pnl_delta TEXT NOT NULL DEFAULT '0'"
                )
            positions_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(experiment1_positions)").fetchall()
            }
            if "margin" not in positions_columns:
                conn.execute(
                    "ALTER TABLE experiment1_positions ADD COLUMN margin TEXT NOT NULL DEFAULT '0'"
                )

    def _ensure_accounts(self) -> None:
        with self._connect() as conn:
            for account, cash in STARTING_CASH.items():
                row = conn.execute(
                    "SELECT starting_cash, cash, realized_pnl, fees_paid FROM experiment1_accounts WHERE account=?",
                    (account.value,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO experiment1_accounts
                        (account, starting_cash, cash, realized_pnl, fees_paid,
                         peak_equity, last_equity, max_drawdown)
                        VALUES (?, ?, ?, '0', '0', ?, ?, '0')
                        """,
                        (account.value, str(cash), str(cash), str(cash), str(cash)),
                    )
                    continue
                untouched = (
                    Decimal(row["realized_pnl"]) == 0
                    and Decimal(row["fees_paid"]) == 0
                    and not conn.execute(
                        "SELECT 1 FROM experiment1_positions WHERE account=? LIMIT 1",
                        (account.value,),
                    ).fetchone()
                )
                if untouched and Decimal(row["starting_cash"]) != cash:
                    conn.execute(
                        """
                        UPDATE experiment1_accounts
                        SET starting_cash=?, cash=?, peak_equity=?, last_equity=?, max_drawdown='0'
                        WHERE account=?
                        """,
                        (str(cash), str(cash), str(cash), str(cash), account.value),
                    )

    def submit_intent(self, intent: OrderIntent) -> IntentStatus:
        """
        Submit one intent for MarketHunter validation. A policy rejection
        is persisted as an auditable IntentStatus.BLOCKED row with its
        exact status_reason (never silently dropped) before the
        Experiment1Error is (still) raised, preserving the existing
        caller contract (e.g. the API's HTTP 400 mapping). Resubmitting
        the exact same intent_id + content afterwards - blocked or not -
        is idempotent: it returns the already-recorded status without
        re-raising or re-validating.
        """
        # The BLOCKED-row insert below must be committed even though the
        # caller still sees an exception - so the exception is raised
        # AFTER the `with` block exits (and commits), never from inside
        # it, since exiting a sqlite3 connection context manager via an
        # exception rolls back everything written in that transaction.
        validation_error: Experiment1Error | None = None

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM experiment1_intents WHERE intent_id=?", (intent.intent_id,)).fetchone()
            if row is not None:
                if self._intent_from_row(row) == intent:
                    return IntentStatus(row["status"])
                raise Experiment1Error("intent_id already exists with different content")

            try:
                self._validate_intent_policy(intent)
            except Experiment1Error as exc:
                validation_error = exc
                status = IntentStatus.BLOCKED
                status_reason = str(exc)
            else:
                status = IntentStatus.NO_ACTION if intent.action in (DecisionAction.WAIT, DecisionAction.HOLD) else IntentStatus.PENDING
                status_reason = None

            self._insert_intent_row(conn, intent, status, status_reason)

        if validation_error is not None:
            raise validation_error
        return status

    def _insert_intent_row(
        self, conn: sqlite3.Connection, intent: OrderIntent, status: IntentStatus, status_reason: str | None
    ) -> None:
        conn.execute(
            """INSERT INTO experiment1_intents
            (intent_id, created_at, account, action, symbol, quantity, reason,
             leverage, stop_loss, take_profit, status, status_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (intent.intent_id, intent.created_at.isoformat(), intent.account.value, intent.action.value,
             intent.symbol, str(intent.quantity), intent.reason, str(intent.leverage),
             None if intent.stop_loss is None else str(intent.stop_loss),
             None if intent.take_profit is None else str(intent.take_profit), status.value, status_reason),
        )

    def blocked_intent_ids(self) -> tuple[str, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT intent_id FROM experiment1_intents WHERE status=? ORDER BY created_at, intent_id",
                (IntentStatus.BLOCKED.value,),
            ).fetchall()
            return tuple(row["intent_id"] for row in rows)

    def intent_status_reason(self, intent_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status_reason FROM experiment1_intents WHERE intent_id=?", (intent_id,)
            ).fetchone()
            if row is None:
                raise Experiment1Error("unknown intent")
            return row["status_reason"]

    def pending_intent_ids(self) -> tuple[str, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT intent_id FROM experiment1_intents WHERE status=? ORDER BY created_at, intent_id",
                (IntentStatus.PENDING.value,),
            ).fetchall()
            return tuple(row["intent_id"] for row in rows)

    def get_intent(self, intent_id: str) -> OrderIntent:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM experiment1_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if row is None:
                raise Experiment1Error("unknown intent")
            return self._intent_from_row(row)

    def execute_pending(self, intent_id: str, quote: MarketQuote) -> FillRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM experiment1_intents WHERE intent_id=?", (intent_id,)).fetchone()
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
            conn.execute("UPDATE experiment1_intents SET status=? WHERE intent_id=?", (IntentStatus.FILLED.value, intent_id))
            self._update_equity(conn, fill, quote.price)
            return fill

    def _validate_intent_policy(self, intent: OrderIntent) -> None:
        if intent.account in NO_LEVERAGE_ACCOUNTS:
            if intent.action not in (DecisionAction.BUY, DecisionAction.SELL, DecisionAction.WAIT, DecisionAction.HOLD):
                raise Experiment1Error("Investments/Spot only allow BUY/SELL/WAIT/HOLD")
            if intent.leverage != Decimal("1"):
                raise Experiment1Error("Investments/Spot leverage must be 1x")
            return
        if intent.action not in (DecisionAction.LONG, DecisionAction.SHORT, DecisionAction.WAIT, DecisionAction.HOLD):
            raise Experiment1Error("Futures only allow LONG/SHORT/WAIT/HOLD")
        if intent.leverage > MAX_FUTURES_LEVERAGE:
            raise Experiment1Error("Futures leverage exceeds conservative 3x cap")

    def _build_fill(self, intent: OrderIntent, quote: MarketQuote) -> FillRecord:
        buy_like = intent.action in (DecisionAction.BUY, DecisionAction.LONG)
        slip = quote.slippage_bps / Decimal("10000")
        fill_price = quote.price * (Decimal("1") + slip if buy_like else Decimal("1") - slip)
        fee = fill_price * intent.quantity * quote.fee_bps / Decimal("10000")
        return FillRecord(intent.intent_id, intent.account, intent.action, intent.symbol, intent.quantity,
                          quote.price, fill_price, fee, intent.leverage, quote.observed_at,
                          quote.source, quote.source_reference)

    def _apply_fill(self, conn: sqlite3.Connection, fill: FillRecord) -> None:
        account = self._account_row(conn, fill.account)
        cash = Decimal(account["cash"]); realized = Decimal(account["realized_pnl"]); fees_paid = Decimal(account["fees_paid"])
        row = conn.execute("SELECT * FROM experiment1_positions WHERE account=? AND symbol=?", (fill.account.value, fill.symbol)).fetchone()
        old_qty = Decimal(row["quantity"]) if row else Decimal("0"); old_avg = Decimal(row["average_price"]) if row else Decimal("0")
        old_margin = Decimal(row["margin"]) if row else Decimal("0")
        realized_delta = Decimal("0")
        if fill.account in NO_LEVERAGE_ACCOUNTS:
            if fill.action is DecisionAction.BUY:
                cost = fill.fill_price * fill.quantity + fill.fee
                if cost > cash: raise Experiment1Error("insufficient paper cash")
                new_qty = old_qty + fill.quantity
                new_avg = (old_avg * old_qty + fill.fill_price * fill.quantity) / new_qty if new_qty else Decimal("0")
                cash -= cost
            else:
                if fill.quantity > old_qty: raise Experiment1Error("cannot paper-sell more than held quantity")
                realized_delta = (fill.fill_price - old_avg) * fill.quantity
                realized += realized_delta
                cash += fill.fill_price * fill.quantity - fill.fee
                new_qty = old_qty - fill.quantity; new_avg = old_avg if new_qty else Decimal("0")
            # leverage is always 1x here (enforced by _validate_intent_policy) -
            # margin equals full notional, informational only; spot's own
            # cash check above already gates entry, so this is never enforced.
            new_margin = abs(new_qty) * new_avg
        else:
            signed = fill.quantity if fill.action is DecisionAction.LONG else -fill.quantity
            same_direction = old_qty == 0 or (old_qty > 0 and signed > 0) or (old_qty < 0 and signed < 0)
            if same_direction:
                new_qty = old_qty + signed
                new_avg = (abs(old_qty) * old_avg + abs(signed) * fill.fill_price) / abs(new_qty) if new_qty else Decimal("0")
            else:
                close_qty = min(abs(old_qty), abs(signed)); direction = Decimal("1") if old_qty > 0 else Decimal("-1")
                realized_delta = (fill.fill_price - old_avg) * close_qty * direction
                realized += realized_delta; cash += (fill.fill_price - old_avg) * close_qty * direction
                new_qty = old_qty + signed
                new_avg = Decimal("0") if new_qty == 0 else (fill.fill_price if (old_qty > 0 > new_qty) or (old_qty < 0 < new_qty) else old_avg)
            cash -= fill.fee
            # Initial margin = notional / leverage - the textbook definition
            # of leverage itself (not a venue-specific mechanic). Reserved
            # margin only ever needs a fresh check when it INCREASES for
            # this position - covers a plain entry, pyramiding, and the
            # leftover leg of a reversal that flips through flat; a partial
            # or full close only ever releases margin, never needs one.
            new_margin = abs(new_qty) * new_avg / fill.leverage if new_qty else Decimal("0")
            if new_margin > old_margin:
                used_margin_others = self._used_margin(conn, fill.account) - old_margin
                if cash < used_margin_others + new_margin:
                    raise Experiment1Error(
                        "insufficient margin for futures position "
                        f"(required {used_margin_others + new_margin}, available {cash})"
                    )
        fees_paid += fill.fee
        conn.execute("""INSERT INTO experiment1_positions(account,symbol,quantity,average_price,leverage,margin) VALUES (?,?,?,?,?,?)
            ON CONFLICT(account,symbol) DO UPDATE SET quantity=excluded.quantity,average_price=excluded.average_price,leverage=excluded.leverage,margin=excluded.margin""",
            (fill.account.value, fill.symbol, str(new_qty), str(new_avg), str(fill.leverage), str(new_margin)))
        conn.execute("UPDATE experiment1_accounts SET cash=?,realized_pnl=?,fees_paid=? WHERE account=?", (str(cash),str(realized),str(fees_paid),fill.account.value))
        conn.execute("""INSERT INTO experiment1_fills(intent_id,account,action,symbol,quantity,reference_price,fill_price,fee,leverage,observed_at,source,source_reference,realized_pnl_delta)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (fill.intent_id,fill.account.value,fill.action.value,fill.symbol,str(fill.quantity),str(fill.reference_price),str(fill.fill_price),str(fill.fee),str(fill.leverage),fill.observed_at.isoformat(),fill.source,fill.source_reference,str(realized_delta)))

    def _used_margin(self, conn: sqlite3.Connection, account: AccountKind) -> Decimal:
        rows = conn.execute(
            "SELECT margin FROM experiment1_positions WHERE account=?", (account.value,)
        ).fetchall()
        return sum((Decimal(row["margin"]) for row in rows), Decimal("0"))

    def _recompute_equity(
        self, conn: sqlite3.Connection, account: AccountKind, marks: dict[str, Decimal]
    ) -> tuple[Decimal, Decimal]:
        """
        Deterministically recompute equity/unrealized P&L for `account`
        from its cash plus every open position, valued at marks[symbol]
        where a fresh mark was supplied this cycle, or at the position's
        own recorded average_price (cost basis) otherwise - a
        conservative, non-fabricated stand-in, never a synthetic price.
        Persists peak_equity/last_equity/max_drawdown; returns
        (equity, unrealized_pnl). Pure function of current position
        state + marks, so calling it repeatedly with the same marks is
        idempotent: peak_equity is a monotonic max, last_equity/
        max_drawdown are plain overwrites of the same recomputed values.
        """
        row = self._account_row(conn, account)
        equity = Decimal(row["cash"])
        unrealized = Decimal("0")
        positions = conn.execute("SELECT * FROM experiment1_positions WHERE account=?", (account.value,)).fetchall()
        for position in positions:
            qty = Decimal(position["quantity"])
            if qty == 0:
                continue
            avg = Decimal(position["average_price"])
            mark = marks.get(position["symbol"], avg)
            equity += qty * mark if account in NO_LEVERAGE_ACCOUNTS else (mark - avg) * qty
            unrealized += qty * (mark - avg)
        peak = max(Decimal(row["peak_equity"]), equity)
        drawdown = Decimal("0") if peak == 0 else (peak - equity) / peak
        conn.execute(
            "UPDATE experiment1_accounts SET peak_equity=?,last_equity=?,max_drawdown=? WHERE account=?",
            (str(peak), str(equity), str(max(Decimal(row["max_drawdown"]), drawdown)), account.value),
        )
        return equity, unrealized

    def _update_equity(self, conn: sqlite3.Connection, fill: FillRecord, mark_price: Decimal) -> None:
        # Only the fill's own symbol has a fresh mark_price here
        # (execute_pending receives one quote, for the traded symbol
        # only) - every other open position falls back to cost basis via
        # _recompute_equity's own marks.get() default. Continuous
        # mark-to-market across every held symbol, independent of which
        # one just traded, is reprice_open_positions() below.
        self._recompute_equity(conn, fill.account, {fill.symbol: mark_price})

    def reprice_open_positions(self, account: AccountKind, marks: dict[str, Decimal]) -> AccountState:
        """
        Continuous multi-symbol mark-to-market: recompute NAV/equity/
        drawdown for every currently open position in `account` from a
        fresh-evidence mark per symbol, for as many open symbols as the
        caller could gather quote evidence for this cycle - see
        experiment1/mtm.py for the runtime cycle that gathers `marks`
        from a live quote source and reports per-symbol evidence status.
        A symbol with no entry in `marks` keeps its existing cost-basis
        valuation, the same non-fabrication guarantee _update_equity
        already applies to every symbol besides the one that just
        traded - this method never invents a mark for missing evidence.

        This never creates a fill, never changes cash/realized_pnl/
        fees_paid/position quantities - it is a pure NAV snapshot, so
        repeated calls with the same marks are idempotent by
        construction, and restart-safe since all state lives in the db,
        never in a caller-held object.
        """
        if any(price <= 0 for price in marks.values()):
            raise Experiment1Error("mark price must be positive")
        with self._connect() as conn:
            self._recompute_equity(conn, account, marks)
        return self.account_state(account)

    def account_state(self, account: AccountKind) -> AccountState:
        with self._connect() as conn:
            row = self._account_row(conn, account)
            cash = Decimal(row["cash"])
            # No-leverage accounts pay full cost out of cash at fill time -
            # there is no separate reservation to release, so their
            # position "margin" (== notional, see _apply_fill) is purely
            # informational and must never be subtracted again here; doing
            # so would double-count the same value against available_cash.
            used_margin = self._used_margin(conn, account) if account not in NO_LEVERAGE_ACCOUNTS else Decimal("0")
            return AccountState(account, Decimal(row["starting_cash"]), cash, Decimal(row["realized_pnl"]),
                                Decimal(row["fees_paid"]), Decimal(row["peak_equity"]), Decimal(row["last_equity"]), Decimal(row["max_drawdown"]),
                                used_margin, cash - used_margin)

    def positions(self, account: AccountKind) -> tuple[PositionState, ...]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM experiment1_positions WHERE account=? ORDER BY symbol", (account.value,)).fetchall()
            return tuple(PositionState(account, row["symbol"], Decimal(row["quantity"]), Decimal(row["average_price"]), Decimal(row["leverage"]), Decimal(row["margin"]))
                         for row in rows if Decimal(row["quantity"]) != 0)

    def contribute(self, account: AccountKind, period: str, now: datetime | None = None) -> bool:
        """
        Credit `account`'s cash by its canonical MONTHLY_CONTRIBUTION for
        `period` - an opaque idempotency key such as "2026-09". Returns
        True if applied, False if this exact (account, period) pair was
        already applied - safe to call repeatedly, e.g. from an external
        caller that fires more than once for the same period. This
        method schedules nothing itself; nothing in this engine calls it
        automatically - an operator or a future scheduled job decides
        when to invoke it for a given period.
        """
        if account not in MONTHLY_CONTRIBUTION:
            raise Experiment1Error(f"{account.value} has no configured monthly contribution")
        if not period or not period.strip():
            raise Experiment1Error("period must be non-blank")
        amount = MONTHLY_CONTRIBUTION[account]
        applied_at = (now or datetime.now(timezone.utc)).isoformat()
        with self._connect() as conn:
            row = self._account_row(conn, account)
            existing = conn.execute(
                "SELECT 1 FROM experiment1_contributions WHERE account=? AND period=?",
                (account.value, period),
            ).fetchone()
            if existing is not None:
                return False
            conn.execute(
                "INSERT INTO experiment1_contributions(account,period,amount,applied_at) VALUES (?,?,?,?)",
                (account.value, period, str(amount), applied_at),
            )
            new_cash = Decimal(row["cash"]) + amount
            new_equity = Decimal(row["last_equity"]) + amount
            peak = max(Decimal(row["peak_equity"]), new_equity)
            drawdown = Decimal("0") if peak == 0 else (peak - new_equity) / peak
            conn.execute(
                """UPDATE experiment1_accounts
                   SET cash=?, peak_equity=?, last_equity=?, max_drawdown=?
                   WHERE account=?""",
                (str(new_cash), str(peak), str(new_equity),
                 str(max(Decimal(row["max_drawdown"]), drawdown)), account.value),
            )
        return True

    def contributions(self, account: AccountKind) -> tuple[ContributionRecord, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment1_contributions WHERE account=? ORDER BY period",
                (account.value,),
            ).fetchall()
            return tuple(
                ContributionRecord(account, row["period"], Decimal(row["amount"]), datetime.fromisoformat(row["applied_at"]))
                for row in rows
            )

    def closed_trades(self, account: AccountKind) -> tuple[ClosedTrade, ...]:
        """
        Deterministically reconstruct every completed round-trip trade
        (flat -> non-flat -> flat) per symbol from the immutable fills
        log, ordered by fill application order (the fills table's own
        autoincrement id - never observed_at, which is caller-supplied
        and not guaranteed unique). realized_pnl/fees_paid are exact
        sums of each fill's own persisted realized_pnl_delta/fee - the
        authoritative values the engine computed at fill time, not a
        re-derivation - so this can never drift from account_state().
        A still-open position (never returned to flat) contributes no
        entry here; positions() is the source for open state.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment1_fills WHERE account=? ORDER BY id ASC",
                (account.value,),
            ).fetchall()

        by_symbol: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_symbol.setdefault(row["symbol"], []).append(row)

        trades: list[ClosedTrade] = []
        for symbol, symbol_rows in by_symbol.items():
            running_qty = Decimal("0")
            leg: list[sqlite3.Row] = []
            for fill_row in symbol_rows:
                action = DecisionAction(fill_row["action"])
                signed = (
                    Decimal(fill_row["quantity"])
                    if action in (DecisionAction.BUY, DecisionAction.LONG)
                    else -Decimal(fill_row["quantity"])
                )
                leg.append(fill_row)
                running_qty += signed
                if running_qty == 0:
                    trades.append(self._closed_trade_from_leg(account, symbol, leg))
                    leg = []

        trades.sort(key=lambda trade: trade.closed_at)
        return tuple(trades)

    def _closed_trade_from_leg(
        self, account: AccountKind, symbol: str, leg: list[sqlite3.Row]
    ) -> ClosedTrade:
        realized = sum((Decimal(row["realized_pnl_delta"]) for row in leg), Decimal("0"))
        fees = sum((Decimal(row["fee"]) for row in leg), Decimal("0"))
        return ClosedTrade(
            account=account,
            symbol=symbol,
            opened_at=datetime.fromisoformat(leg[0]["observed_at"]),
            closed_at=datetime.fromisoformat(leg[-1]["observed_at"]),
            realized_pnl=realized,
            fees_paid=fees,
            fill_count=len(leg),
        )

    def _account_row(self, conn: sqlite3.Connection, account: AccountKind) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM experiment1_accounts WHERE account=?", (account.value,)).fetchone()
        if row is None: raise Experiment1Error("account not initialized")
        return row

    def _load_fill(self, conn: sqlite3.Connection, intent_id: str) -> FillRecord:
        row = conn.execute("SELECT * FROM experiment1_fills WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None: raise Experiment1Error("filled intent has no fill record")
        return FillRecord(intent_id=row["intent_id"], account=AccountKind(row["account"]), action=DecisionAction(row["action"]), symbol=row["symbol"],
                          quantity=Decimal(row["quantity"]), reference_price=Decimal(row["reference_price"]), fill_price=Decimal(row["fill_price"]),
                          fee=Decimal(row["fee"]), leverage=Decimal(row["leverage"]), observed_at=datetime.fromisoformat(row["observed_at"]),
                          source=row["source"], source_reference=row["source_reference"])

    def _intent_from_row(self, row: sqlite3.Row) -> OrderIntent:
        return OrderIntent(intent_id=row["intent_id"], created_at=datetime.fromisoformat(row["created_at"]), account=AccountKind(row["account"]),
                           action=DecisionAction(row["action"]), symbol=row["symbol"], quantity=Decimal(row["quantity"]), reason=row["reason"],
                           leverage=Decimal(row["leverage"]), stop_loss=None if row["stop_loss"] is None else Decimal(row["stop_loss"]),
                           take_profit=None if row["take_profit"] is None else Decimal(row["take_profit"]))
