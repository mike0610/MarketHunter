"""
MarketHunter

Tests for CORE-GAP-03 Audit / Read-Model - Slice 1
(audit_read_model/foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from audit_read_model.foundation import (
    AuditCompositionAssessment,
    AuditCompositionRecord,
    AuditCompositionReason,
    AuditCompositionUsability,
    AuditProjectionItem,
    AuditProjectionReference,
    AuditSourceBinding,
    AuditSourceDisposition,
    AuditSourceReference,
    AuditTemporalPair,
    AuditTemporalPairAssessment,
    compose_audit_projection,
)
from time_semantics.foundation import (
    LineageRelation,
    TemporalAssessmentReason,
    TemporalDisposition,
    TemporalFact,
    TemporalReference,
    TemporalRelation,
    TemporalRole,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
AWARE_LATER = datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc)


def make_source_reference(**overrides) -> AuditSourceReference:
    kwargs = dict(
        source_domain="risk",
        source_type="RiskResultRecord",
        source_id="risk-1",
        revision_or_version="1",
    )
    kwargs.update(overrides)
    return AuditSourceReference(**kwargs)


def make_projection_reference(**overrides) -> AuditProjectionReference:
    kwargs = dict(projection_id="proj-1", revision=1)
    kwargs.update(overrides)
    return AuditProjectionReference(**kwargs)


def make_temporal_reference(**overrides) -> TemporalReference:
    kwargs = dict(
        reference_kind="risk_result",
        reference_id="risk-1",
        revision_or_version="1",
    )
    kwargs.update(overrides)
    return TemporalReference(**kwargs)


def make_temporal_fact(**overrides) -> TemporalFact:
    kwargs = dict(
        reference=make_temporal_reference(),
        role=TemporalRole.EVENT_TIME,
        timestamp=AWARE_NOW,
        disposition=TemporalDisposition.KNOWN,
    )
    kwargs.update(overrides)
    return TemporalFact(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in AuditSourceDisposition},
            {
                "CURRENT",
                "UNKNOWN",
                "UNAVAILABLE",
                "STALE",
                "CONFLICT",
                "SUPERSEDED",
                "SOURCE_CHANGED",
            },
        )

    def test_usability_values(self) -> None:
        self.assertEqual(
            {m.value for m in AuditCompositionUsability},
            {"USABLE", "NOT_USABLE"},
        )

    def test_reason_values(self) -> None:
        self.assertEqual(
            {m.value for m in AuditCompositionReason},
            {
                "SOURCE_UNRESOLVED",
                "SOURCE_AMBIGUOUS",
                "SOURCE_DISPOSITION_NOT_USABLE",
                "SOURCE_CURRENT_REQUIRED",
                "TEMPORAL_SOURCE_NOT_IN_COMPOSITION",
                "TEMPORAL_ORDER_REQUIRED_BUT_MISSING",
                "TEMPORAL_RELATION_UNKNOWN",
                "TEMPORAL_RELATION_CONFLICT",
                "TEMPORAL_RELATION_NOT_COMPARABLE",
            },
        )


class AuditSourceReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_source_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.source_id = "other"  # type: ignore[misc]

    def test_blank_source_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_source_reference(source_id="   ")

    def test_blank_source_domain_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_source_reference(source_domain="")

    def test_optional_revision_none_accepted(self) -> None:
        reference = make_source_reference(revision_or_version=None)
        self.assertIsNone(reference.revision_or_version)

    def test_blank_optional_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_source_reference(revision_or_version="  ")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_source_reference(source_id=123)  # type: ignore[arg-type]

    def test_equality_is_by_value(self) -> None:
        self.assertEqual(make_source_reference(), make_source_reference())

    def test_distinct_ids_are_not_equal(self) -> None:
        self.assertNotEqual(
            make_source_reference(source_id="risk-1"),
            make_source_reference(source_id="risk-2"),
        )


class AuditSourceBindingTests(unittest.TestCase):
    def test_frozen(self) -> None:
        binding = AuditSourceBinding(
            reference=make_source_reference(),
            disposition=AuditSourceDisposition.CURRENT,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.disposition = AuditSourceDisposition.STALE  # type: ignore[misc]

    def test_wrong_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditSourceBinding(
                reference="not-a-reference",  # type: ignore[arg-type]
                disposition=AuditSourceDisposition.CURRENT,
            )

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditSourceBinding(
                reference=make_source_reference(),
                disposition="CURRENT",  # type: ignore[arg-type]
            )


class AuditProjectionReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_projection_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.revision = 2  # type: ignore[misc]

    def test_blank_projection_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_projection_reference(projection_id="  ")

    def test_zero_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_projection_reference(revision=0)

    def test_negative_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_projection_reference(revision=-1)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_projection_reference(revision=True)  # type: ignore[arg-type]

    def test_non_int_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_projection_reference(revision="1")  # type: ignore[arg-type]


class AuditCompositionRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(make_source_reference(),),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.source_references = ()  # type: ignore[misc]

    def test_empty_source_references_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AuditCompositionRecord(
                projection=make_projection_reference(),
                source_references=(),
            )

    def test_wrong_projection_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditCompositionRecord(
                projection="not-a-projection",  # type: ignore[arg-type]
                source_references=(make_source_reference(),),
            )

    def test_wrong_source_references_element_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditCompositionRecord(
                projection=make_projection_reference(),
                source_references=("not-a-reference",),  # type: ignore[arg-type]
            )

    def test_exact_duplicate_source_reference_rejected(self) -> None:
        reference = make_source_reference()
        with self.assertRaises(ValueError):
            AuditCompositionRecord(
                projection=make_projection_reference(),
                source_references=(reference, reference),
            )

    def test_distinct_source_identities_never_deduped(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(
                make_source_reference(source_id="risk-1"),
                make_source_reference(source_id="risk-2"),
            ),
        )
        self.assertEqual(len(record.source_references), 2)


class AuditTemporalPairTests(unittest.TestCase):
    def test_frozen(self) -> None:
        pair = AuditTemporalPair(
            left_source_reference=make_source_reference(source_id="a"),
            left_fact=make_temporal_fact(),
            right_source_reference=make_source_reference(source_id="b"),
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            pair.left_fact = make_temporal_fact()  # type: ignore[misc]

    def test_wrong_left_source_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditTemporalPair(
                left_source_reference="not-a-reference",  # type: ignore[arg-type]
                left_fact=make_temporal_fact(),
                right_source_reference=make_source_reference(source_id="b"),
                right_fact=make_temporal_fact(timestamp=AWARE_LATER),
            )

    def test_wrong_left_fact_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditTemporalPair(
                left_source_reference=make_source_reference(source_id="a"),
                left_fact="not-a-fact",  # type: ignore[arg-type]
                right_source_reference=make_source_reference(source_id="b"),
                right_fact=make_temporal_fact(timestamp=AWARE_LATER),
            )

    def test_explicit_mapping_never_cross_validated(self) -> None:
        # The source reference's identity fields and the fact's own
        # TemporalReference are deliberately unrelated - this module
        # never infers or checks that they "match" by name; the pair
        # is accepted exactly as the caller explicitly supplied it.
        pair = AuditTemporalPair(
            left_source_reference=make_source_reference(source_id="risk-1"),
            left_fact=make_temporal_fact(
                reference=make_temporal_reference(reference_id="totally-different")
            ),
            right_source_reference=make_source_reference(source_id="risk-2"),
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )
        self.assertEqual(pair.left_source_reference.source_id, "risk-1")
        self.assertEqual(pair.left_fact.reference.reference_id, "totally-different")


class AuditProjectionItemTests(unittest.TestCase):
    def test_frozen(self) -> None:
        item = AuditProjectionItem(
            source_reference=make_source_reference(),
            disposition=AuditSourceDisposition.CURRENT,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            item.disposition = AuditSourceDisposition.STALE  # type: ignore[misc]

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditProjectionItem(
                source_reference=make_source_reference(),
                disposition="CURRENT",  # type: ignore[arg-type]
            )


class AuditTemporalPairAssessmentTests(unittest.TestCase):
    def test_wrong_pair_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditTemporalPairAssessment(
                pair="not-a-pair",  # type: ignore[arg-type]
                assessment=None,  # type: ignore[arg-type]
            )


class AuditCompositionAssessmentTests(unittest.TestCase):
    def test_not_usable_requires_at_least_one_reason(self) -> None:
        with self.assertRaises(ValueError):
            AuditCompositionAssessment(
                usability=AuditCompositionUsability.NOT_USABLE,
                reasons=(),
                items=(),
                temporal_assessments=(),
            )

    def test_usable_forbids_reasons(self) -> None:
        with self.assertRaises(ValueError):
            AuditCompositionAssessment(
                usability=AuditCompositionUsability.USABLE,
                reasons=(AuditCompositionReason.SOURCE_UNRESOLVED,),
                items=(),
                temporal_assessments=(),
            )

    def test_frozen(self) -> None:
        assessment = AuditCompositionAssessment(
            usability=AuditCompositionUsability.USABLE,
            reasons=(),
            items=(),
            temporal_assessments=(),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            assessment.usability = AuditCompositionUsability.NOT_USABLE  # type: ignore[misc]

    def test_wrong_items_element_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            AuditCompositionAssessment(
                usability=AuditCompositionUsability.USABLE,
                reasons=(),
                items=("not-an-item",),  # type: ignore[arg-type]
                temporal_assessments=(),
            )


class ComposeAuditProjectionTests(unittest.TestCase):
    def test_wrong_record_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            compose_audit_projection("not-a-record", ())  # type: ignore[arg-type]

    def test_wrong_source_bindings_type_rejected(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(make_source_reference(),),
        )
        with self.assertRaises(TypeError):
            compose_audit_projection(record, [])  # type: ignore[arg-type]

    def test_wrong_temporal_pairs_type_rejected(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(make_source_reference(),),
        )
        with self.assertRaises(TypeError):
            compose_audit_projection(
                record, (), temporal_pairs=["not-a-tuple"]  # type: ignore[arg-type]
            )

    def test_wrong_require_current_type_rejected(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(make_source_reference(),),
        )
        with self.assertRaises(TypeError):
            compose_audit_projection(record, (), require_current="yes")  # type: ignore[arg-type]

    def test_single_current_source_resolves_usable(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.CURRENT),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)
        self.assertEqual(result.reasons, ())
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source_reference, reference)
        self.assertEqual(
            result.items[0].disposition, AuditSourceDisposition.CURRENT
        )

    def test_unresolved_source_fails_closed(self) -> None:
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(make_source_reference(),),
        )

        result = compose_audit_projection(record, ())
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(AuditCompositionReason.SOURCE_UNRESOLVED, result.reasons)
        self.assertEqual(result.items, ())

    def test_ambiguous_source_fails_closed(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference, AuditSourceDisposition.STALE),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(AuditCompositionReason.SOURCE_AMBIGUOUS, result.reasons)
        self.assertEqual(result.items, ())

    def test_no_name_based_or_partial_resolution(self) -> None:
        # A binding with a different source_id must never resolve the
        # request, even though every other field is identical - exact
        # equality only, never a name/prefix heuristic.
        requested = make_source_reference(source_id="risk-1")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(requested,),
        )
        bindings = (
            AuditSourceBinding(
                make_source_reference(source_id="risk-1-v2"),
                AuditSourceDisposition.CURRENT,
            ),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(AuditCompositionReason.SOURCE_UNRESOLVED, result.reasons)

    def test_distinct_sources_resolve_independently_never_deduped(self) -> None:
        reference_a = make_source_reference(source_id="risk-1")
        reference_b = make_source_reference(source_id="risk-2")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)
        self.assertEqual(len(result.items), 2)

    def test_item_order_follows_request_order_not_sorted(self) -> None:
        reference_z = make_source_reference(source_id="z-source")
        reference_a = make_source_reference(source_id="a-source")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_z, reference_a),
        )
        bindings = (
            AuditSourceBinding(reference_z, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(
            [item.source_reference.source_id for item in result.items],
            ["z-source", "a-source"],
        )

    def test_current_disposition_always_usable(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.CURRENT),
        )

        result = compose_audit_projection(
            record, bindings, require_current=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)

    def test_superseded_usable_when_current_not_required(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.SUPERSEDED),
        )

        result = compose_audit_projection(
            record, bindings, require_current=False
        )
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)
        self.assertEqual(
            result.items[0].disposition, AuditSourceDisposition.SUPERSEDED
        )

    def test_superseded_fails_when_current_required(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.SUPERSEDED),
        )

        result = compose_audit_projection(
            record, bindings, require_current=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.SOURCE_CURRENT_REQUIRED, result.reasons
        )
        # Item is still recorded - the reason surfaces separately, the
        # binding itself is never dropped or hidden.
        self.assertEqual(len(result.items), 1)

    def test_all_non_current_non_superseded_dispositions_fail_closed(self) -> None:
        for disposition in (
            AuditSourceDisposition.UNKNOWN,
            AuditSourceDisposition.UNAVAILABLE,
            AuditSourceDisposition.STALE,
            AuditSourceDisposition.CONFLICT,
            AuditSourceDisposition.SOURCE_CHANGED,
        ):
            with self.subTest(disposition=disposition):
                reference = make_source_reference()
                record = AuditCompositionRecord(
                    projection=make_projection_reference(),
                    source_references=(reference,),
                )
                bindings = (AuditSourceBinding(reference, disposition),)

                result = compose_audit_projection(record, bindings)
                self.assertEqual(
                    result.usability, AuditCompositionUsability.NOT_USABLE
                )
                self.assertIn(
                    AuditCompositionReason.SOURCE_DISPOSITION_NOT_USABLE,
                    result.reasons,
                )
                self.assertEqual(len(result.items), 1)

    def test_reasons_collected_in_fixed_order_not_short_circuited(self) -> None:
        unresolved_reference = make_source_reference(source_id="missing")
        ambiguous_reference = make_source_reference(source_id="dup")
        not_usable_reference = make_source_reference(source_id="bad")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(
                unresolved_reference,
                ambiguous_reference,
                not_usable_reference,
            ),
        )
        bindings = (
            AuditSourceBinding(ambiguous_reference, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(ambiguous_reference, AuditSourceDisposition.STALE),
            AuditSourceBinding(not_usable_reference, AuditSourceDisposition.CONFLICT),
        )

        result = compose_audit_projection(record, bindings)
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertEqual(
            result.reasons,
            (
                AuditCompositionReason.SOURCE_UNRESOLVED,
                AuditCompositionReason.SOURCE_AMBIGUOUS,
                AuditCompositionReason.SOURCE_DISPOSITION_NOT_USABLE,
            ),
        )

    def test_temporal_source_not_in_composition_flagged_even_without_require_order(
        self,
    ) -> None:
        reference_a = make_source_reference(source_id="a")
        outside_reference = make_source_reference(source_id="outside")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a,),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(),
            right_source_reference=outside_reference,
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,), require_temporal_order=False
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.TEMPORAL_SOURCE_NOT_IN_COMPOSITION,
            result.reasons,
        )
        # The temporal assessment is still computed and carried, even
        # though the composition is not usable.
        self.assertEqual(len(result.temporal_assessments), 1)

    def test_temporal_pair_within_composition_no_source_flag(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(timestamp=AWARE_NOW),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,)
        )
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)
        self.assertEqual(len(result.temporal_assessments), 1)
        self.assertEqual(
            result.temporal_assessments[0].assessment.relation,
            TemporalRelation.BEFORE,
        )

    def test_require_temporal_order_missing_pairs_fails_closed(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.CURRENT),
        )

        result = compose_audit_projection(
            record, bindings, require_temporal_order=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.TEMPORAL_ORDER_REQUIRED_BUT_MISSING,
            result.reasons,
        )

    def test_unknown_temporal_relation_ignored_when_order_not_required(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(
                disposition=TemporalDisposition.UNKNOWN, timestamp=None
            ),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,), require_temporal_order=False
        )
        self.assertEqual(result.usability, AuditCompositionUsability.USABLE)
        self.assertEqual(
            result.temporal_assessments[0].assessment.relation,
            TemporalRelation.UNKNOWN,
        )

    def test_unknown_temporal_relation_blocks_when_order_required(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(
                disposition=TemporalDisposition.UNKNOWN, timestamp=None
            ),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,), require_temporal_order=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.TEMPORAL_RELATION_UNKNOWN, result.reasons
        )

    def test_conflict_temporal_relation_blocks_when_order_required(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(
                disposition=TemporalDisposition.CONFLICT, timestamp=None
            ),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(timestamp=AWARE_LATER),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,), require_temporal_order=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.TEMPORAL_RELATION_CONFLICT, result.reasons
        )

    def test_not_comparable_temporal_relation_blocks_when_order_required(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(role=TemporalRole.EVENT_TIME),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(
                role=TemporalRole.OBSERVED_TIME, timestamp=AWARE_LATER
            ),
        )

        result = compose_audit_projection(
            record, bindings, temporal_pairs=(pair,), require_temporal_order=True
        )
        self.assertEqual(result.usability, AuditCompositionUsability.NOT_USABLE)
        self.assertIn(
            AuditCompositionReason.TEMPORAL_RELATION_NOT_COMPARABLE, result.reasons
        )

    def test_lineage_relations_forwarded_to_temporal_assessment(self) -> None:
        reference_a = make_source_reference(source_id="a")
        reference_b = make_source_reference(source_id="b")
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference_a, reference_b),
        )
        bindings = (
            AuditSourceBinding(reference_a, AuditSourceDisposition.CURRENT),
            AuditSourceBinding(reference_b, AuditSourceDisposition.CURRENT),
        )
        left_temporal_ref = make_temporal_reference(reference_id="left")
        right_temporal_ref = make_temporal_reference(reference_id="right")
        pair = AuditTemporalPair(
            left_source_reference=reference_a,
            left_fact=make_temporal_fact(
                reference=left_temporal_ref, timestamp=AWARE_LATER
            ),
            right_source_reference=reference_b,
            right_fact=make_temporal_fact(
                reference=right_temporal_ref, timestamp=AWARE_NOW
            ),
        )

        # Timestamps alone say left is AFTER right, but explicit
        # lineage says left precedes right - lineage must win here too.
        result = compose_audit_projection(
            record,
            bindings,
            temporal_pairs=(pair,),
            lineage_relations=(
                LineageRelation(left_temporal_ref, right_temporal_ref),
            ),
        )
        self.assertEqual(
            result.temporal_assessments[0].assessment.relation,
            TemporalRelation.BEFORE,
        )
        self.assertIn(
            TemporalAssessmentReason.DIRECT_LINEAGE_PRECEDENCE,
            result.temporal_assessments[0].assessment.reasons,
        )

    def test_deterministic_replay(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        bindings = (
            AuditSourceBinding(reference, AuditSourceDisposition.CURRENT),
        )

        first = compose_audit_projection(record, bindings)
        second = compose_audit_projection(record, bindings)
        self.assertEqual(first.usability, second.usability)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(first.items, second.items)

    def test_does_not_mutate_inputs(self) -> None:
        reference = make_source_reference()
        record = AuditCompositionRecord(
            projection=make_projection_reference(),
            source_references=(reference,),
        )
        binding = AuditSourceBinding(reference, AuditSourceDisposition.CURRENT)
        record_before = dataclasses.astuple(record)
        binding_before = dataclasses.astuple(binding)

        compose_audit_projection(record, (binding,))

        self.assertEqual(record_before, dataclasses.astuple(record))
        self.assertEqual(binding_before, dataclasses.astuple(binding))


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import ast
        from pathlib import Path

        import audit_read_model.foundation as module

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self) -> set[str]:
        import ast

        imported: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def _referenced_names(self) -> set[str]:
        import ast

        tree = self._module_tree()
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only_plus_time_semantics(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "enum",
            "time_semantics",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_time_semantics_import_is_the_named_narrow_set_only(self) -> None:
        import ast

        imported_from_time_semantics: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "time_semantics.foundation"
            ):
                for alias in node.names:
                    imported_from_time_semantics.add(alias.name)

        self.assertEqual(
            imported_from_time_semantics,
            {
                "LineageRelation",
                "TemporalAssessment",
                "TemporalFact",
                "TemporalRelation",
                "assess_temporal_relation",
            },
        )

    def test_no_other_source_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "strategies",
            "risk",
            "portfolio",
            "portfolio_v1",
            "models",
            "research",
            "execution",
            "explainability",
            "api",
            "dashboard",
        ):
            self.assertNotIn(forbidden, imported)
            for name in imported:
                self.assertFalse(
                    name.startswith(forbidden + "."),
                    f"unexpected cross-domain import: {name}",
                )

    def test_no_source_domain_object_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "StrategyIdentity",
            "RiskSizingProposal",
            "RiskResultRecord",
            "PortfolioDecision",
            "ExplanationRecord",
            "ResearchTrade",
            "ExecutionOrder",
            "ExecutionFact",
            "PositionProvenance",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_research_trade_notional_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("notional", referenced)

    def test_no_wall_clock_random_db_filesystem_or_network_usage(self) -> None:
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
            "datetime",
            "random",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_event_spine_api_ui_reports_or_manual_review_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "EventSpine",
            "publish_event",
            "APIRouter",
            "FastAPI",
            "ManualReview",
            "Report",
            "Dashboard",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_latest_max_nearest_or_sort_selector_exported(self) -> None:
        import audit_read_model.foundation as module

        for forbidden in (
            "latest",
            "current",
            "max_timestamp",
            "get_current",
            "get_latest",
            "nearest",
            "sort_by_time",
        ):
            self.assertFalse(hasattr(module, forbidden))

    def test_no_sort_or_min_max_selector_calls(self) -> None:
        import ast

        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")


if __name__ == "__main__":
    unittest.main()
