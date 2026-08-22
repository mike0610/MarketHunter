"""
MarketHunter

Tests for Trend Context Foundation - Slice 1
(trend_context/foundation.py).
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from trend_context.foundation import (
    TrendContextConflictError,
    TrendContextDisposition,
    TrendContextFoundationError,
    TrendContextHistory,
    TrendContextIdentity,
    TrendContextInvariantError,
    TrendContextLineageError,
    TrendContextNotFoundError,
    TrendContextReference,
    TrendContextReleaseRef,
    TrendContextRecord,
    TrendDirection,
    TrendEvidenceRef,
)

AWARE_NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 20, 12, 0)


def make_release_ref(**overrides) -> TrendContextReleaseRef:
    kwargs = dict(release_id="producer-1", opaque_version="v1")
    kwargs.update(overrides)
    return TrendContextReleaseRef(**kwargs)


def make_identity(**overrides) -> TrendContextIdentity:
    kwargs = dict(
        symbol="BTCUSDT",
        market="spot",
        timeframe="1h",
        producer_ref=make_release_ref(),
        model_policy_ref=make_release_ref(
            release_id="policy-1", opaque_version="p1"
        ),
    )
    kwargs.update(overrides)
    return TrendContextIdentity(**kwargs)


def make_reference(**overrides) -> TrendContextReference:
    kwargs = dict(identity=make_identity(), revision=1)
    kwargs.update(overrides)
    return TrendContextReference(**kwargs)


def make_evidence_ref(**overrides) -> TrendEvidenceRef:
    kwargs = dict(source_id="source-1", evidence_id="ev-1")
    kwargs.update(overrides)
    return TrendEvidenceRef(**kwargs)


def make_record(**overrides) -> TrendContextRecord:
    kwargs = dict(
        reference=make_reference(),
        disposition=TrendContextDisposition.KNOWN,
        direction=TrendDirection.UP,
        evidence_refs=(make_evidence_ref(),),
        available_at=AWARE_NOW,
    )
    kwargs.update(overrides)
    return TrendContextRecord(**kwargs)


def make_history(*records: TrendContextRecord) -> TrendContextHistory:
    return TrendContextHistory(records=records)


class ErrorTaxonomyTests(unittest.TestCase):
    def test_error_hierarchy(self) -> None:
        for error_cls in (
            TrendContextInvariantError,
            TrendContextConflictError,
            TrendContextNotFoundError,
            TrendContextLineageError,
        ):
            self.assertTrue(
                issubclass(error_cls, TrendContextFoundationError)
            )

        self.assertTrue(issubclass(TrendContextFoundationError, Exception))


class TrendContextReleaseRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        ref = make_release_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.release_id = "other"  # type: ignore[misc]

    def test_values_preserved_byte_for_byte(self) -> None:
        ref = make_release_ref(release_id="producer-xyz", opaque_version="v2-alpha")
        self.assertEqual(ref.release_id, "producer-xyz")
        self.assertEqual(ref.opaque_version, "v2-alpha")

    def test_blank_release_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_release_ref(release_id="   ")

    def test_blank_opaque_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_release_ref(opaque_version="")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_release_ref(release_id=123)  # type: ignore[arg-type]


class TrendContextIdentityTests(unittest.TestCase):
    def test_frozen(self) -> None:
        identity = make_identity()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            identity.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_exact_strings_preserved(self) -> None:
        identity = make_identity(symbol="ETHUSDT", market="futures", timeframe="4h")
        self.assertEqual(identity.symbol, "ETHUSDT")
        self.assertEqual(identity.market, "futures")
        self.assertEqual(identity.timeframe, "4h")

    def test_blank_symbol_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_identity(symbol="")

    def test_wrong_producer_ref_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_identity(producer_ref="not-a-ref")  # type: ignore[arg-type]

    def test_wrong_model_policy_ref_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_identity(model_policy_ref="not-a-ref")  # type: ignore[arg-type]

    def test_equal_identities_compare_equal(self) -> None:
        self.assertEqual(make_identity(), make_identity())

    def test_different_producer_ref_is_different_identity(self) -> None:
        a = make_identity()
        b = make_identity(producer_ref=make_release_ref(release_id="producer-2"))
        self.assertNotEqual(a, b)


class TrendContextReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.revision = 2  # type: ignore[misc]

    def test_positive_revision_accepted(self) -> None:
        reference = make_reference(revision=3)
        self.assertEqual(reference.revision, 3)

    def test_zero_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reference(revision=0)

    def test_negative_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reference(revision=-1)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_reference(revision=True)  # type: ignore[arg-type]

    def test_non_int_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_reference(revision="1")  # type: ignore[arg-type]

    def test_wrong_identity_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_reference(identity="not-an-identity")  # type: ignore[arg-type]


class TrendEvidenceRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = make_evidence_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.source_id = "other"  # type: ignore[misc]

    def test_values_preserved_byte_for_byte(self) -> None:
        evidence = make_evidence_ref(source_id="candle-feed", evidence_id="bar-42")
        self.assertEqual(evidence.source_id, "candle-feed")
        self.assertEqual(evidence.evidence_id, "bar-42")

    def test_blank_source_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence_ref(source_id="")

    def test_blank_evidence_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence_ref(evidence_id="  ")


class TrendContextRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.direction = TrendDirection.DOWN  # type: ignore[misc]

    def test_known_requires_up_down_or_neutral(self) -> None:
        for direction in (TrendDirection.UP, TrendDirection.DOWN, TrendDirection.NEUTRAL):
            record = make_record(
                disposition=TrendContextDisposition.KNOWN, direction=direction
            )
            self.assertEqual(record.direction, direction)

    def test_known_with_none_direction_rejected(self) -> None:
        with self.assertRaises(TrendContextInvariantError):
            make_record(disposition=TrendContextDisposition.KNOWN, direction=None)

    def test_unknown_requires_none_direction(self) -> None:
        record = make_record(
            disposition=TrendContextDisposition.UNKNOWN, direction=None
        )
        self.assertIsNone(record.direction)

    def test_unknown_with_direction_rejected(self) -> None:
        with self.assertRaises(TrendContextInvariantError):
            make_record(
                disposition=TrendContextDisposition.UNKNOWN,
                direction=TrendDirection.UP,
            )

    def test_unavailable_with_direction_rejected(self) -> None:
        with self.assertRaises(TrendContextInvariantError):
            make_record(
                disposition=TrendContextDisposition.UNAVAILABLE,
                direction=TrendDirection.NEUTRAL,
            )

    def test_conflict_with_direction_rejected(self) -> None:
        with self.assertRaises(TrendContextInvariantError):
            make_record(
                disposition=TrendContextDisposition.CONFLICT,
                direction=TrendDirection.DOWN,
            )

    def test_unknown_is_never_encoded_as_neutral(self) -> None:
        unknown = make_record(disposition=TrendContextDisposition.UNKNOWN, direction=None)
        neutral = make_record(
            disposition=TrendContextDisposition.KNOWN, direction=TrendDirection.NEUTRAL
        )
        self.assertNotEqual(unknown.disposition, neutral.disposition)
        self.assertIsNone(unknown.direction)
        self.assertEqual(neutral.direction, TrendDirection.NEUTRAL)

    def test_evidence_refs_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evidence_refs=[make_evidence_ref()])  # type: ignore[arg-type]

    def test_evidence_refs_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evidence_refs=("not-evidence",))  # type: ignore[arg-type]

    def test_empty_evidence_tuple_permitted(self) -> None:
        record = make_record(evidence_refs=())
        self.assertEqual(record.evidence_refs, ())

    def test_available_at_required_to_be_datetime(self) -> None:
        with self.assertRaises(TypeError):
            make_record(available_at="2026-08-20T12:00:00Z")  # type: ignore[arg-type]

    def test_available_at_must_be_timezone_aware(self) -> None:
        with self.assertRaises(ValueError):
            make_record(available_at=NAIVE_NOW)

    def test_available_at_preserved_exactly(self) -> None:
        record = make_record(available_at=AWARE_NOW)
        self.assertEqual(record.available_at, AWARE_NOW)

    def test_wrong_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(reference="not-a-reference")  # type: ignore[arg-type]

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(disposition="KNOWN")  # type: ignore[arg-type]

    def test_wrong_direction_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(direction="UP")  # type: ignore[arg-type]


class TrendContextHistoryTests(unittest.TestCase):
    def test_frozen(self) -> None:
        history = make_history(make_record())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            history.records = ()  # type: ignore[misc]

    def test_wrong_records_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            TrendContextHistory(records=[make_record()])  # type: ignore[arg-type]

    def test_records_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            TrendContextHistory(records=("not-a-record",))  # type: ignore[arg-type]

    def test_empty_history_accepted(self) -> None:
        history = make_history()
        self.assertEqual(history.records, ())

    def test_identical_replay_accepted(self) -> None:
        record = make_record()
        history = make_history(record, record)
        self.assertEqual(len(history.records), 2)

    def test_equal_but_distinct_duplicate_replay_accepted(self) -> None:
        record_a = make_record()
        record_b = make_record()
        self.assertIsNot(record_a, record_b)
        history = make_history(record_a, record_b)
        self.assertEqual(len(history.records), 2)

    def test_same_key_changed_evidence_hard_conflicts(self) -> None:
        record_a = make_record()
        record_b = make_record(
            evidence_refs=(make_evidence_ref(evidence_id="different"),)
        )
        with self.assertRaises(TrendContextConflictError):
            make_history(record_a, record_b)

    def test_same_key_changed_direction_hard_conflicts(self) -> None:
        record_a = make_record(direction=TrendDirection.UP)
        record_b = make_record(direction=TrendDirection.DOWN)
        with self.assertRaises(TrendContextConflictError):
            make_history(record_a, record_b)

    def test_same_key_changed_disposition_hard_conflicts(self) -> None:
        record_a = make_record(
            disposition=TrendContextDisposition.KNOWN, direction=TrendDirection.UP
        )
        record_b = make_record(
            disposition=TrendContextDisposition.UNKNOWN, direction=None
        )
        with self.assertRaises(TrendContextConflictError):
            make_history(record_a, record_b)

    def test_same_key_changed_available_at_hard_conflicts(self) -> None:
        record_a = make_record(available_at=AWARE_NOW)
        record_b = make_record(
            available_at=datetime(2026, 8, 21, 0, 0, tzinfo=timezone.utc)
        )
        with self.assertRaises(TrendContextConflictError):
            make_history(record_a, record_b)

    def test_lineage_starts_at_revision_one(self) -> None:
        identity = make_identity()
        record = make_record(reference=make_reference(identity=identity, revision=1))
        history = make_history(record)
        self.assertEqual(len(history.records), 1)

    def test_revision_gap_from_one_rejected(self) -> None:
        identity = make_identity()
        record = make_record(reference=make_reference(identity=identity, revision=2))
        with self.assertRaises(TrendContextLineageError):
            make_history(record)

    def test_revision_n_requires_supplied_n_minus_one_same_identity(self) -> None:
        identity = make_identity()
        record_1 = make_record(reference=make_reference(identity=identity, revision=1))
        record_2 = make_record(
            reference=make_reference(identity=identity, revision=2),
            evidence_refs=(make_evidence_ref(evidence_id="ev-2"),),
        )
        history = make_history(record_1, record_2)
        self.assertEqual(len(history.records), 2)

    def test_revision_three_without_revision_two_rejected(self) -> None:
        identity = make_identity()
        record_1 = make_record(reference=make_reference(identity=identity, revision=1))
        record_3 = make_record(
            reference=make_reference(identity=identity, revision=3),
            evidence_refs=(make_evidence_ref(evidence_id="ev-3"),),
        )
        with self.assertRaises(TrendContextLineageError):
            make_history(record_1, record_3)

    def test_changed_scope_is_distinct_identity_and_may_start_at_one(self) -> None:
        identity_a = make_identity(symbol="BTCUSDT")
        identity_b = make_identity(symbol="ETHUSDT")
        record_a = make_record(reference=make_reference(identity=identity_a, revision=1))
        record_b = make_record(reference=make_reference(identity=identity_b, revision=1))
        history = make_history(record_a, record_b)
        self.assertEqual(len(history.records), 2)

    def test_changed_producer_ref_is_distinct_identity_and_may_start_at_one(self) -> None:
        identity_a = make_identity()
        identity_b = make_identity(
            producer_ref=make_release_ref(release_id="producer-2")
        )
        record_a = make_record(reference=make_reference(identity=identity_a, revision=1))
        record_b = make_record(reference=make_reference(identity=identity_b, revision=1))
        history = make_history(record_a, record_b)
        self.assertEqual(len(history.records), 2)

    def test_changed_model_policy_ref_is_distinct_identity_and_may_start_at_one(self) -> None:
        identity_a = make_identity()
        identity_b = make_identity(
            model_policy_ref=make_release_ref(release_id="policy-2")
        )
        record_a = make_record(reference=make_reference(identity=identity_a, revision=1))
        record_b = make_record(reference=make_reference(identity=identity_b, revision=1))
        history = make_history(record_a, record_b)
        self.assertEqual(len(history.records), 2)

    def test_get_exact_returns_matching_record(self) -> None:
        identity = make_identity()
        record = make_record(reference=make_reference(identity=identity, revision=1))
        history = make_history(record)
        self.assertIs(history.get_exact(identity, 1), record)

    def test_get_exact_miss_returns_none(self) -> None:
        history = make_history(make_record())
        other_identity = make_identity(symbol="SOLUSDT")
        self.assertIsNone(history.get_exact(other_identity, 1))

    def test_get_exact_miss_revision_returns_none(self) -> None:
        identity = make_identity()
        record = make_record(reference=make_reference(identity=identity, revision=1))
        history = make_history(record)
        self.assertIsNone(history.get_exact(identity, 2))

    def test_require_exact_returns_matching_record(self) -> None:
        identity = make_identity()
        record = make_record(reference=make_reference(identity=identity, revision=1))
        history = make_history(record)
        self.assertIs(history.require_exact(identity, 1), record)

    def test_require_exact_miss_raises_not_found(self) -> None:
        history = make_history(make_record())
        other_identity = make_identity(symbol="SOLUSDT")
        with self.assertRaises(TrendContextNotFoundError):
            history.require_exact(other_identity, 1)

    def test_get_exact_wrong_identity_type_rejected(self) -> None:
        history = make_history()
        with self.assertRaises(TypeError):
            history.get_exact("not-an-identity", 1)  # type: ignore[arg-type]

    def test_get_exact_bool_revision_rejected(self) -> None:
        history = make_history()
        with self.assertRaises(TypeError):
            history.get_exact(make_identity(), True)  # type: ignore[arg-type]

    def test_get_exact_zero_revision_rejected(self) -> None:
        history = make_history()
        with self.assertRaises(ValueError):
            history.get_exact(make_identity(), 0)

    def test_no_latest_current_nearest_selector_methods(self) -> None:
        import trend_context.foundation as module

        for forbidden in (
            "current",
            "latest",
            "nearest",
            "get_current",
            "get_latest",
            "winner",
        ):
            self.assertFalse(hasattr(module.TrendContextHistory, forbidden))


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import trend_context.foundation as module

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self) -> set[str]:
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
        tree = self._module_tree()
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only(self) -> None:
        imported = self._imported_names()
        allowed = {"__future__", "dataclasses", "datetime", "enum"}
        for name in imported:
            self.assertIn(name, allowed, f"unexpected import: {name}")

    def test_no_cross_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "research",
            "services",
            "exchange",
            "portfolio",
            "portfolio_v1",
            "risk",
            "trade_orchestration",
            "execution",
            "models",
            "explainability",
            "audit_read_model",
            "manual_review",
            "simulation",
            "time_semantics",
            "api",
            "dashboard",
            "pipeline",
            "structure",
            "indicators",
            "regime",
            "strategies",
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
            "ResearchTrade",
            "BaseStrategy",
            "SimulationEvent",
            "Scanner",
            "Signal",
            "CandidateProvenance",
            "TrendState",
            "TrendEngine",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_wall_clock_random_db_filesystem_network(self) -> None:
        referenced = self._referenced_names()
        for forbidden in ("now", "utcnow", "uuid4", "today"):
            self.assertNotIn(forbidden, referenced)

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
            "random",
            "time",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_sort_or_min_max_calls(self) -> None:
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")


if __name__ == "__main__":
    unittest.main()
