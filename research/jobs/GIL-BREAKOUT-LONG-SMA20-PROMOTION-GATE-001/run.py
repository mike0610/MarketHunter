from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
PINNED_SHA="68c8feb855f2d70eda9b195f23b7fdb8b42c9e99"
def main():
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args()
 job=json.loads(Path(a.job).read_text());out=Path(a.output);out.mkdir(parents=True,exist_ok=True);repo=Path("/home/ubuntu/MarketHunter")
 subprocess.run(["git","-C",str(repo),"fetch","origin",PINNED_SHA],check=True)
 raw=subprocess.check_output(["git","-C",str(repo),"show",f"{PINNED_SHA}:research/run_gil_breakout_promotion_gate.py"],text=True)
 script=(out/"promotion_gate.py").resolve();script.write_text(raw)
 proc=subprocess.run([str(repo/".venv/bin/python"),str(script)],cwd=repo,text=True,capture_output=True)
 (out/"runner_stdout.txt").write_text(proc.stdout);(out/"runner_stderr.txt").write_text(proc.stderr)
 if proc.returncode!=0: terminal={"object_id":job["object_id"],"terminal_state":"BLOCKED-EVIDENCE","reason":"promotion-gate-runner-failed","returncode":proc.returncode}
 else:
  payload=json.loads(proc.stdout.strip().splitlines()[-1]);(out/"promotion_gate_result.json").write_text(json.dumps(payload,sort_keys=True,separators=(",",":")))
  terminal={"object_id":job["object_id"],"terminal_state":"EVIDENCE_READY","research_verdict":payload["terminal_verdict"],"reasons":payload["reasons"]}
 (out/"terminal_result.json").write_text(json.dumps(terminal,sort_keys=True,separators=(",",":")))
if __name__=="__main__": main()
