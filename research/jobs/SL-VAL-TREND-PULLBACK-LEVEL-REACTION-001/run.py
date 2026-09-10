import argparse,csv,hashlib,io,json,math,urllib.error,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-TREND-PULLBACK-LEVEL-REACTION-001'
SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT']
WARM=datetime(2020,1,1,tzinfo=timezone.utc)
START=datetime(2021,1,1,tzinfo=timezone.utc)
SPLIT=datetime(2025,1,1,tzinfo=timezone.utc)
END=datetime(2026,8,1,tzinfo=timezone.utc)
TREND=180;PULL=3;ROLL=1080;Q=.90;HOLD=12;DECLUSTER=18;COST=.001
LEVEL_LOOKBACK=60;TOL=.0015;REACTION_GAP=2;VALIDATE=3;MIN_REBOUND=.005

def emit(o,s,**x):
 p=Path(o);p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))

def get(u):
 return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()

def archive(symbol,market,y,m):
 root='spot' if market=='spot' else 'futures/um'
 n=f'{symbol}-4h-{y}-{m:02d}.zip'
 u=f'https://data.binance.vision/data/{root}/monthly/klines/{symbol}/4h/{n}'
 try:z=get(u)
 except urllib.error.HTTPError as e:
  if e.code==404:return None,None
  raise
 e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 out=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  rd=csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0])))
  for x in rd:
   try:
    raw=int(x[0]);o,h,l,c=map(float,x[1:5]);vol=float(x[5]);tb=float(x[9])
   except:continue
   ts=raw/1e6 if raw>10**14 else raw/1e3
   out.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c,'vol':vol,'tb':tb})
 return out,{'url':u,'sha256':a,'rows':len(out)}

def quantile(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x))
 return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)

def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);med=s[len(s)//2] if len(s)%2 else (s[len(s)//2-1]+s[len(s)//2])/2
 g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':len(a),'mean':sum(a)/len(a),'median':med,'hit':sum(x>0 for x in a)/len(a),'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}

def near(px,level):
 return abs(px-level)/level<=TOL

def reaction_count(ref,level,side):
 count=0;last_cluster=-10**9;i=0
 while i<len(ref):
  touched=near(ref[i]['l'] if side=='support' else ref[i]['h'],level)
  if not touched:
   i+=1;continue
  cluster_start=i
  while i+1<len(ref) and near(ref[i+1]['l'] if side=='support' else ref[i+1]['h'],level):
   i+=1
  cluster_end=i
  if cluster_start-last_cluster<=REACTION_GAP:
   last_cluster=cluster_end;i+=1;continue
  end=min(len(ref),cluster_end+1+VALIDATE)
  if side=='support':
   best=max((x['h'] for x in ref[cluster_end+1:end]),default=ref[cluster_end]['c'])
   rebound=best/level-1
  else:
   best=min((x['l'] for x in ref[cluster_end+1:end]),default=ref[cluster_end]['c'])
   rebound=level/best-1 if best>0 else 0
  if rebound>=MIN_REBOUND:count+=1
  last_cluster=cluster_end;i+=1
 return count

