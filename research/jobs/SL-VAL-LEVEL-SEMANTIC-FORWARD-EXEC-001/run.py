import argparse,json,subprocess,sys,tempfile
from pathlib import Path

OBJECT_ID='SL-VAL-LEVEL-SEMANTIC-FORWARD-EXEC-001'
LEGACY_RUNNER=Path('research/jobs/SL-VAL-LEVEL-009/run.py')
PARENT_SHA='9d767934ec1142b1c2b88920098a951bb11bac448ccd0baeacc6ea4545039c8b'
ALLOWED={'LEVEL-FORWARD-SUPPORT','LEVEL-FORWARD-NO-SUPPORT','BLOCKED-EVIDENCE','PROVIDER-BLOCKED'}

def emit(outdir,state,**extra):
    p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**extra},indent=2,sort_keys=True),encoding='utf-8')

def main(job_path,outdir):
    try:
        spec=json.loads(Path(job_path).read_text(encoding='utf-8'))
        required={'object_id':OBJECT_ID,'executor':'vps','parent_census_sha256':PARENT_SHA,'semantic_snapshot_run_id':'34902277568','semantic_snapshot_git_sha':'a015f26d62a3cf8ab49aa9608bc777107e6c69ef','expected_event_count':1391,'expected_unknown_count':4,'expected_decluster_suppressions':435,'interpretation_rule':'PRIMARY only; HALF sensitivity cannot rescue'}
        if any(spec.get(k)!=v for k,v in required.items()):
            emit(outdir,'BLOCKED-EVIDENCE',reason='job_contract_mismatch',outcomes_opened=False); return
        if spec.get('terminal_states')!=['LEVEL-FORWARD-SUPPORT','LEVEL-FORWARD-NO-SUPPORT','BLOCKED-EVIDENCE','PROVIDER-BLOCKED']:
            emit(outdir,'BLOCKED-EVIDENCE',reason='terminal_state_contract_mismatch',outcomes_opened=False); return
        if not LEGACY_RUNNER.is_file():
            emit(outdir,'BLOCKED-EVIDENCE',reason='frozen_level_009_runner_missing',outcomes_opened=False); return
        with tempfile.TemporaryDirectory() as td:
            t=Path(td); old_job=t/'job.json'; old_out=t/'out'; old_out.mkdir()
            old_job.write_text(json.dumps({'object_id':'SL-VAL-LEVEL-009','parent_census_sha256':PARENT_SHA}),encoding='utf-8')
            cp=subprocess.run([sys.executable,str(LEGACY_RUNNER),'--job',str(old_job),'--output',str(old_out)],capture_output=True,text=True,timeout=840)
            tr=old_out/'terminal_result.json'
            if not tr.is_file():
                emit(outdir,'BLOCKED-EVIDENCE',reason='frozen_runner_no_terminal_result',returncode=cp.returncode,stderr=cp.stderr[-2000:],outcomes_opened=False); return
            payload=json.loads(tr.read_text(encoding='utf-8'))
            state=payload.get('terminal_state')
            if state not in ALLOWED:
                emit(outdir,'BLOCKED-EVIDENCE',reason='unexpected_frozen_runner_terminal',observed_terminal_state=state,outcomes_opened=False); return
            payload.pop('object_id',None); payload.pop('terminal_state',None)
            payload['frozen_runner']='research/jobs/SL-VAL-LEVEL-009/run.py'
            payload['semantic_snapshot_run_id']='34902277568'
            payload['semantic_snapshot_git_sha']='a015f26d62a3cf8ab49aa9608bc777107e6c69ef'
            emit(outdir,state,**payload)
            for name in ('level_forward_report.json','pairs.json'):
                src=old_out/name
                if src.is_file(): (Path(outdir)/name).write_bytes(src.read_bytes())
    except subprocess.TimeoutExpired:
        emit(outdir,'BLOCKED-EVIDENCE',reason='inner_runner_timeout',outcomes_opened=False)
    except Exception as e:
        emit(outdir,'BLOCKED-EVIDENCE',reason=repr(e),outcomes_opened=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.job,a.output)
