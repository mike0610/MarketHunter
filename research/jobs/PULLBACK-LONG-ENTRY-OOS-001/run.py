import argparse,json,subprocess
from pathlib import Path
OID="PULLBACK-LONG-ENTRY-OOS-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=300,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True))
 (p/"pullback-oos-evidence.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],cwd=REPO,timeout=120)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],cwd=REPO,timeout=120)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  run=cmd([str(REPO/".venv/bin/python"),"-m","research.run_pullback_validation"],cwd=REPO,timeout=300)
  ev["run"]=run
  if run["rc"]==0 and "OOS TOTAL:" in run["stdout"]:
   emit(out,"EVIDENCE_READY",evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="historical runner failed",evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();main(a.job,a.output)
