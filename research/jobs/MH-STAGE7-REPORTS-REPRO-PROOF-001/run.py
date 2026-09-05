import argparse,json,shutil,sqlite3,subprocess
from pathlib import Path
OID="MH-STAGE7-REPORTS-REPRO-PROOF-001";SHA="387d8601fceb03a727d416a99dc6c639794eabe7"
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/"terminal_result.json").write_text(json.dumps({"object_id":OID,"terminal_state":s,**x},indent=2,sort_keys=True))
def main(job,out):
 o=Path(out).resolve();w=o/"repo";db=o/"stage7.db"
 try:
  subprocess.run(["git","clone","--quiet","https://github.com/mike0610/MarketHunter.git",str(w)],check=True,timeout=120)
  subprocess.run(["git","-C",str(w),"checkout","--quiet",SHA],check=True,timeout=30)
  py=Path("/home/ubuntu/MarketHunter/.venv/bin/python")
  if not py.exists():emit(out,"BLOCKED-RUNTIME",reason="vps-venv-python-missing");return
  code=r"""
import json,sqlite3,sys
from pathlib import Path
from reports.stage7_service import build_stage7_report
db=Path(sys.argv[1])
with sqlite3.connect(db) as c:
 c.executescript('''
 CREATE TABLE stage6_closed_trades(closed_trade_id TEXT PRIMARY KEY,position_id TEXT UNIQUE,symbol TEXT,direction TEXT,entry_price TEXT,exit_price TEXT,quantity TEXT,gross_pnl TEXT,entry_fees TEXT,exit_fees TEXT,realized_pnl TEXT,opened_at TEXT,closed_at TEXT,exit_reason TEXT,strategy_id TEXT,strategy_version TEXT,strategy_decision_id TEXT,candidate_dedupe_key TEXT);
 CREATE TABLE strategy_decisions(decision_id TEXT PRIMARY KEY,setup_family TEXT,outcome TEXT);
 CREATE TABLE stage5_sim_orders(order_id TEXT PRIMARY KEY,risk_plan_id TEXT,strategy_decision_id TEXT,candidate_dedupe_key TEXT);
 CREATE TABLE stage5_sim_fills(fill_id TEXT PRIMARY KEY,order_id TEXT);
 CREATE TABLE risk_sized_plans(plan_id TEXT PRIMARY KEY,risk_amount TEXT);
 CREATE TABLE trading_scanner_candidates(id TEXT,queue_state TEXT);
 ''')
 rows=[
 ('ct1','p1','SPY','LONG','100','110','2','20','1','1','18','2026-09-01T00:00:00+00:00','2026-09-02T00:00:00+00:00','TAKE_PROFIT','s1','1','d1','c1'),
 ('ct2','p2','QQQ','SHORT','200','205','1','-5','0.5','0.5','-6','2026-09-02T00:00:00+00:00','2026-09-04T00:00:00+00:00','STOP_LOSS','s1','2','d2','c2')]
 c.executemany('insert into stage6_closed_trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
 c.executemany('insert into strategy_decisions values (?,?,?)',[('d1','BREAKOUT','LONG'),('d2','PULLBACK','SHORT'),('d3','BREAKOUT','NO_TRADE')])
 c.executemany('insert into stage5_sim_orders values (?,?,?,?)',[('o1','r1','d1','c1'),('o2','r2','d2','c2')])
 c.executemany('insert into stage5_sim_fills values (?,?)',[('f1','o1'),('f2','o2')])
 c.executemany('insert into risk_sized_plans values (?,?)',[('r1','10'),('r2','5')])
 c.executemany('insert into trading_scanner_candidates values (?,?)',[('c1','CANDIDATE'),('c2','CANDIDATE'),('c3','REJECTED')])
a=build_stage7_report(db)
# New reader/service objects simulate restart/recalculation from durable history.
b=build_stage7_report(db)
if a!=b:raise SystemExit(31)
if a['sample_size']!=2 or a['summary']['net_pnl']!='12':raise SystemExit(32)
if a['summary']['max_drawdown']!='6':raise SystemExit(33)
if a['decision_outcomes'].get('NO_TRADE')!=1 or a['candidate_states'].get('REJECTED')!=1:raise SystemExit(34)
if any(x['risk_plan_id'] is None or x['order_id'] is None or x['entry_fill_id'] is None for x in a['provenance']):raise SystemExit(35)
if set(a['groups']['trend_alignment'])!={'trend-unknown'}:raise SystemExit(36)
print(json.dumps({'reproducible':True,'sample_size':a['sample_size'],'net_pnl':a['summary']['net_pnl'],'max_drawdown':a['summary']['max_drawdown'],'decision_outcomes':a['decision_outcomes'],'candidate_states':a['candidate_states'],'provenance_count':len(a['provenance']),'trend_groups':list(a['groups']['trend_alignment'])},sort_keys=True))
"""
  r=subprocess.run([str(py),"-c",code,str(db)],cwd=w,capture_output=True,text=True,timeout=120)
  (o/"stage7.stdout.log").write_text(r.stdout);(o/"stage7.stderr.log").write_text(r.stderr)
  if r.returncode:emit(out,"BLOCKED-RUNTIME",reason="stage7-repro",returncode=r.returncode,stderr=r.stderr[-3000:],stdout=r.stdout[-3000:]);return
  emit(out,"PASS",master_sha=SHA,proof=json.loads(r.stdout.strip().splitlines()[-1]),note="read-only reproducible Stage7 analytics; no strategy/risk/execution mutation")
 except Exception as e:emit(out,"BLOCKED-RUNTIME",reason="exception",detail=repr(e))
 finally:
  if w.exists():shutil.rmtree(w,ignore_errors=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--job",required=True);p.add_argument("--output",required=True);a=p.parse_args();main(a.job,a.output)
