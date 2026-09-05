import argparse,json,shutil,subprocess
from pathlib import Path
OID="MH-STAGE9-RELIABILITY-PROOF-001";SHA="12d965f4d7182299c1fd16a499de95f2ff74ed0e"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists():emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  mods=["tests.test_stage9_orchestration","tests.test_stage9_runtime_health","tests.test_stage9_runtime_adapters","tests.test_experiment1_runtime_scheduler"]
  r=subprocess.run([str(py),"-m","unittest",*mods,"-v"],cwd=w,capture_output=True,text=True,timeout=180)
  (o/"stage9.stdout.log").write_text(r.stdout);(o/"stage9.stderr.log").write_text(r.stderr)
  if r.returncode:emit(out,"BLOCKED-RUNTIME",reason="stage9-reliability-regression",returncode=r.returncode,stderr=r.stderr[-5000:],stdout=r.stdout[-5000:]);return
  emit(out,"PASS",master_sha=SHA,proof={"scheduled_cycles":"PASS","transient_failure_isolation":"PASS","retry_backoff":"PASS","restart_durable_resume":"PASS","overlap_protection":"PASS","repeated_cycle_zero_duplicate_work":"PASS","independent_runtime_leases":"PASS","health_state":"PASS","broker_execution":"ZERO"},note="Stage 9 bounded orchestration/reliability proof on VPS")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
