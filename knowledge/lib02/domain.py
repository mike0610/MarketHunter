from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from .authorization import Lab
from .failures import ValidationFailure


class CoverageState(Enum):
    PENDING = "PENDING"
    COVERED = "COVERED"
    PARTIAL = "PARTIAL"


class MappingState(Enum):
    PROVEN = "PROVEN"
    UNMAPPED = "UNMAPPED"


class ReconciliationState(Enum):
    CURRENT = "CURRENT"
    UNRECONCILED = "UNRECONCILED"
    CONFLICT = "CONFLICT"


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
class EvidenceRelation:
    relation_id: str
    target_id: str
    target_kind: str
    source: Source
    version: Version
    artifact_reference: Optional[str] = None
    fragment: Optional[str] = None
    relation_type: str = ""
    strength: Optional[str] = None
    role: Optional[str] = None
    verification_state: str = ""
    provenance: str = ""
    supersedes_relation_id: Optional[str] = None
    retracts_relation_id: Optional[str] = None
    created_at: str = ""
    revised_at: Optional[str] = None

    def __post_init__(self):
        if not self.relation_id:
            raise ValidationFailure("EvidenceRelation requires a stable relation identity")
        if not self.target_id:
            raise ValidationFailure("EvidenceRelation requires a governed target")
        if not self.target_kind:
            raise ValidationFailure("EvidenceRelation requires a target kind")
        if not self.relation_type:
            raise ValidationFailure("EvidenceRelation requires a relation type")
        if not self.provenance:
            raise ValidationFailure("EvidenceRelation requires provenance")


@dataclass(frozen=True)
class NonFinding:
    non_finding_id: str
    owning_lab: Lab
    program_id: str
    question_id: str
    source: Source
    version: Version
    artifact_reference: str
    range_start: Optional[int]
    range_end: Optional[int]
    search_domain: Optional[str]
    examined_question: str
    condition: str
    examination_method: str
    depth: int
    result: str
    provenance: str
    limitations: str
    created_at: str
    superseded_by: Optional[str] = None

    def __post_init__(self):
        if not self.non_finding_id:
            raise ValidationFailure("NonFinding requires a stable identity")
        if not self.provenance:
            raise ValidationFailure("NonFinding requires durable provenance")
        if self.depth < 0:
            raise ValidationFailure("NonFinding requires a non-negative depth")


@dataclass(frozen=True)
class ContinuityCapsule:
    capsule_id: str
    owning_lab: Lab
    program_id: str
    research_question_id: str
    why: str
    current: str
    done: str
    do_not_repeat: str
    open_inconclusive: str
    bounded_unknowns: str
    program_next_snapshot: Optional["ProgramNext"] = None
    track_next_snapshot: Optional["TrackNext"] = None
    transition_reason: str = ""
    watermark: str = ""
    resume_condition: str = ""
    stored_continuity_state: str = ""
    issuance_provenance: str = ""
    issued_at: str = ""
    superseded_capsule_id: Optional[str] = None
    routing_snapshots: Tuple[str, ...] = ()

    def __post_init__(self):
        if not self.capsule_id:
            raise ValidationFailure("ContinuityCapsule requires a stable identity")
        if not self.owning_lab:
            raise ValidationFailure("ContinuityCapsule requires an owning lab")
        if not self.program_id:
            raise ValidationFailure("ContinuityCapsule requires a Program reference")
        if not self.research_question_id:
            raise ValidationFailure("ContinuityCapsule requires a ResearchQuestion reference")
        if not self.issuance_provenance:
            raise ValidationFailure("ContinuityCapsule requires issuance provenance")


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
    owning_lab: Lab
    purpose: str
    scope: str
    governed_status: str
    program_next: Optional["ProgramNext"] = None
    provenance: str = ""
    refined_from: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: Optional[str] = None
    revision: Optional[str] = None
    governance_hold: Optional[str] = None
    governance_conflict: Optional[str] = None

    def __post_init__(self):
        if not self.program_id:
            raise ValidationFailure("Program must have a stable program_id")
        if not self.purpose:
            raise ValidationFailure("Program must have a bounded purpose")
        if not self.scope:
            raise ValidationFailure("Program must have a bounded scope")
        if not self.governed_status:
            raise ValidationFailure("Program must have a governed status")


@dataclass(frozen=True)
class ReopenCondition:
    reason: str


@dataclass(frozen=True)
class ResearchQuestion:
    question_id: str
    program_id: str
    owning_lab: Lab
    question: str
    scope: str
    governed_status: str
    status: str = "OPEN"
    track_next: Optional["TrackNext"] = None
    completion_reason: Optional[str] = None
    reopen_condition: Optional[ReopenCondition] = None
    provenance: str = ""
    refined_from: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: str = ""
    updated_at: Optional[str] = None
    revision: Optional[str] = None

    def __post_init__(self):
        if not self.question_id:
            raise ValidationFailure("ResearchQuestion must have a stable question_id")
        if not self.question:
            raise ValidationFailure("ResearchQuestion must have an exact bounded question")
        if not self.scope:
            raise ValidationFailure("ResearchQuestion must have a bounded scope")
        if not self.governed_status:
            raise ValidationFailure("ResearchQuestion must have a governed status")

    def reopen(self, condition: Optional[ReopenCondition]):
        from .failures import ReopenConditionError

        if condition is None:
            raise ReopenConditionError("Explicit reopen condition required")

        return ResearchQuestion(
            question_id=self.question_id,
            program_id=self.program_id,
            owning_lab=self.owning_lab,
            question=self.question,
            scope=self.scope,
            governed_status=self.governed_status,
            status="OPEN",
            track_next=self.track_next,
            completion_reason=None,
            reopen_condition=condition,
            provenance=self.provenance,
            refined_from=self.refined_from,
            superseded_by=self.superseded_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
            revision=self.revision,
        )
