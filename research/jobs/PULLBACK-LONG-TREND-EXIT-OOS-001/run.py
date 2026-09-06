import argparse,json,subprocess
from pathlib import Path
OID="PULLBACK-LONG-TREND-EXIT-OOS-001";REPO=Path("/home/ubuntu/MarketHunter")
def c(a,t=300):p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=REPO);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def main(job,out):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);ev={}
 try:
  ev["fetch"]=c(["git","fetch","origin","master"],120);ev["pull"]=c(["git","pull","--ff-only","origin","master"],120);ev["sha"]=c(["git","rev-parse","HEAD"])["stdout"];r=c([str(REPO/".venv/bin/python"),"-m","research.run_pullback_trend_exit_validation"]);ev["run"]=r
  state="EVIDENCE_READY" if r["rc"]==0 and '"oos_total"' in r["stdout"] else "BLOCKED-RUNTIME"
 except Exception as e:state="BLOCKED-RUNTIME";ev["exception"]=repr(e)
 d={"object_id":OID,"terminal_state":state,"evidence":ev,"broker":"ZERO","ibkr":"ZERO","live_money":"ZERO"}
 (p/"terminal_result.json").write_text(json.dumps(d));(p/"pullback-trend-exit-oos.json").write_text(json.dumps(d,indent=2))
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("--job",required=True);a.add_argument("--output",required=True);x=a.parse_args();main(x.job,x.output)
