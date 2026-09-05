from __future__ import annotations
from datetime import datetime,timedelta
from experiment1.market_data_evidence import evaluate_market_data_evidence
from experiment1.models import MarketDataEvidence

def require_independent_execution_evidence(e:MarketDataEvidence,*,instrument:str,currency:str,exchange:str|None,now:datetime,max_age_seconds:int)->MarketDataEvidence:
 result=evaluate_market_data_evidence(e,expected_instrument=instrument,expected_currency=currency,expected_exchange=exchange,
  execution_max_age=timedelta(seconds=max_age_seconds),valuation_max_age=timedelta(seconds=max_age_seconds),now=now)
 if not result.execution_evidence_ok:raise ValueError("investment execution evidence is not execution-grade")
 if e.provider=="GIL_SIMULATED_REFERENCE_CLOSE_FILL":raise ValueError("GIL-declared reference close cannot satisfy Stage 8 autonomous execution evidence")
 return e
