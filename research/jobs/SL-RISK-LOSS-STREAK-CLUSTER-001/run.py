import argparse
import hashlib
import json
import math
import random
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

OBJECT_ID='SL-RISK-LOSS-STREAK-CLUSTER-001'
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


def longest_streak(labels):
    best=cur=0
    for x in labels:
        if x: cur+=1; best=max(best,cur)
        else: cur=0
    return best


def max_window_losses(labels,w=10):
    if not labels: return 0
    if len(labels)<=w: return sum(labels)
    s=sum(labels[:w]); best=s
    for i in range(w,len(labels)):
        s+=labels[i]-labels[i-w]; best=max(best,s)
    return best


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
            if pp==0: exclusions['zero_profit']+=1; continue
            ts=parse_ts(t.get('closed_at'))
            base_rows.append({'id':str(t.get('id')),'strategy':str(t.get('strategy') or 'UNKNOWN'),'symbol':str(t.get('symbol') or 'UNKNOWN'),'market':str(t.get('market') or 'UNKNOWN'),'timeframe':str(t.get('timeframe') or 'UNKNOWN'),'closed_at':ts,'loss':pp<0,'profit_percent':pp})
        valid=[r for r in base_rows if r['closed_at'] is not None]
        ts_cov=(len(valid)/len(base_rows)) if base_rows else 0.0
        valid.sort(key=lambda r:(r['closed_at'],r['id']))
        strategies=sorted({r['strategy'] for r in valid})
        base={'snapshot':{'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'snapshot_sha256':snap_sha},'contract':{'question':'Do negative completed core outcomes cluster into temporal loss streaks beyond a null preserving each strategy marginal loss count and its observed closure slots?','primary_metric':'longest consecutive loss streak in deterministic closed_at,id order','null':'10000 deterministic within-strategy label permutations over fixed temporal slots','seed':SEED,'signal_gate':{'upper_tail_p_le':SIGNAL_P,'observed_over_null_median_ge':SIGNAL_RATIO,'both_required':True},'no_signal_gate':{'upper_tail_p_ge':NO_SIGNAL_P,'observed_over_null_median_le':NO_SIGNAL_RATIO,'both_required':True},'minimums':{'eligible_trades':MIN_TRADES,'strategies':MIN_STRATEGIES,'timestamp_coverage':MIN_TS_COVERAGE},'interpretation':'temporal risk dependence evidence only; no sizing/allocation or edge rule inferred'},'counts':{'eligible_before_timestamp':len(base_rows),'eligible_timestamped':len(valid),'strategies':len(strategies),'timestamp_coverage':ts_cov,'exclusions':dict(exclusions)}}
        if len(valid)<MIN_TRADES or len(strategies)<MIN_STRATEGIES or ts_cov<MIN_TS_COVERAGE:
            emit(out,'BLOCKED-EVIDENCE',reason='frozen sample/strategy/timestamp gate not met',**base); return
        labels=[r['loss'] for r in valid]
        obs=longest_streak(labels); obs_w10=max_window_losses(labels,10)
        by_strategy=defaultdict(list)
        for i,r in enumerate(valid): by_strategy[r['strategy']].append(i)
        rng=random.Random(SEED); null_streak=[]; null_w10=[]
        original=list(labels)
        for _ in range(PERMUTATIONS):
            perm=[False]*len(valid)
            for s,idxs in by_strategy.items():
                vals=[original[i] for i in idxs]; rng.shuffle(vals)
                for i,v in zip(idxs,vals): perm[i]=v
            null_streak.append(longest_streak(perm)); null_w10.append(max_window_losses(perm,10))
        med=pctile(null_streak,.50); p95=pctile(null_streak,.95); ratio=(obs/med) if med else float('inf')
        p=(1+sum(x>=obs for x in null_streak))/(PERMUTATIONS+1)
        losses=sum(labels); loss_rate=losses/len(labels)
        strategy_counts=[]
        for s,idxs in sorted(by_strategy.items()):
            n=len(idxs); l=sum(original[i] for i in idxs)
            strategy_counts.append({'strategy':s,'n':n,'losses':l,'loss_rate':l/n})
        evidence={**base,'observed':{'trades':len(valid),'losses':losses,'loss_rate':loss_rate,'longest_loss_streak':obs,'max_losses_in_10_trade_window':obs_w10,'strategy_breakdown':strategy_counts},'null':{'permutations':PERMUTATIONS,'longest_streak_median':med,'longest_streak_p95':p95,'upper_tail_p':p,'observed_over_null_median':ratio,'max_10_window_median':pctile(null_w10,.50),'max_10_window_p95':pctile(null_w10,.95)}}
        ep=Path(out); ep.mkdir(parents=True,exist_ok=True)
        raw=json.dumps(evidence,indent=2,sort_keys=True); (ep/'loss_streak_cluster_evidence.json').write_text(raw); ev_sha=hashlib.sha256(raw.encode()).hexdigest()
        if p<=SIGNAL_P and ratio>=SIGNAL_RATIO:
            state='STREAK-CLUSTER-SIGNAL'; reason='observed longest loss streak exceeds frozen permutation significance and effect-size gates'
        elif p>=NO_SIGNAL_P and ratio<=NO_SIGNAL_RATIO:
            state='NO-MATERIAL-STREAK-CLUSTER'; reason='observed longest loss streak remains within frozen no-material clustering gates'
        else:
            state='INCONCLUSIVE-STREAK-CLUSTER'; reason='temporal streak evidence falls between frozen signal and no-material gates'
        emit(out,state,reason=reason,evidence_file='loss_streak_cluster_evidence.json',evidence_sha256=ev_sha,eligible_trades=len(valid),strategies=len(strategies),losses=losses,loss_rate=loss_rate,longest_loss_streak=obs,null_median_longest_streak=med,null_p95_longest_streak=p95,upper_tail_p=p,observed_over_null_median=ratio,max_losses_in_10_trade_window=obs_w10,**base)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
