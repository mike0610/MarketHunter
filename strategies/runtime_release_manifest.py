"""
MarketHunter

strategies/runtime_release_manifest.py

Module:
Strategy Runtime Release Authority Foundation - immutable,
version-controlled canonical manifest of explicit governed
StrategyIdentity + StrategyVersion release declarations only

Responsibilities:
- Define StrategyReleaseDeclaration: an exact, frozen pairing of one
  StrategyIdentity with one StrategyVersion that belongs to it.
- Define StrategyReleaseManifest: an immutable, read-only container
  of release declarations with exact (strategy_id, opaque version)
  lookup only.
- Expose STRATEGY_RELEASE_MANIFEST: the module-level canonical
  manifest. It ships empty until governed release declarations are
  explicitly reviewed and issued through repository change.

Non-goals (frozen by MH-STRATEGY-RUNTIME-PROVENANCE-SOURCE-002
Council decision):
- No runtime registry service, persistence, database, schema,
  filesystem, or network of any kind. This module is a read-only,
  version-controlled Python source - issuance happens only through
  explicit reviewed repository change merged under Strategy
  authority.
- No mutable issuer, append/update/delete API, or runtime writer.
- No current/latest/nearest/time/SemVer/name/class/file selector or
  inference of any kind. version is opaque, caller-supplied text -
  never parsed or ordered.
- No overwrite, winner selection, or fallback. Same release key
  (strategy_id, version) with a different semantic payload is a hard
  conflict at manifest construction; nothing ever chooses a winner.
- No wall clock, random, or scheduler usage. Git/manifest history is
  not CandidateProvenance OBSERVED_TIME.
- No Scanner, Signal, pipeline, Research, Simulation, market-data, or
  Strategy Lab import or wiring of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass

from strategies.registry_foundation import StrategyIdentity, StrategyVersion


class StrategyReleaseManifestError(Exception):
    """Base error for StrategyReleaseManifest failures."""


class StrategyReleaseIdentityMismatchError(StrategyReleaseManifestError):
    """version.strategy_id does not match identity.strategy_id."""


class StrategyReleaseConflictError(StrategyReleaseManifestError):
    """Same exact release key already declared with a different payload."""


class StrategyReleaseNotFoundError(StrategyReleaseManifestError):
    """No declaration exists for the exact requested release key."""


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


@dataclass(frozen=True, slots=True)
class StrategyReleaseDeclaration:
    """
    Exact pairing of one StrategyIdentity with one StrategyVersion
    that belongs to it. release_key = (identity.strategy_id,
    version.version) exactly - version remains opaque text and is
    never parsed, ordered, or compared as SemVer.
    """

    identity: StrategyIdentity
    version: StrategyVersion

    def __post_init__(self) -> None:
        if not isinstance(self.identity, StrategyIdentity):
            raise TypeError("identity must be a StrategyIdentity")

        if not isinstance(self.version, StrategyVersion):
            raise TypeError("version must be a StrategyVersion")

        if self.version.strategy_id != self.identity.strategy_id:
            raise StrategyReleaseIdentityMismatchError(
                "version.strategy_id must exactly match identity.strategy_id"
            )

    @property
    def release_key(self) -> tuple[str, str]:
        return (self.identity.strategy_id, self.version.version)


@dataclass(frozen=True, slots=True)
class StrategyReleaseManifest:
    """
    Immutable, read-only container of release declarations. Lookup
    is exact-key only - there is no current/latest/nearest selector
    of any kind. An identical duplicate declaration at the same
    release key is deterministic/idempotent; a declaration at the
    same release key with a different payload is a hard conflict at
    construction time - no overwrite or winner selection.
    """

    declarations: tuple[StrategyReleaseDeclaration, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.declarations, tuple) or not all(
            isinstance(item, StrategyReleaseDeclaration)
            for item in self.declarations
        ):
            raise TypeError(
                "declarations must be a tuple of StrategyReleaseDeclaration"
            )

        seen: dict[tuple[str, str], StrategyReleaseDeclaration] = {}

        for declaration in self.declarations:
            key = declaration.release_key
            existing = seen.get(key)

            if existing is None:
                seen[key] = declaration
                continue

            if existing != declaration:
                raise StrategyReleaseConflictError(
                    f"release key {key!r} already declared with a "
                    "different payload"
                )

    def get_exact(
        self, strategy_id: str, version: str
    ) -> StrategyReleaseDeclaration | None:
        _require_nonblank(strategy_id, "strategy_id")
        _require_nonblank(version, "version")

        for declaration in self.declarations:
            if declaration.release_key == (strategy_id, version):
                return declaration

        return None

    def require_exact(
        self, strategy_id: str, version: str
    ) -> StrategyReleaseDeclaration:
        declaration = self.get_exact(strategy_id, version)

        if declaration is None:
            raise StrategyReleaseNotFoundError(
                f"no release declared for ({strategy_id!r}, {version!r})"
            )

        return declaration


STRATEGY_RELEASE_MANIFEST = StrategyReleaseManifest(declarations=())
