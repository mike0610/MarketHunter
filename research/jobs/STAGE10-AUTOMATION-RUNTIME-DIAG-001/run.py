import argparse,json,subprocess
from pathlib import Path
OID="STAGE10-AUTOMATION-RUNTIME-DIAG-001"
def cmd(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=30)
 return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def main(job,out):
 outp=Path(out);outp.mkdir(parents=True,exist_ok=True)
 try:
  result={
   "object_id":OID,
   "terminal_state":"EVIDENCE_READY",
   "repo_sha":cmd(["git","-C","/home/ubuntu/MarketHunter","rev-parse","HEAD"]),
   "service_status":cmd(["systemctl","status","experiment1-runtime.service","--no-pager","-l"]),
   "service_cat":cmd(["systemctl","cat","experiment1-runtime.service"]),
   "timer_cat":cmd(["systemctl","cat","experiment1-runtime.timer"]),
   "journal":cmd(["journalctl","-u","experiment1-runtime.service","-n","120","--no-pager","-o","short-iso"]),
   "env_keys":cmd(["bash","-lc","if [ -f /home/ubuntu/MarketHunter/deploy/systemd/experiment1-runtime.env ]; then sed -E 's/=.*/=<redacted>/' /home/ubuntu/MarketHunter/deploy/systemd/experiment1-runtime.env; else echo MISSING; fi"]),
   "scanner_unit_files":cmd(["bash","-lc","ls -l /etc/systemd/system/gil-trading-scanner-runtime.* /lib/systemd/system/gil-trading-scanner-runtime.* 2>/dev/null || true"]),
  }
 except Exception as e:
  result={"object_id":OID,"terminal_state":"BLOCKED-RUNTIME","reason":repr(e)}
 (outp/"runtime-diag.json").write_text(json.dumps(result,indent=2,sort_keys=True))
 (outp/"terminal_result.json").write_text(json.dumps(result,sort_keys=True))
if __name__=="__main__":
 ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True);a=ap.parse_args();main(a.job,a.output)
