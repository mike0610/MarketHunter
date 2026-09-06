import argparse,json,sqlite3,subprocess
from pathlib import Path
OID="GIL-TWELVE-SCANNER-E2E-001";REPO=Path("/home/ubuntu/MarketHunter");DB=REPO/"data/gil_twelve_scanner_proof.db";ENV=REPO/"deploy/systemd/gil-trading-scanner-runtime.env"
def cmd(a,t=180,cwd=None):
 p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=cwd);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**x};(p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True));(p/"gil-twelve-scanner-proof.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO);ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO);ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  ENV.write_text("TRADING_SCANNER_DB_PATH="+str(DB)+"\nTRADING_SCANNER_MARKET_DATA_PROVIDER=twelve_data\nTRADING_SCANNER_UNIVERSE_SYMBOLS=SPY,QQQ,AAPL,MSFT,NVDA\nTRADING_SCANNER_MAX_DATA_AGE_SECONDS=345600\nTRADING_SCANNER_HISTORY_LIMIT=120\n")
  ev["install_service"]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/gil-trading-scanner-runtime.service"),"/etc/systemd/system/gil-trading-scanner-runtime.service"])
  ev["reload"]=cmd(["sudo","systemctl","daemon-reload"])
  if DB.exists(): DB.unlink()
  ev["start"]=cmd(["sudo","systemctl","start","gil-trading-scanner-runtime.service"],240)
  ev["service"]=cmd(["systemctl","show","gil-trading-scanner-runtime.service","--property=Result,ExecMainStatus","--no-pager"])
  if not DB.exists():
   emit(out,"BLOCKED-EVIDENCE",reason="scanner produced no proof database",evidence=ev,broker="ZERO",live_money="ZERO");return
  con=sqlite3.connect(DB);con.row_factory=sqlite3.Row
  tables=[r[0] for r in con.execute("select name from sqlite_master where type='table'").fetchall()]
  target=next((t for t in tables if "candidate" in t.lower()),None)
  if not target:
   emit(out,"BLOCKED-RUNTIME",reason="candidate table not found",tables=tables,evidence=ev,broker="ZERO",live_money="ZERO");return
  rows=[dict(r) for r in con.execute('select * from "'+target+'"').fetchall()]
  con.close()
  symbols=sorted({str(r.get("symbol","")) for r in rows if r.get("symbol")})
  states={}
  for r in rows:
   st=str(r.get("queue_state","UNKNOWN"));states[st]=states.get(st,0)+1
  breakout=[r for r in rows if str(r.get("setup_family",""))=="BREAKOUT_OR_PULLBACK_IN_TREND"]
  ok=ev["start"]["rc"]==0 and "Result=success" in ev["service"]["stdout"] and symbols==["AAPL","MSFT","NVDA","QQQ","SPY"] and len(breakout)==5
  emit(out,"PASS" if ok else "BLOCKED-RUNTIME",verdict="GIL_TWELVE_SCANNER_E2E_PASS" if ok else None,checks={"service_success":ev["start"]["rc"]==0,"symbols":symbols,"row_count":len(rows),"queue_states":states,"breakout_rows":len(breakout)},evidence=ev,broker="ZERO",live_money="ZERO")
 except Exception as e: emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
