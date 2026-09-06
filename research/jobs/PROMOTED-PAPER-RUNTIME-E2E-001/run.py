import argparse,asyncio,json,subprocess,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

OID="PROMOTED-PAPER-RUNTIME-E2E-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=180,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True))
 (p/"promoted-paper-e2e.json").write_text(json.dumps(d,indent=2,sort_keys=True,default=str))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  # Install real production dispatcher timer. It must remain paper-only and may idle safely.
  cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/promoted-paper-runtime.service"),"/etc/systemd/system/promoted-paper-runtime.service"])
  cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/promoted-paper-runtime.timer"),"/etc/systemd/system/promoted-paper-runtime.timer"])
  cmd(["sudo","systemctl","daemon-reload"])
  cmd(["sudo","systemctl","enable","--now","promoted-paper-runtime.timer"])
  ev["service_start"]=cmd(["sudo","systemctl","start","promoted-paper-runtime.service"],180)
  ev["service"]=cmd(["systemctl","show","promoted-paper-runtime.service","--property=LoadState,ActiveState,SubState,Result,ExecMainStatus","--no-pager"])
  ev["timer"]=cmd(["systemctl","show","promoted-paper-runtime.timer","--property=LoadState,ActiveState,SubState,UnitFileState,LastTriggerUSec,NextElapseUSecRealtime","--no-pager"])
  # Isolated synthetic E2E: never touches production DBs.
  script=r'''
import asyncio,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.models import AccountKind,MarketQuote
from experiment1.runtime import run_market_cycle
from experiment1.trading_decision import drain_trading_decision_inbox
from research.autonomous_loop.models import ResearchObject
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

class Q:
 def __init__(self,p,t):self.price=Decimal(p);self.t=t;self.n=0
 async def quote_for(self,intent):
  self.n+=1
  return MarketQuote(intent.symbol,self.price,self.t,"SYSTEM_TEST","q"+str(self.n),Decimal("4"),Decimal("6"))

with tempfile.TemporaryDirectory() as td:
 root=Path(td)
 rr=AutonomousResearchRepository(root/"research.db")
 rr.enqueue(ResearchObject("P","SPY","LONG","H-P"))
 rr.terminal("P","PROMOTION-ELIGIBLE",{"paper_contract":{
  "strategy_id":"PROMOTED-E2E","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND","direction":"LONG",
  "account":"SPOT","requested_leverage":"1","cluster_key":"US_EQ","entry_trigger_source":"SIGNAL_BAR_HIGH",
  "expiry_seconds":259200,"take_profit_r":"3"}},hypothesis_id="H-P")
 pt=datetime.fromisoformat(rr.release_candidate("P")["created_at"])
 ss=TradingScannerStore(root/"scanner.db")
 c=TradingCandidate(1,"SPY","STK","SMART","USD",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("promoted",),
  LiquidityContext(Decimal("1000000"),Decimal("500000000"),Decimal("500")),VolatilityContext(Decimal("2")),
  "OK",True,pt+timedelta(seconds=1),"scan","1:BREAKOUT_OR_PULLBACK_IN_TREND:scan",QueueState.CANDIDATE,
  invalidation_reference="close below structural stop (490)",signal_bar_high=Decimal("505"),signal_bar_low=Decimal("495"))
 ss.record_candidate(c)
 e=Experiment1Engine(root/"experiment1.db")
 ds=PromotedPaperDispatchStore(root/"dispatch.db")
 kwargs=dict(research_repo=rr,scanner_store=ss,engine=e,dispatch_store=ds,
  strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
  open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),
  risk_policy=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),345600))
 first=dispatch_promoted_candidates(**kwargs);second=dispatch_promoted_candidates(**kwargs)
 assert len(first)==1 and first[0].status=="QUEUED" and second==()
 q=Q("506",pt+timedelta(seconds=2))
 ing=asyncio.run(drain_trading_decision_inbox(e,q));assert ing[0].outcome=="PENDING"
 fill=asyncio.run(run_market_cycle(e,q));assert fill[0].outcome=="PAPER_FILLED"
 intent=e.get_intent(ing[0].intent_id);assert intent.quantity==Decimal("1.33333333") and intent.take_profit==Decimal("550")
 q.price=Decimal("551");q.t=pt+timedelta(seconds=3)
 life=asyncio.run(run_protective_exit_cycle(e,q,(ing[0].intent_id,)));assert life[0].outcome=="TAKE_PROFIT"
 closed=e.closed_trades(AccountKind.SPOT);assert len(closed)==1 and closed[0].realized_pnl>0
 print("PROMOTED_PAPER_E2E_PASS",intent.quantity,intent.stop_loss,intent.take_profit,closed[0].realized_pnl)
'''
  ev["synthetic"]=cmd([str(REPO/".venv/bin/python"),"-c",script],180,REPO)
  timer_ok="ActiveState=active" in ev["timer"]["stdout"] and "UnitFileState=enabled" in ev["timer"]["stdout"]
  service_ok=ev["service_start"]["rc"]==0 and "Result=success" in ev["service"]["stdout"]
  e2e_ok=ev["synthetic"]["rc"]==0 and "PROMOTED_PAPER_E2E_PASS" in ev["synthetic"]["stdout"]
  state="PASS" if timer_ok and service_ok and e2e_ok else "BLOCKED-RUNTIME"
  emit(out,state,verdict="PROMOTED_PAPER_RUNTIME_PASS" if state=="PASS" else None,checks={"timer":timer_ok,"service":service_ok,"synthetic_e2e":e2e_ok},evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
