from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from experiment1.engine import Experiment1Engine, Experiment1Error
from experiment1.models import (\n    AccountKind, DecisionAction, GilInboxStatus, MarketQuote, OrderIntent, TradingInboxStatus\n)


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

    def test_filled_intent_ids_lists_only_filled_not_pending_or_blocked(self) -> None:
        self.engine.submit_intent(self.intent(intent_id="pending-1"))
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(self.intent(intent_id="blocked-1", leverage=Decimal("2")))
        self.engine.submit_intent(self.intent(intent_id="filled-1", created_at=NOW + timedelta(minutes=1)))
        self.engine.execute_pending(
            "filled-1", self.quote(observed_at=NOW + timedelta(minutes=2), source_reference="q-filled")
        )

        self.assertEqual(self.engine.filled_intent_ids(), ("filled-1",))
        self.assertIn("pending-1", self.engine.pending_intent_ids())
        self.assertIn("blocked-1", self.engine.blocked_intent_ids())


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


class Experiment1FuturesMarginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def intent(self, **overrides) -> OrderIntent:
        data = dict(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("10"),
            reason="verified setup",
            leverage=Decimal("2"),
        )
        data.update(overrides)
        return OrderIntent(**data)

    def quote(self, **overrides) -> MarketQuote:
        data = dict(
            symbol="BTCUSDT",
            price=Decimal("100"),
            observed_at=NOW + timedelta(minutes=1),
            source="test-feed",
            source_reference="quote-1",
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        )
        data.update(overrides)
        return MarketQuote(**data)

    def test_leverage_gives_margin_less_than_full_notional(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())
        position = self.engine.positions(AccountKind.FUTURES)[0]
        # notional = 10 * 100 = 1000; margin = notional / leverage(2) = 500.
        self.assertEqual(position.notional, Decimal("1000"))
        self.assertEqual(position.margin, Decimal("500"))
        self.assertLess(position.margin, position.notional)

    def test_margin_reserved_reduces_available_cash_not_cash(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("500"))
        self.assertEqual(state.cash, Decimal("2000"))  # wallet balance untouched by margin
        self.assertEqual(state.available_cash, Decimal("1500"))

    def test_insufficient_margin_rejects_and_leaves_state_untouched(self) -> None:
        self.engine.submit_intent(self.intent(quantity=Decimal("100")))
        with self.assertRaises(Experiment1Error) as ctx:
            self.engine.execute_pending("intent-1", self.quote())
        self.assertIn("insufficient margin", str(ctx.exception))
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), ())
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.cash, Decimal("2000"))
        self.assertEqual(state.used_margin, Decimal("0"))

    def test_pyramiding_recomputes_and_gates_increased_margin(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(intent_id="intent-2", quantity=Decimal("5"), created_at=NOW + timedelta(minutes=2))
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(observed_at=NOW + timedelta(minutes=3), source_reference="quote-2"),
        )
        position = self.engine.positions(AccountKind.FUTURES)[0]
        # 15 @ 100, leverage 2x -> margin 750.
        self.assertEqual(position.quantity, Decimal("15"))
        self.assertEqual(position.margin, Decimal("750"))
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("750"))
        self.assertEqual(state.available_cash, Decimal("1250"))

    def test_partial_close_releases_margin_without_triggering_check(self) -> None:
        self.engine.submit_intent(self.intent(quantity=Decimal("15")))
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                action=DecisionAction.SHORT,
                quantity=Decimal("5"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(price=Decimal("110"), observed_at=NOW + timedelta(minutes=3), source_reference="quote-2"),
        )
        position = self.engine.positions(AccountKind.FUTURES)[0]
        self.assertEqual(position.quantity, Decimal("10"))
        # 10 @ 100 (avg unchanged on a partial close), leverage 2x -> margin 500.
        self.assertEqual(position.margin, Decimal("500"))
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("500"))
        # cash gains the realized P&L from the partial close: 2000 + (110-100)*5 = 2050.
        self.assertEqual(state.cash, Decimal("2050"))
        self.assertEqual(state.available_cash, Decimal("1550"))

    def test_full_close_returns_margin_and_used_margin_to_zero(self) -> None:
        self.engine.submit_intent(self.intent())
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                action=DecisionAction.SHORT,
                quantity=Decimal("10"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(price=Decimal("105"), observed_at=NOW + timedelta(minutes=3), source_reference="quote-2"),
        )
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), ())
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("0"))
        self.assertEqual(state.available_cash, state.cash)

    def test_reversal_through_flat_checks_margin_of_leftover_leg_only(self) -> None:
        self.engine.submit_intent(self.intent())  # LONG 10 @ 100, lev 2 -> margin 500
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                action=DecisionAction.SHORT,
                quantity=Decimal("30"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(observed_at=NOW + timedelta(minutes=3), source_reference="quote-2"),
        )
        position = self.engine.positions(AccountKind.FUTURES)[0]
        # Reversal: 10 closed, leftover -20 @ fill price 100, lev 2 -> margin 1000.
        self.assertEqual(position.quantity, Decimal("-20"))
        self.assertEqual(position.margin, Decimal("1000"))
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("1000"))

    def test_reversal_leftover_leg_rejected_when_margin_insufficient(self) -> None:
        self.engine.submit_intent(self.intent())  # LONG 10 @ 100, lev 2 -> margin 500
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                action=DecisionAction.SHORT,
                quantity=Decimal("100"),
                leverage=Decimal("1"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        with self.assertRaises(Experiment1Error) as ctx:
            self.engine.execute_pending(
                "intent-2",
                self.quote(observed_at=NOW + timedelta(minutes=3), source_reference="quote-2"),
            )
        self.assertIn("insufficient margin", str(ctx.exception))
        # Rejected atomically - the original long position is untouched.
        position = self.engine.positions(AccountKind.FUTURES)[0]
        self.assertEqual(position.quantity, Decimal("10"))
        self.assertEqual(position.margin, Decimal("500"))

    def test_two_simultaneous_positions_sum_into_used_margin(self) -> None:
        self.engine.submit_intent(self.intent())  # BTCUSDT LONG 10 @ 100, lev 2 -> margin 500
        self.engine.execute_pending("intent-1", self.quote())
        self.engine.submit_intent(
            self.intent(
                intent_id="intent-2",
                symbol="ETHUSDT",
                quantity=Decimal("10"),
                created_at=NOW + timedelta(minutes=2),
            )
        )
        self.engine.execute_pending(
            "intent-2",
            self.quote(
                symbol="ETHUSDT",
                price=Decimal("50"),
                observed_at=NOW + timedelta(minutes=3),
                source_reference="quote-2",
            ),
        )
        positions = self.engine.positions(AccountKind.FUTURES)
        self.assertEqual(len(positions), 2)
        state = self.engine.account_state(AccountKind.FUTURES)
        # 500 (BTC) + 250 (ETH: 10 * 50 / 2) = 750.
        self.assertEqual(state.used_margin, Decimal("750"))
        self.assertEqual(state.available_cash, Decimal("1250"))

    def test_leverage_cap_rejection_leaves_margin_untouched(self) -> None:
        with self.assertRaises(Experiment1Error):
            self.engine.submit_intent(self.intent(leverage=Decimal("4")))
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), ())
        state = self.engine.account_state(AccountKind.FUTURES)
        self.assertEqual(state.used_margin, Decimal("0"))
        self.assertEqual(state.available_cash, state.cash)

    def test_no_leverage_accounts_never_reserve_margin(self) -> None:
        self.engine.submit_intent(
            OrderIntent(
                intent_id="spot-1",
                created_at=NOW,
                account=AccountKind.SPOT,
                action=DecisionAction.BUY,
                symbol="BTCUSDT",
                quantity=Decimal("0.01"),
                reason="verified setup",
            )
        )
        self.engine.execute_pending(
            "spot-1",
            MarketQuote(
                symbol="BTCUSDT",
                price=Decimal("10000"),
                observed_at=NOW + timedelta(minutes=1),
                source="test-feed",
                source_reference="quote-1",
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
            ),
        )
        spot_state = self.engine.account_state(AccountKind.SPOT)
        self.assertEqual(spot_state.used_margin, Decimal("0"))
        self.assertEqual(spot_state.available_cash, spot_state.cash)

        ledger_state = self.engine.account_state(AccountKind.INVESTMENTS_DEFENSIVE)
        self.assertEqual(ledger_state.used_margin, Decimal("0"))
        self.assertEqual(ledger_state.available_cash, ledger_state.cash)


