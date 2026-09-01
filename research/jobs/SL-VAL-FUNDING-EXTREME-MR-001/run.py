import argparse,io,json,os,subprocess,sys,urllib.parse,urllib.request,zipfile
from pathlib import Path

def ensure_deps():
    try:
        import numpy as np
        import pandas as pd
        return np,pd
    except ModuleNotFoundError:
        venv=Path('/tmp/mh-research-pydeps')
        py=venv/'bin'/'python'
        if not py.exists():
            subprocess.check_call([sys.executable,'-m','venv',str(venv)])
            subprocess.check_call([str(py),'-m','pip','install','--disable-pip-version-check','numpy','pandas'])
        os.execv(str(py),[str(py),*sys.argv])

np,pd=ensure_deps()
OBJ='SL-VAL-FUNDING-EXTREME-MR-001';SYM='BTCUSDT';START=pd.Timestamp('2022-01-01',tz='UTC');END=pd.Timestamp('2026-08-01',tz='UTC');SPLIT=pd.Timestamp('2025-01-01',tz='UTC')

def getj(url): return json.loads(urllib.request.urlopen(url,timeout=30).read().decode())

def main(job_path,out_dir):
    job=json.loads(Path(job_path).read_text())
    if job.get('object_id')!=OBJ: raise ValueError('object id mismatch')
    OUT=Path(out_dir);OUT.mkdir(parents=True,exist_ok=True)
    rows=[];cur=int(pd.Timestamp('2021-07-01',tz='UTC').timestamp()*1000);end=int(END.timestamp()*1000)
    while cur<end:
        q=urllib.parse.urlencode({'symbol':SYM,'startTime':cur,'endTime':end,'limit':1000});a=getj('https://fapi.binance.com/fapi/v1/fundingRate?'+q)
        if not a: break
        rows+=a;nxt=max(int(x['fundingTime']) for x in a)+1
        if nxt<=cur: break
        cur=nxt
    F=pd.DataFrame(rows);F['time']=pd.to_datetime(F.fundingTime.astype('int64'),unit='ms',utc=True);F['rate']=pd.to_numeric(F.fundingRate);F=F[['time','rate']].drop_duplicates('time').sort_values('time')
    def month(y,m):
        n=f'{SYM}-1h-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{SYM}/1h/{n}'
        try:r=urllib.request.urlopen(u,timeout=30).read()
        except:return None
        z=zipfile.ZipFile(io.BytesIO(r));d=pd.read_csv(z.open(z.namelist()[0]),header=None)
        d=d.iloc[:,:5];d.columns=['open_time','open','high','low','close'];d['open_time']=pd.to_numeric(d['open_time'],errors='coerce');d=d.dropna(subset=['open_time']);unit='us' if d.open_time.iloc[0]>10**14 else 'ms';d['time']=pd.to_datetime(d.open_time,unit=unit,utc=True)
        for c in ['open','high','low','close']:d[c]=pd.to_numeric(d[c],errors='coerce')
        return d[['time','open','high','low','close']]
    K=[]
    for y in range(2021,2027):
        for m in range(1,13):
            t=pd.Timestamp(y,m,1,tz='UTC')
            if t>END or t<pd.Timestamp('2021-07-01',tz='UTC'):continue
            d=month(y,m)
            if d is not None:K.append(d)
    if not K:raise RuntimeError('no futures klines')
    P=pd.concat(K).drop_duplicates('time').sort_values('time').reset_index(drop=True)
    F['q05']=F.rate.shift(1).rolling(540,min_periods=300).quantile(.05);F['q95']=F.rate.shift(1).rolling(540,min_periods=300).quantile(.95)
    tr=[];last=pd.Timestamp('1970-01-01',tz='UTC')
    for _,r in F.iterrows():
        if r.time<START or r.time<last+pd.Timedelta(hours=24) or pd.isna(r.q05) or pd.isna(r.q95):continue
        side=1 if r.rate<r.q05 else (-1 if r.rate>r.q95 else 0)
        if side==0:continue
        entry_candidates=P[P.time>r.time]
        if entry_candidates.empty:continue
        ei=entry_candidates.index[0];xt=P.time.iloc[ei]+pd.Timedelta(hours=24);exits=P[P.time>=xt]
        if exits.empty:continue
        xi=exits.index[0];entry=float(P.open.iloc[ei]);exitp=float(P.open.iloc[xi]);price_ret=side*(exitp/entry-1)
        fund=F[(F.time>P.time.iloc[ei])&(F.time<=P.time.iloc[xi])].rate.sum();funding_ret=-side*fund
        tr.append({'signal_time':r.time,'entry_time':P.time.iloc[ei],'exit_time':P.time.iloc[xi],'side':'LONG' if side==1 else 'SHORT','price_return':price_ret,'funding_return':funding_ret,'gross_return':price_ret+funding_ret});last=r.time
    T=pd.DataFrame(tr)
    def met(x,cost,lev=1):
        if len(x)==0:return {'n':0}
        r=(x.gross_return.to_numpy()-cost/10000)*lev;pos=r[r>0].sum();neg=-r[r<0].sum();eq=np.cumprod(1+r);peak=np.maximum.accumulate(np.r_[1,eq]);dd=np.r_[1,eq]/peak-1;wins=np.sort(r[r>0])[::-1];share=float(wins[0]/wins.sum()) if wins.sum()>0 else None;ls=ml=0
        for v in r:ls=ls+1 if v<0 else 0;ml=max(ml,ls)
        return {'n':len(r),'mean_pct':float(r.mean()*100),'profit_factor':float(pos/neg) if neg>0 else None,'cumulative_pct':float((eq[-1]-1)*100),'max_drawdown_pct':float(dd.min()*100),'top_positive_trade_share':share,'max_loss_streak':ml}
    T['sample']=np.where(T.entry_time<SPLIT,'IS','OOS');o=T[T['sample']=='OOS'];r10=met(o,10,1);r20=met(o,20,1)
    ver='BLOCKED-EVIDENCE' if r10.get('n',0)<30 else ('CANDIDATE' if r10['mean_pct']>0 and r10['profit_factor']>1 and r20['mean_pct']>0 and (r10['top_positive_trade_share'] or 1)<.5 else 'REJECTED')
    res={'object_id':OBJ,'terminal_state':'OUTCOME-COMPLETE','terminal_verdict':ver,'total_events':len(T),'oos_1x_10bps':r10,'oos_1x_20bps':r20,'oos_2x_10bps':met(o,10,2),'oos_3x_10bps':met(o,10,3),'oos_price_return_mean_pct':float(o.price_return.mean()*100) if len(o) else None,'oos_funding_return_mean_pct':float(o.funding_return.mean()*100) if len(o) else None,'parameter_tuning':False}
    (OUT/'terminal_result.json').write_text(json.dumps(res,indent=2));T.to_csv(OUT/'trades.csv',index=False);print(json.dumps(res,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--job',required=True);ap.add_argument('--output',required=True);args=ap.parse_args();main(args.job,args.output)
