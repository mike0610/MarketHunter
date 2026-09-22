#!/usr/bin/env python3
import json, sys, urllib.request
from collections import Counter
from pathlib import Path

OBJECT_ID='SL-VAL-SESSIONRANGE-FORWARD-EXACT-CENSUS-007'
CUTOFF='2026-09-20T17:33:10Z'
URL='https://raw.githubusercontent.com/mike0610/MarketHunter/outcome-intelligence-snapshots/data/outcome_intelligence/latest/trades.json'

def emit(outdir,state,**extra):
    payload={'object_id':OBJECT_ID,'terminal_state':state,'cutoff':CUTOFF,**extra}
    Path(outdir).mkdir(parents=True,exist_ok=True)
    (Path(outdir)/'terminal_result.json').write_text(json.dumps(payload,sort_keys=True,indent=2),encoding='utf-8')

outdir=sys.argv[1] if len(sys.argv)>1 else '.'
try:
    with urllib.request.urlopen(URL,timeout=30) as r:
        raw=r.read()
    doc=json.loads(raw)
    trades=doc.get('trades')
    if not isinstance(trades,list):
        emit(outdir,'BLOCKED-EVIDENCE',reason='trades list missing',source_url=URL); sys.exit(0)
    rows=[]
    for t in trades:
        opened=t.get('opened_at') or t.get('created_at') or ''
        if not (t.get('strategy')=='SessionRange' and t.get('timeframe')=='1h' and opened>=CUTOFF):
            continue
        if t.get('status') not in ('closed','expired'):
            continue
        pnl=t.get('profit_percent')
        pnl_sign='unknown'
        if isinstance(pnl,(int,float)):
            pnl_sign='positive' if pnl>0 else ('negative' if pnl<0 else 'zero')
        rows.append({'symbol':t.get('symbol'),'market':t.get('market'),'side':t.get('side'),'status':t.get('status'),'outcome_group':t.get('outcome_group'),'outcome_type':t.get('outcome_type'),'pnl_sign':pnl_sign})
    def count(key): return dict(sorted(Counter(str(r.get(key)) for r in rows).items()))
    symbols=Counter(str(r.get('symbol')) for r in rows)
    emit(outdir,'CENSUS-COMPLETE',source_url=URL,captured_at_utc=doc.get('captured_at_utc'),source_revision=doc.get('source_revision'),total_snapshot_rows=len(trades),mature_n=len(rows),market_counts=count('market'),side_counts=count('side'),symbol_counts=dict(sorted(symbols.items())),outcome_group_counts=count('outcome_group'),outcome_type_counts=count('outcome_type'),realized_pnl_sign_counts=count('pnl_sign'),unique_symbols=len(symbols),max_symbol_share=(max(symbols.values(),default=0)/len(rows) if rows else 0.0))
except Exception as e:
    emit(outdir,'BLOCKED-EVIDENCE',reason=f'{type(e).__name__}: {e}',source_url=URL)
