"""
MarketHunter

Tests for Portfolio Monetary Authorization Record - Slice 1
(portfolio_v1/monetary_authorization.py).
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from portfolio_v1.monetary_authorization import (
    PortfolioMonetaryAuthorizationOutcome,
    PortfolioMonetaryAuthorizationRecord,
    PortfolioMonetaryAuthorizationRef,
)

AWARE_NOW = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 22, 12, 0)


def make_ref(**overrides) -> PortfolioMonetaryAuthorizationRef:
    kwargs = dict(reference_kind="capital_snapshot", reference="cap-1")
    kwargs.update(overrides)
    return PortfolioMonetaryAuthorizationRef(**kwargs)


def make_record(**overrides) -> PortfolioMonetaryAuthorizationRecord:
    kwargs = dict(
        authorization_id="auth-1",
        authorization_version="v1",
        risk_sizing_proposal_id="proposal-1",
        risk_sizing_proposal_revision=1,
        capital_ref=make_ref(reference_kind="capital_snapshot", reference="cap-1"),
        exposure_ref=make_ref(reference_kind="exposure_snapshot", reference="exp-1"),
        policy_ref=make_ref(reference_kind="policy", reference="pol-1"),
        scope_ref=make_ref(reference_kind="account", reference="acct-1"),
        outcome=PortfolioMonetaryAuthorizationOutcome.PROCEED,
        reasons=(),
        evaluated_at=AWARE_NOW,
    )
    kwargs.update(overrides)
    return PortfolioMonetaryAuthorizationRecord(**kwargs)


def make_block_record(**overrides) -> PortfolioMonetaryAuthorizationRecord:
    kwargs = dict(
        outcome=PortfolioMonetaryAuthorizationOutcome.BLOCK,
        reasons=("capital not usable",),
    )
    kwargs.update(overrides)
    return make_record(**kwargs)


class PortfolioMonetaryAuthorizationOutcomeTests(unittest.TestCase):
    def test_exactly_two_members(self) -> None:
        self.assertEqual(len(PortfolioMonetaryAuthorizationOutcome), 2)
        self.assertEqual(
            {member.value for member in PortfolioMonetaryAuthorizationOutcome},
            {"PROCEED", "BLOCK"},
        )

    def test_no_intermediate_state_members(self) -> None:
        member_names = {
            member.name for member in PortfolioMonetaryAuthorizationOutcome
        }
        for forbidden in (
            "UNKNOWN",
            "UNAVAILABLE",
            "CONFLICT",
            "NOT_APPLICABLE",
            "STALE",
            "SUPERSEDED",
            "SOURCE_CHANGED",
            "PENDING",
        ):
            self.assertNotIn(forbidden, member_names)


class PortfolioMonetaryAuthorizationRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        ref = make_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.reference = "other"  # type: ignore[misc]

    def test_values_round_trip_unchanged(self) -> None:
        ref = make_ref(reference_kind="policy", reference="policy-doc-42")
        self.assertEqual(ref.reference_kind, "policy")
        self.assertEqual(ref.reference, "policy-doc-42")

    def test_blank_reference_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_ref(reference_kind="   ")

    def test_blank_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_ref(reference="")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_ref(reference_kind=123)  # type: ignore[arg-type]


class PortfolioMonetaryAuthorizationRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.authorization_id = "other"  # type: ignore[misc]

    def test_exact_opaque_string_preservation(self) -> None:
        record = make_record(
            authorization_id="auth-xyz",
            authorization_version="2026.x",
            risk_sizing_proposal_id="proposal-abc",
        )
        self.assertEqual(record.authorization_id, "auth-xyz")
        self.assertEqual(record.authorization_version, "2026.x")
        self.assertEqual(record.risk_sizing_proposal_id, "proposal-abc")

    def test_blank_authorization_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(authorization_id="")

    def test_blank_authorization_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(authorization_version="  ")

    def test_blank_risk_sizing_proposal_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(risk_sizing_proposal_id="")

    def test_wrong_type_authorization_id_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(authorization_id=1)  # type: ignore[arg-type]

    def test_positive_risk_sizing_proposal_revision_accepted(self) -> None:
        record = make_record(risk_sizing_proposal_revision=7)
        self.assertEqual(record.risk_sizing_proposal_revision, 7)

    def test_zero_risk_sizing_proposal_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(risk_sizing_proposal_revision=0)

    def test_negative_risk_sizing_proposal_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(risk_sizing_proposal_revision=-1)

    def test_bool_risk_sizing_proposal_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(risk_sizing_proposal_revision=True)  # type: ignore[arg-type]

    def test_non_int_risk_sizing_proposal_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(risk_sizing_proposal_revision="1")  # type: ignore[arg-type]

    def test_wrong_type_capital_ref_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(capital_ref="not-a-ref")  # type: ignore[arg-type]

    def test_wrong_type_exposure_ref_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(exposure_ref="not-a-ref")  # type: ignore[arg-type]

    def test_wrong_type_policy_ref_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(policy_ref="not-a-ref")  # type: ignore[arg-type]

    def test_wrong_type_scope_ref_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(scope_ref="not-a-ref")  # type: ignore[arg-type]

    def test_wrong_type_outcome_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(outcome="PROCEED")  # type: ignore[arg-type]

    def test_evaluated_at_required_to_be_datetime(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evaluated_at="2026-08-22T12:00:00Z")  # type: ignore[arg-type]

    def test_evaluated_at_must_be_timezone_aware(self) -> None:
        with self.assertRaises(ValueError):
            make_record(evaluated_at=NAIVE_NOW)

    def test_evaluated_at_preserved_exactly(self) -> None:
        record = make_record(evaluated_at=AWARE_NOW)
        self.assertEqual(record.evaluated_at, AWARE_NOW)

    def test_reasons_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_block_record(reasons=["capital not usable"])  # type: ignore[arg-type]

    def test_reasons_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            make_block_record(reasons=(1,))  # type: ignore[arg-type]

    def test_reasons_element_must_be_nonblank(self) -> None:
        with self.assertRaises(ValueError):
            make_block_record(reasons=("   ",))

    def test_proceed_requires_empty_reasons(self) -> None:
        record = make_record(
            outcome=PortfolioMonetaryAuthorizationOutcome.PROCEED, reasons=()
        )
        self.assertEqual(record.reasons, ())

    def test_proceed_with_reasons_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(
                outcome=PortfolioMonetaryAuthorizationOutcome.PROCEED,
                reasons=("some reason",),
            )

    def test_block_requires_at_least_one_reason(self) -> None:
        with self.assertRaises(ValueError):
            make_record(
                outcome=PortfolioMonetaryAuthorizationOutcome.BLOCK,
                reasons=(),
            )

    def test_block_with_reasons_accepted(self) -> None:
        record = make_block_record(reasons=("capital not usable", "exposure limit"))
        self.assertEqual(record.reasons, ("capital not usable", "exposure limit"))

    def test_reasons_order_preserved(self) -> None:
        record = make_block_record(reasons=("first", "second"))
        self.assertEqual(record.reasons, ("first", "second"))


class NoMonetarySemanticLeakageTests(unittest.TestCase):
    def test_record_has_no_forbidden_monetary_fields(self) -> None:
        record = make_record()
        field_names = {f.name for f in dataclasses.fields(record)}
        for forbidden in (
            "notional",
            "quantity",
            "amount",
            "exposure_total",
            "direction",
            "leverage",
            "margin",
            "fx",
            "venue",
            "order",
            "current",
            "latest",
        ):
            self.assertNotIn(forbidden, field_names)

    def test_ref_has_no_forbidden_monetary_fields(self) -> None:
        ref = make_ref()
        field_names = {f.name for f in dataclasses.fields(ref)}
        for forbidden in ("amount", "notional", "quantity", "leverage", "margin"):
            self.assertNotIn(forbidden, field_names)

    def test_module_exports_no_issuer_or_service(self) -> None:
        import portfolio_v1.monetary_authorization as module

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
            "Resolver",
            "Lookup",
        ):
            for name in module_names:
                self.assertNotIn(forbidden, name)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import portfolio_v1.monetary_authorization as module

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

    def _defined_function_names(self) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
        return names

    def test_module_is_stdlib_only(self) -> None:
        imported = self._imported_names()
        allowed = {"__future__", "dataclasses", "datetime", "enum"}
        for name in imported:
            self.assertIn(name, allowed, f"unexpected import: {name}")

    def test_no_cross_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "portfolio",
            "portfolio_v1.domain",
            "portfolio_v1.assessment",
            "portfolio_v1.exposure_snapshot",
            "portfolio_v1.monetary_admission_readiness",
            "risk",
            "models",
            "trade_orchestration",
            "execution",
            "research",
            "services",
            "api",
            "dashboard",
            "strategies",
            "market_data",
            "data_quality",
            "trend_context",
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
            "RiskSizingProposal",
            "AccountCapitalSnapshot",
            "PortfolioExposureSnapshot",
            "MonetaryAdmissionReadinessInput",
            "RiskResultRecord",
            "OrderIntent",
            "ExecutionOrder",
            "EntryTriggerProvenanceRecord",
            "MarketDataProvenanceRecord",
            "DataQualityPolicyProvenanceRecord",
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
        import portfolio_v1.monetary_authorization as module

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

    def test_no_resize_cap_backfill_reconstruction_functions(self) -> None:
        function_names = self._defined_function_names()
        for forbidden in (
            "resize",
            "cap",
            "clamp",
            "adjust",
            "backfill",
            "reconstruct",
            "repair",
            "resolve",
            "lookup",
            "infer",
            "select",
        ):
            for name in function_names:
                self.assertNotIn(forbidden, name.lower())

    def test_no_arithmetic_binary_operations(self) -> None:
        forbidden_ops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.BinOp) and isinstance(node.op, forbidden_ops):
                self.fail("unexpected arithmetic BinOp in monetary authorization module")

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
