import argparse,csv,hashlib,io,json,urllib.error,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
O='SL-VAL-REPEATED-LEVEL-REACTION-001';S=['BTCUSDT','ETHUSDT','SOLUSDT'];START=datetime(2021,1,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc)
LOOK=360;TOL=.0015;GAP=2;VALID=3;REBOUND=.005;HOLD=[6,12,30];COST=.001
def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':O,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def load(sym):
 r=[];files=[]
 for y in range(2020,2027):
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
     ts=raw/1e6 if raw>10**14 else raw/1e3;r.append({'ts':int(ts),'o':op,'h':hi,'l':lo,'c':cl})
   files.append({'url':u,'sha256':a})
 return sorted(r,key=lambda x:x['ts']),files
def near(a,b):return abs(a-b)/b<=TOL
def stats(a):
 if not a:return {'n':0,'mean':None,'hit':None}
 return {'n':len(a),'mean':sum(a)/len(a),'hit':sum(x>0 for x in a)/len(a)}
def prior_reactions(ref,level,side):
 out=[];i=0
 while i<len(ref):
  px=ref[i]['l'] if side=='support' else ref[i]['h']
  if not near(px,level):i+=1;continue
  start=i
  while i+1<len(ref) and near(ref[i+1]['l'] if side=='support' else ref[i+1]['h'],level):i+=1
  end=i;nxt=ref[end+1:min(len(ref),end+1+VALID)]
  if side=='support':move=max([x['h']/level-1 for x in nxt],default=0)
  else:move=max([level/x['l']-1 for x in nxt if x['l']>0],default=0)
  if move>=REBOUND and (not out or start-out[-1][1]>GAP):out.append((start,end))
  i+=1
 return len(out)
def eval(sym):
 r,files=load(sym);ev=[];last={'support':-9999,'resistance':-9999}
 for i in range(LOOK,len(r)-max(HOLD)-1):
  b=r[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()):continue
  ref=r[i-LOOK:i]
  for side in ['support','resistance']:
   level=min(x['l'] for x in ref) if side=='support' else max(x['h'] for x in ref)
   touch=near(b['l'] if side=='support' else b['h'],level)
   reject=(b['c']>=level if side=='support' else b['c']<=level)
   if not touch or not reject or i-last[side]<GAP:continue
   n=prior_reactions(ref,level,side)
   if n<1:continue
   rets={}
   for h in HOLD:
    entry=r[i+1]['o'];exitp=r[i+h]['o'];gross=exitp/entry-1 if side=='support' else entry/exitp-1;rets[str(h)]=gross-COST
   ev.append({'ts':b['ts'],'side':side,'prior_reactions':n,'bucket':'REPEATED' if n>=2 else 'SINGLE','period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS','returns':rets});last[side]=i
 o=[x for x in ev if x['period']=='OOS'];cells={}
 for k in ['SINGLE','REPEATED']:
  z=[x for x in o if x['bucket']==k];cells[k]={str(h):stats([x['returns'][str(h)] for x in z]) for h in HOLD}
 return {'symbol':sym,'events':len(ev),'oos_n':len(o),'cells':cells,'sources':files}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=O:raise ValueError('object')
  per=[eval(s) for s in S]
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 pooled={}
 for h in HOLD:
  vals={}
  for k in ['SINGLE','REPEATED']:
   n=0;sm=0
   for r in per:
    x=r['cells'][k][str(h)]
    if x['n'] and x['mean'] is not None:n+=x['n'];sm+=x['n']*x['mean']
   vals[k]={'n':n,'mean':sm/n if n else None}
  d=(vals['REPEATED']['mean']-vals['SINGLE']['mean']) if vals['REPEATED']['mean'] is not None and vals['SINGLE']['mean'] is not None else None
  pooled[str(h)]={**vals,'delta':d}
 primary=pooled['12'];ver='BLOCKED-EVIDENCE' if primary['SINGLE']['n']<20 or primary['REPEATED']['n']<20 else ('REPEATED-REACTION-SUPPORTED' if primary['delta'] is not None and primary['delta']>=.0025 else 'REPEATED-REACTION-NOT-SUPPORTED')
 emit(out,'OUTCOME-COMPLETE',contract={'symbols':S,'tf':'1d','lookback_days':LOOK,'touch_tolerance':TOL,'reaction_gap_days':GAP,'validation_days':VALID,'min_rebound':REBOUND,'holds_days':HOLD,'primary_hold_days':12,'cost':COST,'split':'2025-01-01','parameter_tuning':False,'question':'Does 2+ prior validated reactions at the same horizontal support/resistance level outperform exactly 1 prior reaction?'},per_symbol=per,pooled=pooled,terminal_verdict=ver,parameter_tuning=False,limitations=['horizontal levels only','daily timeframe','no flow/trend-pullback filter','fixed extreme-based level discovery','sloped lines deferred'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
