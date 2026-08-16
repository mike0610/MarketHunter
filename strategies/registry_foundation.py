"""
MarketHunter

strategies/registry_foundation.py

Module:
Strategy Registry + Versioning - Slice 1 (immutable identity/
version/lineage contracts only)

Responsibilities:
- Define StrategyIdentity: the stable identity of a governed
  strategy across versions.
- Define StrategyReference: an opaque, locally-scoped kind+reference
  provenance pointer (rules/config, implementation/code, or evidence).
- Define StrategyVersion: an immutable, explicitly versioned
  snapshot belonging to exactly one StrategyIdentity.
- Define assess_strategy_version_lineage(): a pure, deterministic
  function that validates caller-supplied identity/version/reference
  consistency and explicit lineage only.

Non-goals (frozen by ARCH-REQ-STRATEGY-REGISTRY-IDENTITY-001):
- No registry service, persistence, repository, or runtime writer.
  Slice 1 defines contracts and pure validation only; a future
  Strategy Registry authority alone may persist/issue canonical
  StrategyVersion records.
- No promotion/approval workflow. Strategy Lab/Research may supply
  evidence upstream but this module never auto-promotes it to
  canonical StrategyVersion truth.
- No current/latest-version selector, no mutable current_version
  pointer, no deprecation/retirement lifecycle. Whether a live
  consumer requires the current version is caller-supplied context
  (require_current), never computed here.
- No SemVer or numeric version parsing/sorting. version and
  supersedes_version are opaque, caller-supplied text - lineage is
  proven only by explicit references, never by ordering.
- No identity/version inference from BaseStrategy.name, a concrete
  Python class, a module/config filename, a backtest row, or a
  Strategy Lab/ResearchTrade record.
- No artifact fetch/hash/content-addressing/certification -
  StrategyReference is a provenance pointer only.
- No shared KNOWN/UNKNOWN kernel reuse from other domains (Risk's
  IdentityState, Research's ReferenceState, etc.) - this module is
  intentionally stdlib-only with its own local disposition
  vocabulary, per Council's explicit instruction not to invert
  ownership by importing another domain's identity-state enum.
- No wiring of any kind into existing strategy classes, research
  validation, Risk models, Portfolio, TOP/execution, API, Dashboard,
  runtime, or deploy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class StrategyDisposition(str, Enum):
    """
    Caller-supplied disposition of one identity/version read. Not a
    lifecycle and not a freshness calculation - this module never
    computes whether a record is current, unavailable, conflicting,
    superseded, or affected by a changed source; the caller must
    supply that classification.
    """

    CURRENT = "CURRENT"
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    SUPERSEDED = "SUPERSEDED"
    SOURCE_CHANGED = "SOURCE_CHANGED"


class StrategyUsability(str, Enum):
    USABLE = "USABLE"
    NOT_USABLE = "NOT_USABLE"


class StrategyAssessmentReason(str, Enum):
    IDENTITY_DISPOSITION_NOT_USABLE = "IDENTITY_DISPOSITION_NOT_USABLE"
    VERSION_DISPOSITION_NOT_USABLE = "VERSION_DISPOSITION_NOT_USABLE"
    CURRENT_VERSION_REQUIRED = "CURRENT_VERSION_REQUIRED"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
    VERSION_IDENTITY_MISMATCH = "VERSION_IDENTITY_MISMATCH"
    VERSION_UNRESOLVED = "VERSION_UNRESOLVED"
    VERSION_AMBIGUOUS = "VERSION_AMBIGUOUS"
    PREDECESSOR_UNRESOLVED = "PREDECESSOR_UNRESOLVED"
    PREDECESSOR_AMBIGUOUS = "PREDECESSOR_AMBIGUOUS"
    CROSS_STRATEGY_SUPERSESSION = "CROSS_STRATEGY_SUPERSESSION"


def _require_nonblank(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a str")

    if not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _require_aware_datetime(value: object, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")

    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class StrategyIdentity:
    """
    Stable identity of a governed strategy across versions. Explicit
    caller-supplied authority provenance only - never derived from a
    display name, Python class, filename, or timestamp.
    """

    strategy_id: str
    authority_reference_kind: str
    authority_reference: str

    def __post_init__(self) -> None:
        _require_nonblank(self.strategy_id, "strategy_id")
        _require_nonblank(
            self.authority_reference_kind, "authority_reference_kind"
        )
        _require_nonblank(self.authority_reference, "authority_reference")


@dataclass(frozen=True, slots=True)
class StrategyReference:
    """
    Opaque, locally-scoped provenance pointer (e.g. rules/config,
    implementation/code, or evidence). Not a global artifact
    registry - reference_kind and reference are caller-supplied
    contract vocabulary only.
    """

    reference_kind: str
    reference: str

    def __post_init__(self) -> None:
        _require_nonblank(self.reference_kind, "reference_kind")
        _require_nonblank(self.reference, "reference")


def _require_reference_tuple(
    value: object, field_name: str, *, required_nonempty: bool
) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, StrategyReference) for item in value
    ):
        raise TypeError(f"{field_name} must be a tuple of StrategyReference")

    if required_nonempty and not value:
        raise ValueError(f"{field_name} must be non-empty")

    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} must not contain duplicate references")


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    """
    Immutable, explicitly versioned snapshot belonging to exactly one
    StrategyIdentity. version is opaque caller-supplied text - never
    parsed, ordered, or compared as SemVer. Supersession is declared
    only via supersedes_version, never inferred.
    """

    strategy_id: str
    version: str
    observed_at: datetime
    supersedes_version: str | None
    rules_references: tuple[StrategyReference, ...]
    implementation_references: tuple[StrategyReference, ...]
    evidence_references: tuple[StrategyReference, ...]

    def __post_init__(self) -> None:
        _require_nonblank(self.strategy_id, "strategy_id")
        _require_nonblank(self.version, "version")
        _require_aware_datetime(self.observed_at, "observed_at")

        if self.supersedes_version is not None:
            _require_nonblank(self.supersedes_version, "supersedes_version")

            if self.supersedes_version == self.version:
                raise ValueError(
                    "supersedes_version cannot self-reference the same "
                    "version"
                )

        _require_reference_tuple(
            self.rules_references, "rules_references", required_nonempty=True
        )
        _require_reference_tuple(
            self.implementation_references,
            "implementation_references",
            required_nonempty=False,
        )
        _require_reference_tuple(
            self.evidence_references,
            "evidence_references",
            required_nonempty=True,
        )


@dataclass(frozen=True, slots=True)
class StrategyVersionAssessment:
    usability: StrategyUsability
    reasons: tuple[StrategyAssessmentReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.usability, StrategyUsability):
            raise TypeError("usability must be a StrategyUsability")

        if not isinstance(self.reasons, tuple) or not all(
            isinstance(item, StrategyAssessmentReason) for item in self.reasons
        ):
            raise TypeError(
                "reasons must be a tuple of StrategyAssessmentReason"
            )

        if (
            self.usability is StrategyUsability.NOT_USABLE
            and not self.reasons
        ):
            raise ValueError("NOT_USABLE requires at least one reason")

        if self.usability is StrategyUsability.USABLE and self.reasons:
            raise ValueError(
                "USABLE must not carry reasons - reasons imply this "
                "version is not actually usable"
            )


def assess_strategy_version_lineage(
    identity: StrategyIdentity,
    version: StrategyVersion,
    identities: tuple[StrategyIdentity, ...],
    versions: tuple[StrategyVersion, ...],
    identity_disposition: StrategyDisposition,
    version_disposition: StrategyDisposition,
    require_current: bool,
) -> StrategyVersionAssessment:
    """
    Validate that the supplied target identity/version resolve
    unambiguously within the supplied collections, that the version
    belongs to the target identity, and that any declared
    predecessor resolves exactly once within the same strategy.
    Never fetches, infers, or selects a "current"/"latest" record -
    all resolution is against exactly the collections the caller
    supplied.
    """

    if not isinstance(identity, StrategyIdentity):
        raise TypeError("identity must be a StrategyIdentity")

    if not isinstance(version, StrategyVersion):
        raise TypeError("version must be a StrategyVersion")

    if not isinstance(identities, tuple) or not all(
        isinstance(item, StrategyIdentity) for item in identities
    ):
        raise TypeError("identities must be a tuple of StrategyIdentity")

    if not isinstance(versions, tuple) or not all(
        isinstance(item, StrategyVersion) for item in versions
    ):
        raise TypeError("versions must be a tuple of StrategyVersion")

    if not isinstance(identity_disposition, StrategyDisposition):
        raise TypeError("identity_disposition must be a StrategyDisposition")

    if not isinstance(version_disposition, StrategyDisposition):
        raise TypeError("version_disposition must be a StrategyDisposition")

    if not isinstance(require_current, bool):
        raise TypeError("require_current must be a bool")

    reasons: list[StrategyAssessmentReason] = []

    if identity_disposition is not StrategyDisposition.CURRENT:
        reasons.append(StrategyAssessmentReason.IDENTITY_DISPOSITION_NOT_USABLE)

    if version_disposition is StrategyDisposition.CURRENT:
        pass
    elif version_disposition is StrategyDisposition.SUPERSEDED:
        if require_current:
            reasons.append(StrategyAssessmentReason.CURRENT_VERSION_REQUIRED)
    else:
        reasons.append(StrategyAssessmentReason.VERSION_DISPOSITION_NOT_USABLE)

    matching_identities = [
        item for item in identities if item.strategy_id == identity.strategy_id
    ]

    if len(matching_identities) == 0:
        reasons.append(StrategyAssessmentReason.IDENTITY_UNRESOLVED)
    elif len(matching_identities) > 1:
        reasons.append(StrategyAssessmentReason.IDENTITY_AMBIGUOUS)

    if version.strategy_id != identity.strategy_id:
        reasons.append(StrategyAssessmentReason.VERSION_IDENTITY_MISMATCH)

    matching_versions = [
        item
        for item in versions
        if item.strategy_id == identity.strategy_id
        and item.version == version.version
    ]

    if len(matching_versions) == 0:
        reasons.append(StrategyAssessmentReason.VERSION_UNRESOLVED)
    elif len(matching_versions) > 1:
        reasons.append(StrategyAssessmentReason.VERSION_AMBIGUOUS)

    if version.supersedes_version is not None:
        same_strategy_predecessors = [
            item
            for item in versions
            if item.strategy_id == identity.strategy_id
            and item.version == version.supersedes_version
        ]

        if len(same_strategy_predecessors) == 0:
            other_strategy_predecessors = [
                item
                for item in versions
                if item.strategy_id != identity.strategy_id
                and item.version == version.supersedes_version
            ]

            if other_strategy_predecessors:
                reasons.append(
                    StrategyAssessmentReason.CROSS_STRATEGY_SUPERSESSION
                )
            else:
                reasons.append(
                    StrategyAssessmentReason.PREDECESSOR_UNRESOLVED
                )
        elif len(same_strategy_predecessors) > 1:
            reasons.append(StrategyAssessmentReason.PREDECESSOR_AMBIGUOUS)

    if reasons:
        return StrategyVersionAssessment(
            usability=StrategyUsability.NOT_USABLE,
            reasons=tuple(reasons),
        )

    return StrategyVersionAssessment(
        usability=StrategyUsability.USABLE,
        reasons=(),
    )
