from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import AccountKind, DecisionAction, MarketQuote, OrderIntent


NOW = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)


class Experiment1EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def intent(self, **overrides) -> OrderIntent:
        data = dict(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.SPOT,
            action=DecisionAction.BUY,
            symbol="BTCUSDT",
            quantity=Decimal("0.01"),
            reason="verified setup",
            leverage=Decimal("1"),
        )
        data.update(overrides)
        return OrderIntent(**data)

    def quote(self, **overrides) -> MarketQuote:
        data = dict(
            symbol="BTCUSDT",
            price=Decimal("10000"),
            observed_at=NOW + timedelta(minutes=1),
            source="test-feed",
            source_reference="quote-1",
            fee_bps=Decimal("10"),
            slippage_bps=Decimal("5"),
        )
        data.update(overrides)
        return MarketQuote(**data)

    def test_accounts_start_independently(self) -> None:
        for ledger in (
            AccountKind.INVESTMENTS_DEFENSIVE,
            AccountKind.INVESTMENTS_BALANCED,
            AccountKind.INVESTMENTS_GROWTH,
        ):
            with self.subTest(ledger=ledger):
                self.assertEqual(self.engine.account_state(ledger).cash, Decimal("5000"))
        self.assertEqual(
            self.engine.account_state(AccountKind.SPOT).cash,
            Decimal("2000"),
        )
        self.assertEqual(
            self.engine.account_state(AccountKind.FUTURES).cash,
            Decimal("2000"),
        )

    def test_investments_ledgers_are_independent(self) -> None:
        # A fill in one ledger must not affect the cash/positions of the
        # other two, or of Spot/Futures.
        self.engine.submit_intent(
            self.intent(account=AccountKind.INVESTMENTS_DEFENSIVE, symbol="BTCUSDT")
        )
        self.engine.execute_pending("intent-1", self.quote())

        self.assertLess(
            self.engine.account_state(AccountKind.INVESTMENTS_DEFENSIVE).cash,
            Decimal("5000"),
        )
        self.assertEqual(
            self.engine.account_state(AccountKind.INVESTMENTS_BALANCED).cash,
            Decimal("5000"),
        )
        self.assertEqual(
            self.engine.account_state(AccountKind.INVESTMENTS_GROWTH).cash,
            Decimal("5000"),
        )
        self.assertEqual(self.engine.account_state(AccountKind.SPOT).cash, Decimal("2000"))
        self.assertEqual(
            self.engine.positions(AccountKind.INVESTMENTS_BALANCED), ()
        )

    def test_legacy_investments_kind_is_not_auto_created(self) -> None:
        # Preserved in the enum (never removed) so a pre-existing
        # production row would remain reachable, but a fresh deployment
        # must not silently create it - the canonical model is the three
        # ledgers, not the legacy single account.
        with self.assertRaises(Experiment1Error):
            self.engine.account_state(AccountKind.INVESTMENTS)

    def test_wait_is_recorded_without_fill(self) -> None:
        status = self.engine.submit_intent(
            self.intent(action=DecisionAction.WAIT, quantity=Decimal("0"))
        )
        self.assertEqual(status.value, "NO_ACTION")
        with self.assertRaises(Experiment1Error):
            self.engine.execute_pending("intent-1", self.quote())

    def test_spot_rejects_leverage(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(self.intent(leverage=Decimal("2")))

    def test_futures_rejects_large_leverage(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(
                self.intent(
                    account=AccountKind.FUTURES,
                    action=DecisionAction.LONG,
                    leverage=Decimal("4"),
                )
            )

    def test_rejected_intent_is_persisted_as_blocked_with_reason(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(self.intent(leverage=Decimal("2")))

        self.assertIn("intent-1", self.engine.blocked_intent_ids())
        reason = self.engine.intent_status_reason("intent-1")
        self.assertIsNotNone(reason)
        self.assertIn("leverage", reason.lower())

    def test_resubmitting_identical_blocked_intent_is_idempotent(self) -> None:
        blocked = self.intent(leverage=Decimal("2"))
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(blocked)

        # Same intent_id, identical content, submitted again: returns the
        # already-recorded outcome instead of re-raising or re-validating.
        status = self.engine.submit_intent(blocked)
        self.assertEqual(status.value, "BLOCKED")
        self.assertEqual(len(self.engine.blocked_intent_ids()), 1)

    def test_futures_rejection_is_also_persisted(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(
                self.intent(
                    account=AccountKind.FUTURES,
                    action=DecisionAction.LONG,
                    leverage=Decimal("4"),
                )
            )
        self.assertIn("intent-1", self.engine.blocked_intent_ids())
        self.assertIn("3x", self.engine.intent_status_reason("intent-1"))

    def test_accepted_intent_has_no_status_reason(self) -> None:
        self.engine.submit_intent(self.intent())
        self.assertIsNone(self.engine.intent_status_reason("intent-1"))
        self.assertEqual(self.engine.blocked_intent_ids(), ())

    def test_quote_must_be_forward_and_provenanced(self) -> None:
        self.engine.submit_intent(self.intent())
        with self.assertRaises(Experiment1Error):
            self.engine.execute_pending(
                "intent-1",
                self.quote(observed_at=NOW - timedelta(seconds=1)),
            )

    def test_spot_buy_applies_adverse_slippage_and_fee(self) -> None:
        self.engine.submit_intent(self.intent())
        fill = self.engine.execute_pending("intent-1", self.quote())
        self.assertEqual(fill.fill_price, Decimal("10005.0000"))
        self.assertEqual(fill.fee, Decimal("0.100050000"))
        state = self.engine.account_state(AccountKind.SPOT)
        self.assertEqual(state.cash, Decimal("1899.849950000"))
        positions = self.engine.positions(AccountKind.SPOT)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].quantity, Decimal("0.01"))

    def test_same_intent_and_fill_are_idempotent(self) -> None:
        intent = self.intent()
        self.engine.submit_intent(intent)
        first = self.engine.execute_pending(intent.intent_id, self.quote())
        self.assertEqual(self.engine.submit_intent(intent).value, "FILLED")
        second = self.engine.execute_pending(
            intent.intent_id,
            self.quote(source_reference="quote-2"),
        )
        self.assertEqual(first, second)

    def test_duplicate_intent_id_with_changed_content_fails_closed(self) -> None:
        self.engine.submit_intent(self.intent())
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(self.intent(symbol="ETHUSDT"))

    def test_spot_cannot_sell_more_than_held(self) -> None:
        self.engine.submit_intent(
            self.intent(intent_id="sell-1", action=DecisionAction.SELL)
        )
        with self.assertRaises(Experiment1Error):
            self.engine.execute_pending("sell-1", self.quote())

    def test_equity_includes_untraded_open_positions_at_cost_basis(self) -> None:
        # Regression: a fill in one symbol must not silently drop every
        # other open position from equity/drawdown - the untraded position
        # (BTCUSDT here) must still contribute, valued at its own recorded
        # average_price since no fresh quote for it is available in this
        # fill's context.
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())

        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                symbol="ETHUSDT",
                quantity=Decimal("0.1"),
                created_at=NOW + timedelta(minutes=1),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(
                symbol="ETHUSDT",
                price=Decimal("2000"),
                observed_at=NOW + timedelta(minutes=2),
                source_reference="quote-eth",
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
            ),
        )

        state = self.engine.account_state(AccountKind.SPOT)
        # cash (1699.84995) + BTC 0.01 @ its own avg cost 10005.0000
        # (100.05) + ETH 0.1 @ fresh mark 2000 (200) = 1999.89995.
        self.assertEqual(state.last_equity, Decimal("1999.89995"))

    def test_futures_long_then_short_realizes_pnl(self) -> None:
        self.engine.submit_intent(
            self.intent(
                intent_id="long-1",
                account=AccountKind.FUTURES,
                action=DecisionAction.LONG,
                quantity=Decimal("1"),
                leverage=Decimal("2"),
            )
        )
        self.engine.execute_pending("long-1", self.quote(price=Decimal("100")))
        self.engine.submit_intent(
            self.intent(
                intent_id="short-1",
                created_at=NOW + timedelta(minutes=2),
                account=AccountKind.FUTURES,
                action=DecisionAction.SHORT,
                quantity=Decimal("1"),
                leverage=Decimal("2"),
            )
        )
        self.engine.execute_pending(
            "short-1",
            self.quote(
                price=Decimal("110"),
                observed_at=NOW + timedelta(minutes=3),
                source_reference="quote-2",
            ),
        )
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertGreater(state.realized_pnl, Decimal("0"))
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), ())


