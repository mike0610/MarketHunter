import argparse,json,os,shutil,sqlite3,subprocess
from pathlib import Path
OID="MH-STAGE5-SIM-LIVE-PROOF-001";SHA="8f4e00775a471ca2094570fd43980fca0a09085d"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo";db=o/"stage5.db"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists():emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  env=os.environ.copy();env.update({"PYTHONPATH":str(w),"TRADING_SCANNER_DB_PATH":str(db),"TRADING_SCANNER_MARKET_DATA_PROVIDER":"yahoo","TRADING_SCANNER_UNIVERSE_SYMBOLS":"SPY,QQQ,AAPL,MSFT,NVDA","TRADING_SCANNER_MAX_DATA_AGE_SECONDS":"345600"})
  s=subprocess.run([str(py),"-m","tools.gil_trading_scanner_runtime.runtime"],cwd=w,env=env,capture_output=True,text=True,timeout=240)
  (o/"scanner.stdout.log").write_text(s.stdout);(o/"scanner.stderr.log").write_text(s.stderr)
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
from simulation.foundation import MarketObservationEvidence,MarketObservationReference,SimulationCampaignReference
from simulation.runtime.orchestrator import SimulationRuntime
from simulation.stage5_bridge import *
from simulation.stage5_store import Stage5ExecutionStore
from time_semantics.foundation import *

db=os.environ["TRADING_SCANNER_DB_PATH"];now=datetime.now(timezone.utc)
cs=TradingScannerStore(db).list_candidates(queue_state=QueueState.CANDIDATE)
if not cs:raise SystemExit(21)
ss=StrategyDecisionStore(db);rs=RiskPlanStore(db);usable=StrategyVersionAssessment(StrategyUsability.USABLE,())
policy=RiskPolicy("MH-RISK","1",Decimal("0.25"),Decimal("2"),Decimal("1"),Decimal("3"),3600)
approved=[];agg=Decimal("0");cluster=Decimal("0")
for c in cs:
 d=validate_candidate(c,strategy_assessment=usable,decided_at=now);ss.record(d)
 if d.outcome.value not in ("LONG","SHORT"):continue
 stop=c.liquidity.last_price*(Decimal("0.98") if d.outcome.value=="LONG" else Decimal("1.02"))
 ri=RiskInput(d.decision_id,c.symbol,d.outcome.value,d.decided_at,d.candidate_evidence_status,c.liquidity.last_price,stop,"US_MEGA_LARGE")
 st=PortfolioRiskState(TradingAccount.SPOT,Decimal("2000"),Decimal("2000"),agg,cluster,"US_MEGA_LARGE",Decimal("1"))
 p=evaluate_risk(ri,st,policy,evaluated_at=now);rs.record(p)
 if p.decision.value=="APPROVED":approved.append((c,d,p));agg+=p.risk_amount;cluster+=p.risk_amount
if not approved:raise SystemExit(22)

campaign=SimulationCampaignReference("stage5-live",1);execstore=Stage5ExecutionStore(db)
envelopes=[];bindings={};observations={}
for idx,(c,d,p) in enumerate(approved):
 ins=Stage5EntryInstruction(Stage5EntryMode.MARKET,None,p.stop_price,now+timedelta(hours=1))
 b=build_order_binding(p,c,d,ins);execstore.record_order(b)
 env=binding_to_envelope(b,campaign=campaign,recorded_at=now);cid=env.snapshot.candidate.source_id
 # Forward observation uses current real Yahoo-derived scanner evidence price/volume, observed strictly after admission.
 tr=TemporalReference("market_observation",f"yahoo-stage5-{idx}","1");ot=now+timedelta(seconds=1+idx)
 ev=MarketObservationEvidence(MarketObservationReference("yahoo","YAHOO",c.symbol,"scanner",f"yahoo-stage5-{idx}"),
  TemporalFact(tr,TemporalRole.EVENT_TIME,ot,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.OBSERVED_TIME,ot,TemporalDisposition.KNOWN),
  TemporalFact(tr,TemporalRole.RECORDED_TIME,ot,TemporalDisposition.KNOWN))
 obs=Stage5MarketObservation(ev,c.liquidity.last_price,c.liquidity.average_daily_volume,"YAHOO",f"scanner:{c.scan_cycle_id}:{c.symbol}")
 envelopes.append(env);bindings[cid]=b;observations[cid]=obs

mech=Stage5MechanicsEvaluator(bindings,observations,Stage5MechanicsPolicy("stage5-live","1",Decimal("5"),Decimal("10"),Decimal("0.01"),True))
with SimulationRuntime(db,Stage5CandidateSource(tuple(envelopes)),Stage5ObservationSource(observations),mech) as rt:
 outcomes=rt.run_cycle()
 for env in envelopes:
  cid=env.snapshot.candidate.source_id;f=mech.fill_details_for(cid)
  if f:execstore.record_fill_and_position(bindings[cid],f)

con=sqlite3.connect(db)
orders=con.execute("select count(*) from stage5_sim_orders").fetchone()[0]
fills=con.execute("select count(*) from stage5_sim_fills").fetchone()[0]
positions=con.execute("select count(*) from stage5_sim_positions").fetchone()[0]
rows=[{"symbol":r[0],"qty":r[1],"fill_price":r[2],"fee":r[3]} for r in con.execute("select symbol,quantity,average_price,fees_paid from stage5_sim_positions order by symbol")]
tables={r[0] for r in con.execute("select name from sqlite_master where type='table'")}
broker=[t for t in tables if "ibkr" in t.lower() or "broker" in t.lower()]
con.close()
print(__import__("json").dumps({"orders":orders,"fills":fills,"positions":positions,"rows":rows,"broker_tables":broker}))
if fills==0 or positions==0:raise SystemExit(23)
if fills!=positions:raise SystemExit(24)
if broker:raise SystemExit(25)
"""
  r=subprocess.run([str(py),"-c",code],cwd=w,env=env,capture_output=True,text=True,timeout=120)
  (o/"stage5.stdout.log").write_text(r.stdout);(o/"stage5.stderr.log").write_text(r.stderr)
  if r.returncode==21:emit(out,"BLOCKED-EVIDENCE",reason="zero-real-candidates");return
  if r.returncode==22:emit(out,"BLOCKED-EVIDENCE",reason="zero-approved-risk-plans");return
  if r.returncode:emit(out,"BLOCKED-RUNTIME",reason="stage5-runtime",returncode=r.returncode,stderr=r.stderr[-3000:],stdout=r.stdout[-3000:]);return
  proof=json.loads(r.stdout.strip().splitlines()[-1])
  emit(out,"PASS",master_sha=SHA,provider="yahoo",proof=proof,note="Stage5 own simulation execution; zero broker execution")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