class Experiment1RepriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _open(self, intent_id: str, symbol: str, price: Decimal, quantity: Decimal = Decimal("1")) -> None:
        self.engine.submit_intent(
            OrderIntent(
                intent_id=intent_id,
                created_at=NOW,
                account=AccountKind.FUTURES,
                action=DecisionAction.LONG,
                symbol=symbol,
                quantity=quantity,
                reason="reprice test",
                leverage=Decimal("2"),
            )
        )
        self.engine.execute_pending(
            intent_id,
            MarketQuote(
                symbol=symbol,
                price=price,
                observed_at=NOW + timedelta(minutes=1),
                source="test-feed",
                source_reference=f"open-{symbol}",
                fee_bps=Decimal("0"),
                slippage_bps=Decimal("0"),
            ),
        )

    def test_reprice_updates_equity_from_fresh_marks_for_multiple_symbols(self) -> None:
        self._open("intent-1", "BTCUSDT", Decimal("100"))
        self._open("intent-2", "ETHUSDT", Decimal("50"))

        state = self.engine.reprice_open_positions(
            AccountKind.FUTURES, {"BTCUSDT": Decimal("110"), "ETHUSDT": Decimal("40")}
        )

        # cash 2000 + BTC unrealized (110-100)*1=10 + ETH unrealized (40-50)*1=-10 = 2000.
        self.assertEqual(state.last_equity, Decimal("2000"))

    def test_reprice_falls_back_to_cost_basis_for_symbols_without_a_fresh_mark(self) -> None:
        self._open("intent-1", "BTCUSDT", Decimal("100"))
        self._open("intent-2", "ETHUSDT", Decimal("50"))

        # Only BTCUSDT has fresh evidence this cycle - ETHUSDT must fall
        # back to its own recorded average_price, never a fabricated mark.
        state = self.engine.reprice_open_positions(AccountKind.FUTURES, {"BTCUSDT": Decimal("110")})

        # cash 2000 + BTC unrealized (110-100)*1=10 + ETH unrealized (50-50)*1=0 = 2010.
        self.assertEqual(state.last_equity, Decimal("2010"))

    def test_reprice_never_creates_a_fill_or_changes_cash_or_positions(self) -> None:
        self._open("intent-1", "BTCUSDT", Decimal("100"))
        cash_before = self.engine.account_state(AccountKind.FUTURES).cash
        positions_before = self.engine.positions(AccountKind.FUTURES)
        pending_before = self.engine.pending_intent_ids()

        self.engine.reprice_open_positions(AccountKind.FUTURES, {"BTCUSDT": Decimal("999")})

        self.assertEqual(self.engine.account_state(AccountKind.FUTURES).cash, cash_before)
        self.assertEqual(self.engine.positions(AccountKind.FUTURES), positions_before)
        self.assertEqual(self.engine.pending_intent_ids(), pending_before)
        self.assertEqual(self.engine.closed_trades(AccountKind.FUTURES), ())

    def test_reprice_is_idempotent_across_repeated_calls(self) -> None:
        self._open("intent-1", "BTCUSDT", Decimal("100"))

        marks = {"BTCUSDT": Decimal("120")}
        first = self.engine.reprice_open_positions(AccountKind.FUTURES, marks)
        second = self.engine.reprice_open_positions(AccountKind.FUTURES, marks)

        self.assertEqual(first, second)

    def test_reprice_rejects_non_positive_mark_price_and_leaves_state_untouched(self) -> None:
        self._open("intent-1", "BTCUSDT", Decimal("100"))
        state_before = self.engine.account_state(AccountKind.FUTURES)

        with self.assertRaises(Experiment1Error):
            self.engine.reprice_open_positions(AccountKind.FUTURES, {"BTCUSDT": Decimal("0")})

        self.assertEqual(self.engine.account_state(AccountKind.FUTURES), state_before)

    def test_reprice_matches_fill_triggered_equity_given_the_same_single_mark(self) -> None:
        # Cross-check that the refactor kept the fill-triggered path
        # (_update_equity) and the standalone multi-symbol path
        # (reprice_open_positions) mathematically consistent: repricing
        # with only the traded symbol's mark must reproduce exactly what
        # the fill itself already computed.
        self._open("intent-1", "BTCUSDT", Decimal("100"))
        equity_from_fill = self.engine.account_state(AccountKind.FUTURES).last_equity

        state = self.engine.reprice_open_positions(AccountKind.FUTURES, {"BTCUSDT": Decimal("100")})

        self.assertEqual(state.last_equity, equity_from_fill)


