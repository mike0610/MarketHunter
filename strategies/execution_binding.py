"""
MarketHunter

strategies/execution_binding.py

Module:
Strategy Execution Binding - transport-only pairing of one concrete
strategy implementation with one exact already-issued
StrategyReleaseDeclaration

Responsibilities:
- Define StrategyExecutionBinding: an immutable pairing of a
  concrete BaseStrategy instance with an exact
  StrategyReleaseDeclaration. identity/version delegate directly to
  the wrapped release - never copied, reconstructed, or normalized.
- Define bind_strategy_release(): a pure helper that resolves exactly
  one already-issued release from a StrategyReleaseManifest by
  (strategy_id, opaque version) and constructs the binding.

Non-goals (frozen by MH-STRATEGY-EXECUTION-BINDING-001 Council
decision):
- Binding is transport/provenance only - never an issuer, registry,
  or current/latest selector. It never mints, repairs, defaults, or
  infers a release from name/class/module/file/time/SemVer ordering.
- No new Strategy release authority. bind_strategy_release() reads
  exactly one already-issued declaration from the caller-supplied
  manifest (STRATEGY_RELEASE_MANIFEST by default) via require_exact()
  only - a missing exact release surfaces the manifest's own
  StrategyReleaseNotFoundError, never a fabricated binding. Because
  the canonical manifest currently ships empty, canonical production
  composition cannot construct a governed binding until a separately
  reviewed declaration is issued.
- No Scanner/Signal/pipeline/Research/Simulation/market-data import
  or wiring of any kind - this module is Strategy-domain transport
  only.
"""

from __future__ import annotations

from dataclasses import dataclass

from strategies.base_strategy import BaseStrategy
from strategies.registry_foundation import StrategyIdentity, StrategyVersion
from strategies.runtime_release_manifest import (
    STRATEGY_RELEASE_MANIFEST,
    StrategyReleaseDeclaration,
    StrategyReleaseManifest,
)


class StrategyExecutionBindingError(Exception):
    """Base error for StrategyExecutionBinding failures."""


class StrategyExecutionBindingConflictError(StrategyExecutionBindingError):
    """The same concrete implementation object is bound to conflicting releases."""


@dataclass(frozen=True, slots=True)
class StrategyExecutionBinding:
    """
    Transport/provenance-only pairing of one concrete BaseStrategy
    instance with one exact StrategyReleaseDeclaration.
    """

    implementation: BaseStrategy
    release: StrategyReleaseDeclaration

    def __post_init__(self) -> None:
        if not isinstance(self.implementation, BaseStrategy):
            raise TypeError("implementation must be a BaseStrategy")

        if not isinstance(self.release, StrategyReleaseDeclaration):
            raise TypeError("release must be a StrategyReleaseDeclaration")

    @property
    def identity(self) -> StrategyIdentity:
        return self.release.identity

    @property
    def version(self) -> StrategyVersion:
        return self.release.version


def bind_strategy_release(
    implementation: BaseStrategy,
    *,
    strategy_id: str,
    version: str,
    manifest: StrategyReleaseManifest = STRATEGY_RELEASE_MANIFEST,
) -> StrategyExecutionBinding:
    """
    Resolve exactly one already-issued release declaration from
    manifest by (strategy_id, opaque version) and bind it to
    implementation. No current/latest/name/class/file/SemVer/time
    inference of any kind - a missing exact release surfaces the
    manifest's own StrategyReleaseNotFoundError rather than a
    guessed/default binding.
    """

    if not isinstance(implementation, BaseStrategy):
        raise TypeError("implementation must be a BaseStrategy")

    if not isinstance(manifest, StrategyReleaseManifest):
        raise TypeError("manifest must be a StrategyReleaseManifest")

    release = manifest.require_exact(strategy_id, version)

    return StrategyExecutionBinding(implementation=implementation, release=release)