class Experiment1ContributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_contribute_credits_cash_and_equity(self) -> None:
        applied = self.engine.contribute(
            AccountKind.INVESTMENTS_DEFENSIVE, "2026-09", now=NOW
        )
        self.assertTrue(applied)
        state = self.engine.account_state(AccountKind.INVESTMENTS_DEFENSIVE)
        self.assertEqual(state.cash, Decimal("7000"))
        self.assertEqual(state.last_equity, Decimal("7000"))
        self.assertEqual(state.peak_equity, Decimal("7000"))

    def test_contribute_same_period_twice_is_idempotent(self) -> None:
        first = self.engine.contribute(AccountKind.INVESTMENTS_BALANCED, "2026-09", now=NOW)
        second = self.engine.contribute(AccountKind.INVESTMENTS_BALANCED, "2026-09", now=NOW)
        self.assertTrue(first)
        self.assertFalse(second)
        state = self.engine.account_state(AccountKind.INVESTMENTS_BALANCED)
        self.assertEqual(state.cash, Decimal("7000"))

    def test_contribute_different_periods_both_apply(self) -> None:
        self.engine.contribute(AccountKind.INVESTMENTS_GROWTH, "2026-09", now=NOW)
        self.engine.contribute(
            AccountKind.INVESTMENTS_GROWTH, "2026-10", now=NOW + timedelta(days=30)
        )
        state = self.engine.account_state(AccountKind.INVESTMENTS_GROWTH)
        self.assertEqual(state.cash, Decimal("9000"))

    def test_contribute_rejects_account_with_no_configured_amount(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.contribute(AccountKind.SPOT, "2026-09", now=NOW)

    def test_contributions_lists_applied_history(self) -> None:
        self.engine.contribute(AccountKind.INVESTMENTS_DEFENSIVE, "2026-09", now=NOW)
        records = self.engine.contributions(AccountKind.INVESTMENTS_DEFENSIVE)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].period, "2026-09")
        self.assertEqual(records[0].amount, Decimal("2000"))

    def test_contribute_never_auto_disables_or_schedules(self) -> None:
        # Structural guarantee: contribute() is purely on-demand - no
        # attribute/method on the engine represents a scheduling action.
        engine_attrs = {name for name in dir(self.engine) if not name.startswith("_")}
        for forbidden in ("schedule", "cron", "auto_contribute"):
            for name in engine_attrs:
                self.assertNotIn(forbidden, name.lower())


