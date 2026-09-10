import argparse,json,math,subprocess
from collections import defaultdict
from pathlib import Path

OBJECT_ID='SL-STATS-MFE-GIVEBACK-001'
REPO='/home/ubuntu/MarketHunter'
SNAP='data/outcome_intelligence/latest/trades.json'
SNAP_BRANCH='outcome-intelligence-snapshots'
MFE_MIN=2.0
MIN_OVERALL_N=100
MIN_CELL_N=20
BROAD_CELL_NEG_RATE=0.20
OVERALL_SIGNAL_RATE=0.30
MAX_TOP2_NEG_SHARE_FOR_BROAD=0.60
MIN_BROAD_CELLS=3


def emit(out,state,**payload):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))


def load_snapshot():
    subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
    return json.loads(raw)


def finite_number(v):
    return isinstance(v,(int,float)) and math.isfinite(float(v))


def summarize(rows,key):
    groups=defaultdict(list)
    for t in rows: groups[str(t.get(key) or 'UNKNOWN')].append(t)
    out=[]
    for name,a in sorted(groups.items()):
        neg=[t for t in a if float(t['profit_percent'])<0]
        give=[float(t['max_profit_percent'])-float(t['profit_percent']) for t in a]
        out.append({'value':name,'n':len(a),'negative_n':len(neg),'negative_rate':len(neg)/len(a) if a else None,
                    'mean_final_profit_percent':sum(float(t['profit_percent']) for t in a)/len(a) if a else None,
                    'mean_mfe_percent':sum(float(t['max_profit_percent']) for t in a)/len(a) if a else None,
                    'mean_giveback_pp':sum(give)/len(give) if give else None})
    return out


def main(out,job):
    try:
        cfg=json.loads(Path(job).read_text())
        if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
        snap=load_snapshot()
        trades=snap.get('trades')
        if not isinstance(trades,list): raise ValueError('snapshot trades missing')
        eligible=[t for t in trades if t.get('market') in ('spot','futures') and t.get('status') in ('closed','expired') and finite_number(t.get('profit_percent')) and finite_number(t.get('max_profit_percent'))]
        cohort=[t for t in eligible if float(t['max_profit_percent'])>=MFE_MIN]
        if len(cohort)<MIN_OVERALL_N:
            emit(out,'BLOCKED-EVIDENCE',reason='mfe cohort below predeclared minimum',snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},cohort_n=len(cohort),minimum_n=MIN_OVERALL_N)
            return
        neg=[t for t in cohort if float(t['profit_percent'])<0]
        overall_rate=len(neg)/len(cohort)
        strategy=summarize(cohort,'strategy')
        qualifying=[x for x in strategy if x['n']>=MIN_CELL_N]
        broad_cells=[x for x in qualifying if x['negative_rate']>=BROAD_CELL_NEG_RATE]
        neg_by_strategy=sorted(((x['negative_n'],x['value']) for x in strategy),reverse=True)
        top2_neg=sum(x[0] for x in neg_by_strategy[:2])
        top2_share=top2_neg/len(neg) if neg else 0.0
        if overall_rate<OVERALL_SIGNAL_RATE:
            state='WEAK-GIVEBACK-SIGNAL'
        elif len(qualifying)<MIN_BROAD_CELLS:
            state='BLOCKED-EVIDENCE'
        elif len(broad_cells)>=MIN_BROAD_CELLS and top2_share<MAX_TOP2_NEG_SHARE_FOR_BROAD:
            state='BROAD-GIVEBACK-SIGNAL'
        else:
            state='CONCENTRATED-GIVEBACK-SIGNAL'
        emit(out,state,
             contract={'mfe_min_percent':MFE_MIN,'min_overall_n':MIN_OVERALL_N,'min_strategy_cell_n':MIN_CELL_N,'overall_signal_rate':OVERALL_SIGNAL_RATE,'broad_cell_negative_rate':BROAD_CELL_NEG_RATE,'min_broad_cells':MIN_BROAD_CELLS,'max_top2_negative_share_for_broad':MAX_TOP2_NEG_SHARE_FOR_BROAD},
             snapshot={'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'total':snap.get('total')},
             overall={'eligible_completed_n':len(eligible),'mfe_cohort_n':len(cohort),'negative_n':len(neg),'negative_rate':overall_rate,'mean_final_profit_percent':sum(float(t['profit_percent']) for t in cohort)/len(cohort),'mean_giveback_pp':sum(float(t['max_profit_percent'])-float(t['profit_percent']) for t in cohort)/len(cohort)},
             concentration={'qualifying_strategy_cells_n':len(qualifying),'broad_strategy_cells_n':len(broad_cells),'top2_negative_share':top2_share,'top2_negative_strategies':[name for _,name in neg_by_strategy[:2]]},
             by_strategy=strategy,by_timeframe=summarize(cohort,'timeframe'),by_market=summarize(cohort,'market'),by_direction=summarize(cohort,'direction'),
             interpretation='Descriptive attribution only; no exit threshold, trailing, breakeven, sizing, strategy promotion or rejection is authorized by this object.')
    except Exception as e:
        emit(out,'PROVIDER-BLOCKED',reason=repr(e))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); args=ap.parse_args(); main(args.output,args.job)
