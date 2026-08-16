"""
MarketHunter

Tests for the Strategy Registry + Versioning - Slice 1
(strategies/registry_foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from strategies.registry_foundation import (
    StrategyAssessmentReason,
    StrategyDisposition,
    StrategyIdentity,
    StrategyReference,
    StrategyUsability,
    StrategyVersion,
    StrategyVersionAssessment,
    assess_strategy_version_lineage,
)

AWARE_NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def make_identity(**overrides) -> StrategyIdentity:
    kwargs = dict(
        strategy_id="strategy-1",
        authority_reference_kind="notion_page",
        authority_reference="notion-strategy-1",
    )
    kwargs.update(overrides)
    return StrategyIdentity(**kwargs)


def make_reference(**overrides) -> StrategyReference:
    kwargs = dict(reference_kind="rules_doc", reference="rules-doc-1")
    kwargs.update(overrides)
    return StrategyReference(**kwargs)


def make_version(**overrides) -> StrategyVersion:
    kwargs = dict(
        strategy_id="strategy-1",
        version="v-alpha-not-semver",
        observed_at=AWARE_NOW,
        supersedes_version=None,
        rules_references=(make_reference(),),
        implementation_references=(),
        evidence_references=(make_reference(reference_kind="evidence", reference="ev-1"),),
    )
    kwargs.update(overrides)
    return StrategyVersion(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in StrategyDisposition},
            {
                "CURRENT",
                "UNKNOWN",
                "UNAVAILABLE",
                "CONFLICT",
                "SUPERSEDED",
                "SOURCE_CHANGED",
            },
        )

    def test_usability_values(self) -> None:
        self.assertEqual(
            {m.value for m in StrategyUsability},
            {"USABLE", "NOT_USABLE"},
        )

    def test_reason_values(self) -> None:
        self.assertEqual(
            {m.value for m in StrategyAssessmentReason},
            {
                "IDENTITY_DISPOSITION_NOT_USABLE",
                "VERSION_DISPOSITION_NOT_USABLE",
                "CURRENT_VERSION_REQUIRED",
                "IDENTITY_UNRESOLVED",
                "IDENTITY_AMBIGUOUS",
                "VERSION_IDENTITY_MISMATCH",
                "VERSION_UNRESOLVED",
                "VERSION_AMBIGUOUS",
                "PREDECESSOR_UNRESOLVED",
                "PREDECESSOR_AMBIGUOUS",
                "CROSS_STRATEGY_SUPERSESSION",
            },
        )


class StrategyIdentityTests(unittest.TestCase):
    def test_frozen(self) -> None:
        identity = make_identity()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            identity.strategy_id = "other"  # type: ignore[misc]

    def test_blank_strategy_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_identity(strategy_id="   ")

    def test_blank_authority_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_identity(authority_reference="")


class StrategyReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.reference = "other"  # type: ignore[misc]

    def test_blank_reference_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_reference(reference="  ")


class StrategyVersionTests(unittest.TestCase):
    def test_frozen(self) -> None:
        version = make_version()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            version.version = "other"  # type: ignore[misc]

    def test_naive_observed_at_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_version(observed_at=datetime(2026, 8, 16, 12, 0))

    def test_opaque_version_accepted_no_semver_required(self) -> None:
        version = make_version(version="not-a-semver-string-at-all-2026")
        self.assertEqual(version.version, "not-a-semver-string-at-all-2026")

    def test_rules_references_must_be_nonempty(self) -> None:
        with self.assertRaises(ValueError):
            make_version(rules_references=())

    def test_evidence_references_must_be_nonempty(self) -> None:
        with self.assertRaises(ValueError):
            make_version(evidence_references=())

    def test_implementation_references_empty_allowed(self) -> None:
        version = make_version(implementation_references=())
        self.assertEqual(version.implementation_references, ())

    def test_rules_references_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_version(rules_references=[make_reference()])  # type: ignore[arg-type]

    def test_duplicate_rules_references_rejected(self) -> None:
        ref = make_reference()
        with self.assertRaises(ValueError):
            make_version(rules_references=(ref, ref))

    def test_duplicate_evidence_references_rejected(self) -> None:
        ref = make_reference(reference_kind="evidence", reference="ev-1")
        with self.assertRaises(ValueError):
            make_version(evidence_references=(ref, ref))

    def test_blank_supersedes_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_version(supersedes_version="   ")

    def test_supersedes_version_cannot_self_reference(self) -> None:
        with self.assertRaises(ValueError):
            make_version(version="v1", supersedes_version="v1")

    def test_valid_supersedes_version_accepted(self) -> None:
        version = make_version(version="v2", supersedes_version="v1")
        self.assertEqual(version.supersedes_version, "v1")


class StrategyVersionAssessmentTests(unittest.TestCase):
    def test_usable_cannot_carry_reasons(self) -> None:
        with self.assertRaises(ValueError):
            StrategyVersionAssessment(
                usability=StrategyUsability.USABLE,
                reasons=(StrategyAssessmentReason.IDENTITY_UNRESOLVED,),
            )

    def test_not_usable_requires_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            StrategyVersionAssessment(
                usability=StrategyUsability.NOT_USABLE, reasons=()
            )


class AssessStrategyVersionLineageTests(unittest.TestCase):
    def test_valid_current_lineage_is_usable(self) -> None:
        identity = make_identity()
        version = make_version()

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.USABLE)
        self.assertEqual(result.reasons, ())

    def test_valid_same_strategy_predecessor_accepted(self) -> None:
        identity = make_identity()
        v1 = make_version(version="v1")
        v2 = make_version(version="v2", supersedes_version="v1")

        result = assess_strategy_version_lineage(
            identity,
            v2,
            (identity,),
            (v1, v2),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.USABLE)

    def test_historical_version_remains_valid_after_successor(self) -> None:
        identity = make_identity()
        v1 = make_version(version="v1")
        v2 = make_version(version="v2", supersedes_version="v1")

        # v1 is now historically superseded but its own record is
        # still a valid, usable historical reference when currentness
        # is not required.
        result = assess_strategy_version_lineage(
            identity,
            v1,
            (identity,),
            (v1, v2),
            StrategyDisposition.CURRENT,
            StrategyDisposition.SUPERSEDED,
            False,
        )
        self.assertEqual(result.usability, StrategyUsability.USABLE)

    def test_superseded_historical_but_current_required_fails(self) -> None:
        identity = make_identity()
        v1 = make_version(version="v1")

        result = assess_strategy_version_lineage(
            identity,
            v1,
            (identity,),
            (v1,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.SUPERSEDED,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.CURRENT_VERSION_REQUIRED, result.reasons
        )

    def test_successor_presence_does_not_infer_currentness(self) -> None:
        # v1 has a successor (v2) but v1's own disposition is
        # explicitly CURRENT here - the assessment must trust the
        # caller-supplied disposition, not infer SUPERSEDED merely
        # because a successor exists in the versions collection.
        identity = make_identity()
        v1 = make_version(version="v1")
        v2 = make_version(version="v2", supersedes_version="v1")

        result = assess_strategy_version_lineage(
            identity,
            v1,
            (identity,),
            (v1, v2),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.USABLE)

    def test_non_current_identity_disposition_fails(self) -> None:
        for disposition in StrategyDisposition:
            if disposition is StrategyDisposition.CURRENT:
                continue
            with self.subTest(disposition=disposition):
                identity = make_identity()
                version = make_version()
                result = assess_strategy_version_lineage(
                    identity,
                    version,
                    (identity,),
                    (version,),
                    disposition,
                    StrategyDisposition.CURRENT,
                    True,
                )
                self.assertEqual(
                    result.usability, StrategyUsability.NOT_USABLE
                )
                self.assertIn(
                    StrategyAssessmentReason.IDENTITY_DISPOSITION_NOT_USABLE,
                    result.reasons,
                )

    def test_non_current_non_superseded_version_disposition_fails(
        self,
    ) -> None:
        for disposition in (
            StrategyDisposition.UNKNOWN,
            StrategyDisposition.UNAVAILABLE,
            StrategyDisposition.CONFLICT,
            StrategyDisposition.SOURCE_CHANGED,
        ):
            with self.subTest(disposition=disposition):
                identity = make_identity()
                version = make_version()
                result = assess_strategy_version_lineage(
                    identity,
                    version,
                    (identity,),
                    (version,),
                    StrategyDisposition.CURRENT,
                    disposition,
                    False,
                )
                self.assertEqual(
                    result.usability, StrategyUsability.NOT_USABLE
                )
                self.assertIn(
                    StrategyAssessmentReason.VERSION_DISPOSITION_NOT_USABLE,
                    result.reasons,
                )

    def test_identity_unresolved_fails_closed(self) -> None:
        identity = make_identity()
        version = make_version()

        result = assess_strategy_version_lineage(
            identity,
            version,
            (),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.IDENTITY_UNRESOLVED, result.reasons
        )

    def test_identity_ambiguous_fails_closed(self) -> None:
        identity = make_identity()
        duplicate_identity = make_identity(
            authority_reference_kind="other_kind", authority_reference="other-ref"
        )
        version = make_version()

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity, duplicate_identity),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.IDENTITY_AMBIGUOUS, result.reasons
        )

    def test_version_identity_mismatch_fails_closed(self) -> None:
        identity = make_identity(strategy_id="strategy-1")
        version = make_version(strategy_id="strategy-2")

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.VERSION_IDENTITY_MISMATCH, result.reasons
        )

    def test_version_unresolved_fails_closed(self) -> None:
        identity = make_identity()
        version = make_version()

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.VERSION_UNRESOLVED, result.reasons
        )

    def test_version_ambiguous_fails_closed(self) -> None:
        identity = make_identity()
        version = make_version()
        duplicate_version = make_version(
            rules_references=(make_reference(reference="rules-doc-2"),)
        )

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version, duplicate_version),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.VERSION_AMBIGUOUS, result.reasons
        )

    def test_predecessor_unresolved_fails_closed(self) -> None:
        identity = make_identity()
        version = make_version(version="v2", supersedes_version="v1")

        result = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.PREDECESSOR_UNRESOLVED, result.reasons
        )

    def test_predecessor_ambiguous_fails_closed(self) -> None:
        identity = make_identity()
        v1a = make_version(version="v1")
        v1b = make_version(
            version="v1",
            rules_references=(make_reference(reference="rules-doc-2"),),
        )
        v2 = make_version(version="v2", supersedes_version="v1")

        result = assess_strategy_version_lineage(
            identity,
            v2,
            (identity,),
            (v1a, v1b, v2),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.PREDECESSOR_AMBIGUOUS, result.reasons
        )

    def test_cross_strategy_supersession_fails_closed(self) -> None:
        identity = make_identity(strategy_id="strategy-1")
        other_identity = make_identity(
            strategy_id="strategy-2",
            authority_reference="notion-strategy-2",
        )
        other_strategy_v1 = make_version(
            strategy_id="strategy-2", version="v1"
        )
        v2 = make_version(
            strategy_id="strategy-1", version="v2", supersedes_version="v1"
        )

        result = assess_strategy_version_lineage(
            identity,
            v2,
            (identity, other_identity),
            (other_strategy_v1, v2),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(result.usability, StrategyUsability.NOT_USABLE)
        self.assertIn(
            StrategyAssessmentReason.CROSS_STRATEGY_SUPERSESSION,
            result.reasons,
        )

    def test_deterministic_replay(self) -> None:
        identity = make_identity()
        version = make_version()

        first = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        second = assess_strategy_version_lineage(
            identity,
            version,
            (identity,),
            (version,),
            StrategyDisposition.CURRENT,
            StrategyDisposition.CURRENT,
            True,
        )
        self.assertEqual(first.usability, second.usability)
        self.assertEqual(first.reasons, second.reasons)

    def test_wrong_identity_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_strategy_version_lineage(
                "not-an-identity",  # type: ignore[arg-type]
                make_version(),
                (),
                (),
                StrategyDisposition.CURRENT,
                StrategyDisposition.CURRENT,
                True,
            )

    def test_wrong_require_current_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_strategy_version_lineage(
                make_identity(),
                make_version(),
                (make_identity(),),
                (make_version(),),
                StrategyDisposition.CURRENT,
                StrategyDisposition.CURRENT,
                "true",  # type: ignore[arg-type]
            )


class ScopeDisciplineTests(unittest.TestCase):
    def _imported_names(self) -> set[str]:
        import ast
        from pathlib import Path

        import strategies.registry_foundation as module

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

        import strategies.registry_foundation as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only_no_cross_domain_imports(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = ("__future__", "dataclasses", "datetime", "enum")
        for name in imported:
            self.assertTrue(
                any(name == p or name.startswith(p + ".") for p in allowed_prefixes),
                f"unexpected import: {name}",
            )

    def test_no_base_strategy_or_name_inference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("BaseStrategy", referenced)
        self.assertNotIn("__class__", referenced)
        self.assertNotIn("__module__", referenced)
        self.assertNotIn("__name__", referenced)

    def test_no_research_or_risk_conflation(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("ResearchTrade", referenced)
        self.assertNotIn("IdentityState", referenced)
        self.assertNotIn("ReferenceState", referenced)
        self.assertNotIn("RiskSizingProposal", referenced)

    def test_no_persistence_filesystem_or_wall_clock_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "sqlite3",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "fastapi",
            "uuid",
            "random",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_now_or_random_usage(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("uuid4", referenced)

    def test_no_sort_or_latest_selector_exported(self) -> None:
        import strategies.registry_foundation as module

        self.assertFalse(hasattr(module, "get_current_strategy"))
        self.assertFalse(hasattr(module, "latest_version"))
        self.assertFalse(hasattr(module, "current_version"))


if __name__ == "__main__":
    unittest.main()
