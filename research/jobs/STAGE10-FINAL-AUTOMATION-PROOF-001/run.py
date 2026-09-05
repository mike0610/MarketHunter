import argparse,json,subprocess,sqlite3
from pathlib import Path
OID="STAGE10-FINAL-AUTOMATION-PROOF-001";EXPECTED_SHA="d76304fa09e0ac8b8c5fab55581972aba0b7c781"
REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=180):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
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
 p=cmd([str(REPO/".venv/bin/python"),"-m","stage10.system_test_e2e","--db",str(db),"--account",account],timeout=180)
 if p["rc"]!=0: return {"process":p,"result":None}
 try: result=json.loads(p["stdout"])
 except Exception: result=None
 return {"process":p,"result":result}
def main(job,out):
 ev={}
 try:
  cmd(["git","-C",str(REPO),"fetch","origin","master"],timeout=120)
  pull=cmd(["git","-C",str(REPO),"pull","--ff-only","origin","master"],timeout=120);ev["pull"]=pull
  sha=cmd(["git","-C",str(REPO),"rev-parse","HEAD"])["stdout"];ev["deployed_sha"]=sha
  if sha!=EXPECTED_SHA: raise RuntimeError(f"VPS SHA {sha} != {EXPECTED_SHA}")
  ev["spot"]=run_case("SPOT",REPO/"data/stage10-system-test-spot.db")
  ev["futures"]=run_case("FUTURES",REPO/"data/stage10-system-test-futures.db")
  ev["scanner_timer"]=show("gil-trading-scanner-runtime.timer")
  ev["experiment_timer"]=show("experiment1-runtime.timer")
  ev["crypto_timer"]=show("crypto-paper-observer.timer")
  ev["scanner_service"]=show("gil-trading-scanner-runtime.service")
  ev["experiment_service"]=show("experiment1-runtime.service")
  ev["scanner_journal"]=cmd(["journalctl","-u","gil-trading-scanner-runtime.service","-n","30","--no-pager","-o","short-iso"])
  ev["experiment_journal"]=cmd(["journalctl","-u","experiment1-runtime.service","-n","40","--no-pager","-o","short-iso"])
  spot=ev["spot"]["result"]; fut=ev["futures"]["result"]
  cases_ok=all([
   isinstance(spot,dict),spot and spot.get("status")=="PASS",spot and spot.get("risk_decision")=="APPROVED",spot and spot.get("leverage")=="1",
   spot and spot.get("test_only_excluded_from_reports") is True,
   isinstance(fut,dict),fut and fut.get("status")=="PASS",fut and fut.get("risk_decision")=="APPROVED",fut and fut.get("leverage")=="3",
   fut and fut.get("test_only_excluded_from_reports") is True,
  ])
  timers_ok=all(
   "ActiveState=active" in ev[k]["stdout"] and "UnitFileState=enabled" in ev[k]["stdout"]
   for k in ("scanner_timer","experiment_timer","crypto_timer")
  )
  scanner_ok=("Result=success" in ev["scanner_service"]["stdout"] and "scanner cycle complete" in ev["scanner_journal"]["stdout"])
  experiment_ok=("Result=success" in ev["experiment_service"]["stdout"] and "experiment1 runtime cycle complete" in ev["experiment_journal"]["stdout"] and "Trading Slack transport: disabled" in ev["experiment_journal"]["stdout"])
  if cases_ok and timers_ok and scanner_ok and experiment_ok:
   emit(out,"PASS",verdict="STAGE10_TECHNICAL_AUTOMATION_PASS",evidence=ev,
    active_trading="AUTONOMOUS_PAPER_TECHNICAL_READY",
    strategy_release="NONE_PROMOTABLE",
    broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="final proof checks failed",
    checks={"system_test_cases":cases_ok,"timers":timers_ok,"scanner":scanner_ok,"experiment":experiment_ok},
    evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True)
 a=ap.parse_args();main(a.job,a.output)
