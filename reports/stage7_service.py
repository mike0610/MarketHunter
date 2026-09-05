from __future__ import annotations
from dataclasses import asdict
from decimal import Decimal
from reports.stage7_analytics import group_by,summarize
from reports.stage7_repository import Stage7ClosedTradeReader

def _jsonable(v):
 if isinstance(v,Decimal):return str(v)
 if isinstance(v,dict):return {k:_jsonable(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [_jsonable(x) for x in v]
 return v

def build_stage7_report(db_path)->dict:
 samples=Stage7ClosedTradeReader(db_path).read_all()
 summary=summarize(samples)
 groups={}
 for field in ("strategy_id","strategy_version","direction","exit_reason","symbol"):
  groups[field]={k:asdict(v) for k,v in group_by(samples,field).items()}
 return _jsonable({"summary":asdict(summary),"groups":groups,"sample_size":len(samples),
  "automation_note":"analytics only; no strategy promotion/disable or execution mutation"})
