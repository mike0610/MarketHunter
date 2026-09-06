from datetime import datetime,timezone
from decimal import Decimal
import tempfile
from pathlib import Path
from investments.stage8_models import *
from investments.stage8_store import Stage8InvestmentStore
from investments.research_queue import *

NOW=datetime(2026,9,6,tzinfo=timezone.utc)
def c(cid,score="80",rule=None,fresh=True):
 return InvestmentCandidate(cid,"ABC","GLOBAL","QUALITY_VALUE",Decimal(score),rule,InvestmentEvidence("REAL",NOW,"e:"+cid,Decimal("100"),"fund:q",None,fresh),InvestmentCandidateState.CANDIDATE,"screen")

def test_material_candidate_without_rule_enters_deep_research_once():
 with tempfile.TemporaryDirectory() as td:
  p=Path(td);s=Stage8InvestmentStore(p/"s.db");q=InvestmentResearchQueue(p/"q.db")
  r,a=admit_candidate(c("1"),materiality_floor=Decimal("50"),stage8=s,queue=q)
  assert r.route is InvestmentRoute.GIL_DEEP_ANALYSIS and a
  _,again=admit_candidate(c("1"),materiality_floor=Decimal("50"),stage8=s,queue=q)
  assert not again and len(q.pending())==1

def test_low_materiality_stale_and_deterministic_do_not_enter_gil_queue():
 with tempfile.TemporaryDirectory() as td:
  p=Path(td);s=Stage8InvestmentStore(p/"s.db");q=InvestmentResearchQueue(p/"q.db")
  for x in (c("low","10"),c("stale",fresh=False),c("rule",rule="INV-R1")):
   _,added=admit_candidate(x,materiality_floor=Decimal("50"),stage8=s,queue=q);assert not added
  assert q.pending()==()

def test_queue_is_priority_ordered_and_durable():
 with tempfile.TemporaryDirectory() as td:
  q=InvestmentResearchQueue(Path(td)/"q.db")
  q.enqueue(InvestmentResearchQueueItem("a","A",NOW,"e:a",Decimal("60")))
  q.enqueue(InvestmentResearchQueueItem("b","B",NOW,"e:b",Decimal("90")))
  assert [r["candidate_id"] for r in q.pending()]==["b","a"]
  q.mark("b","DECIDED");assert [r["candidate_id"] for r in q.pending()]==["a"]