class Experiment1GilInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Experiment1Engine(Path(self.tmp.name) / "experiment1.db")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_receive_gil_decision_persists_a_pending_drain_row(self) -> None:
        record = self.engine.receive_gil_decision("gil-1", '{"a":1}', now=NOW)

        self.assertEqual(record.decision_id, "gil-1")
        self.assertEqual(record.status, GilInboxStatus.PENDING_DRAIN)
        self.assertIsNone(record.outcome)
        self.assertEqual(record.received_at, NOW)
        self.assertEqual(self.engine.pending_gil_decision_inbox(), (("gil-1", '{"a":1}'),))

    def test_receive_gil_decision_is_idempotent_on_identical_resubmission(self) -> None:
        first = self.engine.receive_gil_decision("gil-1", '{"a":1}', now=NOW)
        second = self.engine.receive_gil_decision("gil-1", '{"a":1}', now=NOW + timedelta(minutes=5))

        self.assertEqual(first, second)
        self.assertEqual(len(self.engine.pending_gil_decision_inbox()), 1)

    def test_receive_gil_decision_rejects_a_decision_id_reused_with_different_content(self) -> None:
        self.engine.receive_gil_decision("gil-1", '{"a":1}', now=NOW)
        with self.assertRaises(Experiment1Error):
            self.engine.receive_gil_decision("gil-1", '{"a":2}', now=NOW)

    def test_record_malformed_gil_decision_persists_a_malformed_row_never_pending_drain(self) -> None:
        record = self.engine.record_malformed_gil_decision(
            "gil-bad", '{"decision_id":"gil-bad"}', "decided_at must be timezone-aware", now=NOW
        )

        self.assertEqual(record.status, GilInboxStatus.MALFORMED)
        self.assertEqual(record.outcome_reason, "decided_at must be timezone-aware")
        self.assertEqual(self.engine.pending_gil_decision_inbox(), ())

    def test_mark_gil_decision_processed_updates_status_outcome_and_intent_id(self) -> None:
        self.engine.receive_gil_decision("gil-1", '{"a":1}', now=NOW)
        self.engine.mark_gil_decision_processed(
            "gil-1", outcome="PENDING", outcome_reason=None, intent_id="gil-decision:gil-1", now=NOW + timedelta(minutes=1)
        )

        record = self.engine.gil_decision_inbox_status("gil-1")
        self.assertEqual(record.status, GilInboxStatus.PROCESSED)
        self.assertEqual(record.outcome, "PENDING")
        self.assertEqual(record.intent_id, "gil-decision:gil-1")
        self.assertEqual(record.processed_at, NOW + timedelta(minutes=1))
        self.assertEqual(self.engine.pending_gil_decision_inbox(), ())

    def test_gil_decision_inbox_status_returns_none_for_unknown_decision_id(self) -> None:
        self.assertIsNone(self.engine.gil_decision_inbox_status("unknown"))

    def test_gil_decision_inbox_survives_a_process_restart(self) -> None:
        db_path = Path(self.tmp.name) / "restart.db"
        first = Experiment1Engine(db_path)
        first.receive_gil_decision("gil-1", '{"a":1}', now=NOW)
        first.mark_gil_decision_processed("gil-1", outcome="PENDING", outcome_reason=None, intent_id="gil-decision:gil-1")

        second = Experiment1Engine(db_path)
        record = second.gil_decision_inbox_status("gil-1")
        self.assertEqual(record.status, GilInboxStatus.PROCESSED)
        self.assertEqual(record.outcome, "PENDING")


