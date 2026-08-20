"""
MarketHunter

Tests for Strategy Runtime Release Authority Foundation
(strategies/runtime_release_manifest.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timezone

from strategies.registry_foundation import StrategyIdentity, StrategyReference, StrategyVersion
from strategies.runtime_release_manifest import (
    STRATEGY_RELEASE_MANIFEST,
    StrategyReleaseConflictError,
    StrategyReleaseDeclaration,
    StrategyReleaseIdentityMismatchError,
    StrategyReleaseManifest,
    StrategyReleaseManifestError,
    StrategyReleaseNotFoundError,
)

AWARE_NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def make_identity(**overrides) -> StrategyIdentity:
    kwargs = dict(
        strategy_id="strategy-1",
        authority_reference_kind="notion_page",
        authority_reference="page-123",
    )
    kwargs.update(overrides)
    return StrategyIdentity(**kwargs)


def make_reference(**overrides) -> StrategyReference:
    kwargs = dict(reference_kind="rules_doc", reference="doc-1")
    kwargs.update(overrides)
    return StrategyReference(**kwargs)


def make_version(**overrides) -> StrategyVersion:
    kwargs = dict(
        strategy_id="strategy-1",
        version="v1",
        observed_at=AWARE_NOW,
        supersedes_version=None,
        rules_references=(make_reference(),),
        implementation_references=(),
        evidence_references=(make_reference(reference_kind="evidence", reference="ev-1"),),
    )
    kwargs.update(overrides)
    return StrategyVersion(**kwargs)


def make_declaration(**overrides) -> StrategyReleaseDeclaration:
    kwargs = dict(identity=make_identity(), version=make_version())
    kwargs.update(overrides)
    return StrategyReleaseDeclaration(**kwargs)


class ErrorTaxonomyTests(unittest.TestCase):
    def test_error_hierarchy(self) -> None:
        self.assertTrue(
            issubclass(StrategyReleaseIdentityMismatchError, StrategyReleaseManifestError)
        )
        self.assertTrue(
            issubclass(StrategyReleaseConflictError, StrategyReleaseManifestError)
        )
        self.assertTrue(
            issubclass(StrategyReleaseNotFoundError, StrategyReleaseManifestError)
        )
        self.assertTrue(issubclass(StrategyReleaseManifestError, Exception))


class StrategyReleaseDeclarationTests(unittest.TestCase):
    def test_frozen(self) -> None:
        declaration = make_declaration()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            declaration.identity = make_identity()  # type: ignore[misc]

    def test_matching_identity_accepted(self) -> None:
        declaration = make_declaration()
        self.assertEqual(declaration.release_key, ("strategy-1", "v1"))

    def test_identity_version_mismatch_rejected(self) -> None:
        mismatched_version = make_version(strategy_id="strategy-2")
        with self.assertRaises(StrategyReleaseIdentityMismatchError):
            StrategyReleaseDeclaration(identity=make_identity(), version=mismatched_version)

    def test_wrong_identity_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyReleaseDeclaration(identity="not-an-identity", version=make_version())  # type: ignore[arg-type]

    def test_wrong_version_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyReleaseDeclaration(identity=make_identity(), version="not-a-version")  # type: ignore[arg-type]

    def test_release_key_uses_opaque_version_string(self) -> None:
        for opaque_version in ("v2", "v10", "alpha", "2026.08.19-rc1"):
            with self.subTest(version=opaque_version):
                declaration = make_declaration(
                    version=make_version(version=opaque_version)
                )
                self.assertEqual(
                    declaration.release_key, ("strategy-1", opaque_version)
                )

    def test_version_governed_references_preserved_by_identity(self) -> None:
        version = make_version()
        declaration = make_declaration(version=version)
        self.assertIs(declaration.version, version)
        self.assertEqual(declaration.version.rules_references, version.rules_references)
        self.assertEqual(declaration.version.evidence_references, version.evidence_references)


class StrategyReleaseManifestTests(unittest.TestCase):
    def test_frozen(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            manifest.declarations = (make_declaration(),)  # type: ignore[misc]

    def test_empty_manifest_accepted(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        self.assertEqual(manifest.declarations, ())

    def test_wrong_declarations_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyReleaseManifest(declarations=[make_declaration()])  # type: ignore[arg-type]

    def test_wrong_declarations_element_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyReleaseManifest(declarations=("not-a-declaration",))  # type: ignore[arg-type]

    def test_two_historical_versions_of_same_strategy_addressable(self) -> None:
        v1 = make_declaration(version=make_version(version="v1"))
        v2 = make_declaration(
            version=make_version(version="v2", supersedes_version="v1")
        )
        manifest = StrategyReleaseManifest(declarations=(v1, v2))

        self.assertEqual(manifest.get_exact("strategy-1", "v1"), v1)
        self.assertEqual(manifest.get_exact("strategy-1", "v2"), v2)

    def test_identical_duplicate_declaration_idempotent(self) -> None:
        declaration = make_declaration()
        manifest = StrategyReleaseManifest(declarations=(declaration, declaration))
        self.assertEqual(manifest.get_exact("strategy-1", "v1"), declaration)

    def test_equal_but_distinct_duplicate_declaration_idempotent(self) -> None:
        first = make_declaration()
        second = make_declaration()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)

        manifest = StrategyReleaseManifest(declarations=(first, second))
        self.assertEqual(manifest.get_exact("strategy-1", "v1"), first)

    def test_same_key_different_payload_hard_conflict(self) -> None:
        first = make_declaration(
            version=make_version(observed_at=AWARE_NOW)
        )
        conflicting = make_declaration(
            version=make_version(
                observed_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
            )
        )
        with self.assertRaises(StrategyReleaseConflictError):
            StrategyReleaseManifest(declarations=(first, conflicting))

    def test_get_exact_unknown_returns_none(self) -> None:
        manifest = StrategyReleaseManifest(declarations=(make_declaration(),))
        self.assertIsNone(manifest.get_exact("strategy-1", "v99"))
        self.assertIsNone(manifest.get_exact("unknown-strategy", "v1"))

    def test_require_exact_unknown_raises(self) -> None:
        manifest = StrategyReleaseManifest(declarations=(make_declaration(),))
        with self.assertRaises(StrategyReleaseNotFoundError):
            manifest.require_exact("strategy-1", "v99")

    def test_require_exact_known_returns_declaration(self) -> None:
        declaration = make_declaration()
        manifest = StrategyReleaseManifest(declarations=(declaration,))
        self.assertEqual(manifest.require_exact("strategy-1", "v1"), declaration)

    def test_versions_never_ordered_v2_before_v10(self) -> None:
        # v10 and v2 as opaque text - lexicographic/SemVer ordering
        # would put "v10" before "v2"; this manifest must never rely
        # on or expose any such ordering.
        v2 = make_declaration(version=make_version(version="v2"))
        v10 = make_declaration(
            version=make_version(version="v10", supersedes_version="v2")
        )
        manifest = StrategyReleaseManifest(declarations=(v2, v10))

        self.assertEqual(manifest.get_exact("strategy-1", "v2"), v2)
        self.assertEqual(manifest.get_exact("strategy-1", "v10"), v10)
        self.assertFalse(hasattr(manifest, "latest"))
        self.assertFalse(hasattr(manifest, "current"))

    def test_alpha_version_addressable_as_opaque_text(self) -> None:
        declaration = make_declaration(version=make_version(version="alpha"))
        manifest = StrategyReleaseManifest(declarations=(declaration,))
        self.assertEqual(manifest.get_exact("strategy-1", "alpha"), declaration)

    def test_distinct_strategies_never_collide(self) -> None:
        strategy_a = make_declaration(
            identity=make_identity(strategy_id="strategy-a"),
            version=make_version(strategy_id="strategy-a"),
        )
        strategy_b = make_declaration(
            identity=make_identity(strategy_id="strategy-b"),
            version=make_version(strategy_id="strategy-b"),
        )
        manifest = StrategyReleaseManifest(declarations=(strategy_a, strategy_b))

        self.assertEqual(manifest.get_exact("strategy-a", "v1"), strategy_a)
        self.assertEqual(manifest.get_exact("strategy-b", "v1"), strategy_b)

    def test_blank_strategy_id_lookup_rejected(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        with self.assertRaises(ValueError):
            manifest.get_exact("  ", "v1")

    def test_blank_version_lookup_rejected(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        with self.assertRaises(ValueError):
            manifest.get_exact("strategy-1", "  ")

    def test_wrong_type_lookup_rejected(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        with self.assertRaises(TypeError):
            manifest.get_exact(123, "v1")  # type: ignore[arg-type]

    def test_no_current_latest_nearest_selector_methods(self) -> None:
        manifest = StrategyReleaseManifest(declarations=())
        for forbidden in ("current", "latest", "nearest", "get_current", "get_latest"):
            self.assertFalse(hasattr(manifest, forbidden))


class CanonicalManifestTests(unittest.TestCase):
    def test_canonical_manifest_is_empty(self) -> None:
        # No governed release declarations have been separately
        # reviewed/issued yet - do not fabricate any to populate this.
        self.assertEqual(STRATEGY_RELEASE_MANIFEST.declarations, ())

    def test_canonical_manifest_is_the_correct_type(self) -> None:
        self.assertIsInstance(STRATEGY_RELEASE_MANIFEST, StrategyReleaseManifest)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import ast
        from pathlib import Path

        import strategies.runtime_release_manifest as module

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self) -> set[str]:
        import ast

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
        import ast

        tree = self._module_tree()
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_plus_registry_foundation_only(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = ("__future__", "dataclasses", "strategies.registry_foundation")
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_registry_foundation_import_is_the_named_narrow_set_only(self) -> None:
        import ast

        imported_from_registry: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "strategies.registry_foundation"
            ):
                for alias in node.names:
                    imported_from_registry.add(alias.name)

        self.assertEqual(
            imported_from_registry, {"StrategyIdentity", "StrategyVersion"}
        )

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
            "RiskResultRecord",
            "ExecutionOrder",
            "Scanner",
            "Signal",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_wall_clock_random_db_filesystem_network(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("utcnow", referenced)
        self.assertNotIn("uuid4", referenced)

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
            "datetime",
            "random",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_current_latest_nearest_selector_exported(self) -> None:
        import strategies.runtime_release_manifest as module

        for forbidden in (
            "current",
            "latest",
            "nearest",
            "get_current",
            "get_latest",
        ):
            self.assertFalse(hasattr(module, forbidden))

    def test_no_sort_or_min_max_calls(self) -> None:
        import ast

        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")

    def test_no_update_delete_append_mutation_methods(self) -> None:
        import strategies.runtime_release_manifest as module

        manifest_methods = {
            name
            for name in dir(module.StrategyReleaseManifest)
            if not name.startswith("_")
        }
        for forbidden in ("append", "update", "delete", "add", "issue", "mutate"):
            for method_name in manifest_methods:
                self.assertNotIn(forbidden, method_name.lower())


if __name__ == "__main__":
    unittest.main()
