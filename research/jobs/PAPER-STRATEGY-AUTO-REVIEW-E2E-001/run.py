import argparse,json,sqlite3,subprocess,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

OID="PAPER-STRATEGY-AUTO-REVIEW-E2E-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(a,t=180):
 p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=REPO);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def show(u):return cmd(["systemctl","show",u,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**x}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True,default=str));(p/"paper-review-e2e.json").write_text(json.dumps(d,indent=2,sort_keys=True,default=str))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"]);ev["pull"]=cmd(["git","pull","--ff-only","origin","master"]);ev["sha"]=cmd(["git","rev-parse","HEAD"])["stdout"]
  for name in ("paper-strategy-review.service","paper-strategy-review.timer"):
   ev["install:"+name]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd"/name),"/etc/systemd/system/"+name])
  ev["daemon"]=cmd(["sudo","systemctl","daemon-reload"]);ev["enable"]=cmd(["sudo","systemctl","enable","--now","paper-strategy-review.timer"])
  ev["timer"]=show("paper-strategy-review.timer")

  proof=r'''
import sqlite3,tempfile
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from experiment1.engine import Experiment1Engine
from research.autonomous_loop.models import ResearchObject,ResearchTrack
from research.autonomous_loop.repository import AutonomousResearchRepository
from risk_mm.models import RiskPolicy
from risk_mm.open_risk_ledger import OpenRiskLedger
from risk_mm.store import RiskPlanStore
from stage10.paper_strategy_review import PaperReviewPolicy,PaperReviewStatus,PaperStrategyReviewStore,run_review_cycle
from stage10.promoted_paper_dispatcher import PromotedPaperDispatchStore,dispatch_promoted_candidates
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import LiquidityContext,QueueState,SetupFamily,TradingCandidate,VolatilityContext
from trading_scanner.store import TradingScannerStore

NOW=datetime.now(timezone.utc)
with tempfile.TemporaryDirectory() as td:
 root=Path(td);exp=root/"experiment.db";dispatch=root/"dispatch.db";review=root/"review.db"
 Experiment1Engine(exp);ds=PromotedPaperDispatchStore(dispatch)
 for i in range(30):
  decision=f"D{i}";entry=f"trading-decision:{decision}"
  ds.record(object_id="O",dedupe=f"C{i}",decision_id=decision,strategy_id="S",version="1",hypothesis_id="H",
            research_track="SL",strategy_decision_id=f"SD{i}",risk_plan_id=f"RP{i}",risk_amount=Decimal("10"))
  with sqlite3.connect(exp) as c:
   c.execute("""insert into experiment1_trading_decision_inbox
    (decision_id,received_at,raw_payload,status,outcome,outcome_reason,intent_id,processed_at)
    values(?,?,?,?,?,?,?,?)""",(decision,NOW.isoformat(),"{}","PROCESSED","PENDING",None,entry,NOW.isoformat()))
   t=NOW+timedelta(minutes=i*2)
   c.execute("""insert into experiment1_fills
    (intent_id,account,action,symbol,quantity,reference_price,fill_price,fee,leverage,observed_at,source,source_reference,realized_pnl_delta)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(entry,"SPOT","BUY","BTCUSDT","1","100","100","0","1",t.isoformat(),"TEST","e","0"))
   c.execute("""insert into experiment1_fills
    (intent_id,account,action,symbol,quantity,reference_price,fill_price,fee,leverage,observed_at,source,source_reference,realized_pnl_delta)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(entry+":protective:STOP_LOSS","SPOT","SELL","BTCUSDT","1","95","95","0","1",(t+timedelta(minutes=1)).isoformat(),"TEST","x","-5"))
 r1=run_review_cycle(dispatch_db=dispatch,experiment_db=exp,review_db=review,policy=PaperReviewPolicy(30))
 r2=run_review_cycle(dispatch_db=dispatch,experiment_db=exp,review_db=review,policy=PaperReviewPolicy(30))
 assert len(r1)==1 and r1[0].status is PaperReviewStatus.PAUSE and r1[0].average_net_r==Decimal("-0.5")
 with sqlite3.connect(review) as c:
  assert c.execute("select count(*) from paper_strategy_review_events").fetchone()[0]==1

 repo=AutonomousResearchRepository(root/"research.db")
 repo.enqueue(ResearchObject("O","BTCUSDT","LONG","H",research_track=ResearchTrack.SL))
 repo.terminal("O","PROMOTION-ELIGIBLE",{"paper_contract":{
  "strategy_id":"S","version":"1","setup_family":"BREAKOUT_OR_PULLBACK_IN_TREND","direction":"LONG","account":"SPOT",
  "requested_leverage":"1","cluster_key":"CRYPTO","entry_trigger_source":"SIGNAL_BAR_HIGH","expiry_seconds":86400,"take_profit_r":"2"
 }},hypothesis_id="H")
 promoted=datetime.fromisoformat(repo.release_candidate("O")["created_at"])
 scanner=TradingScannerStore(root/"scanner.db")
 scanner.record_candidate(TradingCandidate(999,"BTCUSDT","CRYPTO_SPOT","BINANCE","USDT",SetupFamily.BREAKOUT_OR_PULLBACK_IN_TREND,
  ("new forward setup",),LiquidityContext(Decimal("1000000"),Decimal("1000000000"),Decimal("100")),
  VolatilityContext(Decimal("2")),"OK",True,promoted+timedelta(seconds=1),"scan-new","cand-new",QueueState.CANDIDATE,
  invalidation_reference="structural stop (95)",signal_bar_high=Decimal("101"),signal_bar_low=Decimal("96")))
 engine=Experiment1Engine(root/"paper.db")
 out=dispatch_promoted_candidates(
  research_repo=repo,scanner_store=scanner,engine=engine,dispatch_store=PromotedPaperDispatchStore(root/"dispatch2.db"),
  strategy_store=StrategyDecisionStore(root/"strategy.db"),risk_store=RiskPlanStore(root/"risk.db"),
  open_risk_ledger=OpenRiskLedger(root/"openrisk.db"),risk_policy=RiskPolicy("MH-RISK","1",Decimal("1"),Decimal("3"),Decimal("2"),Decimal("3"),345600),
  research_track=ResearchTrack.SL,review_store=PaperStrategyReviewStore(review))
 assert len(out)==1 and out[0].status=="PAUSED"
 assert engine.trading_decision_inbox_status("promoted-paper:O:cand-new") is None
 print("PAPER_REVIEW_E2E_PASS",r1[0].status.value,str(r1[0].average_net_r),str(r1[0].profit_factor_r),out[0].status)
'''
  ev["proof"]=cmd([str(REPO/".venv/bin/python"),"-c",proof],180)
  timer_ok="ActiveState=active" in ev["timer"]["stdout"] and "UnitFileState=enabled" in ev["timer"]["stdout"]
  proof_ok=ev["proof"]["rc"]==0 and ev["proof"]["stdout"].startswith("PAPER_REVIEW_E2E_PASS PAUSE -0.5 ") and ev["proof"]["stdout"].endswith(" PAUSED")
  master_ok=ev["sha"]=="b7c97e8b2303e7cf7a262f448968683376367074"
  emit(out,"PASS" if timer_ok and proof_ok and master_ok else "BLOCKED-RUNTIME",
       verdict="PAPER_STRATEGY_AUTO_REVIEW_PASS" if timer_ok and proof_ok and master_ok else None,
       checks={"timer":timer_ok,"proof":proof_ok,"master":master_ok},evidence=ev,broker="ZERO",live_money="ZERO")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
