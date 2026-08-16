"""
MarketHunter

Tests for the Risk Engine v1 - Slice 1 pure deterministic
RiskSizingProposal issuer/evaluator
(risk/sizing_proposal_issuer.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from models.risk_result_record import IdentityState
from models.risk_sizing_proposal import ProposalDisposition, RiskSizingProposal
from risk.sizing_proposal_issuer import (
    RiskPolicyReference,
    RiskSizingEvaluationInput,
    RiskSizingEvaluationResult,
    RiskSizingIssuability,
    RiskSizingIssueReason,
    evaluate_risk_sizing_proposal,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def make_policy(**overrides) -> RiskPolicyReference:
    kwargs = dict(policy_id="sizing-policy-1", policy_version="1.0.0")
    kwargs.update(overrides)
    return RiskPolicyReference(**kwargs)


def make_input(**overrides) -> RiskSizingEvaluationInput:
    kwargs = dict(
        proposal_id="proposal-1",
        revision=1,
        generated_at=AWARE_NOW,
        supersedes_revision=None,
        instrument_reference_kind="symbol",
        instrument_reference="BTCUSDT",
        direction="long",
        quantity=Decimal("0.5"),
        quantity_unit="BTC",
        notional=Decimal("15000.00"),
        notional_currency="USD",
        reference_price=Decimal("30000.00"),
        reference_price_currency="USD",
        reference_price_unit="BTC",
        reference_price_source_kind="exchange_mid",
        reference_price_source_reference="binance-mid-1",
        risk_result_id="risk-1",
        risk_result_revision=1,
        policy_id="sizing-policy-1",
        policy_version="1.0.0",
        candidate_state=IdentityState.KNOWN,
        candidate_reference_kind="signal",
        candidate_reference="sig-1",
        strategy_reference_state=IdentityState.KNOWN,
        strategy_reference="strategy-1",
        strategy_version_state=IdentityState.KNOWN,
        strategy_version="1.0.0",
        risk_amount=None,
        risk_amount_currency=None,
        risk_amount_unit=None,
        governing_policy=make_policy(),
        candidate_disposition=ProposalDisposition.CURRENT,
        price_disposition=ProposalDisposition.CURRENT,
        risk_result_disposition=ProposalDisposition.CURRENT,
        policy_disposition=ProposalDisposition.CURRENT,
    )
    kwargs.update(overrides)
    return RiskSizingEvaluationInput(**kwargs)


class RiskPolicyReferenceTests(unittest.TestCase):
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


class EnumValueTests(unittest.TestCase):
    def test_issuability_values(self) -> None:
        self.assertEqual(
            {m.value for m in RiskSizingIssuability},
            {"ISSUABLE", "NOT_ISSUABLE"},
        )

    def test_issue_reason_values(self) -> None:
        self.assertEqual(
            {m.value for m in RiskSizingIssueReason},
            {
                "CANDIDATE_NOT_CURRENT",
                "PRICE_NOT_CURRENT",
                "RISK_RESULT_NOT_CURRENT",
                "POLICY_NOT_CURRENT",
                "CANDIDATE_IDENTITY_NOT_KNOWN",
                "POLICY_REFERENCE_INVALID",
                "POLICY_MISMATCH",
                "INVALID_PROPOSAL_INPUT",
            },
        )


class RiskSizingEvaluationInputTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evaluation_input = make_input()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evaluation_input.proposal_id = "other"  # type: ignore[misc]

    def test_wrong_governing_policy_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(governing_policy="not-a-policy")  # type: ignore[arg-type]

    def test_wrong_candidate_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(candidate_disposition="CURRENT")  # type: ignore[arg-type]

    def test_wrong_price_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(price_disposition="CURRENT")  # type: ignore[arg-type]

    def test_wrong_risk_result_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(risk_result_disposition="CURRENT")  # type: ignore[arg-type]

    def test_wrong_policy_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_input(policy_disposition="CURRENT")  # type: ignore[arg-type]


class RiskSizingEvaluationResultTests(unittest.TestCase):
    def test_frozen(self) -> None:
        result = evaluate_risk_sizing_proposal(make_input())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.issuability = RiskSizingIssuability.NOT_ISSUABLE  # type: ignore[misc]

    def test_issuable_requires_proposal(self) -> None:
        with self.assertRaises(ValueError):
            RiskSizingEvaluationResult(
                issuability=RiskSizingIssuability.ISSUABLE,
                reasons=(),
                proposal=None,
            )

    def test_issuable_cannot_carry_reasons(self) -> None:
        proposal = evaluate_risk_sizing_proposal(make_input()).proposal
        with self.assertRaises(ValueError):
            RiskSizingEvaluationResult(
                issuability=RiskSizingIssuability.ISSUABLE,
                reasons=(RiskSizingIssueReason.INVALID_PROPOSAL_INPUT,),
                proposal=proposal,
            )

    def test_not_issuable_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            RiskSizingEvaluationResult(
                issuability=RiskSizingIssuability.NOT_ISSUABLE,
                reasons=(),
                proposal=None,
            )

    def test_not_issuable_cannot_carry_proposal(self) -> None:
        proposal = evaluate_risk_sizing_proposal(make_input()).proposal
        with self.assertRaises(ValueError):
            RiskSizingEvaluationResult(
                issuability=RiskSizingIssuability.NOT_ISSUABLE,
                reasons=(RiskSizingIssueReason.INVALID_PROPOSAL_INPUT,),
                proposal=proposal,
            )


class EvaluateRiskSizingProposalTests(unittest.TestCase):
    def test_wrong_input_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            evaluate_risk_sizing_proposal("not-an-input")  # type: ignore[arg-type]

    def test_complete_current_input_is_issuable(self) -> None:
        result = evaluate_risk_sizing_proposal(make_input())
        self.assertEqual(result.issuability, RiskSizingIssuability.ISSUABLE)
        self.assertEqual(result.reasons, ())
        self.assertIsInstance(result.proposal, RiskSizingProposal)

    def test_success_copies_every_field_exactly(self) -> None:
        result = evaluate_risk_sizing_proposal(make_input())
        proposal = result.proposal

        self.assertEqual(proposal.proposal_id, "proposal-1")
        self.assertEqual(proposal.revision, 1)
        self.assertEqual(proposal.generated_at, AWARE_NOW)
        self.assertEqual(proposal.instrument_reference, "BTCUSDT")
        self.assertEqual(proposal.direction, "long")
        self.assertEqual(proposal.quantity, Decimal("0.5"))
        self.assertEqual(proposal.notional, Decimal("15000.00"))
        self.assertEqual(proposal.reference_price, Decimal("30000.00"))
        self.assertEqual(proposal.risk_result_id, "risk-1")
        self.assertEqual(proposal.risk_result_revision, 1)
        self.assertEqual(proposal.policy_id, "sizing-policy-1")
        self.assertEqual(proposal.policy_version, "1.0.0")
        self.assertEqual(proposal.candidate_reference, "sig-1")

    def test_repeated_evaluation_is_equal(self) -> None:
        first = evaluate_risk_sizing_proposal(make_input())
        second = evaluate_risk_sizing_proposal(make_input())

        self.assertEqual(first.issuability, second.issuability)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(
            dataclasses.astuple(first.proposal),
            dataclasses.astuple(second.proposal),
        )

    def test_evaluation_does_not_mutate_input(self) -> None:
        evaluation_input = make_input()
        before = dataclasses.astuple(evaluation_input)

        evaluate_risk_sizing_proposal(evaluation_input)

        after = dataclasses.astuple(evaluation_input)
        self.assertEqual(before, after)

    def test_non_current_candidate_disposition_fails_closed(self) -> None:
        for disposition in ProposalDisposition:
            if disposition is ProposalDisposition.CURRENT:
                continue
            with self.subTest(disposition=disposition):
                result = evaluate_risk_sizing_proposal(
                    make_input(candidate_disposition=disposition)
                )
                self.assertEqual(
                    result.issuability, RiskSizingIssuability.NOT_ISSUABLE
                )
                self.assertIsNone(result.proposal)
                self.assertIn(
                    RiskSizingIssueReason.CANDIDATE_NOT_CURRENT, result.reasons
                )

    def test_non_current_price_disposition_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(price_disposition=ProposalDisposition.STALE)
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(RiskSizingIssueReason.PRICE_NOT_CURRENT, result.reasons)

    def test_non_current_risk_result_disposition_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(risk_result_disposition=ProposalDisposition.SUPERSEDED)
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(
            RiskSizingIssueReason.RISK_RESULT_NOT_CURRENT, result.reasons
        )

    def test_non_current_policy_disposition_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(policy_disposition=ProposalDisposition.CONFLICT)
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(RiskSizingIssueReason.POLICY_NOT_CURRENT, result.reasons)

    def test_candidate_unknown_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(
                candidate_state=IdentityState.UNKNOWN,
                candidate_reference_kind=None,
                candidate_reference=None,
            )
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(
            RiskSizingIssueReason.CANDIDATE_IDENTITY_NOT_KNOWN, result.reasons
        )

    def test_invalid_governing_policy_fails_closed(self) -> None:
        policy = make_policy()
        # RiskPolicyReference's own constructor already guarantees
        # nonblank fields; simulate a corrupted reference via direct
        # attribute mutation to exercise this evaluator's own
        # defensive re-check.
        object.__setattr__(policy, "policy_id", "")

        result = evaluate_risk_sizing_proposal(
            make_input(governing_policy=policy)
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(
            RiskSizingIssueReason.POLICY_REFERENCE_INVALID, result.reasons
        )

    def test_policy_mismatch_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(
                governing_policy=make_policy(policy_version="2.0.0"),
            )
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertIn(RiskSizingIssueReason.POLICY_MISMATCH, result.reasons)

    def test_invalid_proposal_constructor_data_fails_closed_no_coercion(
        self,
    ) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(quantity=0.5)  # type: ignore[arg-type]
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertIsNone(result.proposal)
        self.assertEqual(
            result.reasons, (RiskSizingIssueReason.INVALID_PROPOSAL_INPUT,)
        )

    def test_invalid_proposal_blank_field_fails_closed(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(instrument_reference="   ")
        )
        self.assertEqual(result.issuability, RiskSizingIssuability.NOT_ISSUABLE)
        self.assertEqual(
            result.reasons, (RiskSizingIssueReason.INVALID_PROPOSAL_INPUT,)
        )

    def test_multiple_reasons_collected_in_fixed_order(self) -> None:
        result = evaluate_risk_sizing_proposal(
            make_input(
                candidate_disposition=ProposalDisposition.STALE,
                price_disposition=ProposalDisposition.STALE,
                candidate_state=IdentityState.UNKNOWN,
                candidate_reference_kind=None,
                candidate_reference=None,
            )
        )
        self.assertEqual(
            result.reasons,
            (
                RiskSizingIssueReason.CANDIDATE_NOT_CURRENT,
                RiskSizingIssueReason.PRICE_NOT_CURRENT,
                RiskSizingIssueReason.CANDIDATE_IDENTITY_NOT_KNOWN,
            ),
        )


class ScopeDisciplineTests(unittest.TestCase):
    def _referenced_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import risk.sizing_proposal_issuer as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def _imported_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import risk.sizing_proposal_issuer as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)

        return imported

    def test_no_account_capital_snapshot_import(self) -> None:
        self.assertNotIn("AccountCapitalSnapshot", self._imported_names())
        self.assertNotIn(
            "models.account_capital_snapshot", self._imported_names()
        )

    def test_no_risk_manager_or_position_size_import(self) -> None:
        imported = self._imported_names()
        self.assertNotIn("RiskManager", imported)
        self.assertNotIn("PositionSize", imported)
        self.assertNotIn("risk.risk_manager", imported)
        self.assertNotIn("risk.position_size", imported)

    def test_no_legacy_risk_result_monetary_field_reads(self) -> None:
        referenced = self._referenced_names()
        for field_name in (
            "position_size",
            "account_size",
            "risk_percent",
        ):
            self.assertNotIn(field_name, referenced)

    def test_no_research_trade_notional_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("ResearchTrade", referenced)

    def test_no_portfolio_decision_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("PortfolioDecision", referenced)

    def test_no_execution_or_broker_import(self) -> None:
        imported = self._imported_names()
        self.assertFalse(
            any(
                name == "execution" or name.startswith("execution.")
                for name in imported
            )
        )

    def test_no_persistence_api_or_runtime_import(self) -> None:
        imported = self._imported_names()
        for forbidden in ("sqlite3", "fastapi", "httpx", "requests"):
            self.assertNotIn(forbidden, imported)

    def test_no_wall_clock_or_random_usage(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("uuid4", referenced)
        self.assertNotIn("random", referenced)

    def test_no_arithmetic_deriving_quantity_notional_risk(self) -> None:
        import ast
        from pathlib import Path

        import risk.sizing_proposal_issuer as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        arithmetic_ops = (
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
        )
        # BinOp also covers `X | None` type-union annotations (BitOr),
        # which are not arithmetic - only flag genuine math operators.
        arithmetic_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic_ops)
        ]
        self.assertEqual(arithmetic_nodes, [])


if __name__ == "__main__":
    unittest.main()
