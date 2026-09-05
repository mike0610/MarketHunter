from __future__ import annotations
from dataclasses import asdict
from decimal import Decimal
from reports.stage7_analytics import group_by,summarize,TREND_UNKNOWN
from reports.stage7_repository import Stage7ClosedTradeReader

def _jsonable(v):
 if isinstance(v,Decimal):return str(v)
 if isinstance(v,dict):return {k:_jsonable(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [_jsonable(x) for x in v]
 return v

def build_stage7_report(db_path)->dict:
 reader=Stage7ClosedTradeReader(db_path);samples=reader.read_all();summary=summarize(samples)
 groups={}
 for field in ("strategy_id","strategy_version","setup_family","direction","trend_alignment","exit_reason","symbol"):
  groups[field]={k:asdict(v) for k,v in group_by(samples,field).items()}
 provenance=[{
  "closed_trade_id":s.closed_trade_id,"candidate_dedupe_key":s.candidate_dedupe_key,
  "strategy_decision_id":s.strategy_decision_id,"risk_plan_id":s.risk_plan_id,
  "order_id":s.order_id,"entry_fill_id":s.entry_fill_id,"position_id":s.position_id,
 } for s in samples]
 return _jsonable({
  "summary":asdict(summary),"groups":groups,"sample_size":len(samples),
  "decision_outcomes":reader.decision_outcomes(),"candidate_states":reader.candidate_states(),
  "provenance":provenance,
  "trend_alignment_note":f"trend alignment is {TREND_UNKNOWN} until an explicit governed trend-context fact is persisted; Reports never infers it from direction/price alone",
  "automation_note":"analytics only; no tuning, promotion, disable, risk mutation, or execution mutation"
 })
