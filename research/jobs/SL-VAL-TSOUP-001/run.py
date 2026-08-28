import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TSOUP-001'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
START=datetime(2019,1,1,tzinfo=timezone.utc); SPLIT=datetime(2024,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
LOOKBACK=20; HOLD=3; COST=0.001

def emit(outdir,state,**x):
 p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**x},indent=2,sort_keys=True),encoding='utf-8')

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def load_month(y,m):
 name=f'BTCUSDT-1d-{y}-{m:02d}.zip'; url=f'{BASE}/{name}'; z=get(url)
 expected=get(url+'.CHECKSUM').decode().split()[0].lower(); actual=hashlib.sha256(z).hexdigest()
 if expected!=actual: raise ValueError(f'checksum mismatch {name}')
 rows=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  names=[n for n in q.namelist() if not n.endswith('/')]
  if len(names)!=1: raise ValueError(f'zip members {name}: {names}')
  for r in csv.reader(io.TextIOWrapper(q.open(names[0]),encoding='utf-8')):
   if not r: continue
   try: raw=int(r[0]); o,h,l,c=map(float,r[1:5])
   except Exception: continue
   ts=raw/1_000_000 if raw>10**14 else raw/1_000
   rows.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return rows,{'url':url,'sha256':actual,'rows':len(rows)}

def stats(rs):
 if not rs:return {'n':0,'mean':None,'median':None,'hit_rate':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(rs); med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 gains=sum(x for x in rs if x>0); losses=-sum(x for x in rs if x<0); eq=1.0; peak=1.0; mdd=0.0
 for x in rs: eq*=1+x; peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
 return {'n':len(rs),'mean':sum(rs)/len(rs),'median':med,'hit_rate':sum(x>0 for x in rs)/len(rs),'pf':gains/losses if losses>0 else None,'cum':eq-1,'max_dd':mdd}

def main(outdir,job):
 try:
  spec=json.loads(Path(job).read_text());
  if spec.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
  rows=[]; files=[]
  for y in range(2018,2027):
   for m in range(1,13):
    dt=datetime(y,m,1,tzinfo=timezone.utc)
    if dt<datetime(2018,12,1,tzinfo=timezone.utc) or dt>=END: continue
    rr,meta=load_month(y,m); rows+=rr; files.append(meta)
 except Exception as e:
  emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False); return
 rows=sorted(rows,key=lambda x:x['ts']); ts=[r['ts'] for r in rows]
 if len(ts)!=len(set(ts)) or any(ts[i+1]<=ts[i] for i in range(len(ts)-1)):
  emit(outdir,'EVIDENCE-FAIL',reason='duplicate_or_nonmonotonic_source',parameter_tuning=False); return
 trades=[]
 for i in range(LOOKBACK,len(rows)-HOLD):
  b=rows[i]
  if not (int(START.timestamp())<=b['ts']<int(END.timestamp())): continue
  prior=rows[i-LOOKBACK:i]; ph=max(x['h'] for x in prior); pl=min(x['l'] for x in prior)
  side=None
  if b['h']>ph and b['c']<ph: side='SHORT'
  elif b['l']<pl and b['c']>pl: side='LONG'
  if not side: continue
  entry=rows[i+1]['o']; exitp=rows[i+HOLD]['o']
  gross=(exitp/entry-1) if side=='LONG' else (entry/exitp-1)
  net=gross-COST
  trades.append({'ts':b['ts'],'side':side,'gross':gross,'net':net,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
 isr=[x['net'] for x in trades if x['period']=='IS']; oos=[x['net'] for x in trades if x['period']=='OOS']
 # Frozen terminal rule: OOS must have >=30 events, positive net expectancy, PF>1, and not collapse at doubled 20bp cost.
 oos20=[x['gross']-0.002 for x in trades if x['period']=='OOS']; s10=stats(oos); s20=stats(oos20)
 if s10['n']<30: verdict='BLOCKED-EVIDENCE'
 elif s10['mean']>0 and (s10['pf'] or 0)>1 and s20['mean']>0: verdict='CANDIDATE'
 else: verdict='REJECTED'
 emit(outdir,'OUTCOME-COMPLETE',contract={'market':'BTCUSDT Spot','tf':'1d','lookback_bars':LOOKBACK,'entry':'next_bar_open','hold_bars':HOLD,'round_trip_cost':COST,'split':'2024-01-01','tuning':False},source_files=files,is_stats=stats(isr),oos_stats_10bps=s10,oos_stats_20bps=s20,terminal_verdict=verdict,trade_count=len(trades),parameter_tuning=False)

if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); main(a.output,a.job)
