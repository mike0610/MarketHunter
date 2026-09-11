import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID='SL-RISK-DRAWDOWN-SEQUENCE-001'
REPO='/home/ubuntu/MarketHunter'
SNAP_BRANCH='outcome-intelligence-snapshots'
SNAP='data/outcome_intelligence/latest/trades.json'
MIN_TRADES=150
MIN_STRATEGIES=5
MIN_TS_COVERAGE=0.90
PERMUTATIONS=10000
SEED=20260911
SIGNAL_P=0.05
SIGNAL_RATIO=1.50
NO_SIGNAL_P=0.10
NO_SIGNAL_RATIO=1.20


def emit(out,state,**payload):
    p=Path(out); p.mkdir(parents=True,exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**payload},indent=2,sort_keys=True))


def load_snapshot():
    subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
    raw=subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30).stdout
    return json.loads(raw),hashlib.sha256(raw.encode()).hexdigest()


def parse_ts(x):
    if not x: return None
    try: return datetime.fromisoformat(str(x).replace('Z','+00:00'))
    except ValueError: return None


def max_drawdown_additive(returns):
    equity=0.0; peak=0.0; max_dd=0.0; trough_idx=-1; peak_idx=-1; current_peak_idx=-1
    for i,r in enumerate(returns):
        equity += r
        if equity > peak:
            peak=equity; current_peak_idx=i
        dd=peak-equity
        if dd > max_dd:
            max_dd=dd; peak_idx=current_peak_idx; trough_idx=i
    return max_dd,peak_idx,trough_idx


def worst_window_sum(returns,w=10):
    if not returns: return 0.0
    if len(returns)<=w: return sum(returns)
    s=sum(returns[:w]); worst=s
    for i in range(w,len(returns)):
        s+=returns[i]-returns[i-w]
        worst=min(worst,s)
    return worst


def pctile(xs,q):
    ys=sorted(xs)
    if not ys: return None
    pos=(len(ys)-1)*q; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    return ys[lo] if lo==hi else ys[lo]+(ys[hi]-ys[lo])*(pos-lo)


