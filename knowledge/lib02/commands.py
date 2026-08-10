from dataclasses import dataclass
from typing import Optional

from .authorization import ActorContext
from .failures import ValidationFailure


@dataclass(frozen=True)
class ProgramNext:
    program_id: str
    actor_id: str
    note: Optional[str] = None


@dataclass(frozen=True)
class TrackNext:
    research_question_id: str
    actor_id: str
    note: Optional[str] = None


@dataclass(frozen=True)
class SetProgramNext:
    program_id: str
    program_next: ProgramNext
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("SetProgramNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import Program

        if not isinstance(target, Program):
            raise ValidationFailure("SetProgramNext targets Program only")
        if self.program_next.program_id != target.program_id:
            raise ValidationFailure("ProgramNext.program_id must match Program target")

    def authorize(self, actor_context: ActorContext, target: object) -> None:
        from .domain import Program

        if not isinstance(actor_context, ActorContext):
            raise ValidationFailure("ActorContext required for authorization")
        if not isinstance(target, Program):
            raise ValidationFailure("SetProgramNext targets Program only")
        actor_context.authorize_mutation(target.owning_lab)


@dataclass(frozen=True)
class ClearProgramNext:
    program_id: str
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("ClearProgramNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import Program

        if not isinstance(target, Program):
            raise ValidationFailure("ClearProgramNext targets Program only")
        if self.program_id != target.program_id:
            raise ValidationFailure("ClearProgramNext.program_id must match Program target")

    def authorize(self, actor_context: ActorContext, target: object) -> None:
        from .domain import Program

        if not isinstance(actor_context, ActorContext):
            raise ValidationFailure("ActorContext required for authorization")
        if not isinstance(target, Program):
            raise ValidationFailure("ClearProgramNext targets Program only")
        actor_context.authorize_mutation(target.owning_lab)


@dataclass(frozen=True)
class SetTrackNext:
    research_question_id: str
    track_next: TrackNext
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("SetTrackNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("SetTrackNext targets ResearchQuestion only")
        if target.status == "CLOSED":
            raise ValidationFailure("CLOSED ResearchQuestion cannot receive new TrackNext without reopen semantics")
        if self.track_next.research_question_id != target.question_id:
            raise ValidationFailure("TrackNext.research_question_id must match ResearchQuestion target")

    def authorize(self, actor_context: ActorContext, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(actor_context, ActorContext):
            raise ValidationFailure("ActorContext required for authorization")
        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("SetTrackNext targets ResearchQuestion only")
        actor_context.authorize_mutation(target.owning_lab)


@dataclass(frozen=True)
class ClearTrackNext:
    research_question_id: str
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("ClearTrackNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("ClearTrackNext targets ResearchQuestion only")
        if self.research_question_id != target.question_id:
            raise ValidationFailure("ClearTrackNext.research_question_id must match ResearchQuestion target")

    def authorize(self, actor_context: ActorContext, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(actor_context, ActorContext):
            raise ValidationFailure("ActorContext required for authorization")
        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("ClearTrackNext targets ResearchQuestion only")
        actor_context.authorize_mutation(target.owning_lab)


@dataclass(frozen=True)
class ClearProgramNext:
    program_id: str
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("ClearProgramNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import Program

        if not isinstance(target, Program):
            raise ValidationFailure("ClearProgramNext targets Program only")


@dataclass(frozen=True)
class SetTrackNext:
    research_question_id: str
    track_next: TrackNext
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("SetTrackNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("SetTrackNext targets ResearchQuestion only")
        if target.status == "CLOSED":
            raise ValidationFailure("CLOSED ResearchQuestion cannot receive new TrackNext without reopen semantics")


@dataclass(frozen=True)
class ClearTrackNext:
    research_question_id: str
    reason: str

    def __post_init__(self):
        if not self.reason:
            raise ValidationFailure("ClearTrackNext requires an explicit reason")

    def validate_target(self, target: object) -> None:
        from .domain import ResearchQuestion

        if not isinstance(target, ResearchQuestion):
            raise ValidationFailure("ClearTrackNext targets ResearchQuestion only")
