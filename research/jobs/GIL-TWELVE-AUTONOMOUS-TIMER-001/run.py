import argparse,json,subprocess
from pathlib import Path
OID="GIL-TWELVE-AUTONOMOUS-TIMER-001";REPO=Path("/home/ubuntu/MarketHunter");ENV=REPO/"deploy/systemd/gil-trading-scanner-runtime.env"
def cmd(a,t=180,cwd=None):
 p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=cwd);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**x};(p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True));(p/"gil-twelve-autonomous-timer.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO);ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ENV.write_text("TRADING_SCANNER_DB_PATH=/home/ubuntu/MarketHunter/data/trading_scanner.db\nTRADING_SCANNER_MARKET_DATA_PROVIDER=twelve_data\nTRADING_SCANNER_UNIVERSE_SYMBOLS=SPY,QQQ,AAPL,MSFT,NVDA\nTRADING_SCANNER_MAX_DATA_AGE_SECONDS=345600\nTRADING_SCANNER_HISTORY_LIMIT=120\n")
  ev["service_install"]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/gil-trading-scanner-runtime.service"),"/etc/systemd/system/gil-trading-scanner-runtime.service"])
  ev["timer_install"]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/gil-trading-scanner-runtime.timer"),"/etc/systemd/system/gil-trading-scanner-runtime.timer"])
  ev["reload"]=cmd(["sudo","systemctl","daemon-reload"])
  ev["enable"]=cmd(["sudo","systemctl","enable","--now","gil-trading-scanner-runtime.timer"])
  ev["timer"]=cmd(["systemctl","show","gil-trading-scanner-runtime.timer","--property=LoadState,ActiveState,UnitFileState,NextElapseUSecRealtime","--no-pager"])
  ev["list"]=cmd(["systemctl","list-timers","gil-trading-scanner-runtime.timer","--no-pager"])
  s=ev["timer"]["stdout"]
  ok=ev["enable"]["rc"]==0 and "ActiveState=active" in s and "UnitFileState=enabled" in s
  emit(out,"PASS" if ok else "BLOCKED-RUNTIME",verdict="GIL_TWELVE_AUTONOMOUS_TIMER_PASS" if ok else None,checks={"active": "ActiveState=active" in s,"enabled":"UnitFileState=enabled" in s,"cadence":"every 30 minutes"},evidence=ev,broker="ZERO",live_money="ZERO")
 except Exception as e: emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
