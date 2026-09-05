import argparse,json,subprocess
from pathlib import Path
OID="STAGE10-FINAL-AUTOMATION-PROOF-003";EXPECTED_SHA="96f347be95ed4286d9bf4b9da1d684ab6a3b9d97"
REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=180,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def show(unit):
 return cmd(["systemctl","show",unit,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 data={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(data,sort_keys=True))
 (p/"final-automation-proof.json").write_text(json.dumps(data,indent=2,sort_keys=True))
def run_case(account,db):
 if db.exists(): db.unlink()
 p=cmd([str(REPO/".venv/bin/python"),"-m","stage10.system_test_e2e","--db",str(db),"--account",account],timeout=180,cwd=REPO)
 if p["rc"]!=0:return {"process":p,"result":None}
 try:r=json.loads(p["stdout"])
 except Exception:r=None
 return {"process":p,"result":r}
def main(job,out):
 ev={}
 try:
  cmd(["git","fetch","origin","master"],timeout=120,cwd=REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],timeout=120,cwd=REPO)
  sha=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"];ev["deployed_sha"]=sha
  if sha!=EXPECTED_SHA:raise RuntimeError(f"VPS SHA {sha} != {EXPECTED_SHA}")
  ev["spot"]=run_case("SPOT",REPO/"data/stage10-system-test-spot.db")
  ev["futures"]=run_case("FUTURES",REPO/"data/stage10-system-test-futures.db")
  for k,u in [("scanner_timer","gil-trading-scanner-runtime.timer"),("experiment_timer","experiment1-runtime.timer"),("crypto_timer","crypto-paper-observer.timer"),("scanner_service","gil-trading-scanner-runtime.service"),("experiment_service","experiment1-runtime.service")]:
   ev[k]=show(u)
  ev["scanner_journal"]=cmd(["journalctl","-u","gil-trading-scanner-runtime.service","-n","30","--no-pager","-o","short-iso"])
  ev["experiment_journal"]=cmd(["journalctl","-u","experiment1-runtime.service","-n","50","--no-pager","-o","short-iso"])
  s=ev["spot"]["result"];f=ev["futures"]["result"]
  cases_ok=bool(s and f and s.get("status")=="PASS" and s.get("risk_decision")=="APPROVED" and s.get("leverage")=="1" and s.get("test_only_excluded_from_reports") is True and f.get("status")=="PASS" and f.get("risk_decision")=="APPROVED" and f.get("leverage")=="3" and f.get("test_only_excluded_from_reports") is True)
  timers_ok=all("ActiveState=active" in ev[k]["stdout"] and "UnitFileState=enabled" in ev[k]["stdout"] for k in ("scanner_timer","experiment_timer","crypto_timer"))
  scanner_ok="Result=success" in ev["scanner_service"]["stdout"] and "scanner cycle complete" in ev["scanner_journal"]["stdout"]
  experiment_ok="Result=success" in ev["experiment_service"]["stdout"] and "experiment1 runtime cycle complete" in ev["experiment_journal"]["stdout"] and "Trading Slack transport: disabled" in ev["experiment_journal"]["stdout"]
  if cases_ok and timers_ok and scanner_ok and experiment_ok:
   emit(out,"PASS",verdict="STAGE10_TECHNICAL_AUTOMATION_PASS",active_trading="AUTONOMOUS_PAPER_TECHNICAL_READY",strategy_release="NONE_PROMOTABLE",evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="final proof checks failed",checks={"system_test_cases":cases_ok,"timers":timers_ok,"scanner":scanner_ok,"experiment":experiment_ok},evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();main(a.job,a.output)
