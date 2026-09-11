import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

OBJECT_ID = 'SL-RISK-LOSS-SEVERITY-TAIL-001'
REPO = '/home/ubuntu/MarketHunter'
SNAP_BRANCH = 'outcome-intelligence-snapshots'
SNAP = 'data/outcome_intelligence/latest/trades.json'
MIN_LOSSES = 50
MIN_STRATEGIES = 3
OVERSHOOT_R = 1.25
SIGNAL_SHARE = 0.10
SIGNAL_P95_R = 1.50
NO_SIGNAL_SHARE = 0.05
NO_SIGNAL_P95_R = 1.25


def emit(out, state, **payload):
    p = Path(out); p.mkdir(parents=True, exist_ok=True)
    (p/'terminal_result.json').write_text(json.dumps({'object_id': OBJECT_ID, 'terminal_state': state, **payload}, indent=2, sort_keys=True))


def pctile(xs, q):
    ys = sorted(xs)
    if not ys: return None
    pos = (len(ys)-1)*q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi: return ys[lo]
    return ys[lo] + (ys[hi]-ys[lo])*(pos-lo)


def load_snapshot():
    subprocess.run(['git','-C',REPO,'fetch','origin',SNAP_BRANCH], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
    raw = subprocess.run(['git','-C',REPO,'show',f'FETCH_HEAD:{SNAP}'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30).stdout
    return json.loads(raw), hashlib.sha256(raw.encode()).hexdigest()


def planned_stop_pct(t):
    e, s = t.get('entry_price'), t.get('stop_loss')
    try:
        e, s = float(e), float(s)
    except (TypeError, ValueError):
        return None
    if e <= 0 or s <= 0: return None
    d = str(t.get('direction','')).upper()
    if d == 'LONG' and s >= e: return None
    if d == 'SHORT' and s <= e: return None
    if d not in ('LONG','SHORT'): return None
    return abs(e-s)/e*100.0


def main(out, job):
    try:
        cfg = json.loads(Path(job).read_text())
        if cfg.get('object_id') != OBJECT_ID: raise ValueError('object_id mismatch')
        snap, snap_sha = load_snapshot()
        trades = snap.get('trades')
        if not isinstance(trades, list): raise ValueError('snapshot trades missing')
        rows=[]; exclusion=Counter()
        for t in trades:
            if t.get('research_group') != 'core' or t.get('is_experimental'):
                exclusion['not_core_or_experimental'] += 1; continue
            if t.get('status') not in ('closed','expired') or t.get('outcome_group') != 'negative':
                exclusion['not_completed_negative'] += 1; continue
            try: pp=float(t.get('profit_percent'))
            except (TypeError,ValueError): exclusion['missing_profit_percent'] += 1; continue
            if pp >= 0: exclusion['negative_group_nonnegative_profit'] += 1; continue
            sp=planned_stop_pct(t)
            if not sp or sp <= 0: exclusion['invalid_planned_stop'] += 1; continue
            loss=-pp; r=loss/sp
            rows.append({'id':str(t.get('id')),'strategy':str(t.get('strategy') or 'UNKNOWN'),'symbol':str(t.get('symbol') or 'UNKNOWN'),'market':str(t.get('market') or 'UNKNOWN'),'timeframe':str(t.get('timeframe') or 'UNKNOWN'),'close_reason':str(t.get('close_reason') or 'UNKNOWN'),'loss_pct':loss,'planned_stop_pct':sp,'loss_r':r})
        strategies=sorted({r['strategy'] for r in rows})
        base={'snapshot':{'captured_at_utc':snap.get('captured_at_utc'),'source':snap.get('source'),'source_revision':snap.get('source_revision'),'snapshot_sha256':snap_sha},'contract':{'question':'Do completed negative core trades exhibit realized loss tails materially beyond their ex-ante planned stop distance?','primary_metric':'realized loss percent divided by planned stop distance percent (loss_r)','signal_gate':{'share_loss_r_gt_1_25_ge':SIGNAL_SHARE,'p95_loss_r_ge':SIGNAL_P95_R,'both_required':True},'no_signal_gate':{'share_loss_r_gt_1_25_le':NO_SIGNAL_SHARE,'p95_loss_r_le':NO_SIGNAL_P95_R,'both_required':True},'minimums':{'eligible_losses':MIN_LOSSES,'strategies':MIN_STRATEGIES},'interpretation':'risk/execution severity evidence only; sizing does not create edge and no allocation rule is inferred'},'counts':{'eligible_losses':len(rows),'strategies':len(strategies),'exclusions':dict(exclusion)}}
        if len(rows)<MIN_LOSSES or len(strategies)<MIN_STRATEGIES:
            emit(out,'BLOCKED-EVIDENCE',reason='frozen loss-count/strategy-breadth gate not met',**base); return
        rs=[r['loss_r'] for r in rows]; losses=[r['loss_pct'] for r in rows]
        share=sum(x>OVERSHOOT_R for x in rs)/len(rs); p50=pctile(rs,.50); p90=pctile(rs,.90); p95=pctile(rs,.95); p99=pctile(rs,.99); mx=max(rs)
        k=max(1,math.ceil(len(losses)*0.10)); top10=sum(sorted(losses,reverse=True)[:k])/sum(losses) if sum(losses)>0 else 0.0
        reasons=Counter(r['close_reason'] for r in rows)
        by_strategy=defaultdict(list)
        for r in rows: by_strategy[r['strategy']].append(r['loss_r'])
        strat=[{'strategy':s,'n':len(v),'p95_loss_r':pctile(v,.95),'max_loss_r':max(v),'share_gt_1_25r':sum(x>OVERSHOOT_R for x in v)/len(v)} for s,v in sorted(by_strategy.items())]
        evidence={**base,'observed':{'median_loss_r':p50,'p90_loss_r':p90,'p95_loss_r':p95,'p99_loss_r':p99,'max_loss_r':mx,'share_loss_r_gt_1_25':share,'share_loss_r_gt_2':sum(x>2 for x in rs)/len(rs),'top_10pct_share_of_total_realized_loss_pct':top10,'close_reason_counts':dict(reasons),'strategy_breakdown':strat}}
        p=Path(out); p.mkdir(parents=True,exist_ok=True)
        ev_raw=json.dumps(evidence,indent=2,sort_keys=True); (p/'loss_severity_tail_evidence.json').write_text(ev_raw); ev_sha=hashlib.sha256(ev_raw.encode()).hexdigest()
        if share>=SIGNAL_SHARE and p95>=SIGNAL_P95_R:
            state='TAIL-SEVERITY-SIGNAL'; reason='realized loss tail exceeds frozen stop-normalized prevalence and p95 severity gates'
        elif share<=NO_SIGNAL_SHARE and p95<=NO_SIGNAL_P95_R:
            state='NO-MATERIAL-TAIL-SEVERITY'; reason='realized loss tail remains within frozen no-material-tail gates'
        else:
            state='INCONCLUSIVE-TAIL-SEVERITY'; reason='stop-normalized tail evidence falls between frozen signal and no-material-tail gates'
        emit(out,state,reason=reason,evidence_file='loss_severity_tail_evidence.json',evidence_sha256=ev_sha,eligible_losses=len(rows),strategies=len(strategies),median_loss_r=p50,p95_loss_r=p95,p99_loss_r=p99,max_loss_r=mx,share_loss_r_gt_1_25=share,share_loss_r_gt_2=sum(x>2 for x in rs)/len(rs),top_10pct_share_of_total_realized_loss_pct=top10,**base)
    except Exception as e:
        emit(out,'BLOCKED-EVIDENCE',reason=f'execution/data failure: {e!r}')

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
