"""
MarketHunter

Tests for Slice 1 strategy mathematical validation boundary/value
objects (research/validation/contracts.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.validation import (
    CheckApplicability,
    CheckOutcome,
    ReferenceState,
    ValidationCheckEvidence,
    ValidationCheckId,
    ValidationEvidence,
    ValidationPolicyRef,
    ValidationRunRequest,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)

_ALL_CHECK_IDS = (
    ValidationCheckId.WFV_PREDECLARATION,
    ValidationCheckId.PROSPECTIVE_SELECTION,
    ValidationCheckId.PURGING,
    ValidationCheckId.EMBARGO,
    ValidationCheckId.FINAL_OOS_ACCEPTANCE,
)


def make_policy(**overrides) -> ValidationPolicyRef:
    kwargs = dict(
        policy_id="policy-1",
        policy_version="1.0.0",
        source_claim_ids=("claim-1", "claim-2"),
    )
    kwargs.update(overrides)
    return ValidationPolicyRef(**kwargs)


def make_run_request(**overrides) -> ValidationRunRequest:
    kwargs = dict(
        run_id="run-1",
        requested_at=AWARE_NOW,
        strategy_id="strat-1",
        strategy_version_state=ReferenceState.KNOWN,
        strategy_version="2.1.0",
        dataset_reference="dataset-1",
        time_range_reference="range-1",
        configuration_reference="config-1",
        policy=make_policy(),
    )
    kwargs.update(overrides)
    return ValidationRunRequest(**kwargs)


def make_check_evidence(
    check_id: ValidationCheckId, **overrides
) -> ValidationCheckEvidence:
    kwargs = dict(
        check_id=check_id,
        applicability=CheckApplicability.APPLICABLE,
        outcome=CheckOutcome.PASS,
        reason=None,
        evidence_references=("ref-1",),
    )
    kwargs.update(overrides)
    return ValidationCheckEvidence(**kwargs)


def make_all_checks() -> tuple[ValidationCheckEvidence, ...]:
    return tuple(make_check_evidence(check_id) for check_id in _ALL_CHECK_IDS)


def make_evidence(**overrides) -> ValidationEvidence:
    kwargs = dict(
        evidence_id="evidence-1",
        run_id="run-1",
        created_at=AWARE_NOW,
        strategy_id="strat-1",
        strategy_version_state=ReferenceState.KNOWN,
        strategy_version="2.1.0",
        policy=make_policy(),
        dataset_reference="dataset-1",
        time_range_reference="range-1",
        configuration_reference="config-1",
        chronology_basis_reference="chronology-1",
        train_test_origin_references=("origin-1",),
        parameter_freeze_state=ReferenceState.KNOWN,
        parameter_freeze_at=AWARE_NOW,
        checks=make_all_checks(),
        reproducibility_reference="repro-1",
    )
    kwargs.update(overrides)
    return ValidationEvidence(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_reference_state_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReferenceState}, {"KNOWN", "UNKNOWN"}
        )

    def test_check_applicability_values(self) -> None:
        self.assertEqual(
            {m.value for m in CheckApplicability},
            {"APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"},
        )

    def test_check_outcome_values(self) -> None:
        self.assertEqual(
            {m.value for m in CheckOutcome},
            {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"},
        )

    def test_validation_check_id_values(self) -> None:
        self.assertEqual(
            {m.value for m in ValidationCheckId},
            {
                "WFV_PREDECLARATION",
                "PROSPECTIVE_SELECTION",
                "PURGING",
                "EMBARGO",
                "FINAL_OOS_ACCEPTANCE",
            },
        )


class ValidationPolicyRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        policy = make_policy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.policy_id = "other"  # type: ignore[misc]

    def test_blank_policy_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_policy(policy_id="  ")

    def test_empty_source_claim_ids_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_policy(source_claim_ids=())

    def test_source_claim_ids_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_policy(source_claim_ids=["claim-1"])  # type: ignore[arg-type]


class ValidationRunRequestTests(unittest.TestCase):
    def test_frozen(self) -> None:
        request = make_run_request()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            request.run_id = "other"  # type: ignore[misc]

    def test_blank_run_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_run_request(run_id="   ")

    def test_naive_requested_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_run_request(requested_at=datetime(2026, 8, 16, 12, 0))

    def test_known_strategy_version_requires_value(self) -> None:
        with self.assertRaises(ValueError):
            make_run_request(
                strategy_version_state=ReferenceState.KNOWN,
                strategy_version=None,
            )

    def test_unknown_strategy_version_requires_null(self) -> None:
        with self.assertRaises(ValueError):
            make_run_request(
                strategy_version_state=ReferenceState.UNKNOWN,
                strategy_version="2.1.0",
            )

    def test_unknown_strategy_version_state_accepted_with_null(self) -> None:
        request = make_run_request(
            strategy_version_state=ReferenceState.UNKNOWN,
            strategy_version=None,
        )
        self.assertIsNone(request.strategy_version)

    def test_strategy_version_never_inferred(self) -> None:
        # UNKNOWN state must not silently default to any placeholder
        # value - it must remain exactly None.
        request = make_run_request(
            strategy_version_state=ReferenceState.UNKNOWN,
            strategy_version=None,
        )
        self.assertIsNone(request.strategy_version)
        self.assertEqual(request.strategy_version_state, ReferenceState.UNKNOWN)

    def test_policy_provenance_required(self) -> None:
        with self.assertRaises(TypeError):
            make_run_request(policy="not-a-policy")  # type: ignore[arg-type]


class ValidationCheckEvidenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = make_check_evidence(ValidationCheckId.PURGING)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.reason = "x"  # type: ignore[misc]

    def test_not_applicable_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.EMBARGO,
                applicability=CheckApplicability.NOT_APPLICABLE,
                outcome=CheckOutcome.NOT_APPLICABLE,
                reason=None,
                evidence_references=(),
            )

    def test_not_applicable_requires_matching_outcome(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.EMBARGO,
                applicability=CheckApplicability.NOT_APPLICABLE,
                outcome=CheckOutcome.PASS,
                reason="not relevant to this strategy",
                evidence_references=(),
            )

    def test_not_applicable_with_reason_accepted(self) -> None:
        evidence = make_check_evidence(
            ValidationCheckId.EMBARGO,
            applicability=CheckApplicability.NOT_APPLICABLE,
            outcome=CheckOutcome.NOT_APPLICABLE,
            reason="not relevant to this strategy",
            evidence_references=(),
        )
        self.assertEqual(evidence.outcome, CheckOutcome.NOT_APPLICABLE)

    def test_unknown_applicability_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.PURGING,
                applicability=CheckApplicability.UNKNOWN,
                outcome=CheckOutcome.UNKNOWN,
                reason=None,
                evidence_references=(),
            )

    def test_unknown_applicability_requires_matching_outcome(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.PURGING,
                applicability=CheckApplicability.UNKNOWN,
                outcome=CheckOutcome.FAIL,
                reason="insufficient data to determine",
                evidence_references=(),
            )

    def test_unknown_applicability_with_reason_accepted(self) -> None:
        evidence = make_check_evidence(
            ValidationCheckId.PURGING,
            applicability=CheckApplicability.UNKNOWN,
            outcome=CheckOutcome.UNKNOWN,
            reason="insufficient data to determine",
            evidence_references=(),
        )
        self.assertEqual(evidence.applicability, CheckApplicability.UNKNOWN)

    def test_pass_requires_evidence_reference(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.WFV_PREDECLARATION,
                outcome=CheckOutcome.PASS,
                evidence_references=(),
            )

    def test_pass_with_evidence_reference_accepted(self) -> None:
        evidence = make_check_evidence(
            ValidationCheckId.WFV_PREDECLARATION,
            outcome=CheckOutcome.PASS,
            evidence_references=("doc-1",),
        )
        self.assertEqual(evidence.outcome, CheckOutcome.PASS)

    def test_fail_requires_reason(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.PROSPECTIVE_SELECTION,
                outcome=CheckOutcome.FAIL,
                reason=None,
                evidence_references=(),
            )

    def test_fail_with_reason_accepted(self) -> None:
        evidence = make_check_evidence(
            ValidationCheckId.PROSPECTIVE_SELECTION,
            outcome=CheckOutcome.FAIL,
            reason="failed prospective selection window check",
            evidence_references=(),
        )
        self.assertEqual(evidence.outcome, CheckOutcome.FAIL)

    def test_applicable_with_unknown_outcome_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_check_evidence(
                ValidationCheckId.PURGING,
                applicability=CheckApplicability.APPLICABLE,
                outcome=CheckOutcome.UNKNOWN,
                reason=None,
                evidence_references=(),
            )

    def test_wrong_check_id_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_check_evidence("WFV_PREDECLARATION")  # type: ignore[arg-type]


class ValidationEvidenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = make_evidence()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.evidence_id = "other"  # type: ignore[misc]

    def test_naive_created_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(created_at=datetime(2026, 8, 16, 12, 0))

    def test_known_strategy_version_requires_value(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(
                strategy_version_state=ReferenceState.KNOWN,
                strategy_version=None,
            )

    def test_unknown_strategy_version_requires_null(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(
                strategy_version_state=ReferenceState.UNKNOWN,
                strategy_version="2.1.0",
            )

    def test_empty_train_test_origin_references_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(train_test_origin_references=())

    def test_known_parameter_freeze_requires_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(
                parameter_freeze_state=ReferenceState.KNOWN,
                parameter_freeze_at=None,
            )

    def test_known_parameter_freeze_requires_aware_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(
                parameter_freeze_state=ReferenceState.KNOWN,
                parameter_freeze_at=datetime(2026, 8, 16, 12, 0),
            )

    def test_unknown_parameter_freeze_requires_null_timestamp(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(
                parameter_freeze_state=ReferenceState.UNKNOWN,
                parameter_freeze_at=AWARE_NOW,
            )

    def test_unknown_parameter_freeze_accepted_with_null(self) -> None:
        evidence = make_evidence(
            parameter_freeze_state=ReferenceState.UNKNOWN,
            parameter_freeze_at=None,
        )
        self.assertIsNone(evidence.parameter_freeze_at)

    def test_all_five_checks_exactly_once_accepted(self) -> None:
        evidence = make_evidence(checks=make_all_checks())
        self.assertEqual(len(evidence.checks), 5)

    def test_missing_check_rejected(self) -> None:
        incomplete = tuple(
            make_check_evidence(check_id) for check_id in _ALL_CHECK_IDS[:-1]
        )
        with self.assertRaises(ValueError):
            make_evidence(checks=incomplete)

    def test_duplicate_check_rejected(self) -> None:
        duplicated = make_all_checks()[:-1] + (
            make_check_evidence(ValidationCheckId.WFV_PREDECLARATION),
        )
        with self.assertRaises(ValueError):
            make_evidence(checks=duplicated)

    def test_checks_must_be_tuple_of_check_evidence(self) -> None:
        with self.assertRaises(TypeError):
            make_evidence(checks=list(make_all_checks()))  # type: ignore[arg-type]

    def test_warnings_unknowns_invalidations_conflicts_default_empty(self) -> None:
        evidence = make_evidence()
        self.assertEqual(evidence.warnings, ())
        self.assertEqual(evidence.unknowns, ())
        self.assertEqual(evidence.invalidations, ())
        self.assertEqual(evidence.conflicts, ())

    def test_warnings_field_is_immutable_tuple(self) -> None:
        evidence = make_evidence(warnings=("watch this",))
        self.assertIsInstance(evidence.warnings, tuple)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.warnings = ()  # type: ignore[misc]

    def test_lineage_references_are_plain_strings_not_mutation(self) -> None:
        original = make_evidence(evidence_id="evidence-1")
        superseding = make_evidence(
            evidence_id="evidence-2", supersedes_evidence_id="evidence-1"
        )

        # The prior object is untouched - lineage is a reference only.
        self.assertEqual(original.evidence_id, "evidence-1")
        self.assertIsNone(original.supersedes_evidence_id)
        self.assertEqual(superseding.supersedes_evidence_id, "evidence-1")

    def test_blank_supersedes_evidence_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(supersedes_evidence_id="   ")

    def test_reproducibility_reference_required(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(reproducibility_reference="")


class ScopeDisciplineTests(unittest.TestCase):
    def test_no_overall_lifecycle_or_status_object_exported(self) -> None:
        import research.validation as module

        exported = set(module.__all__)
        self.assertNotIn("ValidationRun", exported)
        self.assertNotIn("ValidationStatus", exported)
        self.assertFalse(hasattr(module, "ValidationRun"))
        self.assertFalse(hasattr(module, "ValidationStatus"))

    def test_no_signal_or_research_trade_dependency(self) -> None:
        import research.validation.contracts as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import ResearchTrade", source)
        self.assertNotIn("research.models.trade", source)
        self.assertNotIn("Signal", source)


if __name__ == "__main__":
    unittest.main()
