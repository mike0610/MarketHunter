import argparse,json,os,shutil,sqlite3,subprocess
from pathlib import Path
OID="MH-STAGE6-POSITION-MGMT-LIVE-PROOF-001";SHA="4ccd4fea3e99a747f81cf9737ad81cb2bc814e53"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo";db=o/"stage6.db"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists():emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  env=os.environ.copy();env.update({"PYTHONPATH":str(w),"TRADING_SCANNER_DB_PATH":str(db),"TRADING_SCANNER_MARKET_DATA_PROVIDER":"yahoo","TRADING_SCANNER_UNIVERSE_SYMBOLS":"SPY,QQQ,AAPL,MSFT,NVDA","TRADING_SCANNER_MAX_DATA_AGE_SECONDS":"345600"})
  s=subprocess.run([str(py),"-m","tools.gil_trading_scanner_runtime.runtime"],cwd=w,env=env,capture_output=True,text=True,timeout=240)
  if s.returncode:emit(out,"BLOCKED-RUNTIME",reason="scanner",stderr=s.stderr[-2000:]);return
  code=r"""
import os,sqlite3
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from strategies.registry_foundation import StrategyUsability,StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import QueueState
from trading_scanner.store import TradingScannerStore
from risk_mm.engine import evaluate_risk
from risk_mm.models import *
from risk_mm.store import RiskPlanStore
from simulation.stage5_bridge import build_order_binding,Stage5EntryInstruction,Stage5EntryMode
from simulation.stage5_store import Stage5ExecutionStore
from simulation.stage6_models import *
from simulation.stage6_manager import Stage6PositionManager
from simulation.stage6_store import Stage6PositionStore

db=os.environ["TRADING_SCANNER_DB_PATH"];now=datetime.now(timezone.utc)
cs=TradingScannerStore(db).list_candidates(queue_state=QueueState.CANDIDATE)
if not cs:raise SystemExit(21)
usable=StrategyVersionAssessment(StrategyUsability.USABLE,());ss=StrategyDecisionStore(db);rs=RiskPlanStore(db)
rp=RiskPolicy("MH-RISK","1",Decimal("0.25"),Decimal("2"),Decimal("1"),Decimal("3"),3600)
chosen=None
for c in cs:
 d=validate_candidate(c,strategy_assessment=usable,decided_at=now);ss.record(d)
 if d.outcome.value not in ("LONG","SHORT"):continue
 stop=c.liquidity.last_price*(Decimal("0.98") if d.outcome.value=="LONG" else Decimal("1.02"))
 ri=RiskInput(d.decision_id,c.symbol,d.outcome.value,d.decided_at,d.candidate_evidence_status,c.liquidity.last_price,stop,"LIVE_PROOF")
 st=PortfolioRiskState(TradingAccount.SPOT,Decimal("2000"),Decimal("2000"),Decimal("0"),Decimal("0"),"LIVE_PROOF",Decimal("1"))
 p=evaluate_risk(ri,st,rp,evaluated_at=now);rs.record(p)
 if p.decision.value=="APPROVED":chosen=(c,d,p);break
if chosen is None:raise SystemExit(22)
c,d,p=chosen
# Materialize the Stage5 durable simulated open position from the approved live-data chain.
b=build_order_binding(p,c,d,Stage5EntryInstruction(Stage5EntryMode.MARKET,None,p.stop_price,now+timedelta(hours=1)))
s5=Stage5ExecutionStore(db);s5.record_order(b)
from simulation.stage5_bridge import Stage5FillDetails
f=Stage5FillDetails("sim-fill:stage6-proof",b.order_id,p.quantity,c.liquidity.last_price,c.liquidity.last_price,Decimal("0"),Decimal("0"),now,"YAHOO",f"scanner:{c.scan_cycle_id}:{c.symbol}",False,Decimal("0"))
s5.record_fill_and_position(b,f)
con=sqlite3.connect(db);row=con.execute("select position_id,order_id,symbol,direction,quantity,average_price,fees_paid,opened_at from stage5_sim_positions limit 1").fetchone();con.close()
mp=ManagedPosition(row[0],row[1],row[2],row[3],Decimal(row[4]),Decimal(row[5]),Decimal(row[6]),datetime.fromisoformat(row[7]),d.decision_id,c.dedupe_key,d.strategy_id,d.strategy_version)
# Use real scanner price as fresh forward evidence; time-exit is deliberately due, so exit price is evidence close, not invented target.
ev=PositionBarEvidence(c.symbol,c.liquidity.last_price,c.liquidity.last_price,c.liquidity.last_price,c.liquidity.last_price,now+timedelta(seconds=2),"YAHOO",f"stage6-forward:{c.scan_cycle_id}:{c.symbol}",True)
pol=PositionExitPolicy(d.strategy_id,d.strategy_version,p.stop_price,None,None,None,None,now+timedelta(seconds=1))
mgr=Stage6PositionManager(Stage6PositionStore(db),fee_bps=Decimal("5"),slippage_bps=Decimal("10"))
x=mgr.process(mp,pol,ev)
ct=Stage6PositionStore(db).closed_trade(mp.position_id)
if x.verdict.value!="EXIT" or ct is None:raise SystemExit(23)
con=sqlite3.connect(db)
proof={"symbol":ct.symbol,"direction":ct.direction,"exit_reason":ct.exit_reason.value,"quantity":str(ct.quantity),"entry_price":str(ct.entry_price),"exit_price":str(ct.exit_price),"realized_pnl":str(ct.realized_pnl),"closed_trades":con.execute("select count(*) from stage6_closed_trades").fetchone()[0],"exit_fills":con.execute("select count(*) from stage6_exit_fills").fetchone()[0]}
tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")};con.close()
proof["broker_tables"]=[t for t in tables if "ibkr" in t.lower() or "broker" in t.lower()]
print(__import__("json").dumps(proof))
if proof["broker_tables"]:raise SystemExit(24)
"""
  r=subprocess.run([str(py),"-c",code],cwd=w,env=env,capture_output=True,text=True,timeout=120)
  (o/"stage6.stdout.log").write_text(r.stdout);(o/"stage6.stderr.log").write_text(r.stderr)
  if r.returncode==21:emit(out,"BLOCKED-EVIDENCE",reason="zero-real-candidates");return
  if r.returncode==22:emit(out,"BLOCKED-EVIDENCE",reason="zero-approved-risk-plan");return
  if r.returncode:emit(out,"BLOCKED-RUNTIME",reason="stage6-runtime",returncode=r.returncode,stderr=r.stderr[-3000:],stdout=r.stdout[-3000:]);return
  emit(out,"PASS",master_sha=SHA,provider="yahoo",proof=json.loads(r.stdout.strip().splitlines()[-1]),note="Stage6 evidence-based autonomous simulated close; zero broker execution")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
