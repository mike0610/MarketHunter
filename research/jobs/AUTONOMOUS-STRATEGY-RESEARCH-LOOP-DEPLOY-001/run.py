import argparse,json,sqlite3,subprocess
from pathlib import Path
OID="AUTONOMOUS-STRATEGY-RESEARCH-LOOP-DEPLOY-001"
REPO=Path("/home/ubuntu/MarketHunter")
DB=REPO/"data/autonomous_research.db"
def cmd(args,timeout=180,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def show(unit):
 return cmd(["systemctl","show",unit,"--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"])
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True))
 (p/"autonomous-loop-proof.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def db_snapshot():
 if not DB.exists(): return {"exists":False}
 with sqlite3.connect(DB) as c:
  c.row_factory=sqlite3.Row
  objs=[dict(r) for r in c.execute("select object_id,market,direction,stage,status,verdict,attempt from research_loop_objects order by priority,object_id")]
  nk=c.execute("select count(*) from research_negative_knowledge").fetchone()[0]
  rc=c.execute("select count(*) from research_release_candidates").fetchone()[0]
  ev=c.execute("select count(*) from research_loop_events").fetchone()[0]
 return {"exists":True,"objects":objs,"negative_knowledge":nk,"release_candidates":rc,"events":ev}
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/autonomous-strategy-research.service"),"/etc/systemd/system/autonomous-strategy-research.service"])
  cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/autonomous-strategy-research.timer"),"/etc/systemd/system/autonomous-strategy-research.timer"])
  cmd(["sudo","systemctl","daemon-reload"])
  cmd(["sudo","systemctl","enable","--now","autonomous-strategy-research.timer"])
  # clean proof DB only if it does not exist yet; never erase prior durable state
  before=db_snapshot();ev["before"]=before
  first=cmd(["sudo","systemctl","start","autonomous-strategy-research.service"],180);ev["first_start"]=first
  ev["after_first"]=db_snapshot()
  second=cmd(["sudo","systemctl","start","autonomous-strategy-research.service"],180);ev["second_start"]=second
  ev["after_second"]=db_snapshot()
  ev["service"]=show("autonomous-strategy-research.service")
  ev["timer"]=show("autonomous-strategy-research.timer")
  ev["journal"]=cmd(["journalctl","-u","autonomous-strategy-research.service","-n","80","--no-pager","-o","short-iso"])
  a=ev["after_first"];b=ev["after_second"]
  objs=a.get("objects",[])
  three_terminal=(len(objs)>=3 and all(x["status"]=="TERMINAL" for x in objs[:3]))
  expected=three_terminal and all(x["verdict"]=="BLOCKED-EVIDENCE" for x in objs[:3])
  idempotent=(a==b)
  timer_ok=("ActiveState=active" in ev["timer"]["stdout"] and "UnitFileState=enabled" in ev["timer"]["stdout"])
  service_ok=(first["rc"]==0 and second["rc"]==0 and "Result=success" in ev["service"]["stdout"])
  no_release=(a.get("release_candidates")==0)
  if all((three_terminal,expected,idempotent,timer_ok,service_ok,no_release)):
   emit(out,"PASS",verdict="AUTONOMOUS_STRATEGY_RESEARCH_LOOP_PASS",evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
  else:
   emit(out,"BLOCKED-RUNTIME",reason="acceptance proof failed",checks={"three_terminal":three_terminal,"expected_verdicts":expected,"idempotent_second_run":idempotent,"timer":timer_ok,"service":service_ok,"no_release":no_release},evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",ibkr="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
