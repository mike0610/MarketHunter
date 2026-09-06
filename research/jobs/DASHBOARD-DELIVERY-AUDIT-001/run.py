import argparse,json,subprocess
from pathlib import Path
OID="DASHBOARD-DELIVERY-AUDIT-001";REPO=Path("/home/ubuntu/MarketHunter")
def cmd(a,t=120):
 p=subprocess.run(a,capture_output=True,text=True,timeout=t,cwd=REPO);return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}
def emit(out,state,**x):
 p=Path(out);p.mkdir(parents=True,exist_ok=True);d={"object_id":OID,"terminal_state":state,**x}
 (p/"terminal_result.json").write_text(json.dumps(d,sort_keys=True));(p/"dashboard-delivery-audit.json").write_text(json.dumps(d,indent=2,sort_keys=True))
def main(job,out):
 ev={}
 try:
  ev["nginx_T"]=cmd(["sudo","nginx","-T"],120)
  ev["api_unit"]=cmd(["systemctl","cat","markethunter-api"],60)
  ev["repo_head"]=cmd(["git","rev-parse","HEAD"],60)
  ev["dashboard_dist"]=cmd(["bash","-lc","ls -ld dashboard/dist 2>/dev/null; find dashboard/dist -maxdepth 1 -type f -printf '%f %TY-%Tm-%TdT%TH:%TM:%TS\n' 2>/dev/null | head -20"],60)
  ev["nginx_roots"]=cmd(["bash","-lc","sudo nginx -T 2>/dev/null | grep -E '^[[:space:]]*(root|alias|try_files)'"],60)
  emit(out,"EVIDENCE_READY",evidence=ev)
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason=repr(e),evidence=ev)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
