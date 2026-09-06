import argparse,json,subprocess
from pathlib import Path

OID="ALPACA-PAPER-RUNTIME-WIRING-001";REPO=Path("/home/ubuntu/MarketHunter")
ENV=REPO/"deploy/systemd/experiment1-runtime.env"
def cmd(args,timeout=180,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def has_env_key(path,key):
 if not path.exists(): return False
 for line in path.read_text(errors="ignore").splitlines():
  s=line.strip()
  if not s or s.startswith("#") or "=" not in s: continue
  k,v=s.split("=",1)
  if k.strip()==key and bool(v.strip()): return True
 return False
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True))
 (p/"alpaca-paper-runtime-proof.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  key=has_env_key(ENV,"EXPERIMENT1_ALPACA_API_KEY_ID")
  secret=has_env_key(ENV,"EXPERIMENT1_ALPACA_API_SECRET_KEY")
  ev["credentials_present"]={"key_id":key,"secret_key":secret}
  # Never expose values. Verify service can construct runtime and fail closed.
  ev["compile"]=cmd([str(REPO/".venv/bin/python"),"-m","py_compile","tools/experiment1_runtime/runtime.py"],120,REPO)
  ev["restart"]=cmd(["sudo","systemctl","restart","experiment1-runtime.service"],180)
  ev["service"]=cmd(["systemctl","show","experiment1-runtime.service","--property=LoadState,ActiveState,SubState,Result,ExecMainStatus","--no-pager"])
  ev["timer"]=cmd(["systemctl","show","experiment1-runtime.timer","--property=LoadState,ActiveState,SubState,UnitFileState,LastTriggerUSec,NextElapseUSecRealtime","--no-pager"])
  ev["journal"]=cmd(["journalctl","-u","experiment1-runtime.service","-n","40","--no-pager","-o","short-iso"])
  service_ok=ev["restart"]["rc"]==0 and "Result=success" in ev["service"]["stdout"]
  timer_ok="ActiveState=active" in ev["timer"]["stdout"] and "UnitFileState=enabled" in ev["timer"]["stdout"]
  code_ok=ev["compile"]["rc"]==0 and ev["sha"]=="5071bc73de4a55998facfbc539c8ce504c5b0e83"
  if not (service_ok and timer_ok and code_ok):
   emit(out,"BLOCKED-RUNTIME",reason="runtime/timer/master proof failed",checks={"service":service_ok,"timer":timer_ok,"master":code_ok},evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO");return
  if key and secret:
   emit(out,"PASS",verdict="ALPACA_PAPER_RUNTIME_WIRED_CREDENTIALS_PRESENT",evidence=ev,live_quote_proof="NOT_RUN_MARKET_CLOSED_OR_SEPARATE",broker_orders="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"NEEDS-CREDENTIALS",verdict="ALPACA_PAPER_RUNTIME_WIRED_FAIL_CLOSED",evidence=ev,missing={"key_id":not key,"secret_key":not secret},broker_orders="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
