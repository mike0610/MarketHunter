from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class CoverageState(Enum):
    PENDING = "PENDING"
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"


class MappingState(Enum):
    PROVEN = "PROVEN"
    UNMAPPED = "UNMAPPED"


@dataclass(frozen=True)
class Source:
    name: str
    version: str


@dataclass(frozen=True)
class Version:
    value: str


@dataclass(frozen=True)
class Claim:
    """Immutable semantic claim with explicit refinement/supersession links."""

    claim_id: str
    semantic: str
    source: Source
    refined_by: Optional[str] = None
    superseded_by: Optional[str] = None


@dataclass(frozen=True)
class ContinuityCapsule:
    """Stores routing snapshots only and is immutable."""

    # Use an immutable class-level empty tuple as the default so the
    # attribute exists on the class object (tests expect `hasattr` True)
    routing_snapshots: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Coverage:
    """Coverage is bounded by Source/version/range × ResearchQuestion × depth."""

    source: Source
    version: Version
    range_start: int
    range_end: int
    research_question_id: str
    depth: int = 0
    state: CoverageState = CoverageState.PENDING


@dataclass(frozen=True)
class ExaminationResult:
    """Separate from Coverage state: stores the findings of an examination."""

    covered: bool
    findings: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Program:
    program_id: str
    owner: str
    # Program owns PROGRAM NEXT only; mutations come via commands


@dataclass(frozen=True)
class ReopenCondition:
    reason: str


@dataclass(frozen=True)
class ResearchQuestion:
    question_id: str
    owner: str
    status: str = "OPEN"

    def reopen(self, condition: Optional[ReopenCondition]):
        from .failures import ReopenConditionError

        if condition is None:
            raise ReopenConditionError("Explicit reopen condition required")
        # semantics: reopening returns a new ResearchQuestion with status OPEN
        return ResearchQuestion(question_id=self.question_id, owner=self.owner, status="OPEN")
