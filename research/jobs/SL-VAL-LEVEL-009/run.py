import argparse,csv,hashlib,io,json,math,statistics,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-LEVEL-009'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
START=datetime(2019,1,1,tzinfo=timezone.utc); END=datetime(2022,1,1,tzinfo=timezone.utc)
PARENT_SHA='9d767934ec1142b1c2b88920098a951bb11bac448ccd0baeacc6ea4545039c8b'
HORIZONS=(1,3,5,10)

def emit(outdir,state,**x):
 p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
 (p/'terminal_result.json').write_text(json.dumps({'object_id':OBJECT_ID,'terminal_state':state,**x},indent=2,sort_keys=True),encoding='utf-8')

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
 with urllib.request.urlopen(req,timeout=30) as r:return r.read()

def load_month(y,m):
 name=f'BTCUSDT-1d-{y}-{m:02d}.zip'; url=f'{BASE}/{name}'
 z=get(url); expected=get(url+'.CHECKSUM').decode().split()[0].lower(); actual=hashlib.sha256(z).hexdigest()
 if expected!=actual: raise ValueError(f'checksum mismatch {name}')
 rows=[]
 with zipfile.ZipFile(io.BytesIO(z)) as q:
  names=[n for n in q.namelist() if not n.endswith('/')]
  if len(names)!=1: raise ValueError(f'zip members {name}: {names}')
  text=io.TextIOWrapper(q.open(names[0]),encoding='utf-8')
  for r in csv.reader(text):
   if not r: continue
   try: raw=int(r[0]); o,h,l,c=map(float,r[1:5])
   except Exception: continue
   ts=raw/1_000_000 if raw>10**14 else raw/1_000
   rows.append({'ts':int(ts),'o':o,'h':h,'l':l,'c':c})
 return rows,{'url':url,'sha256':actual,'rows':len(rows)}

def nearest_level(p,step):
 lo=math.floor(p/step)*step; hi=lo+step
 return lo if (p-lo)<= (hi-p) else hi

def raw_event(prev,bar,factor):
 p=prev['c']; g=10**(math.floor(math.log10(p))-1); L=nearest_level(p,g*factor)
 if abs(p-L)<1e-12:return None,'PREV_CLOSE_AT_LEVEL'
 if p<L:
  direction='UP'
  if bar['h']<L:return None,None
  if bar['c']>L: label='POST_CROSS_CONTINUATION'
  elif bar['c']<L: label='AT_LEVEL_REFLECTION'
  else:return None,'CLOSE_AT_LEVEL'
 else:
  direction='DOWN'
  if bar['l']>L:return None,None
  if bar['c']<L: label='POST_CROSS_CONTINUATION'
  elif bar['c']>L: label='AT_LEVEL_REFLECTION'
  else:return None,'CLOSE_AT_LEVEL'
 return {'ts':bar['ts'],'level':round(L,12),'direction':direction,'label':label,'grid':'PRIMARY' if factor==1 else 'HALF'},None

def census(rows):
 out=[]; unknown=[]; suppressed=0; last={}
 for i in range(1,len(rows)):
  if not (int(START.timestamp())<=rows[i]['ts']<int(END.timestamp())): continue
  for factor in (1.0,0.5):
   e,u=raw_event(rows[i-1],rows[i],factor)
   if u: unknown.append((rows[i]['ts'],factor,u))
   if not e: continue
   key=(e['grid'],e['level'],e['direction']); prev_idx=last.get(key)
   if prev_idx is not None and i-prev_idx<=5: suppressed+=1; continue
   last[key]=i; out.append(e)
 return out,unknown,suppressed

def lagged_rv20(rows):
 rv=[None]*len(rows); rets=[None]+[math.log(rows[i]['c']/rows[i-1]['c']) for i in range(1,len(rows))]
 for i in range(21,len(rows)): rv[i]=statistics.pstdev([rets[j] for j in range(i-20,i)])
 return rv

def trailing_deciles(rv):
 out=[None]*len(rv)
 for i,v in enumerate(rv):
  if v is None: continue
  hist=[x for x in rv[max(0,i-252):i] if x is not None]
  if len(hist)<20: continue
  rank=sum(1 for x in hist if x<=v)/len(hist); out[i]=min(9,max(0,int(math.ceil(rank*10)-1)))
 return out

