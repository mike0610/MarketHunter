"""
MarketHunter

Tests for Entry Trigger Provenance Foundation - Slice 1
(strategies/entry_trigger_provenance.py).
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from strategies.base_strategy import BaseStrategy
from strategies.entry_trigger_provenance import (
    EntryTriggerBindingConflictError,
    EntryTriggerDeclaration,
    EntryTriggerEvidenceRef,
    EntryTriggerIdentity,
    EntryTriggerInvariantError,
    EntryTriggerParentReleaseMismatchError,
    EntryTriggerProvenanceDisposition,
    EntryTriggerProvenanceError,
    EntryTriggerProvenanceRecord,
    EntryTriggerProvenanceResult,
    EntryTriggerReference,
    validate_entry_trigger_binding,
)
from strategies.execution_binding import StrategyExecutionBinding
from strategies.registry_foundation import StrategyIdentity, StrategyReference, StrategyVersion
from strategies.runtime_release_manifest import StrategyReleaseDeclaration

AWARE_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 21, 12, 0)


def make_strategy_identity(**overrides) -> StrategyIdentity:
    kwargs = dict(
        strategy_id="strategy-1",
        authority_reference_kind="notion_page",
        authority_reference="page-123",
    )
    kwargs.update(overrides)
    return StrategyIdentity(**kwargs)


def make_strategy_reference(**overrides) -> StrategyReference:
    kwargs = dict(reference_kind="rules_doc", reference="doc-1")
    kwargs.update(overrides)
    return StrategyReference(**kwargs)


def make_strategy_version(**overrides) -> StrategyVersion:
    kwargs = dict(
        strategy_id="strategy-1",
        version="v1",
        observed_at=AWARE_NOW,
        supersedes_version=None,
        rules_references=(make_strategy_reference(),),
        implementation_references=(),
        evidence_references=(
            make_strategy_reference(reference_kind="evidence", reference="ev-1"),
        ),
    )
    kwargs.update(overrides)
    return StrategyVersion(**kwargs)


def make_strategy_release(**overrides) -> StrategyReleaseDeclaration:
    kwargs = dict(
        identity=make_strategy_identity(), version=make_strategy_version()
    )
    kwargs.update(overrides)
    return StrategyReleaseDeclaration(**kwargs)


class FakeStrategy(BaseStrategy):
    async def analyze(self, snapshot):
        return None


def make_binding(**overrides) -> StrategyExecutionBinding:
    kwargs = dict(implementation=FakeStrategy(), release=make_strategy_release())
    kwargs.update(overrides)
    return StrategyExecutionBinding(**kwargs)


def make_trigger_identity(**overrides) -> EntryTriggerIdentity:
    kwargs = dict(strategy_id="strategy-1", trigger_id="trigger-1")
    kwargs.update(overrides)
    return EntryTriggerIdentity(**kwargs)


def make_declaration(**overrides) -> EntryTriggerDeclaration:
    kwargs = dict(
        identity=make_trigger_identity(),
        opaque_version="tv1",
        strategy_release=make_strategy_release(),
    )
    kwargs.update(overrides)
    return EntryTriggerDeclaration(**kwargs)


def make_reference(**overrides) -> EntryTriggerReference:
    kwargs = dict(declaration=make_declaration())
    kwargs.update(overrides)
    return EntryTriggerReference(**kwargs)


def make_evidence_ref(**overrides) -> EntryTriggerEvidenceRef:
    kwargs = dict(source_id="source-1", evidence_id="ev-1")
    kwargs.update(overrides)
    return EntryTriggerEvidenceRef(**kwargs)


def make_record(**overrides) -> EntryTriggerProvenanceRecord:
    kwargs = dict(
        reference=make_reference(),
        symbol="BTCUSDT",
        market="spot",
        timeframe="1h",
        evidence_refs=(make_evidence_ref(),),
        available_at=AWARE_NOW,
    )
    kwargs.update(overrides)
    return EntryTriggerProvenanceRecord(**kwargs)


class ErrorTaxonomyTests(unittest.TestCase):
    def test_error_hierarchy(self) -> None:
        for error_cls in (
            EntryTriggerInvariantError,
            EntryTriggerParentReleaseMismatchError,
            EntryTriggerBindingConflictError,
        ):
            self.assertTrue(
                issubclass(error_cls, EntryTriggerProvenanceError)
            )

        self.assertTrue(issubclass(EntryTriggerProvenanceError, Exception))


class EntryTriggerIdentityTests(unittest.TestCase):
    def test_frozen(self) -> None:
        identity = make_trigger_identity()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            identity.trigger_id = "other"  # type: ignore[misc]

    def test_values_preserved_byte_for_byte(self) -> None:
        identity = make_trigger_identity(
            strategy_id="strategy-xyz", trigger_id="trigger-abc"
        )
        self.assertEqual(identity.strategy_id, "strategy-xyz")
        self.assertEqual(identity.trigger_id, "trigger-abc")

    def test_blank_strategy_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_trigger_identity(strategy_id="  ")

    def test_blank_trigger_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_trigger_identity(trigger_id="")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_trigger_identity(strategy_id=123)  # type: ignore[arg-type]


class EntryTriggerDeclarationTests(unittest.TestCase):
    def test_frozen(self) -> None:
        declaration = make_declaration()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            declaration.opaque_version = "other"  # type: ignore[misc]

    def test_opaque_version_preserved_byte_for_byte(self) -> None:
        declaration = make_declaration(opaque_version="tv-alpha-2")
        self.assertEqual(declaration.opaque_version, "tv-alpha-2")

    def test_blank_opaque_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_declaration(opaque_version="")

    def test_strategy_release_preserved_by_identity(self) -> None:
        release = make_strategy_release()
        declaration = make_declaration(
            identity=make_trigger_identity(strategy_id=release.identity.strategy_id),
            strategy_release=release,
        )
        self.assertIs(declaration.strategy_release, release)

    def test_wrong_identity_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_declaration(identity="not-an-identity")  # type: ignore[arg-type]

    def test_wrong_strategy_release_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_declaration(strategy_release="not-a-release")  # type: ignore[arg-type]

    def test_parent_strategy_id_mismatch_hard_fails(self) -> None:
        with self.assertRaises(EntryTriggerParentReleaseMismatchError):
            make_declaration(
                identity=make_trigger_identity(strategy_id="different-strategy"),
                strategy_release=make_strategy_release(),
            )

    def test_declaration_key_exact_tuple(self) -> None:
        declaration = make_declaration()
        self.assertEqual(
            declaration.declaration_key,
            ("strategy-1", "trigger-1", "v1", "tv1"),
        )

    def test_same_trigger_text_under_different_release_is_distinct(self) -> None:
        release_a = make_strategy_release()
        release_b = make_strategy_release(
            version=make_strategy_version(version="v2")
        )
        declaration_a = make_declaration(strategy_release=release_a)
        declaration_b = make_declaration(strategy_release=release_b)

        self.assertNotEqual(declaration_a, declaration_b)
        self.assertNotEqual(
            declaration_a.declaration_key, declaration_b.declaration_key
        )

    def test_equal_declarations_compare_equal(self) -> None:
        self.assertEqual(make_declaration(), make_declaration())


class EntryTriggerReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.declaration = make_declaration()  # type: ignore[misc]

    def test_declaration_preserved_by_identity(self) -> None:
        declaration = make_declaration()
        reference = make_reference(declaration=declaration)
        self.assertIs(reference.declaration, declaration)

    def test_identity_property_delegates_exactly(self) -> None:
        declaration = make_declaration()
        reference = make_reference(declaration=declaration)
        self.assertIs(reference.identity, declaration.identity)

    def test_opaque_version_property_delegates_exactly(self) -> None:
        declaration = make_declaration()
        reference = make_reference(declaration=declaration)
        self.assertEqual(reference.opaque_version, declaration.opaque_version)

    def test_strategy_release_property_delegates_exactly(self) -> None:
        declaration = make_declaration()
        reference = make_reference(declaration=declaration)
        self.assertIs(reference.strategy_release, declaration.strategy_release)

    def test_wrong_declaration_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_reference(declaration="not-a-declaration")  # type: ignore[arg-type]


class EntryTriggerEvidenceRefTests(unittest.TestCase):
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


class EntryTriggerProvenanceRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_scope_strings_preserved(self) -> None:
        record = make_record(symbol="ETHUSDT", market="futures", timeframe="4h")
        self.assertEqual(record.symbol, "ETHUSDT")
        self.assertEqual(record.market, "futures")
        self.assertEqual(record.timeframe, "4h")

    def test_blank_symbol_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(symbol="")

    def test_blank_market_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(market="  ")

    def test_blank_timeframe_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(timeframe="")

    def test_wrong_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(reference="not-a-reference")  # type: ignore[arg-type]

    def test_evidence_refs_must_be_tuple(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evidence_refs=[make_evidence_ref()])  # type: ignore[arg-type]

    def test_evidence_refs_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            make_record(evidence_refs=("not-evidence",))  # type: ignore[arg-type]

    def test_evidence_refs_order_preserved(self) -> None:
        ev1 = make_evidence_ref(evidence_id="ev-1")
        ev2 = make_evidence_ref(evidence_id="ev-2")
        record = make_record(evidence_refs=(ev1, ev2))
        self.assertEqual(record.evidence_refs, (ev1, ev2))

    def test_empty_evidence_tuple_permitted(self) -> None:
        record = make_record(evidence_refs=())
        self.assertEqual(record.evidence_refs, ())

    def test_duplicate_exact_evidence_ref_rejected(self) -> None:
        ev = make_evidence_ref()
        with self.assertRaises(EntryTriggerInvariantError):
            make_record(evidence_refs=(ev, ev))

    def test_duplicate_equal_but_distinct_evidence_ref_rejected(self) -> None:
        ev_a = make_evidence_ref()
        ev_b = make_evidence_ref()
        self.assertIsNot(ev_a, ev_b)
        with self.assertRaises(EntryTriggerInvariantError):
            make_record(evidence_refs=(ev_a, ev_b))

    def test_available_at_required_to_be_datetime(self) -> None:
        with self.assertRaises(TypeError):
            make_record(available_at="2026-08-21T12:00:00Z")  # type: ignore[arg-type]

    def test_available_at_must_be_timezone_aware(self) -> None:
        with self.assertRaises(ValueError):
            make_record(available_at=NAIVE_NOW)

    def test_available_at_preserved_exactly(self) -> None:
        record = make_record(available_at=AWARE_NOW)
        self.assertEqual(record.available_at, AWARE_NOW)


class EntryTriggerProvenanceDispositionTests(unittest.TestCase):
    def test_exact_four_members(self) -> None:
        self.assertEqual(
            {member.value for member in EntryTriggerProvenanceDisposition},
            {"KNOWN", "UNKNOWN", "UNAVAILABLE", "CONFLICT"},
        )


class EntryTriggerProvenanceResultTests(unittest.TestCase):
    def test_frozen(self) -> None:
        result = EntryTriggerProvenanceResult(
            disposition=EntryTriggerProvenanceDisposition.KNOWN,
            record=make_record(),
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.record = None  # type: ignore[misc]

    def test_known_requires_exactly_one_record(self) -> None:
        record = make_record()
        result = EntryTriggerProvenanceResult(
            disposition=EntryTriggerProvenanceDisposition.KNOWN, record=record
        )
        self.assertIs(result.record, record)

    def test_known_with_none_record_rejected(self) -> None:
        with self.assertRaises(EntryTriggerInvariantError):
            EntryTriggerProvenanceResult(
                disposition=EntryTriggerProvenanceDisposition.KNOWN, record=None
            )

    def test_unknown_requires_none_record(self) -> None:
        result = EntryTriggerProvenanceResult(
            disposition=EntryTriggerProvenanceDisposition.UNKNOWN, record=None
        )
        self.assertIsNone(result.record)

    def test_unknown_with_record_rejected(self) -> None:
        with self.assertRaises(EntryTriggerInvariantError):
            EntryTriggerProvenanceResult(
                disposition=EntryTriggerProvenanceDisposition.UNKNOWN,
                record=make_record(),
            )

    def test_unavailable_with_record_rejected(self) -> None:
        with self.assertRaises(EntryTriggerInvariantError):
            EntryTriggerProvenanceResult(
                disposition=EntryTriggerProvenanceDisposition.UNAVAILABLE,
                record=make_record(),
            )

    def test_conflict_with_record_rejected(self) -> None:
        with self.assertRaises(EntryTriggerInvariantError):
            EntryTriggerProvenanceResult(
                disposition=EntryTriggerProvenanceDisposition.CONFLICT,
                record=make_record(),
            )

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            EntryTriggerProvenanceResult(disposition="KNOWN", record=make_record())  # type: ignore[arg-type]

    def test_wrong_record_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            EntryTriggerProvenanceResult(
                disposition=EntryTriggerProvenanceDisposition.KNOWN,
                record="not-a-record",  # type: ignore[arg-type]
            )


class ValidateEntryTriggerBindingTests(unittest.TestCase):
    def test_matching_binding_reference_passes(self) -> None:
        release = make_strategy_release()
        binding = make_binding(release=release)
        reference = make_reference(declaration=make_declaration(strategy_release=release))
        self.assertIsNone(validate_entry_trigger_binding(reference, binding))

    def test_matching_binding_record_passes(self) -> None:
        release = make_strategy_release()
        binding = make_binding(release=release)
        record = make_record(
            reference=make_reference(
                declaration=make_declaration(strategy_release=release)
            )
        )
        self.assertIsNone(validate_entry_trigger_binding(record, binding))

    def test_mismatched_release_hard_conflicts(self) -> None:
        binding = make_binding(release=make_strategy_release())
        other_release = make_strategy_release(
            version=make_strategy_version(version="v2")
        )
        reference = make_reference(
            declaration=make_declaration(strategy_release=other_release)
        )
        with self.assertRaises(EntryTriggerBindingConflictError):
            validate_entry_trigger_binding(reference, binding)

    def test_equal_but_distinct_release_object_still_passes(self) -> None:
        release_a = make_strategy_release()
        release_b = make_strategy_release()
        self.assertIsNot(release_a, release_b)
        self.assertEqual(release_a, release_b)

        binding = make_binding(release=release_a)
        reference = make_reference(
            declaration=make_declaration(strategy_release=release_b)
        )
        self.assertIsNone(validate_entry_trigger_binding(reference, binding))

    def test_wrong_reference_or_record_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            validate_entry_trigger_binding("not-a-reference", make_binding())  # type: ignore[arg-type]

    def test_wrong_binding_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            validate_entry_trigger_binding(make_reference(), "not-a-binding")  # type: ignore[arg-type]

    def test_pure_no_mutation_or_result_fabrication(self) -> None:
        release = make_strategy_release()
        binding = make_binding(release=release)
        reference = make_reference(declaration=make_declaration(strategy_release=release))
        result = validate_entry_trigger_binding(reference, binding)
        self.assertIsNone(result)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import strategies.entry_trigger_provenance as module

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

    def test_module_is_stdlib_plus_narrow_strategy_domain_only(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "datetime",
            "enum",
            "strategies.execution_binding",
            "strategies.runtime_release_manifest",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_strategy_domain_imports_are_the_named_narrow_set_only(self) -> None:
        imported_names: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.ImportFrom) and node.module in (
                "strategies.execution_binding",
                "strategies.runtime_release_manifest",
            ):
                for alias in node.names:
                    imported_names.add(alias.name)

        self.assertEqual(
            imported_names,
            {"StrategyExecutionBinding", "StrategyReleaseDeclaration"},
        )

    def test_no_base_strategy_import(self) -> None:
        imported = self._imported_names()
        self.assertNotIn("strategies.base_strategy", imported)

    def test_no_other_cross_domain_imports(self) -> None:
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
            "trend_context",
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
            "Scanner",
            "Signal",
            "SignalContext",
            "CandidateProvenance",
            "SimulationEvent",
            "TrendContextRecord",
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
        import strategies.entry_trigger_provenance as module

        for forbidden in (
            "current",
            "latest",
            "nearest",
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

    def test_no_manifest_history_writer_issuer_surface(self) -> None:
        import strategies.entry_trigger_provenance as module

        module_names = {name for name in dir(module) if not name.startswith("_")}
        for forbidden in ("Manifest", "History", "Repository", "Issuer", "Writer"):
            for name in module_names:
                self.assertNotIn(forbidden, name)


if __name__ == "__main__":
    unittest.main()
