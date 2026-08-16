"""
MarketHunter

Tests for the Unified TOP Foundation - Slice 1
(models/execution_foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from models.execution_foundation import (
    ExecutionFact,
    ExecutionOrder,
    PositionProvenance,
    RelationshipAssessment,
    RelationshipDisposition,
    RelationshipReason,
    RelationshipUsability,
    assess_position_provenance,
)
from models.risk_result_record import IdentityState

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def make_order(**overrides) -> ExecutionOrder:
    kwargs = dict(
        execution_order_id="order-1",
        revision=1,
        observed_at=AWARE_NOW,
        supersedes_revision=None,
        venue_reference_kind="exchange",
        venue_reference="binance",
        source_reference_kind="venue_order_id",
        source_reference="venue-order-1",
        account_reference_kind="account",
        account_reference="acct-1",
        instrument_reference_kind="symbol",
        instrument_reference="BTCUSDT",
        order_intent_state=IdentityState.KNOWN,
        order_intent_id="intent-1",
        order_intent_version="1.0.0",
        order_intent_reference="intent-ref-1",
    )
    kwargs.update(overrides)
    return ExecutionOrder(**kwargs)


def make_fact(**overrides) -> ExecutionFact:
    kwargs = dict(
        execution_fact_id="fact-1",
        fact_kind="fill",
        fact_at=AWARE_NOW,
        venue_reference_kind="exchange",
        venue_reference="binance",
        source_reference_kind="venue_fill_id",
        source_reference="venue-fill-1",
        execution_order_state=IdentityState.KNOWN,
        execution_order_id="order-1",
        execution_order_revision=1,
    )
    kwargs.update(overrides)
    return ExecutionFact(**kwargs)


def make_position(**overrides) -> PositionProvenance:
    kwargs = dict(
        position_id="position-1",
        revision=1,
        observed_at=AWARE_NOW,
        supersedes_revision=None,
        account_reference_kind="account",
        account_reference="acct-1",
        instrument_reference_kind="symbol",
        instrument_reference="BTCUSDT",
        execution_fact_ids=("fact-1",),
    )
    kwargs.update(overrides)
    return PositionProvenance(**kwargs)


class ExecutionOrderTests(unittest.TestCase):
    def test_frozen(self) -> None:
        order = make_order()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            order.revision = 2  # type: ignore[misc]

    def test_blank_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_order(execution_order_id="   ")

    def test_non_positive_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_order(revision=0)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_order(revision=True)  # type: ignore[arg-type]

    def test_naive_observed_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_order(observed_at=datetime(2026, 8, 16, 12, 0))

    def test_valid_supersession_accepted(self) -> None:
        order = make_order(revision=2, supersedes_revision=1)
        self.assertEqual(order.supersedes_revision, 1)

    def test_supersedes_revision_not_less_than_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_order(revision=2, supersedes_revision=2)

    def test_supersession_never_inferred_stays_none(self) -> None:
        order = make_order(revision=1, supersedes_revision=None)
        self.assertIsNone(order.supersedes_revision)

    def test_exact_venue_source_account_instrument_provenance(self) -> None:
        order = make_order(
            venue_reference_kind="exchange",
            venue_reference="coinbase",
            source_reference_kind="venue_order_id",
            source_reference="cb-order-9",
            account_reference_kind="account",
            account_reference="acct-9",
            instrument_reference_kind="symbol",
            instrument_reference="ETHUSDT",
        )
        self.assertEqual(order.venue_reference, "coinbase")
        self.assertEqual(order.source_reference, "cb-order-9")
        self.assertEqual(order.account_reference, "acct-9")
        self.assertEqual(order.instrument_reference, "ETHUSDT")

    def test_known_order_intent_requires_all_fields(self) -> None:
        with self.assertRaises(ValueError):
            make_order(
                order_intent_state=IdentityState.KNOWN,
                order_intent_id=None,
                order_intent_version=None,
                order_intent_reference=None,
            )

    def test_unknown_order_intent_requires_all_null(self) -> None:
        order = make_order(
            order_intent_state=IdentityState.UNKNOWN,
            order_intent_id=None,
            order_intent_version=None,
            order_intent_reference=None,
        )
        self.assertIsNone(order.order_intent_id)

    def test_unknown_order_intent_with_value_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_order(
                order_intent_state=IdentityState.UNKNOWN,
                order_intent_id="intent-1",
                order_intent_version=None,
                order_intent_reference=None,
            )

    def test_order_intent_reference_distinct_from_execution_order_id(
        self,
    ) -> None:
        # OrderIntent ref != ExecutionOrder identity: they are
        # separate fields carrying separate identities.
        order = make_order(
            execution_order_id="order-1", order_intent_id="intent-1"
        )
        self.assertNotEqual(order.execution_order_id, order.order_intent_id)


class ExecutionFactTests(unittest.TestCase):
    def test_frozen(self) -> None:
        fact = make_fact()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fact.fact_kind = "cancel"  # type: ignore[misc]

    def test_blank_fact_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(execution_fact_id="")

    def test_naive_fact_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(fact_at=datetime(2026, 8, 16, 12, 0))

    def test_known_execution_order_requires_id_and_revision(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                execution_order_state=IdentityState.KNOWN,
                execution_order_id=None,
                execution_order_revision=None,
            )

    def test_unknown_execution_order_requires_null(self) -> None:
        fact = make_fact(
            execution_order_state=IdentityState.UNKNOWN,
            execution_order_id=None,
            execution_order_revision=None,
        )
        self.assertIsNone(fact.execution_order_id)
        self.assertIsNone(fact.execution_order_revision)

    def test_unknown_execution_order_with_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                execution_order_state=IdentityState.UNKNOWN,
                execution_order_id="order-1",
                execution_order_revision=None,
            )

    def test_non_positive_execution_order_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(execution_order_revision=0)

    def test_history_immutable_object_unchanged(self) -> None:
        fact = make_fact()
        before = dataclasses.astuple(fact)
        # Simulate downstream processing that must not rewrite history.
        _ = assess_position_provenance(
            make_position(execution_fact_ids=(fact.execution_fact_id,)),
            (make_order(),),
            (fact,),
            RelationshipDisposition.CURRENT,
        )
        after = dataclasses.astuple(fact)
        self.assertEqual(before, after)


class PositionProvenanceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        position = make_position()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            position.revision = 2  # type: ignore[misc]

    def test_empty_execution_fact_ids_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_position(execution_fact_ids=())

    def test_execution_fact_ids_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_position(execution_fact_ids=["fact-1"])  # type: ignore[arg-type]

    def test_contains_provenance_only_no_economic_fields(self) -> None:
        field_names = {f.name for f in dataclasses.fields(PositionProvenance)}
        for forbidden in (
            "quantity",
            "lots",
            "average_price",
            "realized_pnl",
            "unrealized_pnl",
            "net_quantity",
            "open",
            "close",
            "hedge",
        ):
            self.assertNotIn(forbidden, field_names)


class RelationshipAssessmentTests(unittest.TestCase):
    def test_usable_cannot_carry_reasons(self) -> None:
        with self.assertRaises(ValueError):
            RelationshipAssessment(
                usability=RelationshipUsability.USABLE,
                disposition=RelationshipDisposition.CURRENT,
                reasons=(RelationshipReason.MISSING_FACT_REFERENCE,),
            )

    def test_not_usable_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            RelationshipAssessment(
                usability=RelationshipUsability.NOT_USABLE,
                disposition=RelationshipDisposition.CURRENT,
                reasons=(),
            )


class AssessPositionProvenanceTests(unittest.TestCase):
    def test_exact_current_chain_is_usable(self) -> None:
        result = assess_position_provenance(
            make_position(),
            (make_order(),),
            (make_fact(),),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.USABLE)
        self.assertEqual(result.reasons, ())

    def test_multiple_orders_may_contribute(self) -> None:
        order_a = make_order(execution_order_id="order-a", revision=1)
        order_b = make_order(execution_order_id="order-b", revision=1)
        fact_a = make_fact(
            execution_fact_id="fact-a",
            execution_order_id="order-a",
            execution_order_revision=1,
        )
        fact_b = make_fact(
            execution_fact_id="fact-b",
            execution_order_id="order-b",
            execution_order_revision=1,
        )
        position = make_position(execution_fact_ids=("fact-a", "fact-b"))

        result = assess_position_provenance(
            position,
            (order_a, order_b),
            (fact_a, fact_b),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.USABLE)

    def test_non_current_disposition_fails_closed(self) -> None:
        for disposition in (
            RelationshipDisposition.UNKNOWN,
            RelationshipDisposition.UNAVAILABLE,
            RelationshipDisposition.CONFLICT,
            RelationshipDisposition.SUPERSEDED,
            RelationshipDisposition.SOURCE_CHANGED,
        ):
            with self.subTest(disposition=disposition):
                result = assess_position_provenance(
                    make_position(),
                    (make_order(),),
                    (make_fact(),),
                    disposition,
                )
                self.assertEqual(
                    result.usability, RelationshipUsability.NOT_USABLE
                )
                self.assertIn(
                    RelationshipReason.DISPOSITION_NOT_CURRENT,
                    result.reasons,
                )

    def test_missing_fact_reference_fails_closed(self) -> None:
        position = make_position(execution_fact_ids=("missing-fact",))
        result = assess_position_provenance(
            position, (make_order(),), (make_fact(),), RelationshipDisposition.CURRENT
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.MISSING_FACT_REFERENCE, result.reasons
        )

    def test_duplicate_fact_reference_fails_closed(self) -> None:
        fact_1 = make_fact(execution_fact_id="fact-1", source_reference="a")
        fact_2 = make_fact(execution_fact_id="fact-1", source_reference="b")
        result = assess_position_provenance(
            make_position(execution_fact_ids=("fact-1",)),
            (make_order(),),
            (fact_1, fact_2),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.DUPLICATE_FACT_REFERENCE, result.reasons
        )

    def test_unknown_order_reference_fails_closed(self) -> None:
        fact = make_fact(
            execution_order_state=IdentityState.UNKNOWN,
            execution_order_id=None,
            execution_order_revision=None,
        )
        result = assess_position_provenance(
            make_position(execution_fact_ids=(fact.execution_fact_id,)),
            (make_order(),),
            (fact,),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.EXECUTION_ORDER_REFERENCE_UNKNOWN,
            result.reasons,
        )

    def test_unresolved_order_reference_fails_closed(self) -> None:
        fact = make_fact(
            execution_order_id="order-does-not-exist",
            execution_order_revision=1,
        )
        result = assess_position_provenance(
            make_position(execution_fact_ids=(fact.execution_fact_id,)),
            (make_order(),),
            (fact,),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.EXECUTION_ORDER_REFERENCE_UNRESOLVED,
            result.reasons,
        )

    def test_order_revision_mismatch_fails_closed(self) -> None:
        fact = make_fact(
            execution_order_id="order-1", execution_order_revision=2
        )
        result = assess_position_provenance(
            make_position(execution_fact_ids=(fact.execution_fact_id,)),
            (make_order(execution_order_id="order-1", revision=1),),
            (fact,),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.ORDER_REVISION_MISMATCH, result.reasons
        )

    def test_account_scope_mismatch_fails_closed(self) -> None:
        order = make_order(account_reference="acct-other")
        result = assess_position_provenance(
            make_position(account_reference="acct-1"),
            (order,),
            (make_fact(),),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.ACCOUNT_SCOPE_MISMATCH, result.reasons
        )

    def test_instrument_scope_mismatch_fails_closed(self) -> None:
        order = make_order(instrument_reference="ETHUSDT")
        result = assess_position_provenance(
            make_position(instrument_reference="BTCUSDT"),
            (order,),
            (make_fact(),),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.INSTRUMENT_SCOPE_MISMATCH, result.reasons
        )

    def test_duplicate_order_key_fails_closed(self) -> None:
        order_1 = make_order(source_reference="venue-order-1a")
        order_2 = make_order(source_reference="venue-order-1b")
        result = assess_position_provenance(
            make_position(),
            (order_1, order_2),
            (make_fact(),),
            RelationshipDisposition.CURRENT,
        )
        self.assertEqual(result.usability, RelationshipUsability.NOT_USABLE)
        self.assertIn(
            RelationshipReason.AMBIGUOUS_REFERENCE, result.reasons
        )

    def test_wrong_position_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_position_provenance(
                "not-a-position",  # type: ignore[arg-type]
                (make_order(),),
                (make_fact(),),
                RelationshipDisposition.CURRENT,
            )

    def test_wrong_orders_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_position_provenance(
                make_position(),
                [make_order()],  # type: ignore[arg-type]
                (make_fact(),),
                RelationshipDisposition.CURRENT,
            )

    def test_wrong_facts_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_position_provenance(
                make_position(),
                (make_order(),),
                [make_fact()],  # type: ignore[arg-type]
                RelationshipDisposition.CURRENT,
            )

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_position_provenance(
                make_position(),
                (make_order(),),
                (make_fact(),),
                "CURRENT",  # type: ignore[arg-type]
            )

    def test_assessment_does_not_mutate_inputs(self) -> None:
        position = make_position()
        order = make_order()
        fact = make_fact()

        position_before = dataclasses.astuple(position)
        order_before = dataclasses.astuple(order)
        fact_before = dataclasses.astuple(fact)

        assess_position_provenance(
            position, (order,), (fact,), RelationshipDisposition.CURRENT
        )

        self.assertEqual(position_before, dataclasses.astuple(position))
        self.assertEqual(order_before, dataclasses.astuple(order))
        self.assertEqual(fact_before, dataclasses.astuple(fact))


class ScopeDisciplineTests(unittest.TestCase):
    def test_no_legacy_trade_order_or_result_import(self) -> None:
        import ast
        from pathlib import Path

        import models.execution_foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.name)
                if node.module:
                    imported_names.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name)

        self.assertNotIn("models.trade_order", imported_names)
        self.assertNotIn("models.trade_result", imported_names)
        self.assertNotIn("TradeOrder", imported_names)
        self.assertNotIn("TradeResult", imported_names)
        self.assertFalse(any(name.startswith("execution.") for name in imported_names))

    def test_no_research_trade_reference(self) -> None:
        import ast
        from pathlib import Path

        import models.execution_foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names_referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self.assertNotIn("ResearchTrade", names_referenced)

    def test_no_persistence_or_db_imports(self) -> None:
        import ast
        from pathlib import Path

        import models.execution_foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_names: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module_name = getattr(node, "module", None)
                if module_name:
                    imported_names.add(module_name)
                for alias in node.names:
                    imported_names.add(alias.name)

        for forbidden in ("sqlite3", "requests", "fastapi", "httpx"):
            self.assertNotIn(forbidden, imported_names)


if __name__ == "__main__":
    unittest.main()
