import argparse, json, shutil, subprocess
from pathlib import Path
OID="GIL-BREAKOUT-LONG-SMA20-TREND-EXIT-VALIDATION-001"; SHA="8925eb710170edc7b614471162f85c2da8d31a3f"
def emit(out,state,**extra):
 p=Path(out); p.mkdir(parents=True,exist_ok=True); (p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":state,**extra},sort_keys=True))
def main(job,out):
 outp=Path(out).resolve(); repo=outp/"repo"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(repo)],check=True,timeout=120)
  subprocess.run(["git","-C",str(repo),"checkout","--quiet",SHA],check=True,timeout=30)
  p=subprocess.run(["python3","-m","research.run_breakout_trend_exit_validation"],cwd=repo,capture_output=True,text=True,timeout=300)
  (outp/"breakout-sma20-trend-exit.json").write_text(p.stdout); (outp/"runner-stderr.txt").write_text(p.stderr)
  if p.returncode: emit(out,"BLOCKED-RUNTIME",master_sha=SHA,reason="runner-failed",returncode=p.returncode); return
  data=json.loads(p.stdout); oos=data.get("oos_total")
  if not isinstance(oos,dict) or not oos.get("trades"): emit(out,"BLOCKED-RUNTIME",master_sha=SHA,reason="missing-oos-evidence"); return
  emit(out,"EVIDENCE_READY",master_sha=SHA,hypothesis=data.get("hypothesis"),oos_total=oos,per_symbol=[{"symbol":x["symbol"],"oos":x["oos"]} for x in data.get("symbols",[])],notes=data.get("notes",{}),broker_execution="ZERO",live_money="ZERO")
 except Exception as e: emit(out,"BLOCKED-RUNTIME",master_sha=SHA,reason="exception",detail=repr(e))
 finally:
  if repo.exists(): shutil.rmtree(repo,ignore_errors=True)
if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("--job",required=True); ap.add_argument("--output",required=True); a=ap.parse_args(); main(a.job,a.output)
