from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

class InvestmentRoute(str,Enum):
 DETERMINISTIC="DETERMINISTIC"
 GIL_DEEP_ANALYSIS="GIL_DEEP_ANALYSIS"
 REJECT="REJECT"

class InvestmentCandidateState(str,Enum):
 CANDIDATE="CANDIDATE"
 WAIT="WAIT"
 REJECTED="REJECTED"

@dataclass(frozen=True,slots=True)
class InvestmentEvidence:
 provider:str
 observed_at:datetime
 source_reference:str
 market_price:Decimal
 fundamentals_reference:str|None=None
 event_reference:str|None=None
 fresh:bool=True

@dataclass(frozen=True,slots=True)
class InvestmentCandidate:
 candidate_id:str
 symbol:str
 universe_id:str
 setup_family:str
 materiality_score:Decimal
 deterministic_rule_id:str|None
 evidence:InvestmentEvidence
 state:InvestmentCandidateState
 reason:str

@dataclass(frozen=True,slots=True)
class InvestmentRoutingResult:
 candidate_id:str
 route:InvestmentRoute
 reason:str
 deterministic_rule_id:str|None
 evidence_reference:str
 observed_at:datetime
