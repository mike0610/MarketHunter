"""
MarketHunter

Tests for the RiskSizingProposal Contract - Slice 1
(models/risk_sizing_proposal.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from models.risk_result_record import IdentityState
from models.risk_sizing_proposal import (
    ProposalConsumability,
    ProposalDisposition,
    RiskSizingProposal,
    assess_risk_sizing_proposal_consumability,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def make_proposal(**overrides) -> RiskSizingProposal:
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
    )
    kwargs.update(overrides)
    return RiskSizingProposal(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in ProposalDisposition},
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

    def test_consumability_values(self) -> None:
        self.assertEqual(
            {m.value for m in ProposalConsumability},
            {"CONSUMABLE", "NOT_CONSUMABLE"},
        )


class RiskSizingProposalTests(unittest.TestCase):
    def test_frozen(self) -> None:
        proposal = make_proposal()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            proposal.quantity = Decimal("1")  # type: ignore[misc]

    def test_blank_proposal_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(proposal_id="   ")

    def test_naive_generated_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(generated_at=datetime(2026, 8, 16, 12, 0))

    def test_non_positive_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(revision=0)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_proposal(revision=True)  # type: ignore[arg-type]

    def test_valid_supersession_accepted(self) -> None:
        proposal = make_proposal(revision=2, supersedes_revision=1)
        self.assertEqual(proposal.supersedes_revision, 1)

    def test_supersedes_revision_not_less_than_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(revision=2, supersedes_revision=2)

    def test_supersedes_revision_greater_than_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(revision=2, supersedes_revision=3)

    def test_non_positive_supersedes_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(revision=2, supersedes_revision=0)

    def test_supersedes_revision_never_inferred_stays_none(self) -> None:
        proposal = make_proposal(revision=1, supersedes_revision=None)
        self.assertIsNone(proposal.supersedes_revision)

    def test_quantity_must_be_decimal(self) -> None:
        with self.assertRaises(TypeError):
            make_proposal(quantity=0.5)  # type: ignore[arg-type]

    def test_notional_must_be_decimal(self) -> None:
        with self.assertRaises(TypeError):
            make_proposal(notional=15000)  # type: ignore[arg-type]

    def test_reference_price_must_be_decimal(self) -> None:
        with self.assertRaises(TypeError):
            make_proposal(reference_price="30000.00")  # type: ignore[arg-type]

    def test_blank_quantity_unit_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(quantity_unit="")

    def test_blank_notional_currency_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(notional_currency="  ")

    def test_reference_price_provenance_complete(self) -> None:
        proposal = make_proposal()
        self.assertEqual(proposal.reference_price_currency, "USD")
        self.assertEqual(proposal.reference_price_unit, "BTC")
        self.assertEqual(proposal.reference_price_source_kind, "exchange_mid")
        self.assertEqual(
            proposal.reference_price_source_reference, "binance-mid-1"
        )

    def test_blank_reference_price_source_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(reference_price_source_reference="")

    def test_exact_risk_result_identity_preserved(self) -> None:
        proposal = make_proposal(risk_result_id="risk-42", risk_result_revision=7)
        self.assertEqual(proposal.risk_result_id, "risk-42")
        self.assertEqual(proposal.risk_result_revision, 7)

    def test_non_positive_risk_result_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(risk_result_revision=0)

    def test_policy_id_and_version_preserved(self) -> None:
        proposal = make_proposal(policy_id="policy-x", policy_version="2.0.0")
        self.assertEqual(proposal.policy_id, "policy-x")
        self.assertEqual(proposal.policy_version, "2.0.0")

    def test_blank_policy_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(policy_version="   ")

    def test_known_candidate_requires_kind_and_reference(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                candidate_state=IdentityState.KNOWN,
                candidate_reference_kind=None,
                candidate_reference=None,
            )

    def test_unknown_candidate_requires_null_kind_and_reference(self) -> None:
        proposal = make_proposal(
            candidate_state=IdentityState.UNKNOWN,
            candidate_reference_kind=None,
            candidate_reference=None,
        )
        self.assertIsNone(proposal.candidate_reference_kind)
        self.assertIsNone(proposal.candidate_reference)

    def test_unknown_candidate_with_non_null_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                candidate_state=IdentityState.UNKNOWN,
                candidate_reference_kind="signal",
                candidate_reference=None,
            )

    def test_known_strategy_reference_requires_value(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                strategy_reference_state=IdentityState.KNOWN,
                strategy_reference=None,
            )

    def test_unknown_strategy_reference_requires_null(self) -> None:
        proposal = make_proposal(
            strategy_reference_state=IdentityState.UNKNOWN,
            strategy_reference=None,
        )
        self.assertIsNone(proposal.strategy_reference)

    def test_unknown_strategy_reference_with_value_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                strategy_reference_state=IdentityState.UNKNOWN,
                strategy_reference="strategy-1",
            )

    def test_known_strategy_version_requires_value(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                strategy_version_state=IdentityState.KNOWN,
                strategy_version=None,
            )

    def test_unknown_strategy_version_requires_null(self) -> None:
        proposal = make_proposal(
            strategy_version_state=IdentityState.UNKNOWN,
            strategy_version=None,
        )
        self.assertIsNone(proposal.strategy_version)

    def test_risk_amount_all_present_accepted(self) -> None:
        proposal = make_proposal(
            risk_amount=Decimal("500.00"),
            risk_amount_currency="USD",
            risk_amount_unit="USD",
        )
        self.assertEqual(proposal.risk_amount, Decimal("500.00"))

    def test_risk_amount_all_absent_accepted(self) -> None:
        proposal = make_proposal(
            risk_amount=None,
            risk_amount_currency=None,
            risk_amount_unit=None,
        )
        self.assertIsNone(proposal.risk_amount)

    def test_risk_amount_partial_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                risk_amount=Decimal("500.00"),
                risk_amount_currency=None,
                risk_amount_unit="USD",
            )

    def test_risk_amount_currency_only_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_proposal(
                risk_amount=None,
                risk_amount_currency="USD",
                risk_amount_unit=None,
            )

    def test_risk_amount_must_be_decimal(self) -> None:
        with self.assertRaises(TypeError):
            make_proposal(
                risk_amount=500.0,  # type: ignore[arg-type]
                risk_amount_currency="USD",
                risk_amount_unit="USD",
            )


class AssessConsumabilityTests(unittest.TestCase):
    def test_current_is_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.CURRENT
        )
        self.assertEqual(result, ProposalConsumability.CONSUMABLE)

    def test_unknown_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.UNKNOWN
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_unavailable_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.UNAVAILABLE
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_stale_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.STALE
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_conflict_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.CONFLICT
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_superseded_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.SUPERSEDED
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_source_changed_is_not_consumable(self) -> None:
        result = assess_risk_sizing_proposal_consumability(
            make_proposal(), ProposalDisposition.SOURCE_CHANGED
        )
        self.assertEqual(result, ProposalConsumability.NOT_CONSUMABLE)

    def test_wrong_proposal_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_risk_sizing_proposal_consumability(
                "not-a-proposal", ProposalDisposition.CURRENT  # type: ignore[arg-type]
            )

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_risk_sizing_proposal_consumability(
                make_proposal(), "CURRENT"  # type: ignore[arg-type]
            )

    def test_assessment_does_not_mutate_proposal(self) -> None:
        proposal = make_proposal()
        before = dataclasses.astuple(proposal)

        assess_risk_sizing_proposal_consumability(
            proposal, ProposalDisposition.STALE
        )

        after = dataclasses.astuple(proposal)
        self.assertEqual(before, after)


class ScopeDisciplineTests(unittest.TestCase):
    def test_never_reads_legacy_risk_result_monetary_fields(self) -> None:
        import ast
        from pathlib import Path

        import models.risk_sizing_proposal as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names_referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        for field_name in (
            "position_size",
            "risk_percent",
            "account_size",
        ):
            self.assertNotIn(field_name, names_referenced)

    def test_no_research_trade_reference(self) -> None:
        import ast
        from pathlib import Path

        import models.risk_sizing_proposal as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names_referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self.assertNotIn("ResearchTrade", names_referenced)

    def test_no_portfolio_decision_reference(self) -> None:
        import ast
        from pathlib import Path

        import models.risk_sizing_proposal as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names_referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        }
        self.assertNotIn("PortfolioDecision", names_referenced)
        self.assertNotIn("PositionSizingDecision", names_referenced)


if __name__ == "__main__":
    unittest.main()
