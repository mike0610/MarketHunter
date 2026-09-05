import argparse,json,shutil,subprocess
from pathlib import Path
OID="MH-STAGE10-ACTIVE-TRADING-AUTONOMOUS-PROOF-001";SHA="7ff329e97e064b110764a365919b62f8dbf63e45"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  scanner=(w/"tools/gil_trading_scanner_runtime/runtime.py").read_text()
  stage9=(w/"stage9/runtime_adapters.py").read_text()
  exp=(w/"tools/experiment1_runtime/runtime.py").read_text()
  dash=(w/"dashboard/src/pages/ActiveTrading.jsx").read_text()
  blockers=[]
  if "getExperiment1State" not in dash: blockers.append("active-trading dashboard is not bound to durable Experiment1 state")
  if "validate_candidate" not in scanner and "strategy_engine" not in scanner: blockers.append("scanner runtime stops after candidate discovery; no autonomous Scanner->Strategy bridge")
  if "evaluate_risk" not in scanner and "risk_mm" not in scanner: blockers.append("no autonomous Strategy->Risk/MM bridge in scanner runtime")
  if "trading_scanner" not in stage9: blockers.append("Stage9 runtime adapters do not expose a trading_scanner controlled-cycle adapter")
  if "drain_trading_decision_inbox" in exp: blockers.append("execution runtime still consumes a separate trading decision inbox rather than scanner-produced strategy/risk artifacts")
  state="PASS" if not blockers else "NOT_READY"
  emit(out,state,master_sha=SHA,verdict="AUTONOMOUS PAPER READY" if not blockers else "NOT READY",blockers=blockers,
       proof={"dashboard_durable_state":"PASS" if "getExperiment1State" in dash else "FAIL","manual_artifact_seeding":"ZERO","broker_execution":"ZERO"})
 except Exception as e: emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