def direction_convention(prev,factor):
 p=prev['c']; L=nearest_level(p,(10**(math.floor(math.log10(p))-1))*factor)
 if abs(p-L)<1e-12:return None
 return 'UP' if p<L else 'DOWN'

def signed_metrics(rows,i,h,direction):
 if i+h>=len(rows):return None
 c0=rows[i]['c']; s=1.0 if direction=='UP' else -1.0; seg=rows[i+1:i+h+1]
 fwd=s*math.log(rows[i+h]['c']/c0)
 if direction=='UP': mfe=max(math.log(b['h']/c0) for b in seg); mae=min(math.log(b['l']/c0) for b in seg)
 else: mfe=max(math.log(c0/b['l']) for b in seg); mae=min(math.log(c0/b['h']) for b in seg)
 return {'ret':fwd,'mfe':mfe,'mae':mae,'win':1 if fwd>0 else 0}

def mean(xs): return statistics.fmean(xs) if xs else None
def med(xs): return statistics.median(xs) if xs else None

def build_report(rows,events,dec):
 idx={r['ts']:i for i,r in enumerate(rows)}; report={}; pairs_all={}
 for grid,factor in (('PRIMARY',1.0),('HALF',0.5)):
  accepted={e['ts'] for e in events if e['grid']==grid}; candidates=[]
  for i in range(1,len(rows)-10):
   t=rows[i]['ts']; y=datetime.fromtimestamp(t,timezone.utc).year
   if y not in (2019,2020,2021) or t in accepted or dec[i] is None: continue
   d=direction_convention(rows[i-1],factor); e,u=raw_event(rows[i-1],rows[i],factor)
   if d is None or e is not None or u is not None: continue
   candidates.append({'i':i,'ts':t,'year':y,'direction':d,'decile':dec[i]})
  used=set(); pairs=[]; unmatched=[]
  for e in [x for x in events if x['grid']==grid]:
   i=idx[e['ts']]
   if dec[i] is None: unmatched.append({'event':e,'reason':'EVENT_DECILE_UNAVAILABLE'}); continue
   y=datetime.fromtimestamp(e['ts'],timezone.utc).year
   pool=[c for c in candidates if c['year']==y and c['direction']==e['direction'] and c['ts'] not in used]
   if not pool: unmatched.append({'event':e,'reason':'NO_COMPARATOR'}); continue
   pool.sort(key=lambda c:(abs(c['decile']-dec[i]),c['ts'])); c=pool[0]; used.add(c['ts'])
   row={'event':e,'event_decile':dec[i],'control_ts':c['ts'],'control_decile':c['decile'],'horizons':{}}; ok=True
   for h in HORIZONS:
    em=signed_metrics(rows,i,h,e['direction']); cm=signed_metrics(rows,c['i'],h,e['direction'])
    if em is None or cm is None: ok=False; break
    row['horizons'][str(h)]={'event':em,'control':cm,'paired_ret_diff':em['ret']-cm['ret'],'paired_mfe_diff':em['mfe']-cm['mfe'],'paired_mae_diff':em['mae']-cm['mae']}
   if ok:pairs.append(row)
   else: unmatched.append({'event':e,'reason':'HORIZON_UNAVAILABLE'})
  if unmatched:return None,{'grid':grid,'unmatched_count':len(unmatched),'examples':unmatched[:10]}
  stats={}
  for h in HORIZONS:
   hs=[p['horizons'][str(h)] for p in pairs]
   er=[x['event']['ret'] for x in hs]; cr=[x['control']['ret'] for x in hs]
   stats[str(h)]={'n':len(hs),'event_mean_ret':mean(er),'event_median_ret':med(er),'control_mean_ret':mean(cr),'control_median_ret':med(cr),'event_win_fraction':mean([x['event']['win'] for x in hs]),'control_win_fraction':mean([x['control']['win'] for x in hs]),'event_median_mfe':med([x['event']['mfe'] for x in hs]),'control_median_mfe':med([x['control']['mfe'] for x in hs]),'event_median_mae':med([x['event']['mae'] for x in hs]),'control_median_mae':med([x['control']['mae'] for x in hs]),'paired_median_ret_diff':med([x['paired_ret_diff'] for x in hs]),'paired_median_mfe_diff':med([x['paired_mfe_diff'] for x in hs]),'paired_median_mae_diff':med([x['paired_mae_diff'] for x in hs])}
  report[grid]={'n':len(pairs),'stats':stats}; pairs_all[grid]=pairs
 return {'report':report,'pairs':pairs_all},None

