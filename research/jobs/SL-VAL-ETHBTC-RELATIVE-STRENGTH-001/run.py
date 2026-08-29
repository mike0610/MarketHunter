import io, json, math, hashlib, zipfile, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

OBJ='SL-VAL-ETHBTC-RELATIVE-STRENGTH-001'; SYM='ETHBTC'
START=pd.Timestamp('2022-01-01',tz='UTC'); END=pd.Timestamp('2026-08-01',tz='UTC'); SPLIT=pd.Timestamp('2025-01-01',tz='UTC')
OUT=Path('research_output'); OUT.mkdir(exist_ok=True)

def load_month(y,m):
    name=f'{SYM}-4h-{y}-{m:02d}.zip'; url=f'https://data.binance.vision/data/spot/monthly/klines/{SYM}/4h/{name}'
    try:
        raw=urllib.request.urlopen(url,timeout=30).read()
    except Exception:
        return None
    z=zipfile.ZipFile(io.BytesIO(raw)); f=z.open(z.namelist()[0])
    cols=['open_time','open','high','low','close','volume','close_time','qv','trades','tb','tq','ignore']
    d=pd.read_csv(f,header=None,names=cols); d=d[['open_time','open','high','low','close']]
    unit='us' if d.open_time.iloc[0]>10**14 else 'ms'; d['time']=pd.to_datetime(d.open_time,unit=unit,utc=True)
    for c in ['open','high','low','close']: d[c]=pd.to_numeric(d[c],errors='coerce')
    return d[['time','open','high','low','close']]

frames=[]
for y in range(2021,2027):
  for m in range(1,13):
    t=pd.Timestamp(y,m,1,tz='UTC')
    if t>END or t<pd.Timestamp('2021-10-01',tz='UTC'): continue
    d=load_month(y,m)
    if d is not None: frames.append(d)
if not frames: raise RuntimeError('no data')
df=pd.concat(frames).drop_duplicates('time').sort_values('time').reset_index(drop=True)
df=df[(df.time>=pd.Timestamp('2021-10-01',tz='UTC'))&(df.time<=END)].copy()
df['prior_high42']=df.close.shift(1).rolling(42,min_periods=42).max()
df['signal']=(df.close>df.prior_high42)
tr=[]; next_allowed=-1
for i in range(len(df)-19):
    if i<next_allowed or not bool(df.signal.iloc[i]) or df.time.iloc[i]<START: continue
    entry_i=i+1; exit_i=entry_i+18
    if exit_i>=len(df): break
    entry=float(df.open.iloc[entry_i]); exitp=float(df.open.iloc[exit_i]); gross=exitp/entry-1
    tr.append({'signal_time':df.time.iloc[i],'entry_time':df.time.iloc[entry_i],'exit_time':df.time.iloc[exit_i],'gross_return':gross})
    next_allowed=i+18
T=pd.DataFrame(tr)

def metrics(x,cost_bps):
    if len(x)==0:return {'n':0}
    r=x.gross_return.to_numpy()-cost_bps/10000
    pos=r[r>0].sum(); neg=-r[r<0].sum(); eq=np.cumprod(1+r); peak=np.maximum.accumulate(np.r_[1,eq]); dd=np.r_[1,eq]/peak-1
    wins=np.sort(r[r>0])[::-1]; share=float(wins[0]/wins.sum()) if wins.sum()>0 else None
    loss=0; maxloss=0
    for v in r:
        loss=loss+1 if v<0 else 0; maxloss=max(maxloss,loss)
    return {'n':int(len(r)),'mean_pct':float(r.mean()*100),'median_pct':float(np.median(r)*100),'hit_rate':float((r>0).mean()),'profit_factor':float(pos/neg) if neg>0 else None,'cumulative_pct':float((eq[-1]-1)*100),'max_drawdown_pct':float(dd.min()*100),'top_positive_trade_share':share,'max_loss_streak':int(maxloss)}

T['sample']=np.where(T.entry_time<SPLIT,'IS','OOS')
res={'object_id':OBJ,'terminal_state':'OUTCOME-COMPLETE','market':SYM,'book':'SPOT','leverage':1.0,'total_events':int(len(T)),'is_10bps':metrics(T[T['sample']=='IS'],10),'oos_10bps':metrics(T[T['sample']=='OOS'],10),'oos_20bps':metrics(T[T['sample']=='OOS'],20)}
o=res['oos_10bps']; s=res['oos_20bps']
if o.get('n',0)<30: verdict='BLOCKED-EVIDENCE'
elif o['mean_pct']>0 and o['profit_factor']>1 and s['mean_pct']>0 and (o['top_positive_trade_share'] or 1)<.5: verdict='CANDIDATE'
else: verdict='REJECTED'
res['terminal_verdict']=verdict
if len(T):
    oo=T[T['sample']=='OOS'].copy(); oo['net10']=oo.gross_return-.001; oo['month']=oo.entry_time.dt.to_period('M').astype(str)
    res['oos_monthly']=oo.groupby('month').net10.agg(['count','mean','sum']).reset_index().to_dict('records')
    T.to_csv(OUT/'trades.csv',index=False)
(OUT/'terminal_result.json').write_text(json.dumps(res,indent=2,default=str))
print(json.dumps(res,indent=2,default=str))
