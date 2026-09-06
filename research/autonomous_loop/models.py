from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class ResearchTrack(str, Enum):
    GIL="GIL"
    SL="SL"

class Stage(str, Enum):
    DATA_FEASIBILITY="DATA_FEASIBILITY"
    HYPOTHESIS_FREEZE="HYPOTHESIS_FREEZE"
    VALIDATION="VALIDATION"
    TERMINAL="TERMINAL"

class ResearchVerdict(str, Enum):
    PROMOTION_ELIGIBLE="PROMOTION-ELIGIBLE"
    REJECTED="REJECTED"
    BLOCKED_EVIDENCE="BLOCKED-EVIDENCE"

class TechnicalFailure(str, Enum):
    BLOCKED_RUNTIME="BLOCKED-RUNTIME"
    TOOLING_FAILURE="TOOLING_FAILURE"
    DATA_PROVIDER_FAILURE="DATA_PROVIDER_FAILURE"

@dataclass(frozen=True, slots=True)
class ResearchObject:
    object_id:str
    market:str
    direction:str
    hypothesis_id:str|None=None
    data_handler:str|None=None
    hypothesis_handler:str|None=None
    validation_handler:str|None=None
    product_owner_decision_required:bool=False
    priority:int=100
    research_track:ResearchTrack=ResearchTrack.GIL

    def __post_init__(self):
        if not isinstance(self.research_track,ResearchTrack):
            raise TypeError("research_track must be a ResearchTrack")
        for name in ("object_id","market","direction"):
            v=getattr(self,name)
            if not isinstance(v,str) or not v.strip(): raise ValueError(f"{name} must be nonblank")
        if self.product_owner_decision_required and self.hypothesis_id is not None:
            # A gated object may preserve a hypothesis, but cannot be advanced automatically.
            pass

@dataclass(frozen=True, slots=True)
class StageResult:
    status:str
    evidence:dict
    next_stage:Stage|None=None
    negative_knowledge:dict|None=None