def main(outdir,job):
 try:
  spec=json.loads(Path(job).read_text())
  if spec.get('object_id')!=OBJECT_ID or spec.get('parent_census_sha256')!=PARENT_SHA: raise ValueError('job contract mismatch')
  parent_rows=[]; parent_files=[]
  months=[(2018,12)]+[(y,m) for y in (2019,2020,2021) for m in range(1,13)]
  for y,m in months:
   rr,meta=load_month(y,m); parent_rows+=rr; parent_files.append(meta)
 except Exception as e:
  emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),outcomes_opened=False); return
 parent_rows=sorted(parent_rows,key=lambda x:x['ts']); ts=[r['ts'] for r in parent_rows]
 if len(ts)!=len(set(ts)) or any(ts[i+1]<=ts[i] for i in range(len(ts)-1)):
  emit(outdir,'BLOCKED-EVIDENCE',reason='duplicate_or_nonmonotonic_parent_source',outcomes_opened=False); return
 events,unknown,suppressed=census(parent_rows)
 parent={'contract_version':'LEVEL-007-new-census-v1','scope':'BTCUSDT Spot 1d 2019-01-01..2021-12-31; 2018-12 warmup only','events':events,'unknown':unknown,'decluster_suppressions':suppressed,'files':parent_files,'outcomes_opened':False}
 raw=json.dumps(parent,sort_keys=True,separators=(',',':')); sha=hashlib.sha256(raw.encode()).hexdigest()
 if sha!=PARENT_SHA or len(events)!=1391 or len(unknown)!=4 or suppressed!=435:
  emit(outdir,'BLOCKED-EVIDENCE',reason='parent_census_reproduction_mismatch',observed_census_sha256=sha,event_count=len(events),unknown_count=len(unknown),decluster_suppressions=suppressed,parent_file_count=len(parent_files),outcomes_opened=False); return
 try:
  tail,tail_meta=load_month(2022,1)
 except Exception as e:
  emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),parent_census_sha256=sha,outcomes_opened=False); return
 rows=sorted(parent_rows+tail,key=lambda x:x['ts']); rv=lagged_rv20(rows); dec=trailing_deciles(rv)
 result,err=build_report(rows,events,dec)
 if err:
  emit(outdir,'BLOCKED-EVIDENCE',reason='matching_integrity_failure',details=err,parent_census_sha256=sha,outcomes_opened=False); return
 s5=result['report']['PRIMARY']['stats']['5']; s10=result['report']['PRIMARY']['stats']['10']
 support=(s5['paired_median_ret_diff']>0 and s10['paired_median_ret_diff']>0 and s5['event_win_fraction']>s5['control_win_fraction'] and s10['event_win_fraction']>s10['control_win_fraction'] and s5['event_median_mae']>=s5['control_median_mae'] and s10['event_median_mae']>=s10['control_median_mae'])
 state='LEVEL-FORWARD-SUPPORT' if support else 'LEVEL-FORWARD-NO-SUPPORT'
 p=Path(outdir); p.mkdir(parents=True,exist_ok=True)
 (p/'level_forward_report.json').write_text(json.dumps(result['report'],indent=2,sort_keys=True),encoding='utf-8')
 (p/'pairs.json').write_text(json.dumps(result['pairs'],indent=2,sort_keys=True),encoding='utf-8')
 emit(outdir,state,parent_census_sha256=sha,event_count=len(events),parent_file_count=len(parent_files),tail_file=tail_meta,primary_n=result['report']['PRIMARY']['n'],half_n=result['report']['HALF']['n'],primary_5d=s5,primary_10d=s10,half_5d=result['report']['HALF']['stats']['5'],half_10d=result['report']['HALF']['stats']['10'],interpretation_rule='PRIMARY only; HALF sensitivity cannot rescue',outcomes_opened=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); x=ap.parse_args(); main(x.output,x.job)
