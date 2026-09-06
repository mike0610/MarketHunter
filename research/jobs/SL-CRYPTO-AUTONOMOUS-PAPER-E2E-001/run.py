import argparse,asyncio,json,os,sqlite3,subprocess,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

OID="SL-CRYPTO-AUTONOMOUS-PAPER-E2E-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=240,cwd=None,env=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd,env=env)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def show(unit):
 return cmd(["systemctl","show",unit,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True,default=str))
 (p/"sl-crypto-e2e.json").write_text(json.dumps(d,indent=2,sort_keys=True,default=str))
def scan_counts(db):
 with sqlite3.connect(db) as c:
  rows=c.execute("select sec_type,queue_state,count(*) from trading_scanner_candidates group by sec_type,queue_state order by sec_type,queue_state").fetchall()
 return [{"sec_type":a,"queue_state":b,"count":n} for a,b,n in rows]

def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]

  for name in ("sl-crypto-scanner.service","sl-crypto-scanner.timer","promoted-paper-runtime-sl.service","promoted-paper-runtime-sl.timer"):
   ev["install:"+name]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd"/name),"/etc/systemd/system/"+name])
  ev["daemon_reload"]=cmd(["sudo","systemctl","daemon-reload"])
  ev["enable_scanner"]=cmd(["sudo","systemctl","enable","--now","sl-crypto-scanner.timer"])
  ev["enable_dispatcher"]=cmd(["sudo","systemctl","enable","--now","promoted-paper-runtime-sl.timer"])
  ev["scanner_timer"]=show("sl-crypto-scanner.timer")
  ev["dispatcher_timer"]=show("promoted-paper-runtime-sl.timer")

  with tempfile.TemporaryDirectory() as td:
   root=Path(td);scan_db=root/"scanner.db"
   env=dict(os.environ)
   env.update({"TRADING_SCANNER_DB_PATH":str(scan_db),"SL_CRYPTO_TOP_N":"5","SL_CRYPTO_HISTORY_BARS":"120"})
   ev["live_scanner"]=cmd([str(REPO/".venv/bin/python"),"-m","tools.sl_crypto_scanner_runtime.runtime"],240,REPO,env)
   ev["scan_counts"]=scan_counts(scan_db) if scan_db.exists() else []

   proof=r'''
import asyncio,json,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from exchange.binance_client import BinanceClient
from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import AccountKind,MarketQuote
from experiment1.runtime import run_market_cycle
from experiment1.trading_decision import drain_trading_decision_inbox
from research.autonomous_loop.models import ResearchObject,ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

async def live_price():
 c=BinanceClient();p=await c.get("/api/v3/ticker/price",params={"symbol":"BTCUSDT"})
 return Decimal(str(p["price"]))

async def main():
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);price=await live_price()
  rr=AutonomousResearchRepository(root/"research.db")
  rr.enqueue(ResearchObject("SL-PROOF","BTCUSDT","LONG","SL-H-PROOF",research_track=ResearchTrack.SL))
  trigger=(price*Decimal("0.99")).quantize(Decimal("0.01"));stop=(price*Decimal("0.97")).quantize(Decimal("0.01"))
  rr.terminal("SL-PROOF","PROMOTION-ELIGIBLE",{"paper_contract":{
   "strategy_id":"SL-SYSTEM-PROOF","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND",
   "direction":"LONG","account":"SPOT","requested_leverage":"1","cluster_key":"CRYPTO",
   "entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":86400,"take_profit_r":"2"
  }},hypothesis_id="SL-H-PROOF")
  promoted=datetime.fromisoformat(rr.release_candidate("SL-PROOF")["created_at"])
  discovered=datetime.now(timezone.utc)
  if discovered<=promoted: raise RuntimeError("clock did not advance after promotion")
  ss=TradingScannerStore(root/"scanner.db")
  candidate=TradingCandidate(
   101,"BTCUSDT","CRYPTO_SPOT","BINANCE","USDT",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,("SYSTEM_TEST SL routing proof",),
   LiquidityContext(Decimal("1000000"),Decimal("1000000000"),price),VolatilityContext(Decimal("2")),
   "OK",True,discovered,"sl-proof-scan","sl-proof-candidate",QueueState.CANDIDATE,
   invalidation_reference=f"structural stop ({stop})",signal_bar_high=trigger,signal_bar_low=stop)
  ss.record_candidate(candidate)
  engine=Experiment1Engine(root/"experiment1.db")
  kwargs=dict(
   research_repo=rr,scanner_store=ss,engine=engine,dispatch_store=PromotedPaperDispatchStore(root/"dispatch.db"),
   strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
   open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),
   risk_policy=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),345600),
   research_track=ResearchTrack.SL)
  dispatched=dispatch_promoted_candidates(**kwargs)
  assert len(dispatched)==1 and dispatched[0].status=="QUEUED"
  decision_id=dispatched[0].decision_id
  assert rr.release_candidate("SL-PROOF")["research_track"]=="SL"
  source=BinanceExperiment1QuoteSource()
  ing=await drain_trading_decision_inbox(engine,source)
  assert len(ing)==1 and ing[0].outcome=="PENDING",ing
  fills=await run_market_cycle(engine,source)
  assert len(fills)==1 and fills[0].outcome=="PAPER_FILLED",fills
  intent=engine.get_intent(ing[0].intent_id)
  assert intent.account is AccountKind.SPOT and intent.symbol=="BTCUSDT"
  live_fill=fills[0].fill
  fake_tp=MarketQuote("BTCUSDT",intent.take_profit+Decimal("1"),datetime.now(timezone.utc),"SYSTEM_TEST","synthetic-exit",Decimal("0"),Decimal("0"))
  class Q:
   async def quote_for(self,_):return fake_tp
  life=await run_protective_exit_cycle(engine,Q(),(intent.intent_id,))
  assert life[0].outcome=="TAKE_PROFIT"
  closed=engine.closed_trades(AccountKind.SPOT)
  assert len(closed)==1
  return {"track":"SL","entry_source":live_fill.source,"paper_fill_price":str(live_fill.fill_price),
          "closed_trades":len(closed),"realized_pnl":str(closed[0].realized_pnl),
          "decision_id":decision_id,"broker":"ZERO","live_money":"ZERO"}
print(json.dumps(asyncio.run(main()),sort_keys=True))
'''
   ev["paper_e2e"]=cmd([str(REPO/".venv/bin/python"),"-c",proof],240,REPO)

  counts=ev["scan_counts"]
  spot=sum(x["count"] for x in counts if x["sec_type"]=="CRYPTO_SPOT")
  fut=sum(x["count"] for x in counts if x["sec_type"]=="CRYPTO_FUTURES")
  scanner_ok=ev["live_scanner"]["rc"]==0 and spot>0 and fut>0
  timer_ok=all("ActiveState=active" in ev[k]["stdout"] and "UnitFileState=enabled" in ev[k]["stdout"] for k in ("scanner_timer","dispatcher_timer"))
  paper_ok=ev["paper_e2e"]["rc"]==0 and '"track": "SL"' in ev["paper_e2e"]["stdout"] and '"entry_source": "binance-public-rest"' in ev["paper_e2e"]["stdout"]
  required_sl_commit="a712105f8fa62d074bfaae30fba5c4e1b24eb8f1"
  ancestor=cmd(["git","merge-base","--is-ancestor",required_sl_commit,"HEAD"],cwd=REPO)
  ev["required_sl_commit"]=required_sl_commit
  ev["required_sl_commit_is_ancestor"]=ancestor["rc"]==0
  master_ok=ancestor["rc"]==0
  if all((scanner_ok,timer_ok,paper_ok,master_ok)):
   emit(out,"PASS",verdict="SL_CRYPTO_AUTONOMOUS_PAPER_LOOP_PASS",checks={"scanner":scanner_ok,"timers":timer_ok,"paper_e2e":paper_ok,"master":master_ok},evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="SL crypto E2E acceptance failed",checks={"scanner":scanner_ok,"timers":timer_ok,"paper_e2e":paper_ok,"master":master_ok},evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
