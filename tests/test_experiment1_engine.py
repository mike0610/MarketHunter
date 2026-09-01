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
        self.assertEqual(
            self.engine.account_state(AccountKind.INVESTMENTS).cash,
            Decimal("5000"),
        )
        self.assertEqual(
            self.engine.account_state(AccountKind.SPOT).cash,
            Decimal("2000"),
        )
        self.assertEqual(
            self.engine.account_state(AccountKind.FUTURES).cash,
            Decimal("2000"),
        )

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


if __name__ == "__main__":
    unittest.main()
