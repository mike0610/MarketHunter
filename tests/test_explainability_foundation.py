"""
MarketHunter

Tests for the Explainability Layer - Slice 1
(explainability/foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from explainability.foundation import (
    ExplanationAssessmentReason,
    ExplanationBindingAssessment,
    ExplanationDisposition,
    ExplanationEvidenceBinding,
    ExplanationEvidenceReference,
    ExplanationGeneratorReference,
    ExplanationRecord,
    ExplanationTargetBinding,
    ExplanationTargetReference,
    ExplanationUsability,
    assess_explanation_binding,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def make_target(**overrides) -> ExplanationTargetReference:
    kwargs = dict(
        target_domain="portfolio",
        target_type="monetary_admission_readiness",
        target_id="readiness-1",
        target_revision_or_version=None,
    )
    kwargs.update(overrides)
    return ExplanationTargetReference(**kwargs)


def make_evidence(**overrides) -> ExplanationEvidenceReference:
    kwargs = dict(
        source_kind="risk_result",
        source_id="risk-1",
        source_revision_or_version="1",
    )
    kwargs.update(overrides)
    return ExplanationEvidenceReference(**kwargs)


def make_generator(**overrides) -> ExplanationGeneratorReference:
    kwargs = dict(
        generator_kind="human_analyst",
        generator_id="analyst-1",
        generator_version=None,
    )
    kwargs.update(overrides)
    return ExplanationGeneratorReference(**kwargs)


def make_record(**overrides) -> ExplanationRecord:
    kwargs = dict(
        explanation_id="explanation-1",
        revision=1,
        generated_at=AWARE_NOW,
        supersedes_revision=None,
        target=make_target(),
        evidence_references=(make_evidence(),),
        generator_reference=None,
    )
    kwargs.update(overrides)
    return ExplanationRecord(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in ExplanationDisposition},
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
            {m.value for m in ExplanationUsability},
            {"USABLE", "NOT_USABLE"},
        )

    def test_reason_values(self) -> None:
        self.assertEqual(
            {m.value for m in ExplanationAssessmentReason},
            {
                "TARGET_UNRESOLVED",
                "TARGET_AMBIGUOUS",
                "TARGET_DISPOSITION_NOT_USABLE",
                "TARGET_CURRENT_REQUIRED",
                "EVIDENCE_UNRESOLVED",
                "EVIDENCE_AMBIGUOUS",
                "EVIDENCE_DISPOSITION_NOT_USABLE",
                "EVIDENCE_CURRENT_REQUIRED",
                "PREDECESSOR_UNRESOLVED",
                "PREDECESSOR_AMBIGUOUS",
                "CROSS_EXPLANATION_SUPERSESSION",
            },
        )


class ExplanationTargetReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        target = make_target()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            target.target_id = "other"  # type: ignore[misc]

    def test_blank_target_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_target(target_id="   ")

    def test_optional_revision_accepted_none(self) -> None:
        target = make_target(target_revision_or_version=None)
        self.assertIsNone(target.target_revision_or_version)

    def test_blank_optional_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_target(target_revision_or_version="  ")


class ExplanationEvidenceReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = make_evidence()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.source_id = "other"  # type: ignore[misc]

    def test_blank_source_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_evidence(source_id="")


class ExplanationGeneratorReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        generator = make_generator()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            generator.generator_id = "other"  # type: ignore[misc]

    def test_blank_generator_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_generator(generator_kind="")


class ExplanationRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.revision = 2  # type: ignore[misc]

    def test_blank_explanation_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(explanation_id="   ")

    def test_non_positive_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(revision=0)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(revision=True)  # type: ignore[arg-type]

    def test_naive_generated_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(generated_at=datetime(2026, 8, 16, 12, 0))

    def test_valid_supersession_accepted(self) -> None:
        record = make_record(revision=2, supersedes_revision=1)
        self.assertEqual(record.supersedes_revision, 1)

    def test_supersedes_revision_cannot_self_reference(self) -> None:
        with self.assertRaises(ValueError):
            make_record(revision=1, supersedes_revision=1)

    def test_non_positive_supersedes_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(revision=2, supersedes_revision=0)

    def test_evidence_references_must_be_nonempty(self) -> None:
        with self.assertRaises(ValueError):
            make_record(evidence_references=())

    def test_evidence_references_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evidence_references=[make_evidence()])  # type: ignore[arg-type]

    def test_duplicate_evidence_references_rejected(self) -> None:
        evidence = make_evidence()
        with self.assertRaises(ValueError):
            make_record(evidence_references=(evidence, evidence))

    def test_exact_target_and_evidence_preserved(self) -> None:
        target = make_target(target_id="readiness-42")
        evidence = make_evidence(source_id="risk-42")
        record = make_record(target=target, evidence_references=(evidence,))

        self.assertIs(record.target, target)
        self.assertEqual(record.evidence_references, (evidence,))

    def test_generator_reference_optional_none_accepted(self) -> None:
        record = make_record(generator_reference=None)
        self.assertIsNone(record.generator_reference)

    def test_generator_reference_preserved_when_supplied(self) -> None:
        generator = make_generator()
        record = make_record(generator_reference=generator)
        self.assertIs(record.generator_reference, generator)

    def test_wrong_generator_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(generator_reference="not-a-generator")  # type: ignore[arg-type]


class ExplanationBindingAssessmentTests(unittest.TestCase):
    def test_usable_cannot_carry_reasons(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationBindingAssessment(
                usability=ExplanationUsability.USABLE,
                reasons=(ExplanationAssessmentReason.TARGET_UNRESOLVED,),
            )

    def test_not_usable_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            ExplanationBindingAssessment(
                usability=ExplanationUsability.NOT_USABLE, reasons=()
            )


class AssessExplanationBindingTests(unittest.TestCase):
    def test_valid_current_binding_is_usable(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.USABLE)
        self.assertEqual(result.reasons, ())

    def test_target_unresolved_fails_closed(self) -> None:
        record = make_record()

        result = assess_explanation_binding(
            record,
            (record,),
            (),
            (
                ExplanationEvidenceBinding(
                    record.evidence_references[0], ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.TARGET_UNRESOLVED, result.reasons
        )

    def test_target_ambiguous_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (
                ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),
                ExplanationTargetBinding(target, ExplanationDisposition.STALE),
            ),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.TARGET_AMBIGUOUS, result.reasons
        )

    def test_target_non_usable_disposition_fails_closed(self) -> None:
        for disposition in (
            ExplanationDisposition.UNKNOWN,
            ExplanationDisposition.UNAVAILABLE,
            ExplanationDisposition.STALE,
            ExplanationDisposition.CONFLICT,
            ExplanationDisposition.SOURCE_CHANGED,
        ):
            with self.subTest(disposition=disposition):
                target = make_target()
                evidence = make_evidence()
                record = make_record(
                    target=target, evidence_references=(evidence,)
                )

                result = assess_explanation_binding(
                    record,
                    (record,),
                    (ExplanationTargetBinding(target, disposition),),
                    (
                        ExplanationEvidenceBinding(
                            evidence, ExplanationDisposition.CURRENT
                        ),
                    ),
                    False,
                )
                self.assertEqual(
                    result.usability, ExplanationUsability.NOT_USABLE
                )
                self.assertIn(
                    ExplanationAssessmentReason.TARGET_DISPOSITION_NOT_USABLE,
                    result.reasons,
                )

    def test_target_superseded_historical_usable_when_not_required(
        self,
    ) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (
                ExplanationTargetBinding(
                    target, ExplanationDisposition.SUPERSEDED
                ),
            ),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            False,
        )
        self.assertEqual(result.usability, ExplanationUsability.USABLE)

    def test_target_superseded_fails_when_current_required(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (
                ExplanationTargetBinding(
                    target, ExplanationDisposition.SUPERSEDED
                ),
            ),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.TARGET_CURRENT_REQUIRED, result.reasons
        )

    def test_evidence_unresolved_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.EVIDENCE_UNRESOLVED, result.reasons
        )

    def test_evidence_ambiguous_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.STALE
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.EVIDENCE_AMBIGUOUS, result.reasons
        )

    def test_evidence_non_usable_disposition_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CONFLICT
                ),
            ),
            False,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.EVIDENCE_DISPOSITION_NOT_USABLE,
            result.reasons,
        )

    def test_evidence_superseded_fails_when_current_required(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))

        result = assess_explanation_binding(
            record,
            (record,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.SUPERSEDED
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.EVIDENCE_CURRENT_REQUIRED,
            result.reasons,
        )

    def test_valid_same_explanation_predecessor_accepted(self) -> None:
        target = make_target()
        evidence = make_evidence()
        v1 = make_record(
            explanation_id="explanation-1",
            revision=1,
            target=target,
            evidence_references=(evidence,),
        )
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        result = assess_explanation_binding(
            v2,
            (v1, v2),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.USABLE)

    def test_predecessor_unresolved_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        result = assess_explanation_binding(
            v2,
            (v2,),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.PREDECESSOR_UNRESOLVED, result.reasons
        )

    def test_predecessor_ambiguous_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        v1a = make_record(
            explanation_id="explanation-1",
            revision=1,
            target=target,
            evidence_references=(evidence,),
        )
        v1b = make_record(
            explanation_id="explanation-1",
            revision=1,
            target=target,
            evidence_references=(make_evidence(source_id="risk-2"),),
        )
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        result = assess_explanation_binding(
            v2,
            (v1a, v1b, v2),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.PREDECESSOR_AMBIGUOUS, result.reasons
        )

    def test_cross_explanation_supersession_fails_closed(self) -> None:
        target = make_target()
        evidence = make_evidence()
        other_explanation_v1 = make_record(
            explanation_id="explanation-2",
            revision=1,
            target=target,
            evidence_references=(evidence,),
        )
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        result = assess_explanation_binding(
            v2,
            (other_explanation_v1, v2),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.NOT_USABLE)
        self.assertIn(
            ExplanationAssessmentReason.CROSS_EXPLANATION_SUPERSESSION,
            result.reasons,
        )

    def test_historical_predecessor_remains_valid(self) -> None:
        target = make_target()
        evidence = make_evidence()
        v1 = make_record(
            explanation_id="explanation-1",
            revision=1,
            target=target,
            evidence_references=(evidence,),
        )
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        # v1 is queried directly; it remains a valid historical
        # record even though v2 (its successor) exists.
        result = assess_explanation_binding(
            v1,
            (v1, v2),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            False,
        )
        self.assertEqual(result.usability, ExplanationUsability.USABLE)

    def test_successor_presence_does_not_infer_disposition(self) -> None:
        # v1 has a successor (v2) but v1's own target disposition is
        # explicitly CURRENT here - the assessment must trust the
        # caller-supplied disposition, not infer SUPERSEDED merely
        # because a successor record exists.
        target = make_target()
        evidence = make_evidence()
        v1 = make_record(
            explanation_id="explanation-1",
            revision=1,
            target=target,
            evidence_references=(evidence,),
        )
        v2 = make_record(
            explanation_id="explanation-1",
            revision=2,
            supersedes_revision=1,
            target=target,
            evidence_references=(evidence,),
        )

        result = assess_explanation_binding(
            v1,
            (v1, v2),
            (ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),),
            (
                ExplanationEvidenceBinding(
                    evidence, ExplanationDisposition.CURRENT
                ),
            ),
            True,
        )
        self.assertEqual(result.usability, ExplanationUsability.USABLE)

    def test_deterministic_replay(self) -> None:
        target = make_target()
        evidence = make_evidence()
        record = make_record(target=target, evidence_references=(evidence,))
        target_bindings = (
            ExplanationTargetBinding(target, ExplanationDisposition.CURRENT),
        )
        evidence_bindings = (
            ExplanationEvidenceBinding(evidence, ExplanationDisposition.CURRENT),
        )

        first = assess_explanation_binding(
            record, (record,), target_bindings, evidence_bindings, True
        )
        second = assess_explanation_binding(
            record, (record,), target_bindings, evidence_bindings, True
        )
        self.assertEqual(first.usability, second.usability)
        self.assertEqual(first.reasons, second.reasons)

    def test_wrong_record_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_explanation_binding(
                "not-a-record",  # type: ignore[arg-type]
                (),
                (),
                (),
                True,
            )

    def test_wrong_require_current_type_rejected(self) -> None:
        record = make_record()
        with self.assertRaises(TypeError):
            assess_explanation_binding(
                record,
                (record,),
                (),
                (),
                "true",  # type: ignore[arg-type]
            )


class ScopeDisciplineTests(unittest.TestCase):
    def _imported_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import explainability.foundation as module

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

        import explainability.foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only_no_source_domain_imports(self) -> None:
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

    def test_no_source_domain_object_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "StrategyIdentity",
            "StrategyVersion",
            "RiskSizingProposal",
            "RiskResultRecord",
            "PortfolioDecision",
            "ResearchTrade",
            "ExecutionOrder",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_persistence_filesystem_network_or_llm_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "sqlite3",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "fastapi",
            "httpx",
            "uuid",
            "random",
            "openai",
            "anthropic",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_now_or_random_usage(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("uuid4", referenced)

    def test_no_latest_or_current_selector_exported(self) -> None:
        import explainability.foundation as module

        self.assertFalse(hasattr(module, "latest_explanation"))
        self.assertFalse(hasattr(module, "current_explanation"))
        self.assertFalse(hasattr(module, "get_current_explanation"))

    def test_no_free_text_or_claim_fields_on_record(self) -> None:
        field_names = {f.name for f in dataclasses.fields(ExplanationRecord)}
        for forbidden in (
            "body",
            "text",
            "claim",
            "confidence",
            "recommendation",
            "reason",
        ):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
