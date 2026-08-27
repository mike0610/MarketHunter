import argparse,csv,hashlib,io,json,math,urllib.request,zipfile
from datetime import datetime,timezone
from pathlib import Path

OBJECT_ID='SL-VAL-LEVEL-007'
BASE='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d'
START=datetime(2019,1,1,tzinfo=timezone.utc); END=datetime(2022,1,1,tzinfo=timezone.utc)

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
 p=prev['c']; g=10**(math.floor(math.log10(p))-1); step=g*factor; L=nearest_level(p,step)
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

def pass_a(rows):
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

def pass_b(rows):
 # Independent formulation: signed distance to nearest pre-bar level; same frozen close-side and 5-bar rules.
 out=[]; unknown=[]; suppressed=0; last={}
 for i,b in enumerate(rows[1:],start=1):
  if b['ts']<int(START.timestamp()) or b['ts']>=int(END.timestamp()): continue
  p=rows[i-1]['c']
  for factor,name in ((1.0,'PRIMARY'),(0.5,'HALF')):
   step=(10**(math.floor(math.log10(p))-1))*factor; L=nearest_level(p,step); d=p-L
   if abs(d)<1e-12: unknown.append((b['ts'],factor,'PREV_CLOSE_AT_LEVEL')); continue
   if d<0:
    if b['h']<L: continue
    if b['c']==L: unknown.append((b['ts'],factor,'CLOSE_AT_LEVEL')); continue
    direction='UP'; label='POST_CROSS_CONTINUATION' if b['c']>L else 'AT_LEVEL_REFLECTION'
   else:
    if b['l']>L: continue
    if b['c']==L: unknown.append((b['ts'],factor,'CLOSE_AT_LEVEL')); continue
    direction='DOWN'; label='POST_CROSS_CONTINUATION' if b['c']<L else 'AT_LEVEL_REFLECTION'
   e={'ts':b['ts'],'level':round(L,12),'direction':direction,'label':label,'grid':name}
   key=(name,e['level'],direction)
   if key in last and i-last[key]<=5: suppressed+=1; continue
   last[key]=i; out.append(e)
 return out,unknown,suppressed

def main(outdir,job):
 try:
  spec=json.loads(Path(job).read_text());
  if spec.get('object_id')!=OBJECT_ID: raise ValueError('object_id mismatch')
  rows=[]; files=[]
  for y,m in [(2018,12)]+[(y,m) for y in (2019,2020,2021) for m in range(1,13)]:
   rr,meta=load_month(y,m); rows+=rr; files.append(meta)
 except Exception as e:
  emit(outdir,'PROVIDER-BLOCKED',reason=repr(e),outcomes_opened=False); return
 rows=sorted(rows,key=lambda x:x['ts']); ts=[r['ts'] for r in rows]
 if len(ts)!=len(set(ts)) or any(ts[i+1]<=ts[i] for i in range(len(ts)-1)):
  emit(outdir,'CENSUS-FAIL',reason='duplicate_or_nonmonotonic_source',outcomes_opened=False); return
 a,ua,sa=pass_a(rows); b,ub,sb=pass_b(rows)
 same=(a==b and ua==ub and sa==sb)
 census={'contract_version':'LEVEL-007-new-census-v1','scope':'BTCUSDT Spot 1d 2019-01-01..2021-12-31; 2018-12 warmup only','events':a,'unknown':ua,'decluster_suppressions':sa,'files':files,'outcomes_opened':False}
 p=Path(outdir); p.mkdir(parents=True,exist_ok=True); raw=json.dumps(census,sort_keys=True,separators=(',',':'))
 (p/'census.json').write_text(json.dumps(census,indent=2,sort_keys=True),encoding='utf-8')
 counts={}
 for e in a: counts[e['grid']+'|'+e['direction']+'|'+e['label']]=counts.get(e['grid']+'|'+e['direction']+'|'+e['label'],0)+1
 state='CENSUS-PASS' if same else 'CENSUS-FAIL'
 emit(outdir,state,event_count=len(a),unknown_count=len(ua),decluster_suppressions=sa,counts=counts,census_sha256=hashlib.sha256(raw.encode()).hexdigest(),two_pass_exact_agreement=same,file_count=len(files),outcomes_opened=False)

if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--job',required=True); ap.add_argument('--output',required=True); x=ap.parse_args(); main(x.output,x.job)
