#!/usr/bin/env python3
import json, sys, urllib.request
from collections import Counter
from pathlib import Path

OBJECT_ID='SL-VAL-TRENDPULLBACK-ENTRY-DEFECT-BREADTH-COUNT-005'
CUTOFF='2026-09-15T04:58:42.659349Z'
URL='https://raw.githubusercontent.com/mike0610/MarketHunter/outcome-intelligence-snapshots/data/outcome_intelligence/latest/trades.json'

def emit(outdir, state, **extra):
    payload={'object_id':OBJECT_ID,'terminal_state':state,'cutoff':CUTOFF,**extra}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir)/'terminal_result.json').write_text(json.dumps(payload,sort_keys=True,indent=2),encoding='utf-8')

outdir=sys.argv[1] if len(sys.argv)>1 else '.'
try:
    with urllib.request.urlopen(URL, timeout=30) as r:
        raw=r.read()
    doc=json.loads(raw)
    trades=doc.get('trades')
    if not isinstance(trades,list):
        emit(outdir,'BLOCKED-EVIDENCE',reason='trades list missing',source_url=URL); sys.exit(0)
    rows=[]
    for t in trades:
        opened=t.get('opened_at') or t.get('created_at') or ''
        if not (t.get('strategy')=='TrendPullback' and t.get('market')=='futures' and t.get('timeframe')=='1h' and opened>CUTOFF):
            continue
        if t.get('status') not in ('closed','expired'):
            continue
        cls=t.get('outcome_group')
        if cls not in ('positive','negative'):
            continue
        rows.append((t.get('symbol'),cls))
    classes=Counter(c for _,c in rows); symbols=Counter(s for s,_ in rows)
    n=len(rows); unique=len(symbols); max_count=max(symbols.values(),default=0); max_share=(max_count/n if n else 0.0)
    gates={'n_ge_30':n>=30,'positive_ge_10':classes['positive']>=10,'negative_ge_10':classes['negative']>=10,'symbols_ge_8':unique>=8,'max_symbol_share_le_20pct':max_share<=0.20 if n else False}
    state='BREADTH-GATE-MET' if all(gates.values()) else 'BREADTH-GATE-NOT-MET'
    emit(outdir,state,source_url=URL,captured_at_utc=doc.get('captured_at_utc'),source_revision=doc.get('source_revision'),total_snapshot_rows=len(trades),qualifying_n=n,class_counts=dict(classes),unique_symbols=unique,max_symbol_count=max_count,max_symbol_share=max_share,symbol_counts=dict(sorted(symbols.items())),gates=gates)
except Exception as e:
    emit(outdir,'BLOCKED-EVIDENCE',reason=f'{type(e).__name__}: {e}',source_url=URL)