class Experiment1TradingInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "experiment1.db"
        self.engine = Experiment1Engine(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_receive_trading_decision_persists_pending_row(self) -> None:
        record = self.engine.receive_trading_decision(
            "sl-1", '{"decision_id":"sl-1"}', now=NOW
        )

        self.assertEqual(record.decision_id, "sl-1")
        self.assertEqual(record.status, TradingInboxStatus.PENDING_DRAIN)
        self.assertEqual(record.received_at, NOW)
        self.assertIsNone(record.outcome)
        self.assertEqual(
            self.engine.pending_trading_decision_inbox(),
            (("sl-1", '{"decision_id":"sl-1"}'),),
        )

    def test_identical_replay_is_idempotent_and_keeps_original_timestamp(self) -> None:
        first = self.engine.receive_trading_decision("sl-1", '{"a":1}', now=NOW)
        second = self.engine.receive_trading_decision(
            "sl-1", '{"a":1}', now=NOW + timedelta(minutes=5)
        )

        self.assertEqual(first, second)
        self.assertEqual(first.received_at, NOW)
        self.assertEqual(len(self.engine.pending_trading_decision_inbox()), 1)

    def test_same_id_with_different_payload_fails_closed(self) -> None:
        self.engine.receive_trading_decision("sl-1", '{"a":1}', now=NOW)

        with self.assertRaisesRegex(
            Experiment1Error, "already exists with different content"
        ):
            self.engine.receive_trading_decision("sl-1", '{"a":2}', now=NOW)

    def test_malformed_is_terminal_and_never_pending(self) -> None:
        record = self.engine.record_malformed_trading_decision(
            "sl-bad",
            '{"decision_id":"sl-bad"}',
            "invalid trading envelope",
            now=NOW,
        )

        self.assertEqual(record.status, TradingInboxStatus.MALFORMED)
        self.assertEqual(record.outcome_reason, "invalid trading envelope")
        self.assertEqual(record.processed_at, NOW)
        self.assertEqual(self.engine.pending_trading_decision_inbox(), ())

    def test_mark_processed_removes_row_from_pending_drain(self) -> None:
        self.engine.receive_trading_decision("sl-1", '{"a":1}', now=NOW)
        self.engine.mark_trading_decision_processed(
            "sl-1",
            outcome="PENDING",
            outcome_reason=None,
            intent_id="trading-decision:sl-1",
            now=NOW + timedelta(minutes=1),
        )

        record = self.engine.trading_decision_inbox_status("sl-1")
        self.assertEqual(record.status, TradingInboxStatus.PROCESSED)
        self.assertEqual(record.outcome, "PENDING")
        self.assertEqual(record.intent_id, "trading-decision:sl-1")
        self.assertEqual(record.processed_at, NOW + timedelta(minutes=1))
        self.assertEqual(self.engine.pending_trading_decision_inbox(), ())

    def test_watch_reason_survives_while_row_stays_pending(self) -> None:
        self.engine.receive_trading_decision("sl-1", '{"a":1}', now=NOW)
        self.engine.record_trading_decision_watch("sl-1", "fresh quote unavailable")

        record = self.engine.trading_decision_inbox_status("sl-1")
        self.assertEqual(record.status, TradingInboxStatus.PENDING_DRAIN)
        self.assertEqual(record.outcome_reason, "fresh quote unavailable")
        self.assertEqual(len(self.engine.pending_trading_decision_inbox()), 1)

    def test_trading_inbox_survives_process_restart_and_replay(self) -> None:
        first = Experiment1Engine(self.db_path)
        original = first.receive_trading_decision("sl-1", '{"a":1}', now=NOW)

        second = Experiment1Engine(self.db_path)
        recovered = second.trading_decision_inbox_status("sl-1")
        replay = second.receive_trading_decision(
            "sl-1", '{"a":1}', now=NOW + timedelta(hours=1)
        )

        self.assertEqual(recovered, original)
        self.assertEqual(replay, original)
        self.assertEqual(len(second.pending_trading_decision_inbox()), 1)

    def test_gil_and_trading_namespaces_allow_same_decision_id(self) -> None:
        gil = self.engine.receive_gil_decision("same-id", '{"producer":"gil"}', now=NOW)
        trading = self.engine.receive_trading_decision(
            "same-id", '{"producer":"strategy-lab"}', now=NOW
        )

        self.assertEqual(gil.decision_id, trading.decision_id)
        self.assertEqual(
            self.engine.pending_gil_decision_inbox(),
            (("same-id", '{"producer":"gil"}'),),
        )
        self.assertEqual(
            self.engine.pending_trading_decision_inbox(),
            (("same-id", '{"producer":"strategy-lab"}'),),
        )

    def test_unknown_status_returns_none(self) -> None:
        self.assertIsNone(self.engine.trading_decision_inbox_status("missing"))


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

    def test_reopening_engine_preserves_futures_margin_state(self) -> None:
        first = Experiment1Engine(self.db_path)
        intent = OrderIntent(
            intent_id="intent-1",
            created_at=NOW,
            account=AccountKind.FUTURES,
            action=DecisionAction.LONG,
            symbol="BTCUSDT",
            quantity=Decimal("10"),
            reason="verified setup",
            leverage=Decimal("2"),
        )
        first.submit_intent(intent)
        first.execute_pending(
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
        state_before = first.account_state(AccountKind.FUTURES)
        position_before = first.positions(AccountKind.FUTURES)[0]
        self.assertEqual(position_before.margin, Decimal("500"))
        self.assertEqual(state_before.used_margin, Decimal("500"))

        # Simulate a process restart: a fresh Engine instance over the same
        # db file must recompute (not fabricate or lose) the exact same
        # margin/used_margin/available_cash state.
        second = Experiment1Engine(self.db_path)
        state_after = second.account_state(AccountKind.FUTURES)
        position_after = second.positions(AccountKind.FUTURES)[0]
        self.assertEqual(state_after, state_before)
        self.assertEqual(position_after, position_before)

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
