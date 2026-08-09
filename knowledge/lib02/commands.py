from dataclasses import dataclass
from typing import Optional


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
