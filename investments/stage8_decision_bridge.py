from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from experiment1.models import AccountKind,DecisionAction,GilDecision,MarketDataEvidence
from investments.stage8_boundary import assert_investment_account,assert_investment_action
from investments.stage8_models import InvestmentCandidate,InvestmentRoute,InvestmentRoutingResult

class InvestmentDecisionSource(str,Enum):
 DETERMINISTIC_RULE="DETERMINISTIC_RULE"
 GIL="GIL"

@dataclass(frozen=True,slots=True)
class Stage8InvestmentDecision:
 decision_id:str
 candidate_id:str
 source:InvestmentDecisionSource
 account:AccountKind
 action:DecisionAction
 symbol:str
 decided_at:datetime
 quantity:Decimal
 thesis:str
 evidence_reference:str
 rule_or_gil_reference:str

 def __post_init__(self):
  assert_investment_account(self.account);assert_investment_action(self.action)
  if self.action in (DecisionAction.BUY,DecisionAction.SELL) and self.quantity<=0:raise ValueError("trade decision requires positive quantity")
  if self.action in (DecisionAction.WAIT,DecisionAction.HOLD) and self.quantity!=0:raise ValueError("WAIT/HOLD require zero quantity")

def deterministic_decision(candidate:InvestmentCandidate,route:InvestmentRoutingResult,*,account:AccountKind,action:DecisionAction,quantity:Decimal,thesis:str)->Stage8InvestmentDecision:
 if route.route is not InvestmentRoute.DETERMINISTIC or not route.deterministic_rule_id:
  raise ValueError("deterministic decision requires a deterministic route with formal rule id")
 assert_investment_account(account);assert_investment_action(action)
 return Stage8InvestmentDecision("stage8:"+candidate.candidate_id+":"+route.deterministic_rule_id,candidate.candidate_id,InvestmentDecisionSource.DETERMINISTIC_RULE,account,action,candidate.symbol,route.observed_at,quantity,thesis,route.evidence_reference,route.deterministic_rule_id)

def gil_decision(candidate:InvestmentCandidate,route:InvestmentRoutingResult,gil:GilDecision)->Stage8InvestmentDecision:
 if route.route is not InvestmentRoute.GIL_DEEP_ANALYSIS:raise ValueError("GIL decision requires GIL route")
 assert_investment_account(gil.account);assert_investment_action(gil.action)
 if gil.symbol!=candidate.symbol:raise ValueError("GIL decision symbol mismatch")
 if gil.quantity is None:raise ValueError("GIL decision quantity must be resolved before Stage 8 portfolio bridge")
 return Stage8InvestmentDecision(gil.decision_id,candidate.candidate_id,InvestmentDecisionSource.GIL,gil.account,gil.action,gil.symbol,gil.decided_at,gil.quantity,gil.thesis,route.evidence_reference,"gil:"+gil.decision_id)

def require_gil_decision(route:InvestmentRoutingResult,gil:GilDecision|None)->GilDecision:
 if route.route is InvestmentRoute.GIL_DEEP_ANALYSIS and gil is None:
  raise ValueError("GIL deep-analysis route cannot become BUY/SELL without an actual GIL decision")
 if gil is None:raise ValueError("GIL decision missing")
 return gil