def main(out,job):
    try:
        cfg=json.loads(Path(job).read_text())
        if cfg.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
        snap,snap_sha=load_snapshot(); trades=snap.get('trades')
        if not isinstance(trades,list): raise ValueError('snapshot trades missing')
        base_rows=[]; exclusions=Counter()
        for t in trades:
            if t.get('research_group')!='core' or t.get('is_experimental'):
                exclusions['not_core_or_experimental']+=1; continue
            if t.get('status') not in ('closed','expired') or t.get('outcome_group') not in ('positive','negative'):
                exclusions['not_completed_binary_outcome']+=1; continue
            try: pp=float(t.get('profit_percent'))
            except (TypeError,ValueError): exclusions['missing_profit_percent']+=1; continue
            if not math.isfinite(pp) or pp==0:
                exclusions['invalid_or_zero_profit_percent']+=1; continue
            ts=parse_ts(t.get('closed_at'))
            base_rows.append({'id':str(t.get('id')),'strategy':str(t.get('strategy') or 'UNKNOWN'),'symbol':str(t.get('symbol') or 'UNKNOWN'),'market':str(t.get('market') or 'UNKNOWN'),'timeframe':str(t.get('timeframe') or 'UNKNOWN'),'closed_at':ts,'profit_percent':pp})
        valid=[r for r in base_rows if r['closed_at'] is not None]
        ts_cov=(len(valid)/len(base_rows)) if base_rows else 0.0
        valid.sort(key=lambda r:(r['closed_at'],r['id']))
        strategies=sorted({r['strategy'] for r in valid})
        base={'snapshot':{'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'snapshot_sha256':snap_sha},'contract':{'question':'Does chronological ordering of realized core-trade returns create materially deeper unit-return drawdown than expected after preserving each strategy realized return distribution and observed closure slots?','primary_metric':'maximum peak-to-trough drawdown of additive cumulative profit_percent in deterministic closed_at,id order','null':'10000 deterministic within-strategy permutations of realized profit_percent over fixed temporal slots','seed':SEED,'signal_gate':{'upper_tail_p_le':SIGNAL_P,'observed_over_null_median_ge':SIGNAL_RATIO,'both_required':True},'no_signal_gate':{'upper_tail_p_ge':NO_SIGNAL_P,'observed_over_null_median_le':NO_SIGNAL_RATIO,'both_required':True},'minimums':{'eligible_trades':MIN_TRADES,'strategies':MIN_STRATEGIES,'timestamp_coverage':MIN_TS_COVERAGE},'interpretation':'sequence-risk evidence on an equal-unit additive return path only; not portfolio sizing, leverage, allocation, compounding, or edge evidence'},'counts':{'eligible_before_timestamp':len(base_rows),'eligible_timestamped':len(valid),'strategies':len(strategies),'timestamp_coverage':ts_cov,'exclusions':dict(exclusions)}}
        if len(valid)<MIN_TRADES or len(strategies)<MIN_STRATEGIES or ts_cov<MIN_TS_COVERAGE:
            emit(out,'BLOCKED-EVIDENCE',reason='frozen sample/strategy/timestamp gate not met',**base); return
        returns=[r['profit_percent'] for r in valid]
        obs_dd,obs_peak_idx,obs_trough_idx=max_drawdown_additive(returns)
        obs_w10=worst_window_sum(returns,10)
        by_strategy=defaultdict(list)
        for i,r in enumerate(valid): by_strategy[r['strategy']].append(i)
        rng=random.Random(SEED); null_dd=[]; null_w10=[]
        original=list(returns)
        for _ in range(PERMUTATIONS):
            perm=[0.0]*len(valid)
            for s,idxs in by_strategy.items():
                vals=[original[i] for i in idxs]; rng.shuffle(vals)
                for i,v in zip(idxs,vals): perm[i]=v
            dd,_,_=max_drawdown_additive(perm); null_dd.append(dd); null_w10.append(worst_window_sum(perm,10))
        med=pctile(null_dd,.50); p95=pctile(null_dd,.95); ratio=(obs_dd/med) if med and med>0 else float('inf')
        p=(1+sum(x>=obs_dd for x in null_dd))/(PERMUTATIONS+1)
        strat=[]
        for s,idxs in sorted(by_strategy.items()):
            vals=[original[i] for i in idxs]
            strat.append({'strategy':s,'n':len(vals),'sum_profit_percent':sum(vals),'mean_profit_percent':sum(vals)/len(vals)})
        observed={'trades':len(valid),'sum_profit_percent':sum(returns),'mean_profit_percent':sum(returns)/len(returns),'max_additive_drawdown_pp':obs_dd,'drawdown_peak_index':obs_peak_idx,'drawdown_trough_index':obs_trough_idx,'worst_10_trade_sum_pp':obs_w10,'strategy_breakdown':strat}
        null={'permutations':PERMUTATIONS,'max_drawdown_median_pp':med,'max_drawdown_p95_pp':p95,'upper_tail_p':p,'observed_over_null_median':ratio,'worst_10_trade_sum_median_pp':pctile(null_w10,.50),'worst_10_trade_sum_p05_pp':pctile(null_w10,.05)}
        evidence={**base,'observed':observed,'null':null}
        ep=Path(out); ep.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(evidence,indent=2,sort_keys=True); (ep/'drawdown_sequence_evidence.json').write_text(raw); ev_sha=hashlib.sha256(raw.encode()).hexdigest()
        if p<=SIGNAL_P and ratio>=SIGNAL_RATIO:
            state='DRAWDOWN-SEQUENCE-SIGNAL'; reason='observed unit-return drawdown exceeds frozen permutation significance and effect-size gates'
        elif p>=NO_SIGNAL_P and ratio<=NO_SIGNAL_RATIO:
            state='NO-MATERIAL-DRAWDOWN-SEQUENCE'; reason='observed unit-return drawdown remains within frozen no-material sequence gates'
        else:
            state='INCONCLUSIVE-DRAWDOWN-SEQUENCE'; reason='drawdown-sequence evidence falls between frozen signal and no-material gates'
        emit(out,state,reason=reason,evidence_file='drawdown_sequence_evidence.json',evidence_sha256=ev_sha,eligible_trades=len(valid),strategies=len(strategies),max_additive_drawdown_pp=obs_dd,null_median_max_drawdown_pp=med,null_p95_max_drawdown_pp=p95,upper_tail_p=p,observed_over_null_median=ratio,worst_10_trade_sum_pp=obs_w10,**base)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