class Experiment1ClosedTradesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def intent(self, **overrides) -> OrderIntent:
        data = dict(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.SPOT,
            action=DecisionAction.BUY,
            symbol="BTCUSDT",
            quantity=Decimal("0.01"),
            reason="verified setup",
            leverage=Decimal("1"),
        )
        data.update(overrides)
        return OrderIntent(**data)

    def quote(self, **overrides) -> MarketQuote:
        data = dict(
            symbol="BTCUSDT",
            price=Decimal("10000"),
            observed_at=NOW + timedelta(minutes=1),
            source="test-feed",
            source_reference="quote-1",
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
        data.update(overrides)
        return MarketQuote(**data)

    def test_open_position_produces_no_closed_trade(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())
        self.assertEqual(self.engine.closed_trades(AccountKind.SPOT), ())

    def test_spot_round_trip_produces_one_closed_trade_with_exact_realized_pnl(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote(price=Decimal("100")))
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                action=DecisionAction.SELL,
                created_at=NOW + timedelta(minutes=2),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(
                price=Decimal("150"),
                observed_at=NOW + timedelta(minutes=3),
                source_reference="quote-2",
            ),
        )

        trades = self.engine.closed_trades(AccountKind.SPOT)
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.symbol, "BTCUSDT")
        self.assertEqual(trade.fill_count, 2)
        # (150 - 100) * 0.01 = 0.5, zero fees in this quote.
        self.assertEqual(trade.realized_pnl, Decimal("0.5"))
        self.assertEqual(trade.fees_paid, Decimal("0"))
        self.assertEqual(
            self.engine.account_state(AccountKind.SPOT).realized_pnl, trade.realized_pnl
        )

    def test_closed_trade_realized_pnl_never_drifts_from_account_state(self) -> None:
        # Two independent round trips on the same symbol - sum of closed
        # trades' realized_pnl must exactly equal the account's own
        # cumulative realized_pnl, since both are derived from the same
        # authoritative per-fill values.
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote(price=Decimal("100")))
        self.engine.submit_intent(
            self.intent(intent_id="intent-2", action=DecisionAction.SELL, created_at=NOW + timedelta(minutes=1))
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(price=Decimal("90"), observed_at=NOW + timedelta(minutes=2), source_reference="q2"),
        )
        self.engine.submit_intent(
            self.intent(intent_id="intent-3", created_at=NOW + timedelta(minutes=3))
        )
        self.engine.execute_pending(
            "intent-3",
            self.quote(price=Decimal("90"), observed_at=NOW + timedelta(minutes=4), source_reference="q3"),
        )
        self.engine.submit_intent(
            self.intent(intent_id="intent-4", action=DecisionAction.SELL, created_at=NOW + timedelta(minutes=5))
        )
        self.engine.execute_pending(
            "intent-4",
            self.quote(price=Decimal("120"), observed_at=NOW + timedelta(minutes=6), source_reference="q4"),
        )

        trades = self.engine.closed_trades(AccountKind.SPOT)
        self.assertEqual(len(trades), 2)
        total_realized = sum((trade.realized_pnl for trade in trades), Decimal("0"))
        self.assertEqual(total_realized, self.engine.account_state(AccountKind.SPOT).realized_pnl)

    def test_futures_reversal_through_flat_closes_a_trade(self) -> None:
        self.engine.submit_intent(
            self.intent(
                account=AccountKind.FUTURES,
                action=DecisionAction.LONG,
                quantity=Decimal("1"),
            )
        )
        self.engine.execute_pending("intent-1", self.quote(price=Decimal("100")))
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                account=AccountKind.FUTURES,
                action=DecisionAction.SHORT,
                quantity=Decimal("1"),
                created_at=NOW + timedelta(minutes=1),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(price=Decimal("110"), observed_at=NOW + timedelta(minutes=2), source_reference="q2"),
        )

        trades = self.engine.closed_trades(AccountKind.FUTURES)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].realized_pnl, Decimal("10"))