def evaluate(symbol):
 rows=[];flow={};files=[]
 for y in range(2020,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d<WARM or d>=END:continue
   a,meta=archive(symbol,'spot',y,m)
   if a:rows+=a;files.append(meta)
 for y in range(2025,2027):
  for m in range(1,13):
   d=datetime(y,m,1,tzinfo=timezone.utc)
   if d<SPLIT or d>=END:continue
   a,meta=archive(symbol,'futures',y,m)
   if not a:continue
   files.append(meta)
   for x in a:
    if x['vol']>0:flow[x['ts']]=[x['tb'],max(0.,x['vol']-x['tb'])]
 if not rows:raise ValueError('no spot history '+symbol)
 rows.sort(key=lambda x:x['ts'])
 events=[];last=-10**9
 start_i=max(TREND,PULL,ROLL,LEVEL_LOOKBACK)+1
 for i in range(start_i,len(rows)-HOLD):
  b=rows[i]
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()) or i-last<DECLUSTER:continue
  trend_ret=math.log(rows[i-1]['c']/rows[i-1-TREND]['c'])
  pull_ret=math.log(rows[i]['c']/rows[i-PULL]['c'])
  hist=[abs(math.log(rows[j]['c']/rows[j-PULL]['c'])) for j in range(i-ROLL,i) if j>=PULL]
  if len(hist)<ROLL:continue
  th=quantile(hist,Q);side=None
  if trend_ret>0 and pull_ret<0 and abs(pull_ret)>th:side='LONG'
  elif trend_ret<0 and pull_ret>0 and abs(pull_ret)>th:side='SHORT'
  if not side:continue
  vals=[]
  for k in range(1,4):
   d=flow.get(b['ts']-k*14400)
   if d and d[0]+d[1]>0:vals.append((d[0]-d[1])/(d[0]+d[1]))
  if len(vals)<3:continue
  imbalance=sum(vals)/3
  flow_state='BUY-PRESSURE' if imbalance>0 else ('SELL-PRESSURE' if imbalance<0 else 'NEUTRAL')
  alignment='WITH-FLOW' if (side=='LONG' and flow_state=='BUY-PRESSURE') or (side=='SHORT' and flow_state=='SELL-PRESSURE') else 'COUNTER-FLOW'
  ref=rows[i-LEVEL_LOOKBACK:i]
  if side=='LONG':
   level=min(x['l'] for x in ref)
   current_touch=near(b['l'],level) and b['c']>=level
   lside='support'
  else:
   level=max(x['h'] for x in ref)
   current_touch=near(b['h'],level) and b['c']<=level
   lside='resistance'
  if not current_touch:continue
  rc=reaction_count(ref,level,lside)
  strength='REPEATED' if rc>=2 else 'WEAK'
  entry=rows[i+1]['o'];exitp=rows[i+HOLD]['o']
  gross=exitp/entry-1 if side=='LONG' else entry/exitp-1
  events.append({'ts':b['ts'],'side':side,'alignment':alignment,'level_side':lside,'prior_reactions':rc,'reaction_strength':strength,'net':gross-COST,'period':'IS' if b['ts']<int(SPLIT.timestamp()) else 'OOS'})
  last=i
 o=[x for x in events if x['period']=='OOS']
 weak=st([x['net'] for x in o if x['reaction_strength']=='WEAK'])
 rep=st([x['net'] for x in o if x['reaction_strength']=='REPEATED'])
 cells={}
 for strength in ['WEAK','REPEATED']:
  z=[x for x in o if x['reaction_strength']==strength]
  cells[strength]={'all':st([x['net'] for x in z]),'with_flow':st([x['net'] for x in z if x['alignment']=='WITH-FLOW']),'counter_flow':st([x['net'] for x in z if x['alignment']=='COUNTER-FLOW'])}
 return {'symbol':symbol,'event_count':len(events),'oos_n':len(o),'weak':weak,'repeated':rep,'cells':cells,'source_files':files}

def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  per=[evaluate(s) for s in SYMBOLS]
 except Exception as e:
  emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 weak_n=rep_n=0;weak_sum=rep_sum=0.0
 for r in per:
  a=r['weak'];b=r['repeated']
  if a['n'] and a['mean'] is not None:weak_n+=a['n'];weak_sum+=a['n']*a['mean']
  if b['n'] and b['mean'] is not None:rep_n+=b['n'];rep_sum+=b['n']*b['mean']
 weak_mean=weak_sum/weak_n if weak_n else None
 rep_mean=rep_sum/rep_n if rep_n else None
 delta=(rep_mean-weak_mean) if weak_mean is not None and rep_mean is not None else None
 if weak_n<15 or rep_n<15:verdict='BLOCKED-EVIDENCE'
 elif delta is not None and abs(delta)>=.0025:verdict='REPEATED-REACTION-CONTEXT-SUPPORTED'
 else:verdict='REPEATED-REACTION-CONTEXT-NOT-SUPPORTED'
 emit(out,'OUTCOME-COMPLETE',
  contract={'symbols':SYMBOLS,'tf':'4h','parent_setup':'frozen trend-pullback + prior 3-bucket aggressive flow','horizontal_level':'prior 60-bar extreme on setup side','touch_tolerance':TOL,'reaction_gap_bars':REACTION_GAP,'reaction_validation_bars':VALIDATE,'min_rebound':MIN_REBOUND,'repeated_definition':'at least 2 prior validated reactions; current setup bar must touch/reject same level','split':'2025-01-01','cost':COST,'parameter_tuning':False,'support_rule':'pooled WEAK and REPEATED each n>=15 and absolute mean-return delta >=25bps'},
  per_symbol=per,pooled={'weak_n':weak_n,'repeated_n':rep_n,'weak_mean':weak_mean,'repeated_mean':rep_mean,'repeated_minus_weak':delta},terminal_verdict=verdict,parameter_tuning=False,
  limitations=['horizontal levels only','4h only','single fixed 60-bar lookback inherited as bounded research choice','does not test sloped trendlines yet','fixed hold/no SL-TP'])

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
