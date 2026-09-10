import argparse,csv,hashlib,io,json,urllib.error,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
O='SL-VAL-SWING-ZONE-REACTION-001';SYMS=['BTCUSDT','ETHUSDT','SOLUSDT'];START=datetime(2021,1,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc)
LOOK=720;L=3;R=3;ZONE=.0075;MIN_GAP=10;TOUCH=.0075;HOLD=[6,12,30];COST=.001
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def load(sym):
 rows=[];src=[]
 for y in range(2019,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d>=END:continue
   n=f'{sym}-1d-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/spot/monthly/klines/{sym}/1d/{n}'
   try:z=get(u)
   except urllib.error.HTTPError as e:
    if e.code==404:continue
    raise
   e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
   if a!=e:raise ValueError('checksum '+n)
   with zipfile.ZipFile(io.BytesIO(z)) as q:
    for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
     try:raw=int(x[0]);op,hi,lo,cl=map(float,x[1:5])
     except:continue
     ts=raw/1e6 if raw>10**14 else raw/1e3;rows.append({'ts':int(ts),'o':op,'h':hi,'l':lo,'c':cl})
   src.append({'url':u,'sha256':a})
 return sorted(rows,key=lambda x:x['ts']),src
def swings(ref,side):
 out=[]
 for i in range(L,len(ref)-R):
  px=ref[i]['l'] if side=='support' else ref[i]['h']
  left=[ref[j]['l'] if side=='support' else ref[j]['h'] for j in range(i-L,i)]
  right=[ref[j]['l'] if side=='support' else ref[j]['h'] for j in range(i+1,i+R+1)]
  ok=(all(x>px for x in left) and all(x>=px for x in right)) if side=='support' else (all(x<px for x in left) and all(x<=px for x in right))
  if ok:out.append((i,px))
 return out
def zones(sw):
 z=[]
 for idx,px in sw:
  best=None
  for a in z:
   if abs(px-a['level'])/a['level']<=ZONE:
    best=a;break
  if best is None:z.append({'level':px,'pts':[(idx,px)]})
  else:
   best['pts'].append((idx,px));best['level']=sum(p for _,p in best['pts'])/len(best['pts'])
 return z
def independent(pts):
 keep=[];last=-9999
 for i,p in pts:
  if i-last>=MIN_GAP:keep.append((i,p));last=i
 return keep
def stats(a):
 if not a:return {'n':0,'mean':None,'hit':None}
 return {'n':len(a),'mean':sum(a)/len(a),'hit':sum(x>0 for x in a)/len(a)}
def evaluate(sym):
 rows,src=load(sym);ev=[];last={'support':-9999,'resistance':-9999}
 for i in range(LOOK,len(rows)-max(HOLD)-1):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()):continue
  ref=rows[i-LOOK:i]
  for side in ['support','resistance']:
   candidates=[]
   for z in zones(swings(ref,side)):
    pts=independent(z['pts'])
    if not pts:continue
    level=z['level'];dist=abs((b['l'] if side=='support' else b['h'])-level)/level
    reject=b['c']>=level if side=='support' else b['c']<=level
    if dist<=TOUCH and reject:candidates.append((dist,level,len(pts)))
   if not candidates or i-last[side]<MIN_GAP:continue
   _,level,n=min(candidates,key=lambda x:x[0])
   bucket='THREE_PLUS' if n>=3 else ('TWO' if n==2 else 'ONE')
   rr={}
   for h in HOLD:
    en=rows[i+1]['o'];ex=rows[i+h]['o'];gross=ex/en-1 if side=='support' else en/ex-1;rr[str(h)]=gross-COST
   ev.append({'ts':b['ts'],'side':side,'prior_touches':n,'bucket':bucket,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS','returns':rr});last[side]=i
 o=[x for x in ev if x['period']=='OOS'];cells={}
 for k in ['ONE','TWO','THREE_PLUS']:
  z=[x for x in o if x['bucket']==k];cells[k]={str(h):stats([x['returns'][str(h)] for x in z]) for h in HOLD}
 return {'symbol':sym,'events':len(ev),'oos_n':len(o),'cells':cells,'sources':src}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=O:raise ValueError('object')
  per=[evaluate(s) for s in SYMS]
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 pooled={}
 for h in HOLD:
  pooled[str(h)]={}
  for k in ['ONE','TWO','THREE_PLUS']:
   n=0;sm=0
   for r in per:
    x=r['cells'][k][str(h)]
    if x['n'] and x['mean'] is not None:n+=x['n'];sm+=x['n']*x['mean']
   pooled[str(h)][k]={'n':n,'mean':sm/n if n else None}
 p=pooled['12'];base=p['ONE'];repn=p['TWO']['n']+p['THREE_PLUS']['n'];repsum=sum(x['n']*x['mean'] for x in [p['TWO'],p['THREE_PLUS']] if x['n'] and x['mean'] is not None);repm=repsum/repn if repn else None;delta=repm-base['mean'] if repm is not None and base['mean'] is not None else None
 verdict='BLOCKED-EVIDENCE' if base['n']<20 or repn<20 else ('SWING-ZONE-REPETITION-SUPPORTED' if delta is not None and delta>=.0025 else 'SWING-ZONE-REPETITION-NOT-SUPPORTED')
 emit(out,'OUTCOME-COMPLETE',contract={'symbols':SYMS,'tf':'1d','lookback_days':LOOK,'swing_left_right':[L,R],'zone_half_width_fraction':ZONE,'minimum_independent_touch_gap_days':MIN_GAP,'current_touch_tolerance':TOUCH,'holds_days':HOLD,'primary_hold_days':12,'cost':COST,'split':'2025-01-01','parameter_tuning':False,'question':'Do 2+ independent prior swing reactions clustered into the same horizontal zone outperform a single prior swing reaction?'},per_symbol=per,pooled=pooled,primary={'single':base,'repeated_n':repn,'repeated_mean':repm,'delta':delta},terminal_verdict=verdict,parameter_tuning=False,limitations=['horizontal zones only','daily timeframe','fixed clustering tolerance','sloped support/resistance deferred','no flow or trend filter'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
