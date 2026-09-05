import argparse,json,os,sqlite3,subprocess
from pathlib import Path
OID="STAGE10-AUTOMATION-SCANNER-YAHOO-REPAIR-001"
REPO=Path("/home/ubuntu/MarketHunter")
ENV=REPO/"deploy/systemd/gil-trading-scanner-runtime.env"
def cmd(args,timeout=120):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def show(unit):
 return cmd(["systemctl","show",unit,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def count_rows(db,table):
 if not db.exists(): return None
 with sqlite3.connect(db) as c:
  names={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
  return None if table not in names else c.execute(f"select count(*) from {table}").fetchone()[0]
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True)
 data={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(data,sort_keys=True))
 (p/"scanner-yahoo-evidence.json").write_text(json.dumps(data,indent=2,sort_keys=True))
def main(job,out):
 evidence={}
 try:
  lines=ENV.read_text().splitlines() if ENV.exists() else []
  lines=[x for x in lines if not x.startswith("TRADING_SCANNER_MARKET_DATA_PROVIDER=")]
  lines.append("TRADING_SCANNER_MARKET_DATA_PROVIDER=yahoo")
  ENV.write_text("\n".join(lines)+"\n");os.chmod(ENV,0o600)
  cmd(["sudo","chown","ubuntu:ubuntu",str(ENV)])
  cmd(["sudo","systemctl","reset-failed","gil-trading-scanner-runtime.service"])
  start=cmd(["sudo","systemctl","start","gil-trading-scanner-runtime.service"],timeout=180)
  evidence["start"]=start
  evidence["service"]=show("gil-trading-scanner-runtime.service")
  evidence["timer"]=show("gil-trading-scanner-runtime.timer")
  evidence["journal"]=cmd(["journalctl","-u","gil-trading-scanner-runtime.service","-n","100","--no-pager","-o","short-iso"])
  evidence["candidate_rows"]=count_rows(REPO/"data/trading_scanner.db","trading_scanner_candidates")
  ok=(start["rc"]==0 and "Result=success" in evidence["service"]["stdout"] and "ActiveState=active" in evidence["timer"]["stdout"] and "UnitFileState=enabled" in evidence["timer"]["stdout"] and "scanner cycle complete" in evidence["journal"]["stdout"])
  if ok:
   emit(out,"PASS",verdict="NO_SLACK_SCANNER_RUNTIME_ACTIVE",evidence=evidence,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="Yahoo scanner verification failed",evidence=evidence,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=evidence,broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True)
 a=ap.parse_args();main(a.job,a.output)
