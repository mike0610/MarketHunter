from __future__ import annotations
from datetime import datetime
from experiment1.market_data_evidence import evaluate_market_data_evidence
from experiment1.models import EvidenceValidationStatus,MarketDataEvidence,QuoteMode,PriceType

def require_independent_execution_evidence(e:MarketDataEvidence,*,instrument:str,currency:str,exchange:str,now:datetime,max_age_seconds:int)->MarketDataEvidence:
 result=evaluate_market_data_evidence(e,expected_instrument=instrument,expected_currency=currency,expected_exchange=exchange,now=now,max_age_seconds=max_age_seconds)
 if result.status is not EvidenceValidationStatus.VALID:raise ValueError("investment execution evidence is not valid/fresh")
 if e.price_type not in (PriceType.TRADE,PriceType.BID,PriceType.ASK,PriceType.MID):raise ValueError("investment execution requires independent execution-grade price evidence")
 if e.mode not in (QuoteMode.REALTIME,QuoteMode.DELAYED):raise ValueError("EOD/derived/GIL reference-close is not autonomous execution evidence")
 if e.provider=="GIL_SIMULATED_REFERENCE_CLOSE_FILL":raise ValueError("GIL-declared reference close cannot satisfy Stage 8 autonomous execution evidence")
 return e
