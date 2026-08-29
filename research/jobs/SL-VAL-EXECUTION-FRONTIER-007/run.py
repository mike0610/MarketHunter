import argparse,json
from pathlib import Path
OBJECT_ID='SL-VAL-EXECUTION-FRONTIER-007'
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object_id mismatch')
 except Exception as e:emit(out,'EVIDENCE-FAIL',reason=repr(e));return
 frontier=[
  {'hypothesis':'MOM-12W','state':'REJECTED/FROZEN','reason':'2026 OOS sole LONG episode negative; no rescue'},
  {'hypothesis':'BASIS-RV-Q1-2024','state':'REJECTED/FROZEN','reason':'BASIS-ROBUSTNESS-FAIL'},
  {'hypothesis':'LEVEL-ROUND-NUMBER','state':'BLOCKED-EVIDENCE/FROZEN','reason':'immutable parent event identity unavailable'},
  {'hypothesis':'STABLEFLOW-USDT','state':'BLOCKED-EVIDENCE/FROZEN','reason':'PIT/version provenance unavailable'},
  {'hypothesis':'LSWEEP-24H-6H','state':'OUTCOME-COMPLETE/CLASSIFICATION-UNKNOWN','reason':'immutable outcome payload not readable on authorized surface'},
  {'hypothesis':'DONCHIAN-55-20','state':'OUTCOME-COMPLETE/ROBUSTNESS-UNKNOWN','reason':'robustness payload not readable on authorized surface'},
  {'hypothesis':'TURTLE-SOUP-20-3','state':'OUTCOME-COMPLETE/CLASSIFICATION-UNKNOWN','reason':'terminal payload not readable on authorized surface'}]
 # Deterministic materiality gate: do not reopen rejected/blocked branches and do not rerun outcome-complete jobs merely for payload recovery.
 # Select only a materially distinct executable hypothesis with frozen public-data contract. None is currently frozen in the preserved frontier.
 eligible=[]
 if eligible:emit(out,'FRONTIER-SELECTED',frontier=frontier,selected=eligible[0],parameter_tuning=False)
 else:emit(out,'FRONTIER-EXHAUSTED',frontier=frontier,selected=None,reason='no materially distinct executable frozen hypothesis remains in preserved empirical frontier; new hypothesis formalization would be a separate research object',parameter_tuning=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
