import argparse,json,subprocess
from pathlib import Path
OID="TWELVE-DATA-RUNTIME-WIRING-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(args,timeout=180,cwd=None):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,cwd=cwd)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**extra):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**extra}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True))
 (p/"twelve-runtime-wiring.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["fetch"]=cmd(["git","fetch","origin","master"],120,REPO)
  ev["pull"]=cmd(["git","pull","--ff-only","origin","master"],120,REPO)
  ev["sha"]=cmd(["git","rev-parse","HEAD"],cwd=REPO)["stdout"]
  ev["install"]=cmd(["sudo","install","-m","0644",str(REPO/"deploy/systemd/experiment1-runtime.service"),"/etc/systemd/system/experiment1-runtime.service"])
  ev["reload"]=cmd(["sudo","systemctl","daemon-reload"])
  ev["start"]=cmd(["sudo","systemctl","start","experiment1-runtime.service"],180)
  ev["service"]=cmd(["systemctl","show","experiment1-runtime.service","--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,EnvironmentFiles","--no-pager"])
  s=ev["service"]["stdout"]
  env_ok="twelve-data.env" in s
  service_ok=ev["start"]["rc"]==0 and "Result=success" in s
  state="PASS" if env_ok and service_ok else "BLOCKED-RUNTIME"
  emit(out,state,verdict="TWELVE_DATA_RUNTIME_WIRING_PASS" if state=="PASS" else None,checks={"env_file_wired":env_ok,"service_success":service_ok},evidence=ev,broker="ZERO",live_money="ZERO")
 except Exception as e:
  emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev,broker="ZERO",live_money="ZERO")
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
