from __future__ import annotations
from decimal import Decimal
from investments.stage8_models import *

def route_investment_candidate(candidate:InvestmentCandidate,*,materiality_floor:Decimal)->InvestmentRoutingResult:
 e=candidate.evidence
 if not e.fresh:
  return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.REJECT,"stale investment evidence",None,e.source_reference,e.observed_at)
 if e.market_price<=0:
  return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.REJECT,"invalid market evidence",None,e.source_reference,e.observed_at)
 if candidate.state is InvestmentCandidateState.REJECTED:
  return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.REJECT,candidate.reason,None,e.source_reference,e.observed_at)
 if candidate.materiality_score<materiality_floor:
  return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.REJECT,"below materiality floor",None,e.source_reference,e.observed_at)
 if candidate.deterministic_rule_id:
  return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.DETERMINISTIC,"approved formal deterministic investment rule",candidate.deterministic_rule_id,e.source_reference,e.observed_at)
 return InvestmentRoutingResult(candidate.candidate_id,InvestmentRoute.GIL_DEEP_ANALYSIS,"material candidate requires GIL-owned investment thesis",None,e.source_reference,e.observed_at)
