from datetime import datetime,timezone
from decimal import Decimal
import tempfile
from pathlib import Path
from investments.research_queue import InvestmentResearchQueue,InvestmentResearchQueueItem
from investments.research_worker import InvestmentResearchWorker

NOW=datetime(2026,9,6,tzinfo=timezone.utc)

def test_worker_claims_highest_priority_once_and_marks_in_research():
 with tempfile.TemporaryDirectory() as td:
  q=InvestmentResearchQueue(Path(td)/"q.db")
  q.enqueue(InvestmentResearchQueueItem("a","A",NOW,"e:a",Decimal("60")))
  q.enqueue(InvestmentResearchQueueItem("b","B",NOW,"e:b",Decimal("90")))
  w=InvestmentResearchWorker(q)
  x=w.claim_next(now=NOW)
  assert x and x.candidate_id=="b"
  assert [r["candidate_id"] for r in q.pending()]==["a"]
  assert w.claim_next(now=NOW).candidate_id=="a"
  assert w.claim_next(now=NOW) is None

def test_worker_never_creates_decision_or_order_surface():
 with tempfile.TemporaryDirectory() as td:
  w=InvestmentResearchWorker(InvestmentResearchQueue(Path(td)/"q.db"))
  for forbidden in ("buy","sell","order_intent","decide","research_conclusion"):
   assert not hasattr(w,forbidden)
