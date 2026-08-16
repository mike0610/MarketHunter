"""
MarketHunter

Tests for AccountCapitalSnapshot and the pure Portfolio-side
capital-snapshot usability assessment.
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from models.account_capital_snapshot import (
    AccountCapitalSnapshot,
    CapitalSnapshotState,
)
from portfolio.capital_snapshot import (
    CapitalSnapshotUsability,
    assess_capital_snapshot,
)


def make_snapshot(
    *,
    state: CapitalSnapshotState = CapitalSnapshotState.AVAILABLE,
    source_authority: str | None = "prime-broker-authority",
    source_snapshot_id: str | None = "snap-1",
    source_revision: str | None = "rev-1",
    venue: str | None = "binance",
    account_id: str | None = "acct-1",
    subaccount_id: str | None = "sub-1",
    environment: str | None = "live",
    currency: str | None = "USD",
    as_of: datetime | None = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc),
    account_equity: Decimal | None = Decimal("10000.00"),
    cash: Decimal | None = Decimal("5000.00"),
    balance: Decimal | None = Decimal("10000.00"),
    margin_balance: Decimal | None = Decimal("2000.00"),
    buying_power: Decimal | None = Decimal("8000.00"),
    available_capital: Decimal | None = Decimal("4000.00"),
) -> AccountCapitalSnapshot:
    return AccountCapitalSnapshot(
        state=state,
        source_authority=source_authority,
        source_snapshot_id=source_snapshot_id,
        source_revision=source_revision,
        venue=venue,
        account_id=account_id,
        subaccount_id=subaccount_id,
        environment=environment,
        currency=currency,
        as_of=as_of,
        account_equity=account_equity,
        cash=cash,
        balance=balance,
        margin_balance=margin_balance,
        buying_power=buying_power,
        available_capital=available_capital,
    )


class CapitalSnapshotStateEnumTests(unittest.TestCase):
    def test_state_values(self) -> None:
        self.assertEqual(
            {member.value for member in CapitalSnapshotState},
            {"AVAILABLE", "UNKNOWN", "UNAVAILABLE", "STALE", "CONFLICT"},
        )

    def test_usability_values(self) -> None:
        self.assertEqual(
            {member.value for member in CapitalSnapshotUsability},
            {"USABLE", "UNKNOWN", "UNAVAILABLE", "STALE", "CONFLICT"},
        )


class AccountCapitalSnapshotTests(unittest.TestCase):
    def test_frozen(self) -> None:
        snapshot = make_snapshot()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.cash = Decimal("1")  # type: ignore[misc]

    def test_exact_field_preservation_no_derivation(self) -> None:
        snapshot = make_snapshot(
            account_equity=Decimal("10000.00"),
            cash=Decimal("5000.00"),
            balance=Decimal("10000.00"),
            margin_balance=Decimal("2000.00"),
            buying_power=Decimal("8000.00"),
            available_capital=Decimal("4000.00"),
        )

        self.assertEqual(snapshot.account_equity, Decimal("10000.00"))
        self.assertEqual(snapshot.cash, Decimal("5000.00"))
        self.assertEqual(snapshot.balance, Decimal("10000.00"))
        self.assertEqual(snapshot.margin_balance, Decimal("2000.00"))
        self.assertEqual(snapshot.buying_power, Decimal("8000.00"))
        self.assertEqual(snapshot.available_capital, Decimal("4000.00"))

    def test_negative_decimal_preserved(self) -> None:
        snapshot = make_snapshot(cash=Decimal("-250.50"))
        self.assertEqual(snapshot.cash, Decimal("-250.50"))

    def test_monetary_field_rejects_float(self) -> None:
        with self.assertRaises(TypeError):
            make_snapshot(cash=100.0)  # type: ignore[arg-type]

    def test_monetary_field_rejects_int(self) -> None:
        with self.assertRaises(TypeError):
            make_snapshot(cash=100)  # type: ignore[arg-type]

    def test_monetary_field_accepts_none(self) -> None:
        snapshot = make_snapshot(cash=None)
        self.assertIsNone(snapshot.cash)

    def test_aware_as_of_accepted(self) -> None:
        snapshot = make_snapshot(
            as_of=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        )
        self.assertIsNotNone(snapshot.as_of)

    def test_naive_as_of_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_snapshot(as_of=datetime(2026, 8, 15, 12, 0))

    def test_as_of_none_accepted(self) -> None:
        snapshot = make_snapshot(as_of=None)
        self.assertIsNone(snapshot.as_of)

    def test_no_account_size_or_notional_or_allocated_capital_fields(self) -> None:
        field_names = {f.name for f in dataclasses.fields(AccountCapitalSnapshot)}
        self.assertNotIn("account_size", field_names)
        self.assertNotIn("notional", field_names)
        self.assertNotIn("allocated_capital", field_names)
        self.assertNotIn("base_currency", field_names)
        self.assertNotIn("fx_rate", field_names)


class AssessCapitalSnapshotTests(unittest.TestCase):
    def test_unknown_state_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(state=CapitalSnapshotState.UNKNOWN)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_unavailable_state_maps_to_unavailable(self) -> None:
        snapshot = make_snapshot(state=CapitalSnapshotState.UNAVAILABLE)
        self.assertEqual(
            assess_capital_snapshot(snapshot),
            CapitalSnapshotUsability.UNAVAILABLE,
        )

    def test_stale_state_maps_to_stale(self) -> None:
        snapshot = make_snapshot(state=CapitalSnapshotState.STALE)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.STALE
        )

    def test_conflict_state_maps_to_conflict(self) -> None:
        snapshot = make_snapshot(state=CapitalSnapshotState.CONFLICT)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.CONFLICT
        )

    def test_complete_available_maps_to_usable(self) -> None:
        snapshot = make_snapshot(state=CapitalSnapshotState.AVAILABLE)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.USABLE
        )

    def test_missing_source_authority_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(source_authority=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_blank_source_authority_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(source_authority="   ")
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_missing_source_snapshot_id_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(source_snapshot_id=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_missing_account_id_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(account_id=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_missing_environment_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(environment=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_missing_currency_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(currency=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_as_of_missing_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(as_of=None)
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_all_monetary_none_maps_to_unknown(self) -> None:
        snapshot = make_snapshot(
            account_equity=None,
            cash=None,
            balance=None,
            margin_balance=None,
            buying_power=None,
            available_capital=None,
        )
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.UNKNOWN
        )

    def test_single_monetary_fact_present_is_usable(self) -> None:
        snapshot = make_snapshot(
            account_equity=Decimal("1.00"),
            cash=None,
            balance=None,
            margin_balance=None,
            buying_power=None,
            available_capital=None,
        )
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.USABLE
        )

    def test_optional_source_revision_venue_subaccount_do_not_block_usability(
        self,
    ) -> None:
        snapshot = make_snapshot(
            source_revision=None, venue=None, subaccount_id=None
        )
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.USABLE
        )

    def test_stale_age_is_not_calculated(self) -> None:
        old_as_of = datetime(2000, 1, 1, tzinfo=timezone.utc)
        snapshot = make_snapshot(
            state=CapitalSnapshotState.AVAILABLE, as_of=old_as_of
        )
        self.assertEqual(
            assess_capital_snapshot(snapshot), CapitalSnapshotUsability.USABLE
        )

    def test_rejects_non_snapshot_type(self) -> None:
        with self.assertRaises(TypeError):
            assess_capital_snapshot("not-a-snapshot")  # type: ignore[arg-type]

    def test_rejects_duck_typed_object(self) -> None:
        class FakeSnapshot:
            state = CapitalSnapshotState.AVAILABLE
            source_authority = "a"
            source_snapshot_id = "b"
            account_id = "c"
            environment = "d"
            currency = "e"
            as_of = datetime(2026, 8, 15, tzinfo=timezone.utc)
            account_equity = Decimal("1")
            cash = None
            balance = None
            margin_balance = None
            buying_power = None
            available_capital = None

        with self.assertRaises(TypeError):
            assess_capital_snapshot(FakeSnapshot())  # type: ignore[arg-type]

    def test_assessment_does_not_mutate_input(self) -> None:
        snapshot = make_snapshot()
        before = dataclasses.astuple(snapshot)

        assess_capital_snapshot(snapshot)

        after = dataclasses.astuple(snapshot)
        self.assertEqual(before, after)

    def test_no_fx_or_base_currency_output(self) -> None:
        result = assess_capital_snapshot(make_snapshot())
        self.assertIsInstance(result, CapitalSnapshotUsability)


if __name__ == "__main__":
    unittest.main()
