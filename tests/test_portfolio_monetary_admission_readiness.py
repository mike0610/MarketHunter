"""
MarketHunter

Tests for the Portfolio Monetary Admission Contract - Slice 1
(readiness-only): portfolio_v1/monetary_admission_readiness.py.
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from models.account_capital_snapshot import (
    AccountCapitalSnapshot,
    CapitalSnapshotState,
)
from models.risk_result import RiskResult
from models.risk_result_record import IdentityState, RiskResultRecord
from portfolio.capital_snapshot import CapitalSnapshotUsability
from portfolio_v1.domain import ExposureAssessment, ExposureState
from portfolio_v1.exposure_snapshot import PortfolioExposureSnapshot
from portfolio_v1.monetary_admission_readiness import (
    AdmissionEvidenceState,
    AdmissionReadiness,
    AdmissionReadinessReason,
    MonetaryAdmissionPolicyRef,
    MonetaryAdmissionReadinessInput,
    MonetaryAdmissionReadinessResult,
    assess_monetary_admission_readiness,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _module():
    import portfolio_v1.monetary_admission_readiness as module

    return module


def _referenced_names() -> set[str]:
    tree = ast.parse(Path(_module().__file__).read_text(encoding="utf-8"))
    return {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }


def make_capital_snapshot(**overrides) -> AccountCapitalSnapshot:
    kwargs = dict(
        state=CapitalSnapshotState.AVAILABLE,
        source_authority="prime-broker-authority",
        source_snapshot_id="snap-1",
        source_revision="rev-1",
        venue="binance",
        account_id="acct-1",
        subaccount_id="sub-1",
        environment="live",
        currency="USD",
        as_of=AWARE_NOW,
        account_equity=Decimal("10000.00"),
        cash=Decimal("5000.00"),
        balance=Decimal("10000.00"),
        margin_balance=Decimal("2000.00"),
        buying_power=Decimal("8000.00"),
        available_capital=Decimal("4000.00"),
    )
    kwargs.update(overrides)
    return AccountCapitalSnapshot(**kwargs)


def make_risk_result_record(**overrides) -> RiskResultRecord:
    risk_result = RiskResult(
        entry=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        risk_reward=2.0,
        position_size=10.0,
        risk_amount=50.0,
        account_size=10000.0,
        risk_percent=0.5,
    )
    kwargs = dict(
        risk_result_id="risk-1",
        revision=1,
        generated_at=AWARE_NOW,
        source_state=IdentityState.KNOWN,
        source_reference_kind="signal",
        source_reference="sig-1",
        risk_policy_state=IdentityState.KNOWN,
        risk_policy_version="policy-v1",
        strategy_name="core-breakout",
        strategy_version_state=IdentityState.KNOWN,
        strategy_version="1.0.0",
    )
    kwargs.update(overrides)
    return RiskResultRecord.from_risk_result(risk_result, **kwargs)


def make_exposure_snapshot(**overrides) -> PortfolioExposureSnapshot:
    assessment = ExposureAssessment(
        assessment_id="assessment-1",
        scope="all",
        provenance="persisted_research_trades:all",
        generated_at="2026-08-16T12:00:00+00:00",
        state=ExposureState.MEASURED,
        position_count=3,
        total_notional=300.0,
    )
    kwargs = dict(
        snapshot_id="snapshot-1",
        generated_at="2026-08-16T12:00:00+00:00",
        provenance="persisted_research_trades:all",
        assessments=(assessment,),
        state=ExposureState.MEASURED,
    )
    kwargs.update(overrides)
    return PortfolioExposureSnapshot(**kwargs)


def make_policy(**overrides) -> MonetaryAdmissionPolicyRef:
    kwargs = dict(policy_id="admission-policy-1", policy_version="1.0.0")
    kwargs.update(overrides)
    return MonetaryAdmissionPolicyRef(**kwargs)


def make_input(**overrides) -> MonetaryAdmissionReadinessInput:
    kwargs = dict(
        capital_snapshot=make_capital_snapshot(),
        capital_usability=CapitalSnapshotUsability.USABLE,
        risk_result=make_risk_result_record(),
        risk_evidence_state=AdmissionEvidenceState.CURRENT,
        exposure_snapshot=make_exposure_snapshot(),
        exposure_evidence_state=AdmissionEvidenceState.CURRENT,
        policy=make_policy(),
        evaluated_at=AWARE_NOW,
    )
    kwargs.update(overrides)
    return MonetaryAdmissionReadinessInput(**kwargs)


class MonetaryAdmissionPolicyRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        policy = make_policy()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            policy.policy_id = "other"  # type: ignore[misc]

    def test_blank_policy_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_policy(policy_id="   ")

    def test_blank_policy_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_policy(policy_version="")

    def test_non_str_policy_id_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_policy(policy_id=1)  # type: ignore[arg-type]


class MonetaryAdmissionReadinessInputTests(unittest.TestCase):
    def test_frozen(self) -> None:
        admission_input = make_input()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            admission_input.policy = make_policy()  # type: ignore[misc]

    def test_naive_evaluated_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_input(evaluated_at=datetime(2026, 8, 16, 12, 0))

    def test_wrong_capital_snapshot_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(capital_snapshot="not-a-snapshot")  # type: ignore[arg-type]

    def test_wrong_capital_usability_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(capital_usability="USABLE")  # type: ignore[arg-type]

    def test_wrong_risk_result_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(risk_result="not-a-risk-result")  # type: ignore[arg-type]

    def test_wrong_risk_evidence_state_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(risk_evidence_state="CURRENT")  # type: ignore[arg-type]

    def test_wrong_exposure_snapshot_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(exposure_snapshot="not-a-snapshot")  # type: ignore[arg-type]

    def test_wrong_exposure_evidence_state_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(exposure_evidence_state="CURRENT")  # type: ignore[arg-type]

    def test_wrong_policy_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(policy="not-a-policy")  # type: ignore[arg-type]


class AssessMonetaryAdmissionReadinessTests(unittest.TestCase):
    def test_wrong_input_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_monetary_admission_readiness("not-an-input")  # type: ignore[arg-type]

    def test_complete_current_evidence_is_still_not_ready(self) -> None:
        result = assess_monetary_admission_readiness(make_input())

        self.assertEqual(result.readiness, AdmissionReadiness.NOT_READY)
        self.assertEqual(
            result.reasons,
            (AdmissionReadinessReason.RISK_SIZING_PROPOSAL_NOT_GOVERNED,),
        )

    def test_exact_identities_preserved(self) -> None:
        result = assess_monetary_admission_readiness(make_input())

        self.assertEqual(result.capital_snapshot_id, "snap-1")
        self.assertEqual(result.risk_result_id, "risk-1")
        self.assertEqual(result.risk_result_revision, 1)
        self.assertEqual(result.exposure_snapshot_id, "snapshot-1")
        self.assertEqual(result.policy_id, "admission-policy-1")
        self.assertEqual(result.policy_version, "1.0.0")
        self.assertEqual(result.evaluated_at, AWARE_NOW)

    def test_non_usable_capital_fails_closed(self) -> None:
        admission_input = make_input(
            capital_snapshot=make_capital_snapshot(
                state=CapitalSnapshotState.UNKNOWN
            ),
            capital_usability=CapitalSnapshotUsability.UNKNOWN,
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.CAPITAL_NOT_USABLE, result.reasons
        )
        self.assertEqual(result.readiness, AdmissionReadiness.NOT_READY)

    def test_incomplete_capital_reference_fails_closed(self) -> None:
        admission_input = make_input(
            capital_snapshot=make_capital_snapshot(account_id=None),
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.CAPITAL_REFERENCE_INCOMPLETE,
            result.reasons,
        )

    def test_non_current_risk_evidence_fails_closed(self) -> None:
        admission_input = make_input(
            risk_evidence_state=AdmissionEvidenceState.STALE
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.RISK_EVIDENCE_NOT_CURRENT, result.reasons
        )

    def test_unknown_risk_source_provenance_fails_closed(self) -> None:
        admission_input = make_input(
            risk_result=make_risk_result_record(
                source_state=IdentityState.UNKNOWN,
                source_reference_kind=None,
                source_reference=None,
            ),
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.RISK_PROVENANCE_INCOMPLETE,
            result.reasons,
        )

    def test_unknown_risk_policy_provenance_fails_closed(self) -> None:
        admission_input = make_input(
            risk_result=make_risk_result_record(
                risk_policy_state=IdentityState.UNKNOWN,
                risk_policy_version=None,
            ),
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.RISK_PROVENANCE_INCOMPLETE,
            result.reasons,
        )

    def test_non_current_exposure_evidence_fails_closed(self) -> None:
        admission_input = make_input(
            exposure_evidence_state=AdmissionEvidenceState.SUPERSEDED
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.EXPOSURE_EVIDENCE_NOT_CURRENT,
            result.reasons,
        )

    def test_non_measured_exposure_fails_closed(self) -> None:
        unknown_assessment = ExposureAssessment(
            assessment_id="assessment-1",
            scope="all",
            provenance="persisted_research_trades:all",
            generated_at="2026-08-16T12:00:00+00:00",
            state=ExposureState.UNKNOWN,
        )
        admission_input = make_input(
            exposure_snapshot=make_exposure_snapshot(
                assessments=(unknown_assessment,),
                state=ExposureState.UNKNOWN,
                reasons=("no data available",),
            ),
        )
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.EXPOSURE_NOT_MEASURED, result.reasons
        )

    def test_missing_exposure_provenance_fails_closed(self) -> None:
        snapshot = make_exposure_snapshot()
        # PortfolioExposureSnapshot's own constructor guarantees
        # non-blank provenance; simulate a corrupted/incomplete
        # reference via direct attribute mutation on the frozen
        # instance to exercise this module's own defensive check.
        object.__setattr__(snapshot, "provenance", "")

        admission_input = make_input(exposure_snapshot=snapshot)
        result = assess_monetary_admission_readiness(admission_input)

        self.assertIn(
            AdmissionReadinessReason.EXPOSURE_REFERENCE_INCOMPLETE,
            result.reasons,
        )

    def test_varying_legacy_risk_monetary_payload_does_not_change_result(
        self,
    ) -> None:
        base_result = assess_monetary_admission_readiness(make_input())

        varied_risk_result = make_risk_result_record()
        varied = RiskResultRecord.from_risk_result(
            RiskResult(
                entry=999.0,
                stop_loss=1.0,
                take_profit=2.0,
                risk_reward=3.0,
                position_size=99999.0,
                risk_amount=99999.0,
                account_size=99999.0,
                risk_percent=99.0,
            ),
            risk_result_id="risk-1",
            revision=1,
            generated_at=AWARE_NOW,
            source_state=IdentityState.KNOWN,
            source_reference_kind="signal",
            source_reference="sig-1",
            risk_policy_state=IdentityState.KNOWN,
            risk_policy_version="policy-v1",
            strategy_name="core-breakout",
            strategy_version_state=IdentityState.KNOWN,
            strategy_version="1.0.0",
        )

        varied_result = assess_monetary_admission_readiness(
            make_input(risk_result=varied)
        )

        self.assertEqual(base_result.readiness, varied_result.readiness)
        self.assertEqual(base_result.reasons, varied_result.reasons)
        self.assertEqual(varied_risk_result.entry, 100.0)

    def test_no_research_trade_notional_reference(self) -> None:
        self.assertFalse(hasattr(_module(), "ResearchTrade"))
        self.assertNotIn("notional", _referenced_names())
        self.assertNotIn("ResearchTrade", _referenced_names())

    def test_no_portfolio_decision_or_sizing_decision_reference(self) -> None:
        self.assertNotIn("PortfolioDecision", _referenced_names())
        self.assertNotIn("PositionSizingDecision", _referenced_names())

    def test_never_reads_legacy_risk_monetary_fields(self) -> None:
        referenced = _referenced_names()
        for field_name in (
            "account_size",
            "position_size",
            "risk_amount",
            "risk_percent",
        ):
            self.assertNotIn(field_name, referenced)


class MonetaryAdmissionReadinessResultTests(unittest.TestCase):
    def test_frozen(self) -> None:
        result = assess_monetary_admission_readiness(make_input())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.readiness = AdmissionReadiness.READY_FOR_ADMISSION  # type: ignore[misc]

    def test_ready_for_admission_cannot_carry_reasons(self) -> None:
        with self.assertRaises(ValueError):
            MonetaryAdmissionReadinessResult(
                readiness=AdmissionReadiness.READY_FOR_ADMISSION,
                reasons=(
                    AdmissionReadinessReason.RISK_SIZING_PROPOSAL_NOT_GOVERNED,
                ),
                evaluated_at=AWARE_NOW,
                capital_snapshot_id="snap-1",
                risk_result_id="risk-1",
                risk_result_revision=1,
                exposure_snapshot_id="snapshot-1",
                policy_id="p",
                policy_version="1.0",
            )

    def test_not_ready_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            MonetaryAdmissionReadinessResult(
                readiness=AdmissionReadiness.NOT_READY,
                reasons=(),
                evaluated_at=AWARE_NOW,
                capital_snapshot_id="snap-1",
                risk_result_id="risk-1",
                risk_result_revision=1,
                exposure_snapshot_id="snapshot-1",
                policy_id="p",
                policy_version="1.0",
            )


if __name__ == "__main__":
    unittest.main()
