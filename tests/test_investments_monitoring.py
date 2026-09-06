from datetime import datetime,timezone
from decimal import Decimal
import tempfile
from pathlib import Path
from experiment1.models import AccountKind
from investments.monitoring import *

def test_snapshot_tracks_absolute_relative_pnl_and_thesis_durably():
 x=InvestmentMonitorSnapshot("m1","d1",AccountKind.INVESTMENTS_GROWTH,"ABC",datetime(2026,9,6,tzinfo=timezone.utc),"evidence:fresh",Decimal("110"),Decimal("100"),Decimal("10"),"VWCE",Decimal("0.04"),ThesisStatus.INTACT,"evidence still supports thesis",False)
 assert x.unrealized_pnl==Decimal("100")
 assert x.absolute_return==Decimal("0.1")
 assert x.benchmark_relative_return==Decimal("0.06")
 with tempfile.TemporaryDirectory() as td:
  s=InvestmentMonitoringStore(Path(td)/"m.db");assert s.record(x);assert not s.record(x)
  r=s.rows()[0];assert r["thesis_status"]=="INTACT" and Decimal(r["unrealized_pnl"])==Decimal("100")

def test_broken_thesis_can_explicitly_trigger_revisit_without_auto_sell():
 x=InvestmentMonitorSnapshot("m2","d1",AccountKind.INVESTMENTS_BALANCED,"ABC",datetime(2026,9,6,tzinfo=timezone.utc),"evidence:new",Decimal("80"),Decimal("100"),Decimal("5"),None,None,ThesisStatus.BROKEN,"material thesis evidence changed",True)
 assert x.revisit_triggered
 assert not hasattr(x,"order_intent")
