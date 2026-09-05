import argparse,json,subprocess
from pathlib import Path
OID="STAGE10-AUTOMATION-RUNTIME-INVENTORY-001"
UNITS=[
 "gil-trading-scanner-runtime.timer",
 "gil-trading-scanner-runtime.service",
 "experiment1-runtime.timer",
 "experiment1-runtime.service",
 "crypto-paper-observer.timer",
 "crypto-paper-observer.service",
]
def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=30)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def main(job,out):
 outp=Path(out);outp.mkdir(parents=True,exist_ok=True)
 try:
  units={}
  for u in UNITS:
   units[u]={
    "is_active":cmd(["systemctl","is-active",u]),
    "is_enabled":cmd(["systemctl","is-enabled",u]),
    "show":cmd(["systemctl","show",u,"--property=LoadState,ActiveState,SubState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSec","--no-pager"]),
   }
  timers=cmd(["systemctl","list-timers","--all","--no-pager","--no-legend"])
  sha=cmd(["git","-C","/home/ubuntu/MarketHunter","rev-parse","HEAD"])
  result={"object_id":OID,"terminal_state":"EVIDENCE_READY","repo_sha":sha,"units":units,"timers":timers}
 except Exception as e:
  result={"object_id":OID,"terminal_state":"BLOCKED-RUNTIME","reason":repr(e)}
 (outp/"runtime-inventory.json").write_text(json.dumps(result,indent=2,sort_keys=True))
 (outp/"terminal_result.json").write_text(json.dumps(result,sort_keys=True))
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();main(a.job,a.output)
