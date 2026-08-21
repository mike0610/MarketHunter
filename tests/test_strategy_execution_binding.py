"""
MarketHunter

Tests for Strategy Execution Binding transport
(strategies/execution_binding.py, services/scanner.py,
pipeline/context.py).
"""

from __future__ import annotations

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from models.market_symbol import MarketSymbol
from models.signal import Signal
from pipeline.context import SignalContext
from services.scanner import Scanner
from strategies.base_strategy import BaseStrategy
from strategies.execution_binding import (
    STRATEGY_RELEASE_MANIFEST,
    StrategyExecutionBinding,
    StrategyExecutionBindingConflictError,
    StrategyExecutionBindingError,
    bind_strategy_release,
)
from strategies.registry_foundation import StrategyIdentity, StrategyReference, StrategyVersion
from strategies.runtime_release_manifest import (
    StrategyReleaseDeclaration,
    StrategyReleaseManifest,
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


def make_manifest(*declarations: StrategyReleaseDeclaration) -> StrategyReleaseManifest:
    return StrategyReleaseManifest(declarations=declarations)


class FakeStrategy(BaseStrategy):
    """
    Returns a canned signal (or None) and records every analyze()
    call.
    """

    def __init__(self, name: str, signal_or_none: Signal | None) -> None:
        self.name = name
        self._signal_or_none = signal_or_none
        self.calls: list[MarketSnapshot] = []

    async def analyze(self, snapshot: MarketSnapshot) -> Signal | None:
        self.calls.append(snapshot)
        return self._signal_or_none


def make_binding(**overrides) -> StrategyExecutionBinding:
    kwargs = dict(
        implementation=FakeStrategy("strategy-1", None),
        release=make_declaration(),
    )
    kwargs.update(overrides)
    return StrategyExecutionBinding(**kwargs)


def make_candle(day_index: int) -> Candle:
    open_time = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_index)
    return Candle(
        open_time=open_time,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
        close_time=open_time + timedelta(days=1) - timedelta(seconds=1),
        quote_volume=100000.0,
        trades=100,
        taker_buy_base_volume=500.0,
        taker_buy_quote_volume=50000.0,
    )


def make_candles(count: int = 200) -> list[Candle]:
    return [make_candle(day_index=i) for i in range(count)]


def make_symbol(symbol: str = "BTCUSDT", market: str = "spot") -> MarketSymbol:
    return MarketSymbol(
        symbol=symbol, base_asset=symbol.removesuffix("USDT"), quote_asset="USDT", market=market
    )


def make_snapshot(symbol: str = "BTCUSDT", candles: list[Candle] | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        candles=candles or [],
        ema20=0.0,
        ema50=0.0,
        ema200=0.0,
        atr14=0.0,
        avg_volume20=0.0,
        highest20=0.0,
        lowest20=0.0,
    )


class FakeMarketData:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles

    async def load_candles(self, symbol, interval, limit):
        return self.candles


class FakeSnapshotBuilder:
    def __init__(self, snapshot: MarketSnapshot) -> None:
        self.snapshot = snapshot

    def build(self, symbol, candles):
        return self.snapshot


class FakeSignalHandler:
    """
    Mirrors pipeline.handler.SignalHandler - mutates context in place
    without recreating it, matching real handler behavior.
    """

    name = "fake-handler"

    def __init__(self) -> None:
        self.calls: list[SignalContext] = []

    async def handle(self, context: SignalContext) -> None:
        self.calls.append(context)
        context.metadata["fake_handler_ran"] = True


def build_scanner(
    market_data: FakeMarketData,
    strategies: list[BaseStrategy] | None = None,
    strategy_bindings: list[StrategyExecutionBinding] | None = None,
    snapshot_builder: FakeSnapshotBuilder | None = None,
    pipeline=None,
) -> Scanner:
    scanner = Scanner(
        market_data=market_data,
        strategies=strategies or [],
        strategy_bindings=strategy_bindings,
        pipeline=pipeline,
        timeframe="1d",
        candle_limit=200,
    )

    if snapshot_builder is not None:
        scanner.snapshot_builder = snapshot_builder

    return scanner


class StrategyExecutionBindingTests(unittest.TestCase):
    def test_frozen(self) -> None:
        binding = make_binding()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.release = make_declaration()  # type: ignore[misc]

    def test_release_preserved_by_identity(self) -> None:
        release = make_declaration()
        binding = make_binding(release=release)
        self.assertIs(binding.release, release)

    def test_identity_property_delegates_exactly(self) -> None:
        release = make_declaration()
        binding = make_binding(release=release)
        self.assertIs(binding.identity, release.identity)

    def test_version_property_delegates_exactly(self) -> None:
        release = make_declaration()
        binding = make_binding(release=release)
        self.assertIs(binding.version, release.version)

    def test_wrong_implementation_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyExecutionBinding(
                implementation="not-a-strategy", release=make_declaration()  # type: ignore[arg-type]
            )

    def test_wrong_release_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            StrategyExecutionBinding(
                implementation=FakeStrategy("s", None), release="not-a-release"  # type: ignore[arg-type]
            )

    def test_error_hierarchy(self) -> None:
        self.assertTrue(
            issubclass(StrategyExecutionBindingConflictError, StrategyExecutionBindingError)
        )


