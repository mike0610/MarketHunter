"""
MarketHunter

Tests for CORE-GAP-04 Time Semantics - Slice 1
(time_semantics/foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from time_semantics.foundation import (
    LineageRelation,
    TemporalAssessment,
    TemporalAssessmentReason,
    TemporalDisposition,
    TemporalFact,
    TemporalReference,
    TemporalRelation,
    TemporalRole,
    assess_temporal_relation,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
AWARE_LATER = datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc)


def make_reference(**overrides) -> TemporalReference:
    kwargs = dict(
        reference_kind="risk_result",
        reference_id="risk-1",
        revision_or_version="1",
    )
    kwargs.update(overrides)
    return TemporalReference(**kwargs)


def make_fact(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=make_reference(),
        role=TemporalRole.EVENT_TIME,
        timestamp=AWARE_NOW,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_role_values(self) -> None:
        self.assertEqual(
            {m.value for m in TemporalRole},
            {"EVENT_TIME", "OBSERVED_TIME", "RECORDED_TIME", "LINEAGE_ORDER"},
        )

    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in TemporalDisposition},
            {"KNOWN", "UNKNOWN", "UNAVAILABLE", "CONFLICT"},
        )

    def test_relation_values(self) -> None:
        self.assertEqual(
            {m.value for m in TemporalRelation},
            {"BEFORE", "AFTER", "EQUAL", "UNKNOWN", "CONFLICT", "NOT_COMPARABLE"},
        )


class TemporalReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.reference_id = "other"  # type: ignore[misc]

    def test_blank_reference_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reference(reference_id="   ")

    def test_optional_revision_none_accepted(self) -> None:
        reference = make_reference(revision_or_version=None)
        self.assertIsNone(reference.revision_or_version)

    def test_blank_optional_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reference(revision_or_version="  ")


class TemporalFactTests(unittest.TestCase):
    def test_frozen(self) -> None:
        fact = make_fact()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fact.timestamp = AWARE_LATER  # type: ignore[misc]

    def test_known_clock_fact_requires_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(disposition=TemporalDisposition.KNOWN, timestamp=None)

    def test_known_clock_fact_requires_aware_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                disposition=TemporalDisposition.KNOWN,
                timestamp=datetime(2026, 8, 16, 12, 0),
            )

    def test_unknown_disposition_forbids_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                disposition=TemporalDisposition.UNKNOWN, timestamp=AWARE_NOW
            )

    def test_unavailable_disposition_accepts_null_timestamp(self) -> None:
        fact = make_fact(
            disposition=TemporalDisposition.UNAVAILABLE, timestamp=None
        )
        self.assertIsNone(fact.timestamp)

    def test_conflict_disposition_forbids_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                disposition=TemporalDisposition.CONFLICT, timestamp=AWARE_NOW
            )

    def test_lineage_order_role_forbids_timestamp_even_when_known(self) -> None:
        with self.assertRaises(ValueError):
            make_fact(
                role=TemporalRole.LINEAGE_ORDER,
                disposition=TemporalDisposition.KNOWN,
                timestamp=AWARE_NOW,
            )

    def test_lineage_order_role_accepts_null_timestamp(self) -> None:
        fact = make_fact(
            role=TemporalRole.LINEAGE_ORDER,
            disposition=TemporalDisposition.KNOWN,
            timestamp=None,
        )
        self.assertIsNone(fact.timestamp)
        self.assertEqual(fact.role, TemporalRole.LINEAGE_ORDER)


class LineageRelationTests(unittest.TestCase):
    def test_frozen(self) -> None:
        relation = LineageRelation(make_reference(), make_reference(reference_id="risk-2"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            relation.predecessor = make_reference()  # type: ignore[misc]

    def test_cannot_self_reference(self) -> None:
        reference = make_reference()
        with self.assertRaises(ValueError):
            LineageRelation(reference, reference)

    def test_wrong_predecessor_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            LineageRelation("not-a-reference", make_reference())  # type: ignore[arg-type]


class TemporalAssessmentTests(unittest.TestCase):
    def test_requires_at_least_one_reason(self) -> None:
        with self.assertRaises(ValueError):
            TemporalAssessment(relation=TemporalRelation.EQUAL, reasons=())

    def test_frozen(self) -> None:
        assessment = TemporalAssessment(
            relation=TemporalRelation.EQUAL,
            reasons=(TemporalAssessmentReason.SAME_ROLE_CLOCK_COMPARISON,),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            assessment.relation = TemporalRelation.BEFORE  # type: ignore[misc]


class AssessTemporalRelationTests(unittest.TestCase):
    def test_same_role_before(self) -> None:
        left = make_fact(timestamp=AWARE_NOW)
        right = make_fact(timestamp=AWARE_LATER)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.BEFORE)
        self.assertIn(
            TemporalAssessmentReason.SAME_ROLE_CLOCK_COMPARISON, result.reasons
        )

    def test_same_role_after(self) -> None:
        left = make_fact(timestamp=AWARE_LATER)
        right = make_fact(timestamp=AWARE_NOW)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.AFTER)

    def test_same_role_equal(self) -> None:
        left = make_fact(timestamp=AWARE_NOW)
        right = make_fact(timestamp=AWARE_NOW)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.EQUAL)

    def test_equal_instants_across_different_utc_offsets(self) -> None:
        # 12:00 UTC == 14:00 at UTC+2 - same absolute instant.
        offset_tz = timezone(timedelta(hours=2))
        left = make_fact(timestamp=AWARE_NOW)
        right = make_fact(
            timestamp=datetime(2026, 8, 16, 14, 0, tzinfo=offset_tz)
        )

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.EQUAL)

    def test_cross_role_not_comparable(self) -> None:
        left = make_fact(role=TemporalRole.EVENT_TIME, timestamp=AWARE_LATER)
        right = make_fact(
            role=TemporalRole.OBSERVED_TIME, timestamp=AWARE_NOW
        )

        # Even though left's timestamp is objectively later, different
        # roles must never be compared - out-of-order observation
        # cannot establish event order, and this module refuses to
        # try.
        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.NOT_COMPARABLE)
        self.assertIn(TemporalAssessmentReason.ROLE_MISMATCH, result.reasons)

    def test_lineage_order_role_never_compared_as_clock(self) -> None:
        left = make_fact(
            role=TemporalRole.LINEAGE_ORDER,
            disposition=TemporalDisposition.KNOWN,
            timestamp=None,
        )
        right = make_fact(
            role=TemporalRole.LINEAGE_ORDER,
            disposition=TemporalDisposition.KNOWN,
            timestamp=None,
        )

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.NOT_COMPARABLE)
        self.assertIn(
            TemporalAssessmentReason.LINEAGE_ORDER_NOT_COMPARABLE,
            result.reasons,
        )

    def test_unknown_disposition_fails_closed(self) -> None:
        left = make_fact(
            disposition=TemporalDisposition.UNKNOWN, timestamp=None
        )
        right = make_fact(timestamp=AWARE_NOW)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.UNKNOWN)
        self.assertIn(
            TemporalAssessmentReason.FACT_UNKNOWN_OR_UNAVAILABLE,
            result.reasons,
        )

    def test_unavailable_disposition_fails_closed(self) -> None:
        left = make_fact(
            disposition=TemporalDisposition.UNAVAILABLE, timestamp=None
        )
        right = make_fact(timestamp=AWARE_NOW)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.UNKNOWN)

    def test_conflict_disposition_stays_conflict(self) -> None:
        left = make_fact(
            disposition=TemporalDisposition.CONFLICT, timestamp=None
        )
        right = make_fact(timestamp=AWARE_NOW)

        result = assess_temporal_relation(left, right)
        self.assertEqual(result.relation, TemporalRelation.CONFLICT)
        self.assertIn(
            TemporalAssessmentReason.FACT_CONFLICT, result.reasons
        )

    def test_direct_lineage_precedence_before(self) -> None:
        left_ref = make_reference(reference_id="a")
        right_ref = make_reference(reference_id="b")
        left = make_fact(reference=left_ref, timestamp=AWARE_LATER)
        right = make_fact(reference=right_ref, timestamp=AWARE_NOW)

        # Timestamps alone would say left is AFTER right, but explicit
        # lineage says left precedes right - lineage wins.
        result = assess_temporal_relation(
            left, right, (LineageRelation(left_ref, right_ref),)
        )
        self.assertEqual(result.relation, TemporalRelation.BEFORE)
        self.assertIn(
            TemporalAssessmentReason.DIRECT_LINEAGE_PRECEDENCE, result.reasons
        )

    def test_direct_lineage_precedence_after(self) -> None:
        left_ref = make_reference(reference_id="a")
        right_ref = make_reference(reference_id="b")
        left = make_fact(reference=left_ref, timestamp=AWARE_NOW)
        right = make_fact(reference=right_ref, timestamp=AWARE_LATER)

        result = assess_temporal_relation(
            left, right, (LineageRelation(right_ref, left_ref),)
        )
        self.assertEqual(result.relation, TemporalRelation.AFTER)

    def test_contradictory_lineage_is_conflict(self) -> None:
        left_ref = make_reference(reference_id="a")
        right_ref = make_reference(reference_id="b")
        left = make_fact(reference=left_ref, timestamp=AWARE_NOW)
        right = make_fact(reference=right_ref, timestamp=AWARE_LATER)

        result = assess_temporal_relation(
            left,
            right,
            (
                LineageRelation(left_ref, right_ref),
                LineageRelation(right_ref, left_ref),
            ),
        )
        self.assertEqual(result.relation, TemporalRelation.CONFLICT)
        self.assertIn(
            TemporalAssessmentReason.LINEAGE_CONTRADICTION, result.reasons
        )

    def test_timestamps_never_infer_lineage(self) -> None:
        # No lineage_relations supplied at all - even with a clear
        # timestamp ordering, no BEFORE/AFTER is invented as lineage;
        # the same-role clock comparison is used, which is a
        # different (non-lineage) reason.
        left_ref = make_reference(reference_id="a")
        right_ref = make_reference(reference_id="b")
        left = make_fact(reference=left_ref, timestamp=AWARE_NOW)
        right = make_fact(reference=right_ref, timestamp=AWARE_LATER)

        result = assess_temporal_relation(left, right, ())
        self.assertEqual(result.relation, TemporalRelation.BEFORE)
        self.assertNotIn(
            TemporalAssessmentReason.DIRECT_LINEAGE_PRECEDENCE, result.reasons
        )
        self.assertIn(
            TemporalAssessmentReason.SAME_ROLE_CLOCK_COMPARISON, result.reasons
        )

    def test_deterministic_replay(self) -> None:
        left = make_fact(timestamp=AWARE_NOW)
        right = make_fact(timestamp=AWARE_LATER)

        first = assess_temporal_relation(left, right)
        second = assess_temporal_relation(left, right)
        self.assertEqual(first.relation, second.relation)
        self.assertEqual(first.reasons, second.reasons)

    def test_assessment_does_not_mutate_inputs(self) -> None:
        left = make_fact(timestamp=AWARE_NOW)
        right = make_fact(timestamp=AWARE_LATER)
        left_before = dataclasses.astuple(left)
        right_before = dataclasses.astuple(right)

        assess_temporal_relation(left, right)

        self.assertEqual(left_before, dataclasses.astuple(left))
        self.assertEqual(right_before, dataclasses.astuple(right))

    def test_wrong_left_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_temporal_relation("not-a-fact", make_fact())  # type: ignore[arg-type]

    def test_wrong_lineage_relations_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_temporal_relation(
                make_fact(), make_fact(), [LineageRelation(make_reference(), make_reference(reference_id="x"))]  # type: ignore[arg-type]
            )


class ScopeDisciplineTests(unittest.TestCase):
    def _imported_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import time_semantics.foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)

        return imported

    def _referenced_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import time_semantics.foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = ("__future__", "dataclasses", "datetime", "enum")
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_no_source_domain_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "StrategyIdentity",
            "RiskSizingProposal",
            "RiskResultRecord",
            "PortfolioDecision",
            "ExplanationRecord",
            "ResearchTrade",
            "ExecutionOrder",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_wall_clock_random_db_or_network_usage(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("utcnow", referenced)
        self.assertNotIn("uuid4", referenced)

        imported = self._imported_names()
        for forbidden in (
            "sqlite3",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "fastapi",
            "httpx",
            "socket",
            "ntplib",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_max_latest_or_current_selector_exported(self) -> None:
        import time_semantics.foundation as module

        self.assertFalse(hasattr(module, "latest"))
        self.assertFalse(hasattr(module, "current"))
        self.assertFalse(hasattr(module, "max_timestamp"))
        self.assertFalse(hasattr(module, "get_current"))


if __name__ == "__main__":
    unittest.main()
