import argparse,json,os,shutil,sqlite3,subprocess
from pathlib import Path
OID="MH-STAGE4-RISK-MM-LIVE-PROOF-001"; SHA="16021cdaf07f0d7f763b0bd32f1bbc832a759ef3"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve(); w=o/"repo"; db=o/"stage4.db"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists(): emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  env=os.environ.copy();env.update({"PYTHONPATH":str(w),"TRADING_SCANNER_DB_PATH":str(db),"TRADING_SCANNER_MARKET_DATA_PROVIDER":"yahoo","TRADING_SCANNER_UNIVERSE_SYMBOLS":"SPY,QQQ,AAPL,MSFT,NVDA","TRADING_SCANNER_MAX_DATA_AGE_SECONDS":"345600"})
  s=subprocess.run([str(py),"-m","tools.gil_trading_scanner_runtime.runtime"],cwd=w,env=env,capture_output=True,text=True,timeout=240)
  if s.returncode: emit(out,"BLOCKED-RUNTIME",reason="scanner",stderr=s.stderr[-2000:]);return
  code=r"""
import os,sqlite3
from datetime import datetime,timezone
from decimal import Decimal
from strategies.registry_foundation import StrategyUsability,StrategyVersionAssessment
from strategy_engine.engine import validate_candidate
from strategy_engine.store import StrategyDecisionStore
from trading_scanner.models import QueueState
from trading_scanner.store import TradingScannerStore
from risk_mm.engine import evaluate_risk
from risk_mm.models import *
from risk_mm.store import RiskPlanStore
db=os.environ["TRADING_SCANNER_DB_PATH"]; cs=TradingScannerStore(db).list_candidates(queue_state=QueueState.CANDIDATE)
if not cs: raise SystemExit(21)
ss=StrategyDecisionStore(db); rs=RiskPlanStore(db); usable=StrategyVersionAssessment(StrategyUsability.USABLE,())
policy=RiskPolicy("MH-RISK","1",Decimal("0.5"),Decimal("2"),Decimal("1"),Decimal("3"),3600)
agg=Decimal("0"); cluster=Decimal("0"); now=datetime.now(timezone.utc)
for c in cs:
 d=validate_candidate(c,strategy_assessment=usable,decided_at=now);ss.record(d)
 if d.outcome.value not in ("LONG","SHORT"): continue
 stop=c.liquidity.last_price*(Decimal("0.98") if d.outcome.value=="LONG" else Decimal("1.02"))
 ri=RiskInput(d.decision_id,c.symbol,d.outcome.value,d.decided_at,d.candidate_evidence_status,c.liquidity.last_price,stop,"US_MEGA_LARGE")
 st=PortfolioRiskState(TradingAccount.SPOT,Decimal("2000"),Decimal("2000"),agg,cluster,"US_MEGA_LARGE",Decimal("1"))
 p=evaluate_risk(ri,st,policy,evaluated_at=now);rs.record(p)
 if p.decision.value=="APPROVED": agg+=p.risk_amount;cluster+=p.risk_amount
"""
  r=subprocess.run([str(py),"-c",code],cwd=w,env=env,capture_output=True,text=True,timeout=90)
  if r.returncode==21: emit(out,"BLOCKED-EVIDENCE",reason="zero-candidates");return
  if r.returncode: emit(out,"BLOCKED-RUNTIME",reason="risk-runtime",stderr=r.stderr[-3000:]);return
  con=sqlite3.connect(db);tables={x[0] for x in con.execute("select name from sqlite_master where type='table'")}
  rows=[{"symbol":x[0],"decision":x[1],"risk_amount":x[2],"notional":x[3]} for x in con.execute("select s.symbol,r.decision,r.risk_amount,r.notional from risk_sized_plans r join strategy_decisions s on s.decision_id=r.trading_decision_id order by s.symbol")]
  bad=sorted(t for t in tables if any(k in t.lower() for k in ("order","fill","position","ledger","intent")));con.close()
  if not rows: emit(out,"BLOCKED-EVIDENCE",reason="zero-risk-plans");return
  if bad: emit(out,"BLOCKED-RUNTIME",reason="execution-artifacts",tables=bad);return
  emit(out,"PASS",master_sha=SHA,risk_plans=rows,trading_artifact_tables=[],note="Stage4 deterministic Risk/MM only")
 except Exception as e: emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists(): shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