class BindStrategyReleaseTests(unittest.TestCase):
    def test_exact_bind_by_strategy_id_and_opaque_version(self) -> None:
        declaration = make_declaration()
        manifest = make_manifest(declaration)
        implementation = FakeStrategy("strategy-1", None)

        binding = bind_strategy_release(
            implementation,
            strategy_id="strategy-1",
            version="v1",
            manifest=manifest,
        )

        self.assertIs(binding.implementation, implementation)
        self.assertIs(binding.release, declaration)

    def test_missing_release_fails_closed(self) -> None:
        manifest = make_manifest()
        implementation = FakeStrategy("strategy-1", None)

        with self.assertRaises(StrategyReleaseNotFoundError):
            bind_strategy_release(
                implementation, strategy_id="strategy-1", version="v1", manifest=manifest
            )

    def test_canonical_empty_manifest_cannot_fabricate_binding(self) -> None:
        self.assertEqual(STRATEGY_RELEASE_MANIFEST.declarations, ())

        with self.assertRaises(StrategyReleaseNotFoundError):
            bind_strategy_release(
                FakeStrategy("strategy-1", None), strategy_id="strategy-1", version="v1"
            )

    def test_opaque_version_never_ordered(self) -> None:
        v2 = make_declaration(version=make_version(version="v2"))
        v10 = make_declaration(
            version=make_version(version="v10", supersedes_version="v2")
        )
        manifest = make_manifest(v2, v10)

        bound_v2 = bind_strategy_release(
            FakeStrategy("s", None), strategy_id="strategy-1", version="v2", manifest=manifest
        )
        bound_v10 = bind_strategy_release(
            FakeStrategy("s", None), strategy_id="strategy-1", version="v10", manifest=manifest
        )

        self.assertIs(bound_v2.release, v2)
        self.assertIs(bound_v10.release, v10)

    def test_wrong_implementation_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            bind_strategy_release(
                "not-a-strategy",  # type: ignore[arg-type]
                strategy_id="strategy-1",
                version="v1",
                manifest=make_manifest(make_declaration()),
            )

    def test_wrong_manifest_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            bind_strategy_release(
                FakeStrategy("s", None),
                strategy_id="strategy-1",
                version="v1",
                manifest="not-a-manifest",  # type: ignore[arg-type]
            )


class ScannerConflictTests(unittest.TestCase):
    def test_same_implementation_conflicting_releases_hard_fails(self) -> None:
        implementation = FakeStrategy("strategy-1", None)
        binding_v1 = StrategyExecutionBinding(
            implementation=implementation, release=make_declaration(version=make_version(version="v1"))
        )
        binding_v2 = StrategyExecutionBinding(
            implementation=implementation, release=make_declaration(version=make_version(version="v2"))
        )

        with self.assertRaises(StrategyExecutionBindingConflictError):
            build_scanner(
                FakeMarketData(make_candles()),
                strategy_bindings=[binding_v1, binding_v2],
            )

    def test_exact_duplicate_binding_deduplicated(self) -> None:
        implementation = FakeStrategy("strategy-1", None)
        release = make_declaration()
        binding_a = StrategyExecutionBinding(implementation=implementation, release=release)
        binding_b = StrategyExecutionBinding(implementation=implementation, release=release)

        scanner = build_scanner(
            FakeMarketData(make_candles()),
            strategy_bindings=[binding_a, binding_b],
        )

        self.assertEqual(len(scanner._execution_items), 1)

    def test_wrong_binding_type_in_list_rejected(self) -> None:
        with self.assertRaises(TypeError):
            build_scanner(
                FakeMarketData(make_candles()),
                strategy_bindings=["not-a-binding"],  # type: ignore[list-item]
            )

    def test_legacy_and_governed_strategies_both_present(self) -> None:
        governed = FakeStrategy("governed", None)
        legacy = FakeStrategy("legacy", None)
        binding = StrategyExecutionBinding(implementation=governed, release=make_declaration())

        scanner = build_scanner(
            FakeMarketData(make_candles()),
            strategies=[legacy],
            strategy_bindings=[binding],
        )

        self.assertEqual(len(scanner._execution_items), 2)
        implementations = {item.implementation for item in scanner._execution_items}
        self.assertEqual(implementations, {governed, legacy})

    def test_same_implementation_governed_and_legacy_hard_fails(self) -> None:
        implementation = FakeStrategy("strategy-1", None)
        binding = StrategyExecutionBinding(
            implementation=implementation, release=make_declaration()
        )

        with self.assertRaises(StrategyExecutionBindingConflictError):
            build_scanner(
                FakeMarketData(make_candles()),
                strategies=[implementation],
                strategy_bindings=[binding],
            )

        self.assertEqual(implementation.calls, [])

    def test_governed_only_unaffected_by_overlap_guard(self) -> None:
        implementation = FakeStrategy("strategy-1", None)
        binding = StrategyExecutionBinding(
            implementation=implementation, release=make_declaration()
        )

        scanner = build_scanner(
            FakeMarketData(make_candles()),
            strategy_bindings=[binding],
        )

        self.assertEqual(len(scanner._execution_items), 1)
        self.assertIs(scanner._execution_items[0].strategy_execution_binding, binding)

    def test_legacy_only_unaffected_by_overlap_guard(self) -> None:
        implementation = FakeStrategy("strategy-1", None)

        scanner = build_scanner(
            FakeMarketData(make_candles()),
            strategies=[implementation],
        )

        self.assertEqual(len(scanner._execution_items), 1)
        self.assertIsNone(scanner._execution_items[0].strategy_execution_binding)


class ScannerGovernedExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_governed_scanner_invokes_exact_bound_implementation(self) -> None:
        candles = make_candles()
        signal = Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG", score=95.0)
        implementation = FakeStrategy("strategy-1", signal)
        binding = StrategyExecutionBinding(implementation=implementation, release=make_declaration())

        scanner = build_scanner(
            FakeMarketData(candles),
            strategy_bindings=[binding],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(implementation.calls), 1)

    async def test_binding_survives_collect_to_signal_context(self) -> None:
        candles = make_candles()
        signal = Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG", score=95.0)
        implementation = FakeStrategy("strategy-1", signal)
        binding = StrategyExecutionBinding(implementation=implementation, release=make_declaration())

        captured_contexts: list[SignalContext] = []

        class CapturingPipeline:
            async def process(self, context: SignalContext) -> SignalContext:
                captured_contexts.append(context)
                return context

        scanner = build_scanner(
            FakeMarketData(candles),
            strategy_bindings=[binding],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
            pipeline=CapturingPipeline(),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(captured_contexts), 1)
        self.assertIs(captured_contexts[0].strategy_execution_binding, binding)

    async def test_binding_survives_direction_conflict_resolution(self) -> None:
        candles = make_candles()
        long_signal = Signal(
            symbol="BTCUSDT", market="spot", timeframe="1d", strategy="long-s", direction="LONG", score=95.0
        )
        short_signal = Signal(
            symbol="BTCUSDT", market="spot", timeframe="1d", strategy="short-s", direction="SHORT", score=10.0
        )
        long_implementation = FakeStrategy("long-strategy", long_signal)
        short_implementation = FakeStrategy("short-strategy", short_signal)
        long_binding = StrategyExecutionBinding(
            implementation=long_implementation, release=make_declaration()
        )
        short_binding = StrategyExecutionBinding(
            implementation=short_implementation,
            release=make_declaration(
                identity=make_identity(strategy_id="strategy-2"),
                version=make_version(strategy_id="strategy-2"),
            ),
        )

        captured_contexts: list[SignalContext] = []

        class CapturingPipeline:
            async def process(self, context: SignalContext) -> SignalContext:
                captured_contexts.append(context)
                return context

        scanner = build_scanner(
            FakeMarketData(candles),
            strategy_bindings=[long_binding, short_binding],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
            pipeline=CapturingPipeline(),
        )

        await scanner.scan_symbol(make_symbol())

        # winner (LONG) is accepted and reaches the pipeline with its
        # exact binding intact
        self.assertEqual(len(captured_contexts), 1)
        self.assertIs(captured_contexts[0].strategy_execution_binding, long_binding)

    async def test_binding_remains_after_signal_pipeline_processing(self) -> None:
        from pipeline.signal_pipeline import SignalPipeline

        candles = make_candles()
        signal = Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG", score=95.0)
        implementation = FakeStrategy("strategy-1", signal)
        binding = StrategyExecutionBinding(implementation=implementation, release=make_declaration())
        handler = FakeSignalHandler()

        scanner = build_scanner(
            FakeMarketData(candles),
            strategy_bindings=[binding],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
            pipeline=SignalPipeline(handlers=[handler]),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(handler.calls), 1)
        # the exact same binding object survived real SignalPipeline
        # handler processing unchanged
        self.assertIs(handler.calls[0].strategy_execution_binding, binding)

    async def test_legacy_bare_strategy_yields_none_binding(self) -> None:
        candles = make_candles()
        signal = Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG", score=95.0)
        implementation = FakeStrategy("legacy", signal)

        captured_contexts: list[SignalContext] = []

        class CapturingPipeline:
            async def process(self, context: SignalContext) -> SignalContext:
                captured_contexts.append(context)
                return context

        scanner = build_scanner(
            FakeMarketData(candles),
            strategies=[implementation],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
            pipeline=CapturingPipeline(),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(captured_contexts), 1)
        self.assertIsNone(captured_contexts[0].strategy_execution_binding)

    async def test_signal_strategy_field_alone_never_creates_binding(self) -> None:
        # Signal.strategy is a plain display string that happens to
        # match a real strategy_id/version-looking value - this must
        # never be interpreted as governed identity by the Scanner.
        candles = make_candles()
        signal = Signal(
            symbol="BTCUSDT",
            market="spot",
            timeframe="1d",
            strategy="strategy-1",
            direction="LONG",
            score=95.0,
        )
        implementation = FakeStrategy("legacy", signal)

        captured_contexts: list[SignalContext] = []

        class CapturingPipeline:
            async def process(self, context: SignalContext) -> SignalContext:
                captured_contexts.append(context)
                return context

        scanner = build_scanner(
            FakeMarketData(candles),
            strategies=[implementation],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
            pipeline=CapturingPipeline(),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertIsNone(captured_contexts[0].strategy_execution_binding)
        self.assertEqual(captured_contexts[0].signal.strategy, "strategy-1")

    async def test_exact_duplicate_binding_does_not_double_execute(self) -> None:
        candles = make_candles()
        signal = Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG", score=95.0)
        implementation = FakeStrategy("strategy-1", signal)
        release = make_declaration()
        binding_a = StrategyExecutionBinding(implementation=implementation, release=release)
        binding_b = StrategyExecutionBinding(implementation=implementation, release=release)

        scanner = build_scanner(
            FakeMarketData(candles),
            strategy_bindings=[binding_a, binding_b],
            snapshot_builder=FakeSnapshotBuilder(make_snapshot(candles=candles)),
        )

        await scanner.scan_symbol(make_symbol())

        self.assertEqual(len(implementation.calls), 1)


class SignalContextCarrierTests(unittest.TestCase):
    def test_default_binding_is_none(self) -> None:
        context = SignalContext(
            signal=Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG"),
            snapshot=make_snapshot(),
        )
        self.assertIsNone(context.strategy_execution_binding)

    def test_binding_field_accepts_exact_binding(self) -> None:
        binding = make_binding()
        context = SignalContext(
            signal=Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG"),
            snapshot=make_snapshot(),
            strategy_execution_binding=binding,
        )
        self.assertIs(context.strategy_execution_binding, binding)

    def test_reject_does_not_clear_binding(self) -> None:
        binding = make_binding()
        context = SignalContext(
            signal=Signal(symbol="BTCUSDT", market="spot", timeframe="1d", strategy="s", direction="LONG"),
            snapshot=make_snapshot(),
            strategy_execution_binding=binding,
        )
        context.reject("some reason")
        self.assertIs(context.strategy_execution_binding, binding)


class NoObservedTimeMintedTests(unittest.TestCase):
    def test_no_candidate_provenance_or_observed_time_references(self) -> None:
        import ast
        from pathlib import Path

        import strategies.execution_binding as module

        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        referenced = {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

        for forbidden in ("CandidateProvenance", "OBSERVED_TIME", "observed_at_now"):
            self.assertNotIn(forbidden, referenced)


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self, module):
        import ast
        from pathlib import Path

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self, module) -> set[str]:
        import ast

        imported: set[str] = set()
        for node in ast.walk(self._module_tree(module)):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def test_execution_binding_module_allowed_imports_only(self) -> None:
        import strategies.execution_binding as module

        imported = self._imported_names(module)
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "strategies.base_strategy",
            "strategies.registry_foundation",
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

    def test_execution_binding_no_forbidden_domain_imports(self) -> None:
        import strategies.execution_binding as module

        imported = self._imported_names(module)
        for forbidden in (
            "services",
            "pipeline",
            "research",
            "simulation",
            "models",
        ):
            self.assertNotIn(forbidden, imported)
            for name in imported:
                self.assertFalse(name.startswith(forbidden + "."))

    def test_execution_binding_no_current_latest_selector_exported(self) -> None:
        import strategies.execution_binding as module

        for forbidden in ("current", "latest", "nearest", "get_current", "get_latest"):
            self.assertFalse(hasattr(module, forbidden))

    def test_execution_binding_no_wall_clock_random(self) -> None:
        import strategies.execution_binding as module

        imported = self._imported_names(module)
        for forbidden in ("datetime", "random", "uuid", "time"):
            self.assertNotIn(forbidden, imported)


if __name__ == "__main__":
    unittest.main()