class Experiment1RestartReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "experiment1.db"

    def test_reopening_engine_does_not_mutate_existing_state(self) -> None:
        first = Experiment1Engine(self.db_path)
        intent = OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.SPOT,
            action=DecisionAction.BUY,
            symbol="BTCUSDT",
            quantity=Decimal("0.01"),
            reason="verified setup",
        )
        first.submit_intent(intent)
        fill = first.execute_pending(
            "intent-1",
            MarketQuote(
                symbol="BTCUSDT",
                price=Decimal("100"),
                observed_at=NOW + timedelta(minutes=1),
                source="test-feed",
                source_reference="quote-1",
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
            ),
        )
        state_before = first.account_state(AccountKind.SPOT)

        # Simulate a process restart: a fresh Engine instance over the
        # same db file must see identical state, and re-driving the same
        # already-FILLED intent_id must not double-apply the fill.
        second = Experiment1Engine(self.db_path)
        state_after = second.account_state(AccountKind.SPOT)
        self.assertEqual(state_before, state_after)

        replayed_fill = second.execute_pending(
            "intent-1",
            MarketQuote(
                symbol="BTCUSDT",
                price=Decimal("999"),
                observed_at=NOW + timedelta(minutes=5),
                source="test-feed",
                source_reference="quote-replay",
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
            ),
        )
        self.assertEqual(replayed_fill, fill)
        self.assertEqual(second.account_state(AccountKind.SPOT), state_before)
        self.assertEqual(len(second.positions(AccountKind.SPOT)), 1)
        self.assertEqual(second.positions(AccountKind.SPOT)[0].quantity, Decimal("0.01"))

    def test_reopening_engine_over_pre_existing_db_adds_missing_column(self) -> None:
        # Simulate a database created before realized_pnl_delta existed:
        # build the old schema by hand, then open it with the current
        # Engine and confirm it migrates in place without error and
        # without touching any other column.
        import sqlite3 as sqlite3_module

        conn = sqlite3_module.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE experiment1_accounts (
                account TEXT PRIMARY KEY, starting_cash TEXT NOT NULL, cash TEXT NOT NULL,
                realized_pnl TEXT NOT NULL, fees_paid TEXT NOT NULL, peak_equity TEXT NOT NULL,
                last_equity TEXT NOT NULL, max_drawdown TEXT NOT NULL
            );
            CREATE TABLE experiment1_intents (
                intent_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, account TEXT NOT NULL,
                action TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL, reason TEXT NOT NULL,
                leverage TEXT NOT NULL, stop_loss TEXT, take_profit TEXT, status TEXT NOT NULL, status_reason TEXT
            );
            CREATE TABLE experiment1_positions (
                account TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL,
                average_price TEXT NOT NULL, leverage TEXT NOT NULL, PRIMARY KEY(account, symbol)
            );
            CREATE TABLE experiment1_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT, intent_id TEXT NOT NULL UNIQUE, account TEXT NOT NULL,
                action TEXT NOT NULL, symbol TEXT NOT NULL, quantity TEXT NOT NULL, reference_price TEXT NOT NULL,
                fill_price TEXT NOT NULL, fee TEXT NOT NULL, leverage TEXT NOT NULL, observed_at TEXT NOT NULL,
                source TEXT NOT NULL, source_reference TEXT NOT NULL
            );
            INSERT INTO experiment1_accounts VALUES
                ('SPOT', '2000', '1500', '10', '0.5', '2000', '1500', '0.25');
            INSERT INTO experiment1_fills
                (intent_id, account, action, symbol, quantity, reference_price, fill_price, fee,
                 leverage, observed_at, source, source_reference)
                VALUES ('old-intent', 'SPOT', 'BUY', 'BTCUSDT', '0.01', '100', '100', '0',
                        '1', '2026-01-01T00:00:00+00:00', 'legacy', 'legacy-ref');
            """
        )
        conn.commit()
        conn.close()

        engine = Experiment1Engine(self.db_path)

        # Old account row preserved exactly - no destructive rewrite.
        state = engine.account_state(AccountKind.SPOT)
        self.assertEqual(state.cash, Decimal("1500"))
        self.assertEqual(state.realized_pnl, Decimal("10"))

        # Old fill row preserved and readable; the new column defaulted
        # to '0' for a pre-migration row rather than raising or
        # fabricating a nonzero value.
        trades = engine.closed_trades(AccountKind.SPOT)
        self.assertEqual(trades, ())  # still open (BUY only, never flat)
        positions = engine.positions(AccountKind.SPOT)
        self.assertEqual(len(positions), 0)  # position row was never in the legacy fixture


if __name__ == "__main__":
    unittest.main()
