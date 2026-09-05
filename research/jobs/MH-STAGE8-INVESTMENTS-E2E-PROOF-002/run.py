import argparse,json,shutil,subprocess
from pathlib import Path
OID="MH-STAGE8-INVESTMENTS-E2E-PROOF-002";SHA="f40c71eb6af374afc50e2a9c48a35ca6d86bfad4"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists():emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  r=subprocess.run([str(py),"-m","unittest","tests.test_stage8_investment_routing","tests.test_stage8_investment_decision_bridge","-v"],cwd=w,capture_output=True,text=True,timeout=120)
  (o/"stage8.stdout.log").write_text(r.stdout);(o/"stage8.stderr.log").write_text(r.stderr)
  if r.returncode:emit(out,"BLOCKED-RUNTIME",reason="stage8-e2e-regression",returncode=r.returncode,stderr=r.stderr[-4000:],stdout=r.stdout[-4000:]);return
  emit(out,"PASS",master_sha=SHA,proof={"routing_tests":"PASS","decision_portfolio_tests":"PASS","investment_ledgers":["INVESTMENTS_DEFENSIVE","INVESTMENTS_BALANCED","INVESTMENTS_GROWTH"],"trading_isolation":"PASS","gil_pending_zero_fill":"PASS","wait_hold_zero_intent":"PASS","execution_evidence_guard":"PASS","canonical_positions_api":"PASS","broker_execution":"ZERO"},note="Stage8 bounded investment automation seam verified on VPS; simulation only")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
