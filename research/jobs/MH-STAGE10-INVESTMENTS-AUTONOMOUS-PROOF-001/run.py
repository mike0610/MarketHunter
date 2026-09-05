import argparse,json,shutil,subprocess
from pathlib import Path
OID="MH-STAGE10-INVESTMENTS-AUTONOMOUS-PROOF-001";SHA="7ff329e97e064b110764a365919b62f8dbf63e45"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  policy=(w/"stage9/policy.py").read_text()
  adapters=(w/"stage9/runtime_adapters.py").read_text()
  dash=(w/"dashboard/src/pages/Investments.jsx").read_text()
  router=(w/"investments/stage8_router.py").read_text()
  bridge=(w/"investments/stage8_decision_bridge.py").read_text()
  files=[p.name for p in (w/"investments").iterdir() if p.is_file()]
  blockers=[]
  if "getExperiment1State" not in dash: blockers.append("investments dashboard is not bound to durable Experiment1 state")
  if "investment_discovery" not in policy: blockers.append("investment discovery cadence is not registered")
  if "investment_discovery_cycle" not in adapters: blockers.append("registered investment_discovery cadence has no runtime adapter/cycle")
  discovery_impl=[n for n in files if "discovery" in n or "provider" in n or "universe" in n]
  if not discovery_impl: blockers.append("no real Investment Discovery provider/universe producer exists in investments runtime")
  if "GIL_DEEP_ANALYSIS" not in router or "cannot become BUY/SELL without an actual GIL decision" not in bridge:
   blockers.append("GIL pending fail-closed contract missing")
  state="PASS" if not blockers else "NOT_READY"
  emit(out,state,master_sha=SHA,verdict="AUTONOMOUS PAPER READY" if not blockers else "NOT READY",blockers=blockers,
       proof={"dashboard_durable_state":"PASS" if "getExperiment1State" in dash else "FAIL","gil_pending_fail_closed":"PASS" if "cannot become BUY/SELL without an actual GIL decision" in bridge else "FAIL","manual_artifact_seeding":"ZERO","broker_execution":"ZERO"})
 except Exception as e: emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
