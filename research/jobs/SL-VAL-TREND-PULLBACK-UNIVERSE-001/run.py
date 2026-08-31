import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-TREND-PULLBACK-UNIVERSE-001';SYMS=['BNBUSDT','XRPUSDT','LTCUSDT','ADAUSDT','BCHUSDT']
WARM=datetime(2020,1,1,tzinfo=timezone.utc);START=datetime(2021,1,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180;PULL=3;ROLL=1080;Q=.90;HOLD=12;DECLUSTER=18

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def mon(sym,y,m):
 n=f'{sym}-4h-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/4h/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o,h,l,c=map(float,x[1:5])
   except:continue
   ts=raw/1e6 if raw>10**14 else raw/1e3;r.append({'ts':int(ts),'o':o,'c':c})
 return r,{'url':u,'sha256':a,'rows':len(r)}
def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def st(a):
 if not a:return {'n':0,'mean':None,'pf':None,'cum':None,'max_dd':None}
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def one(sym):
 rows=[];files=[]
 for y in range(2020,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d<WARM or d>=END:continue
   a,b=mon(sym,y,m);rows+=a;files.append(b)
 rows.sort(key=lambda x:x['ts']);ev=[];last=-10**9
 for i in range(max(TREND,PULL,ROLL)+1,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  tr=math.log(rows[i-1]['c']/rows[i-1-TREND]['c']);pr=math.log(rows[i]['c']/rows[i-PULL]['c']);hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i) if j>=PULL]
  if len(hist)<ROLL:continue
  th=quantile(hist,Q);side='LONG' if tr>0 and pr<0 and abs(pr)>th else ('SHORT' if tr<0 and pr>0 and abs(pr)>th else None)
  if not side:continue
  en=rows[i+1]['o'];ex=rows[i+HOLD]['o'];gross=ex/en-1 if side=='LONG' else en/ex-1;ev.append({'sym':sym,'ts':b['ts'],'side':side,'net':gross-.001,'net20':gross-.002,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'});last=i
 return ev,files
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  all_ev=[];sources=[];assets={}
  for sym in SYMS:
   ev,fs=one(sym);all_ev+=ev;sources+=fs;o=[x for x in ev if x['period']=='OOS'];s=st([x['net'] for x in o]);s20=st([x['net20'] for x in o]);assets[sym]={'oos10':s,'oos20':s20,'supported':s['n']>0 and s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0}
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 o=[x for x in all_ev if x['period']=='OOS'];s=st([x['net'] for x in o]);s20=st([x['net20'] for x in o]);n_sup=sum(v['supported'] for v in assets.values())
 verdict='UNIVERSE-SUPPORTED' if s['n']>=100 and n_sup>=3 and s['mean']>0 and (s['pf'] or 0)>1 and s20['mean']>0 else 'UNIVERSE-FAILED'
 emit(out,'OUTCOME-COMPLETE',contract={'parent':'SL-VAL-TREND-PULLBACK-001','symbols':SYMS,'tf':'4h','parameters':'exact frozen parent parameters','parameter_tuning':False},asset_stats=assets,pooled_oos_10bps=s,pooled_oos_20bps=s20,supported_assets=n_sup,terminal_verdict=verdict,event_count=len(all_ev),source_files=sources,parameter_tuning=False,limitations=['legacy liquid alt universe only','pooled trades not independence-adjusted','fixed costs only','support does not imply promotion eligibility'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
