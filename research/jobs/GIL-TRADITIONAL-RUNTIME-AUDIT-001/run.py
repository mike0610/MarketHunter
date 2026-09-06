import argparse,json,os,sqlite3,subprocess
from pathlib import Path
OID="GIL-TRADITIONAL-RUNTIME-AUDIT-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(a,t=120):p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=REPO);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def env_flags(path,keys):
 out={k:False for k in keys}
 if path.exists():
  for line in path.read_text(errors="ignore").splitlines():
   s=line.strip()
   if not s or s.startswith("#") or "=" not in s:continue
   k,v=s.split("=",1)
   if k in out:out[k]=bool(v.strip())
 return out
def unit(name):return cmd(["systemctl","show",name,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def db_counts(path):
 if not path.exists():return {"exists":False}
 with sqlite3.connect(path) as c:
  try:
   rows=c.execute("select sec_type,queue_state,count(*) from trading_scanner_candidates group by sec_type,queue_state order by sec_type,queue_state").fetchall()
  except sqlite3.Error as e:return {"exists":True,"error":str(e)}
 return {"exists":True,"rows":[{"sec_type":a,"queue_state":b,"count":n} for a,b,n in rows]}
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**x}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True));(p/"gil-runtime-audit.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"]);ev["pull"]=cmd(["git","pull","--ff-only","origin","master"]);ev["sha"]=cmd(["git","rev-parse","HEAD"])["stdout"]
  env=REPO/"deploy/systemd/gil-trading-scanner-runtime.env"
  exenv=REPO/"deploy/systemd/experiment1-runtime.env"
  ev["gil_env_exists"]=env.exists()
  ev["gil_env"]=env_flags(env,["TRADING_SCANNER_DB_PATH","TRADING_SCANNER_MARKET_DATA_PROVIDER","TRADING_SCANNER_UNIVERSE_SYMBOLS","TRADING_SCANNER_MAX_DATA_AGE_SECONDS"])
  ev["alpaca_credentials_present"]=env_flags(exenv,["EXPERIMENT1_ALPACA_API_KEY_ID","EXPERIMENT1_ALPACA_API_SECRET_KEY"])
  ev["gil_service"]=unit("gil-trading-scanner-runtime.service");ev["gil_timer"]=unit("gil-trading-scanner-runtime.timer")
  ev["paper_service"]=unit("promoted-paper-runtime.service");ev["paper_timer"]=unit("promoted-paper-runtime.timer")
  ev["scanner_db"]=db_counts(REPO/"data/trading_scanner.db")
  emit(out,"EVIDENCE_READY",evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
