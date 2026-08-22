"""
MarketHunter

Tests for Market Data Source Provenance Foundation - Slice 1
(market_data/provenance.py).
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from market_data.provenance import (
    MarketDataInvariantError,
    MarketDataObservationRef,
    MarketDataProvenanceDisposition,
    MarketDataProvenanceError,
    MarketDataProvenanceRecord,
    MarketDataProvenanceResult,
    MarketDataSourceConflictError,
    MarketDataSourceDeclaration,
    MarketDataSourceIdentity,
    MarketDataSourceReference,
    MarketVenueIdentity,
)

AWARE_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
AWARE_LATER = datetime(2026, 8, 21, 12, 5, tzinfo=timezone.utc)
AWARE_EARLIER = datetime(2026, 8, 21, 11, 55, tzinfo=timezone.utc)
NAIVE_NOW = datetime(2026, 8, 21, 12, 0)


def make_venue(**overrides) -> MarketVenueIdentity:
    kwargs = dict(venue_id="binance")
    kwargs.update(overrides)
    return MarketVenueIdentity(**kwargs)


def make_source_identity(**overrides) -> MarketDataSourceIdentity:
    kwargs = dict(venue=make_venue(), provider_id="binance-rest", source_id="klines")
    kwargs.update(overrides)
    return MarketDataSourceIdentity(**kwargs)


def make_declaration(**overrides) -> MarketDataSourceDeclaration:
    kwargs = dict(identity=make_source_identity(), opaque_version="v1")
    kwargs.update(overrides)
    return MarketDataSourceDeclaration(**kwargs)


def make_source_reference(**overrides) -> MarketDataSourceReference:
    kwargs = dict(declaration=make_declaration())
    kwargs.update(overrides)
    return MarketDataSourceReference(**kwargs)


def make_observation_ref(**overrides) -> MarketDataObservationRef:
    kwargs = dict(source_reference=make_source_reference(), observation_id="obs-1")
    kwargs.update(overrides)
    return MarketDataObservationRef(**kwargs)


def make_record(**overrides) -> MarketDataProvenanceRecord:
    source_reference = overrides.pop("source_reference", make_source_reference())
    kwargs = dict(
        source_reference=source_reference,
        symbol="BTCUSDT",
        market="spot",
        timeframe="1h",
        observation_refs=(
            make_observation_ref(source_reference=source_reference),
        ),
        observed_at=AWARE_NOW,
        available_at=AWARE_LATER,
    )
    kwargs.update(overrides)
    return MarketDataProvenanceRecord(**kwargs)


class ErrorTaxonomyTests(unittest.TestCase):
    def test_error_hierarchy(self) -> None:
        for error_cls in (MarketDataInvariantError, MarketDataSourceConflictError):
            self.assertTrue(issubclass(error_cls, MarketDataProvenanceError))

        self.assertTrue(issubclass(MarketDataProvenanceError, Exception))


class MarketVenueIdentityTests(unittest.TestCase):
    def test_frozen(self) -> None:
        venue = make_venue()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            venue.venue_id = "other"  # type: ignore[misc]

    def test_value_preserved_exactly_without_normalization(self) -> None:
        venue = make_venue(venue_id="  Binance Futures  ")
        self.assertEqual(venue.venue_id, "  Binance Futures  ")

    def test_blank_venue_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_venue(venue_id="   ")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_venue(venue_id=123)  # type: ignore[arg-type]


class MarketDataSourceIdentityTests(unittest.TestCase):
    def test_frozen(self) -> None:
        identity = make_source_identity()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            identity.provider_id = "other"  # type: ignore[misc]

    def test_venue_provider_source_remain_distinct(self) -> None:
        identity = make_source_identity(
            venue=make_venue(venue_id="binance"),
            provider_id="binance-ws",
            source_id="trade-stream",
        )
        self.assertEqual(identity.venue.venue_id, "binance")
        self.assertEqual(identity.provider_id, "binance-ws")
        self.assertEqual(identity.source_id, "trade-stream")
        self.assertNotEqual(identity.provider_id, identity.source_id)

    def test_values_preserved_exactly(self) -> None:
        identity = make_source_identity(provider_id="  provider-x  ")
        self.assertEqual(identity.provider_id, "  provider-x  ")

    def test_blank_provider_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_source_identity(provider_id="")

    def test_blank_source_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_source_identity(source_id="  ")

    def test_wrong_venue_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_source_identity(venue="not-a-venue")  # type: ignore[arg-type]


class MarketDataSourceDeclarationTests(unittest.TestCase):
    def test_frozen(self) -> None:
        declaration = make_declaration()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            declaration.opaque_version = "other"  # type: ignore[misc]

    def test_opaque_version_preserved_exactly(self) -> None:
        declaration = make_declaration(opaque_version="2024-01-rev-3")
        self.assertEqual(declaration.opaque_version, "2024-01-rev-3")

    def test_opaque_version_never_ordered(self) -> None:
        v2 = make_declaration(opaque_version="v2")
        v10 = make_declaration(opaque_version="v10")
        self.assertNotEqual(v2, v10)
        self.assertEqual(v2.opaque_version, "v2")
        self.assertEqual(v10.opaque_version, "v10")

    def test_blank_opaque_version_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_declaration(opaque_version="")

    def test_wrong_identity_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_declaration(identity="not-an-identity")  # type: ignore[arg-type]

    def test_construction_is_not_governed_issuance(self) -> None:
        # Constructing twice with equal payload is deterministic value
        # equality only - no issuer/registry state is created or shared.
        declaration_a = make_declaration()
        declaration_b = make_declaration()
        self.assertIsNot(declaration_a, declaration_b)
        self.assertEqual(declaration_a, declaration_b)


class MarketDataSourceReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_source_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.declaration = make_declaration()  # type: ignore[misc]

    def test_declaration_preserved_by_identity(self) -> None:
        declaration = make_declaration()
        reference = make_source_reference(declaration=declaration)
        self.assertIs(reference.declaration, declaration)

    def test_identity_property_delegates_exactly(self) -> None:
        declaration = make_declaration()
        reference = make_source_reference(declaration=declaration)
        self.assertIs(reference.identity, declaration.identity)

    def test_opaque_version_property_delegates_exactly(self) -> None:
        declaration = make_declaration()
        reference = make_source_reference(declaration=declaration)
        self.assertEqual(reference.opaque_version, declaration.opaque_version)

    def test_wrong_declaration_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_source_reference(declaration="not-a-declaration")  # type: ignore[arg-type]


class MarketDataObservationRefTests(unittest.TestCase):
    def test_frozen(self) -> None:
        observation_ref = make_observation_ref()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            observation_ref.observation_id = "other"  # type: ignore[misc]

    def test_source_reference_preserved_by_identity(self) -> None:
        source_reference = make_source_reference()
        observation_ref = make_observation_ref(source_reference=source_reference)
        self.assertIs(observation_ref.source_reference, source_reference)

    def test_observation_id_preserved_exactly(self) -> None:
        observation_ref = make_observation_ref(observation_id="  bar-42  ")
        self.assertEqual(observation_ref.observation_id, "  bar-42  ")

    def test_blank_observation_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_observation_ref(observation_id="")

    def test_wrong_source_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_observation_ref(source_reference="not-a-reference")  # type: ignore[arg-type]


class MarketDataProvenanceRecordTests(unittest.TestCase):
    def test_frozen(self) -> None:
        record = make_record()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_scope_strings_preserved(self) -> None:
        record = make_record(symbol="ETHUSDT", market="futures", timeframe="4h")
        self.assertEqual(record.symbol, "ETHUSDT")
        self.assertEqual(record.market, "futures")
        self.assertEqual(record.timeframe, "4h")

    def test_market_has_no_venue_inference(self) -> None:
        # market is a product type only - distinct venue values are
        # accepted for the same market string without any cross-check.
        source_a = make_source_reference(
            declaration=make_declaration(
                identity=make_source_identity(venue=make_venue(venue_id="binance"))
            )
        )
        source_b = make_source_reference(
            declaration=make_declaration(
                identity=make_source_identity(venue=make_venue(venue_id="okx"))
            )
        )
        record_a = make_record(source_reference=source_a, market="spot")
        record_b = make_record(source_reference=source_b, market="spot")
        self.assertEqual(record_a.market, record_b.market)
        self.assertNotEqual(
            record_a.source_reference.identity.venue,
            record_b.source_reference.identity.venue,
        )

    def test_blank_symbol_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(symbol="")

    def test_blank_market_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(market="  ")

    def test_blank_timeframe_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_record(timeframe="")

    def test_wrong_source_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_record(source_reference="not-a-reference")  # type: ignore[arg-type]

    def test_observation_refs_must_be_tuple(self) -> None:
        source_reference = make_source_reference()
        with self.assertRaises(TypeError):
            make_record(
                source_reference=source_reference,
                observation_refs=[
                    make_observation_ref(source_reference=source_reference)
                ],  # type: ignore[arg-type]
            )

    def test_observation_refs_element_type_checked(self) -> None:
        with self.assertRaises(TypeError):
            make_record(observation_refs=("not-a-ref",))  # type: ignore[arg-type]

    def test_observation_refs_order_preserved(self) -> None:
        source_reference = make_source_reference()
        ref1 = make_observation_ref(source_reference=source_reference, observation_id="ob-1")
        ref2 = make_observation_ref(source_reference=source_reference, observation_id="ob-2")
        record = make_record(
            source_reference=source_reference, observation_refs=(ref1, ref2)
        )
        self.assertEqual(record.observation_refs, (ref1, ref2))

    def test_empty_observation_tuple_permitted(self) -> None:
        record = make_record(observation_refs=())
        self.assertEqual(record.observation_refs, ())

    def test_duplicate_exact_observation_ref_rejected(self) -> None:
        source_reference = make_source_reference()
        ref = make_observation_ref(source_reference=source_reference)
        with self.assertRaises(MarketDataInvariantError):
            make_record(
                source_reference=source_reference,
                observation_refs=(ref, ref),
            )

    def test_duplicate_equal_but_distinct_observation_ref_rejected(self) -> None:
        source_reference = make_source_reference()
        ref_a = make_observation_ref(source_reference=source_reference)
        ref_b = make_observation_ref(source_reference=source_reference)
        self.assertIsNot(ref_a, ref_b)
        with self.assertRaises(MarketDataInvariantError):
            make_record(
                source_reference=source_reference,
                observation_refs=(ref_a, ref_b),
            )

    def test_foreign_source_observation_ref_rejected(self) -> None:
        record_source = make_source_reference()
        foreign_source = make_source_reference(
            declaration=make_declaration(opaque_version="v2")
        )
        foreign_ref = make_observation_ref(source_reference=foreign_source)

        with self.assertRaises(MarketDataSourceConflictError):
            make_record(
                source_reference=record_source,
                observation_refs=(foreign_ref,),
            )

    def test_observed_at_required_to_be_datetime(self) -> None:
        with self.assertRaises(TypeError):
            make_record(observed_at="2026-08-21T12:00:00Z")  # type: ignore[arg-type]

    def test_available_at_required_to_be_datetime(self) -> None:
        with self.assertRaises(TypeError):
            make_record(available_at="2026-08-21T12:00:00Z")  # type: ignore[arg-type]

    def test_observed_at_must_be_timezone_aware(self) -> None:
        with self.assertRaises(ValueError):
            make_record(observed_at=NAIVE_NOW)

    def test_available_at_must_be_timezone_aware(self) -> None:
        with self.assertRaises(ValueError):
            make_record(available_at=NAIVE_NOW)

    def test_observed_at_and_available_at_preserved_exactly(self) -> None:
        record = make_record(observed_at=AWARE_NOW, available_at=AWARE_LATER)
        self.assertEqual(record.observed_at, AWARE_NOW)
        self.assertEqual(record.available_at, AWARE_LATER)

    def test_no_chronology_invariant_between_observed_at_and_available_at(self) -> None:
        # available_at earlier than observed_at is accepted - Council
        # froze semantic roles only, not an ordering rule.
        record = make_record(observed_at=AWARE_LATER, available_at=AWARE_EARLIER)
        self.assertEqual(record.observed_at, AWARE_LATER)
        self.assertEqual(record.available_at, AWARE_EARLIER)


class MarketDataProvenanceDispositionTests(unittest.TestCase):
    def test_exact_four_members(self) -> None:
        self.assertEqual(
            {member.value for member in MarketDataProvenanceDisposition},
            {"KNOWN", "UNKNOWN", "UNAVAILABLE", "CONFLICT"},
        )


class MarketDataProvenanceResultTests(unittest.TestCase):
    def test_frozen(self) -> None:
        result = MarketDataProvenanceResult(
            disposition=MarketDataProvenanceDisposition.KNOWN, record=make_record()
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.record = None  # type: ignore[misc]

    def test_known_requires_exactly_one_record(self) -> None:
        record = make_record()
        result = MarketDataProvenanceResult(
            disposition=MarketDataProvenanceDisposition.KNOWN, record=record
        )
        self.assertIs(result.record, record)

    def test_known_with_none_record_rejected(self) -> None:
        with self.assertRaises(MarketDataInvariantError):
            MarketDataProvenanceResult(
                disposition=MarketDataProvenanceDisposition.KNOWN, record=None
            )

    def test_unknown_requires_none_record(self) -> None:
        result = MarketDataProvenanceResult(
            disposition=MarketDataProvenanceDisposition.UNKNOWN, record=None
        )
        self.assertIsNone(result.record)

    def test_unknown_with_record_rejected(self) -> None:
        with self.assertRaises(MarketDataInvariantError):
            MarketDataProvenanceResult(
                disposition=MarketDataProvenanceDisposition.UNKNOWN,
                record=make_record(),
            )

    def test_unavailable_with_record_rejected(self) -> None:
        with self.assertRaises(MarketDataInvariantError):
            MarketDataProvenanceResult(
                disposition=MarketDataProvenanceDisposition.UNAVAILABLE,
                record=make_record(),
            )

    def test_conflict_with_record_rejected(self) -> None:
        with self.assertRaises(MarketDataInvariantError):
            MarketDataProvenanceResult(
                disposition=MarketDataProvenanceDisposition.CONFLICT,
                record=make_record(),
            )

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            MarketDataProvenanceResult(disposition="KNOWN", record=make_record())  # type: ignore[arg-type]

    def test_wrong_record_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            MarketDataProvenanceResult(
                disposition=MarketDataProvenanceDisposition.KNOWN,
                record="not-a-record",  # type: ignore[arg-type]
            )

    def test_no_execution_fields_present(self) -> None:
        result = MarketDataProvenanceResult(
            disposition=MarketDataProvenanceDisposition.KNOWN, record=make_record()
        )
        result_fields = {f.name for f in dataclasses.fields(result)}
        record_fields = {f.name for f in dataclasses.fields(result.record)}
        for forbidden in (
            "account",
            "order",
            "execution",
            "routing",
            "broker",
            "capital",
        ):
            for name in result_fields | record_fields:
                self.assertNotIn(forbidden, name.lower())


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import market_data.provenance as module

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

    def test_module_is_stdlib_only(self) -> None:
        imported = self._imported_names()
        allowed = {"__future__", "dataclasses", "datetime", "enum"}
        for name in imported:
            self.assertIn(name, allowed, f"unexpected import: {name}")

    def test_no_cross_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "exchange",
            "services",
            "models",
            "research",
            "portfolio",
            "portfolio_v1",
            "risk",
            "trade_orchestration",
            "execution",
            "explainability",
            "audit_read_model",
            "manual_review",
            "simulation",
            "time_semantics",
            "api",
            "dashboard",
            "pipeline",
            "strategies",
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
            "BaseStrategy",
            "Scanner",
            "Signal",
            "MarketSnapshot",
            "MarketSymbol",
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
        import market_data.provenance as module

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

    def test_no_manifest_history_writer_issuer_registry_surface(self) -> None:
        import market_data.provenance as module

        module_names = {name for name in dir(module) if not name.startswith("_")}
        for forbidden in (
            "Manifest",
            "History",
            "Repository",
            "Issuer",
            "Writer",
            "Registry",
        ):
            for name in module_names:
                self.assertNotIn(forbidden, name)


if __name__ == "__main__":
    unittest.main()
