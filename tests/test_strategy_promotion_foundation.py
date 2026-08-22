"""
MarketHunter

Tests for StrategyVersion Promotion Decision Foundation - Slice 1
(strategies/promotion_foundation.py).
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from strategies.promotion_foundation import (
    StrategyPromotionCandidate,
    StrategyPromotionDecision,
    StrategyPromotionDecisionReference,
    StrategyPromotionOutcome,
    StrategyPromotionReference,
)
from strategies.registry_foundation import StrategyIdentity, StrategyVersion

AWARE_NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 22, 12, 0)


def make_identity(**overrides) -> StrategyIdentity:
    kwargs = dict(
        strategy_id="strategy-1",
        authority_reference_kind="notion_page",
        authority_reference="page-123",
    )
    kwargs.update(overrides)
    return StrategyIdentity(**kwargs)


def make_ref(**overrides) -> StrategyPromotionReference:
    kwargs = dict(reference_kind="rules_doc", reference="doc-1")
    kwargs.update(overrides)
    return StrategyPromotionReference(**kwargs)


def make_candidate(**overrides) -> StrategyPromotionCandidate:
    kwargs = dict(
        strategy_identity=make_identity(),
        proposed_version="rev-A",
        rules_config_refs=(make_ref(),),
        artifact_refs=(make_ref(reference_kind="artifact", reference="art-1"),),
        evidence_refs=(make_ref(reference_kind="evidence", reference="ev-1"),),
        lineage_refs=(make_ref(reference_kind="lineage", reference="lin-1"),),
        provenance_refs=(make_ref(reference_kind="provenance", reference="prov-1"),),
    )
    kwargs.update(overrides)
    return StrategyPromotionCandidate(**kwargs)


def make_decision_reference(**overrides) -> StrategyPromotionDecisionReference:
    kwargs = dict(decision_id="decision-1", decision_version="0007")
    kwargs.update(overrides)
    return StrategyPromotionDecisionReference(**kwargs)


def make_decision(**overrides) -> StrategyPromotionDecision:
    kwargs = dict(
        reference=make_decision_reference(),
        candidate=make_candidate(),
        outcome=StrategyPromotionOutcome.APPROVED,
        decided_at=AWARE_NOW,
        decision_provenance_refs=(
            make_ref(reference_kind="decision_provenance", reference="dp-1"),
        ),
    )
    kwargs.update(overrides)
    return StrategyPromotionDecision(**kwargs)


class StrategyPromotionReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        ref = make_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.reference = "other"  # type: ignore[misc]

    def test_values_round_trip_unchanged(self) -> None:
        ref = make_ref(reference_kind="artifact", reference="s3://bucket/key")
        self.assertEqual(ref.reference_kind, "artifact")
        self.assertEqual(ref.reference, "s3://bucket/key")

    def test_blank_reference_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_ref(reference_kind="   ")

    def test_blank_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_ref(reference="")

    def test_wrong_type_reference_kind_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_ref(reference_kind=123)  # type: ignore[arg-type]

    def test_wrong_type_reference_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_ref(reference=None)  # type: ignore[arg-type]


class StrategyPromotionCandidateTests(unittest.TestCase):
    def test_frozen(self) -> None:
        candidate = make_candidate()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.proposed_version = "other"  # type: ignore[misc]

    def test_requires_canonical_typed_strategy_identity(self) -> None:
        with self.assertRaises(TypeError):
            make_candidate(strategy_identity="not-an-identity")  # type: ignore[arg-type]

    def test_proposed_version_preserved_exactly(self) -> None:
        for version_text in ("rev-A", "2026.x", "0007"):
            candidate = make_candidate(proposed_version=version_text)
            self.assertEqual(candidate.proposed_version, version_text)

    def test_blank_proposed_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_candidate(proposed_version="")

    def test_wrong_type_proposed_version_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_candidate(proposed_version=1)  # type: ignore[arg-type]

    def test_each_ref_collection_must_be_tuple(self) -> None:
        for field_name in (
            "rules_config_refs",
            "artifact_refs",
            "evidence_refs",
            "lineage_refs",
            "provenance_refs",
        ):
            with self.assertRaises(TypeError):
                make_candidate(**{field_name: [make_ref()]})  # type: ignore[arg-type]

    def test_each_ref_collection_rejects_set(self) -> None:
        with self.assertRaises(TypeError):
            make_candidate(rules_config_refs={make_ref()})  # type: ignore[arg-type]

    def test_each_ref_collection_element_type_checked(self) -> None:
        for field_name in (
            "rules_config_refs",
            "artifact_refs",
            "evidence_refs",
            "lineage_refs",
            "provenance_refs",
        ):
            with self.assertRaises(TypeError):
                make_candidate(**{field_name: ("not-a-ref",)})  # type: ignore[arg-type]

    def test_empty_ref_collections_permitted(self) -> None:
        candidate = make_candidate(
            rules_config_refs=(),
            artifact_refs=(),
            evidence_refs=(),
            lineage_refs=(),
            provenance_refs=(),
        )
        self.assertEqual(candidate.rules_config_refs, ())
        self.assertEqual(candidate.provenance_refs, ())

    def test_refs_order_preserved(self) -> None:
        ref1 = make_ref(reference_kind="evidence", reference="ev-1")
        ref2 = make_ref(reference_kind="evidence", reference="ev-2")
        candidate = make_candidate(evidence_refs=(ref1, ref2))
        self.assertEqual(candidate.evidence_refs, (ref1, ref2))

    def test_candidate_is_not_strategy_version(self) -> None:
        candidate = make_candidate()
        self.assertNotIsInstance(candidate, StrategyVersion)
        self.assertFalse(issubclass(StrategyPromotionCandidate, StrategyVersion))

    def test_candidate_exposes_no_strategy_version_minting_method(self) -> None:
        candidate_attrs = {
            name for name in dir(StrategyPromotionCandidate)
            if not name.startswith("_")
        }
        for forbidden in ("to_strategy_version", "mint", "issue", "promote"):
            self.assertNotIn(forbidden, candidate_attrs)


class StrategyPromotionOutcomeTests(unittest.TestCase):
    def test_exactly_two_members(self) -> None:
        self.assertEqual(len(StrategyPromotionOutcome), 2)
        self.assertEqual(
            {member.value for member in StrategyPromotionOutcome},
            {"APPROVED", "REJECTED"},
        )

    def test_no_unknown_unavailable_conflict_members(self) -> None:
        member_names = {member.name for member in StrategyPromotionOutcome}
        for forbidden in (
            "UNKNOWN",
            "UNAVAILABLE",
            "CONFLICT",
            "MISMATCH",
            "INCOMPLETE",
            "PENDING",
        ):
            self.assertNotIn(forbidden, member_names)

    def test_no_normalization_helper_exported(self) -> None:
        import strategies.promotion_foundation as module

        for forbidden in (
            "normalize_outcome",
            "to_outcome",
            "resolve_outcome",
            "coerce_outcome",
        ):
            self.assertFalse(hasattr(module, forbidden))


class StrategyPromotionDecisionReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_decision_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.decision_id = "other"  # type: ignore[misc]

    def test_values_round_trip_unchanged(self) -> None:
        reference = make_decision_reference(
            decision_id="decision-xyz", decision_version="2026.x"
        )
        self.assertEqual(reference.decision_id, "decision-xyz")
        self.assertEqual(reference.decision_version, "2026.x")

    def test_opaque_versions_no_ordering_semantics(self) -> None:
        ref_a = make_decision_reference(decision_version="rev-A")
        ref_b = make_decision_reference(decision_version="0007")
        self.assertNotEqual(ref_a, ref_b)
        self.assertEqual(ref_a.decision_version, "rev-A")
        self.assertEqual(ref_b.decision_version, "0007")

    def test_blank_decision_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_decision_reference(decision_id="")

    def test_blank_decision_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_decision_reference(decision_version="  ")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_decision_reference(decision_id=1)  # type: ignore[arg-type]


class StrategyPromotionDecisionTests(unittest.TestCase):
    def test_frozen(self) -> None:
        decision = make_decision()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.outcome = StrategyPromotionOutcome.REJECTED  # type: ignore[misc]

    def test_requires_typed_reference(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(reference="not-a-reference")  # type: ignore[arg-type]

    def test_requires_typed_candidate(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(candidate="not-a-candidate")  # type: ignore[arg-type]

    def test_requires_typed_outcome(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(outcome="APPROVED")  # type: ignore[arg-type]

    def test_approved_outcome_accepted(self) -> None:
        decision = make_decision(outcome=StrategyPromotionOutcome.APPROVED)
        self.assertEqual(decision.outcome, StrategyPromotionOutcome.APPROVED)

    def test_rejected_outcome_accepted(self) -> None:
        decision = make_decision(outcome=StrategyPromotionOutcome.REJECTED)
        self.assertEqual(decision.outcome, StrategyPromotionOutcome.REJECTED)

    def test_naive_decided_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_decision(decided_at=NAIVE_NOW)

    def test_non_datetime_decided_at_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(decided_at="2026-08-22T12:00:00Z")  # type: ignore[arg-type]

    def test_decided_at_preserved_exactly(self) -> None:
        decision = make_decision(decided_at=AWARE_NOW)
        self.assertEqual(decision.decided_at, AWARE_NOW)

    def test_decision_provenance_refs_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(decision_provenance_refs=[make_ref()])  # type: ignore[arg-type]

    def test_decision_provenance_refs_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            make_decision(decision_provenance_refs=("not-a-ref",))  # type: ignore[arg-type]

    def test_decision_provenance_refs_empty_permitted(self) -> None:
        decision = make_decision(decision_provenance_refs=())
        self.assertEqual(decision.decision_provenance_refs, ())

    def test_candidate_preserved_by_identity(self) -> None:
        candidate = make_candidate()
        decision = make_decision(candidate=candidate)
        self.assertIs(decision.candidate, candidate)

    def test_reference_preserved_by_identity(self) -> None:
        reference = make_decision_reference()
        decision = make_decision(reference=reference)
        self.assertIs(decision.reference, reference)


class NoDecidabilityLeakageTests(unittest.TestCase):
    def test_decision_has_no_intermediate_state_fields(self) -> None:
        decision = make_decision()
        field_names = {f.name for f in dataclasses.fields(decision)}
        for forbidden in (
            "unknown",
            "unavailable",
            "conflict",
            "mismatch",
            "incomplete",
            "pending",
        ):
            self.assertNotIn(forbidden, field_names)

    def test_module_exports_no_evaluator_or_writer(self) -> None:
        import strategies.promotion_foundation as module

        module_names = {
            name for name in dir(module) if not name.startswith("_")
        }
        for forbidden in (
            "Evaluator",
            "Writer",
            "Repository",
            "Service",
            "Issuer",
            "Registry",
            "Manifest",
            "History",
        ):
            for name in module_names:
                self.assertNotIn(forbidden, name)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import strategies.promotion_foundation as module

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

    def test_module_is_stdlib_plus_registry_foundation_only(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "datetime",
            "enum",
            "strategies.registry_foundation",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_registry_foundation_import_is_strategy_identity_only(self) -> None:
        imported_names: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "strategies.registry_foundation"
            ):
                for alias in node.names:
                    imported_names.add(alias.name)

        self.assertEqual(imported_names, {"StrategyIdentity"})

    def test_no_strategy_version_import(self) -> None:
        imported_names: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.name)

        self.assertNotIn("StrategyVersion", imported_names)

    def test_no_forbidden_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "strategies.runtime_release_manifest",
            "strategies.execution_binding",
            "services",
            "pipeline",
            "research",
            "simulation",
            "risk",
            "portfolio",
            "portfolio_v1",
            "trade_orchestration",
            "execution",
            "api",
            "dashboard",
            "market_data",
            "data_quality",
            "trend_context",
            "explainability",
            "audit_read_model",
            "manual_review",
            "time_semantics",
            "models",
            "exchange",
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
            "Scanner",
            "Signal",
            "SimulationEvent",
            "CandidateProvenance",
            "StrategyReleaseDeclaration",
            "StrategyExecutionBinding",
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

    def test_no_current_latest_nearest_selector_exported(self) -> None:
        import strategies.promotion_foundation as module

        for forbidden in (
            "current",
            "latest",
            "nearest",
            "default",
            "get_current",
            "get_latest",
            "winner",
        ):
            self.assertFalse(hasattr(module, forbidden))

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
