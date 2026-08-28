import argparse,csv,hashlib,io,json,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-DONCHIAN-002'; BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
START=datetime(2019,1,1,tzinfo=timezone.utc); SPLIT=datetime(2024,1,1,tzinfo=timezone.utc); END=datetime(2026,8,1,tzinfo=timezone.utc)
ENTRY_N=55; EXIT_N=20; COST=0.001

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):
 q=urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'});return urllib.request.urlopen(q,timeout=30).read()
def month(y,m):
 n=f'BTCUSDT-1d-{y}-{m:02d}.zip';u=f'{BASE}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 out=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for r in csv.reader(io.TextIOWrapper(q.open([x for x in q.namelist() if not x.endswith('/')][0]))):
   try: raw=int(r[0]);o,h,l,c=map(float,r[1:5])
   except:continue
   ts=raw/1e6 if raw>10**14 else raw/1e3;out.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return out,{'url':u,'sha256':a,'rows':len(out)}
def st(rs):
 if not rs:return {'n':0,'mean':None,'pf':None,'cum':None,'max_dd':None}
 g=sum(x for x in rs if x>0);l=-sum(x for x in rs if x<0);eq=pk=1.;dd=0.
 for x in rs:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(rs),'mean':sum(rs)/len(rs),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object id')
  rows=[];files=[]
  for y in range(2018,2027):
   for m in range(1,13):
    d=datetime(y,m,1,tzinfo=timezone.utc)
    if d<datetime(2018,11,1,tzinfo=timezone.utc) or d>=END:continue
    r,f=month(y,m);rows+=r;files.append(f)
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 rows.sort(key=lambda x:x['ts']); trades=[];pos=entry=ets=period=None;i=max(ENTRY_N,EXIT_N)
 while i<len(rows)-1:
  b=rows[i]
  if b['ts']<int(START.timestamp()):i+=1;continue
  if b['ts']>=int(END.timestamp()):break
  if pos is None:
   ph=max(x['h'] for x in rows[i-ENTRY_N:i]);pl=min(x['l'] for x in rows[i-ENTRY_N:i]);sig='LONG' if b['h']>ph else ('SHORT' if b['l']<pl else None)
   if sig:pos=sig;entry=rows[i+1]['o'];ets=rows[i+1]['ts'];period='IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS';i+=1
  else:
   hi=max(x['h'] for x in rows[i-EXIT_N:i]);lo=min(x['l'] for x in rows[i-EXIT_N:i]);ex=(pos=='LONG' and b['l']<lo) or (pos=='SHORT' and b['h']>hi)
   if ex:
    xp=rows[i+1]['o'];gross=xp/entry-1 if pos=='LONG' else entry/xp-1;trades.append({'entry_ts':ets,'exit_ts':rows[i+1]['ts'],'side':pos,'gross':gross,'net':gross-COST,'period':period});pos=entry=ets=period=None;i+=1
  i+=1
 o=[x for x in trades if x['period']=='OOS']; base=[x['net'] for x in o]; longs=[x['net'] for x in o if x['side']=='LONG'];shorts=[x['net'] for x in o if x['side']=='SHORT']
 years={str(datetime.fromtimestamp(x['entry_ts'],timezone.utc).year):[] for x in o}
 for x in o:years[str(datetime.fromtimestamp(x['entry_ts'],timezone.utc).year)].append(x['net'])
 positives=sorted([x for x in o if x['net']>0],key=lambda x:x['net'],reverse=True); loo=[x['net'] for x in o]
 if positives:loo.remove(positives[0]['net'])
 bs=st(base);ls=st(longs);ss=st(shorts);loos=st(loo);ys={y:st(v) for y,v in years.items()}
 profitable_years=sum(1 for v in ys.values() if v['cum'] is not None and v['cum']>0); active_sides=sum(1 for v in (ls,ss) if v['n']>=3 and v['mean'] is not None and v['mean']>0)
 # Frozen robustness gate: parent candidate must remain positive after removing best winner, have >=2 profitable OOS calendar years, and positive expectancy on both sides with >=3 trades each.
 if bs['n']<10:verdict='BLOCKED-EVIDENCE'
 elif loos['mean'] is not None and loos['mean']>0 and (loos['pf'] or 0)>1 and profitable_years>=2 and active_sides==2:verdict='ROBUSTNESS-PASS'
 else:verdict='ROBUSTNESS-FAIL'
 emit(out,'OUTCOME-COMPLETE',contract={'parent':'SL-VAL-DONCHIAN-001','market':'BTCUSDT Spot','entry_channel':55,'exit_channel':20,'cost':0.001,'split':'2024-01-01','parameter_tuning':False},oos=bs,long=ls,short=ss,calendar_years=ys,leave_best_winner_out=loos,profitable_oos_years=profitable_years,positive_expectancy_sides=active_sides,robustness_verdict=verdict,source_files=files,parameter_tuning=False)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
