import argparse,csv,hashlib,io,json,math,urllib.parse,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path
OBJECT_ID='SL-VAL-QUIET-RV-COST-HEADROOM-001';PARENT='SL-VAL-QUIET-RV-FUTURES-REALISM-001';ASSETS=['BTCUSDT','ETHUSDT','BNBUSDT','ADAUSDT','XRPUSDT','DOGEUSDT','LINKUSDT','LTCUSDT'];TF='4h'
WARM=datetime(2022,1,1,tzinfo=timezone.utc);START=datetime(2022,7,1,tzinfo=timezone.utc);SPLIT=datetime(2025,1,1,tzinfo=timezone.utc);END=datetime(2026,8,1,tzinfo=timezone.utc);VOL_WIN=42;VOL_LOOK=540;VOL_Q=.30;DEV_WIN=42;DEV_LOOK=540;DEV_Q=.90;HOLD=6;DECLUSTER=6;COSTS=[.001,.002,.003,.004,.005]
def emit(o,s,**x):p=Path(o);p.mkdir(parents=True,exist_ok=True);(p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':s,**x},indent=2,sort_keys=True))
def get(u):return urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MarketHunter-Research/1.0'}),timeout=30).read()
def funding(sym):
 rows=[];cur=int(WARM.timestamp()*1000);end=int(END.timestamp()*1000)
 while cur<end:
  q=urllib.parse.urlencode({'symbol':sym,'startTime':cur,'endTime':end,'limit':1000});a=json.loads(get('https://fapi.binance.com/fapi/v1/fundingRate?'+q).decode())
  if not a:break
  for x in a:
   t=int(x['fundingTime'])//1000
   if int(WARM.timestamp())<=t<int(END.timestamp()):rows.append((t,float(x['fundingRate'])))
  nxt=max(int(x['fundingTime']) for x in a)+1
  if nxt<=cur:break
  cur=nxt
 return dict(rows)
def mon(sym,y,m):
 n=f'{sym}-{TF}-{y}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{TF}/{n}';z=get(u);e=get(u+'.CHECKSUM').decode().split()[0].lower();a=hashlib.sha256(z).hexdigest()
 if e!=a:raise ValueError('checksum '+n)
 r=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  for x in csv.reader(io.TextIOWrapper(q.open([v for v in q.namelist() if not v.endswith('/')][0]))):
   try:raw=int(x[0]);o=float(x[1]);c=float(x[4])
   except:continue
   ts=int(raw/1e6 if raw>10**14 else raw/1e3);r.append((ts,o,c))
 return r
def qtl(a,q):
 s=sorted(a);x=(len(s)-1)*q;lo=int(math.floor(x));hi=int(math.ceil(x));return s[lo] if lo==hi else s[lo]*(hi-x)+s[hi]*(x-lo)
def sd(a):m=sum(a)/len(a);return math.sqrt(sum((x-m)**2 for x in a)/len(a))
def st(a):
 if not a:return {'n':0,'mean':None,'median':None,'hit':None,'pf':None,'cum':None,'max_dd':None}
 s=sorted(a);n=len(a);med=s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2;g=sum(x for x in a if x>0);l=-sum(x for x in a if x<0);eq=pk=1.;dd=0.
 for x in a:eq*=1+x;pk=max(pk,eq);dd=min(dd,eq/pk-1)
 return {'n':n,'mean':sum(a)/n,'median':med,'hit':sum(x>0 for x in a)/n,'pf':g/l if l else None,'cum':eq-1,'max_dd':dd}
def main(out,job):
 try:
  if json.loads(Path(job).read_text()).get('object_id')!=OBJECT_ID:raise ValueError('object')
  data={};F={}
  for sym in ASSETS:
   F[sym]=funding(sym);rows=[]
   for y in range(2022,2027):
    for m in range(1,13):
     d=datetime(y,m,1,tzinfo=timezone.utc)
     if d<WARM or d>=END:continue
     rows+=mon(sym,y,m)
   data[sym]={t:(o,c) for t,o,c in rows}
 except Exception as e:emit(out,'PROVIDER-BLOCKED',reason=repr(e),parameter_tuning=False);return
 common=sorted(set.intersection(*[set(data[s]) for s in ASSETS]));ret={}
 for s in ASSETS:
  c=[data[s][t][1] for t in common];ret[s]=[None]+[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
 market=[None]+[sum(ret[s][i] for s in ASSETS)/len(ASSETS) for i in range(1,len(common))];rv=[None]*len(common);dev={s:[None]*len(common) for s in ASSETS}
 for i in range(VOL_WIN+1,len(common)):
  rv[i]=sd(market[i-VOL_WIN+1:i+1])
  for s in ASSETS:dev[s][i]=sum(ret[s][j]-market[j] for j in range(i-DEV_WIN+1,i+1))
 events=[];last=-10**9
 for i in range(max(VOL_LOOK,DEV_LOOK)+VOL_WIN+1,len(common)-HOLD-1):
  ts=common[i]
  if ts<int(START.timestamp()) or ts>=int(END.timestamp()) or i-last<DECLUSTER:continue
  vh=[x for x in rv[i-VOL_LOOK:i] if x is not None]
  if rv[i]>qtl(vh,VOL_Q):continue
  vals=[abs(dev[s][j]) for j in range(i-DEV_LOOK,i) for s in ASSETS if dev[s][j] is not None];th=qtl(vals,DEV_Q);cand=max(ASSETS,key=lambda s:abs(dev[s][i]))
  if abs(dev[cand][i])<=th:continue
  side='SHORT' if dev[cand][i]>0 else 'LONG';entry_t=common[i+1];exit_t=common[i+HOLD];entry=data[cand][entry_t][0];exitp=data[cand][exit_t][0];price=exitp/entry-1 if side=='LONG' else entry/exitp-1
  fr=sum(rate for t,rate in F[cand].items() if entry_t<t<=exit_t);fund=-fr if side=='LONG' else fr;gross=price+fund
  events.append({'ts':ts,'asset':cand,'side':side,'price':price,'funding':fund,'gross':gross,'period':'IS' if ts<int(SPLIT.timestamp()) else 'OOS'});last=i
 o=[x for x in events if x['period']=='OOS'];gross=[x['gross'] for x in o];baseline=st([x-.001 for x in gross]);parent_ok=baseline['n']==101 and abs(baseline['mean']-0.00335499)<5e-6 and abs((baseline['pf'] or 0)-1.321827)<5e-4
 if not parent_ok:emit(out,'EVIDENCE-FAIL',reason='parent aggregate reproduction mismatch',reproduced_10bps=baseline,parameter_tuning=False);return
 table={};positive={};by_side={};by_asset={}
 for c in COSTS:
  k=f'{int(c*10000)}bps';vals=[x-c for x in gross];table[k]=st(vals);positive[k]=sum(v>0 for v in vals)/len(vals)
  by_side[k]={s:st([x['gross']-c for x in o if x['side']==s]) for s in ['LONG','SHORT']}
  by_asset[k]={a:st([x['gross']-c for x in o if x['asset']==a]) for a in ASSETS}
 avg=sum(gross)/len(gross);p40=table['40bps'];p50=table['50bps'];fragile=(p40['pf'] is not None and p40['pf']<=1) or (p40['mean']<=0) or (p40['max_dd'] is not None and p40['max_dd']<-0.40)
 label='EXECUTION-COST-FRAGILE' if fragile else ('COST-HEADROOM-ROBUST' if p40['mean']>0 and (p40['pf'] or 0)>1 and p50['mean']<0 else 'INSUFFICIENT-DIAGNOSTIC-EVIDENCE')
 observations=[f'Average gross edge headroom is {avg*10000:.2f} bps per OOS event; this is not safe slippage or executable capacity.',f'At 40bps total cost: mean {p40["mean"]*100:.4f}%, PF {p40["pf"]:.4f}, maxDD {p40["max_dd"]*100:.2f}%.',f'At 50bps total cost: mean {p50["mean"]*100:.4f}%, PF {p50["pf"]:.4f}, maxDD {p50["max_dd"]*100:.2f}%.' ]
 emit(out,'OUTCOME-COMPLETE',terminal_diagnostic_label=label,parent=PARENT,parent_reproduction_10bps=baseline,event_count=len(events),oos_event_count=len(o),average_edge_headroom=avg,cost_stats=table,positive_trade_share=positive,by_side=by_side,by_asset=by_asset,oos_mean_price_component=sum(x['price'] for x in o)/len(o),oos_mean_funding_component=sum(x['funding'] for x in o)/len(o),strongest_observations=observations,next_empirical_object='SL-VAL-QUIET-RV-DRAWDOWN-ANATOMY-001',parameter_tuning=False,limitations=['fixed Binance USD-M 8-asset basket','cost stress is total-cost proxy only','no spread/depth/queue/market-impact/fill model','same frozen sample cannot validate a new cost filter'])
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--job',required=True);a.add_argument('--output',required=True);q=a.parse_args();main(q.output,q.job)
