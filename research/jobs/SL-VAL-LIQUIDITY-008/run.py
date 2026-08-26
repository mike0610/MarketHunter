import argparse, csv, hashlib, io, json, re, sys, urllib.request, urllib.error, zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE='https://data.binance.vision/data/futures/um/daily'


def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MarketHunter-Research/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, repr(e).encode()


def sha(b): return hashlib.sha256(b).hexdigest()


def parse_ts(v):
    if v is None or v=='': return None
    try: return float(v)
    except Exception: pass
    try: return datetime.fromisoformat(v.replace('Z','+00:00')).timestamp()*1000
    except Exception: return None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--job',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    job=json.load(open(args.job))
    out=Path(args.output); rawdir=out/'raw'; rawdir.mkdir(parents=True,exist_ok=True)
    manifest={'object_id':job['object_id'],'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'epoch':'2023-06-01..2023-06-30 UTC','objects':[],'summary':{}}
    blocked=False; failed=False
    totals={k:{'files':0,'rows':0,'checksum_failures':0,'missing':0,'parse_failures':0,'nonmonotonic':0,'duplicate_rows':0,'impossible_values':0} for k in ('bookTicker','bookDepth')}

    for day in range(1,31):
        ds=f'2023-06-{day:02d}'
        for dataset in ('bookTicker','bookDepth'):
            fn=f'BTCUSDT-{dataset}-{ds}.zip'
            url=f'{BASE}/{dataset}/BTCUSDT/{fn}'
            c_url=url+'.CHECKSUM'
            status,data=get(url)
            if status is None or status in (403,451,429,500,502,503,504):
                blocked=True
                manifest['objects'].append({'dataset':dataset,'date':ds,'path':url,'http_status':status,'provider_error':data.decode(errors='replace') if data else None})
                continue
            if status!=200:
                totals[dataset]['missing']+=1; failed=True
                manifest['objects'].append({'dataset':dataset,'date':ds,'path':url,'http_status':status})
                continue
            actual=sha(data); (rawdir/fn).write_bytes(data)
            c_status,c_data=get(c_url)
            expected=None; checksum_ok=None
            if c_status==200 and c_data:
                (rawdir/(fn+'.CHECKSUM')).write_bytes(c_data)
                m=re.search(rb'([0-9a-fA-F]{64})',c_data)
                expected=m.group(1).decode().lower() if m else None
                checksum_ok=(expected==actual) if expected else False
                if not checksum_ok: totals[dataset]['checksum_failures']+=1; failed=True
            else:
                failed=True; totals[dataset]['checksum_failures']+=1

            rec={'dataset':dataset,'date':ds,'path':url,'http_status':status,'byte_count':len(data),'sha256':actual,'checksum_path':c_url,'checksum_http_status':c_status,'checksum_expected_sha256':expected,'checksum_valid':checksum_ok}
            try:
                z=zipfile.ZipFile(io.BytesIO(data)); names=[n for n in z.namelist() if not n.endswith('/')]
                if not names: raise ValueError('empty zip')
                rows_count=0; nonmono=0; dup=0; impossible=0; first_ts=None; last_ts=None; seen=set(); headers_seen=[]
                for member in names:
                    blob=z.read(member)
                    rdr=csv.DictReader(io.TextIOWrapper(io.BytesIO(blob),encoding='utf-8-sig',errors='strict',newline=''))
                    headers=rdr.fieldnames or []; headers_seen.extend(h for h in headers if h not in headers_seen)
                    lower={h.lower():h for h in headers}
                    ts_candidates=[h for h in headers if any(k in h.lower() for k in ('time','timestamp'))]
                    ts_col=ts_candidates[0] if ts_candidates else None
                    prev=None
                    for row in rdr:
                        rows_count+=1
                        row_key=tuple(row.get(h,'') for h in headers)
                        if row_key in seen: dup+=1
                        seen.add(row_key)
                        t=parse_ts(row.get(ts_col)) if ts_col else None
                        if t is not None:
                            if first_ts is None:first_ts=t
                            last_ts=t
                            if prev is not None and t<prev: nonmono+=1
                            prev=t
                        def num(*names):
                            for n in names:
                                h=lower.get(n)
                                if h and row.get(h) not in (None,''):
                                    try:return float(row[h])
                                    except Exception:return None
                            return None
                        if dataset=='bookTicker':
                            bid=num('bid_price','best_bid_price','bidprice','b'); ask=num('ask_price','best_ask_price','askprice','a')
                            bq=num('bid_qty','best_bid_qty','bidqty','bq'); aq=num('ask_qty','best_ask_qty','askqty','aq')
                            for x in (bid,ask,bq,aq):
                                if x is not None and x<0: impossible+=1
                            if bid is not None and ask is not None and bid>ask: impossible+=1
                        else:
                            depth=num('depth'); notional=num('notional')
                            for x in (depth,notional):
                                if x is not None and x<0: impossible+=1
                rec.update({'zip_members':names,'headers':headers_seen,'row_count':rows_count,'timestamp_first':first_ts,'timestamp_last':last_ts,'nonmonotonic_timestamps':nonmono,'duplicate_rows':dup,'impossible_values':impossible})
                totals[dataset]['files']+=1; totals[dataset]['rows']+=rows_count; totals[dataset]['nonmonotonic']+=nonmono; totals[dataset]['duplicate_rows']+=dup; totals[dataset]['impossible_values']+=impossible
                if rows_count==0 or nonmono or dup or impossible: failed=True
            except Exception as e:
                rec['parse_error']=repr(e); totals[dataset]['parse_failures']+=1; failed=True
            manifest['objects'].append(rec)

    manifest['summary']=totals
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True))
    state='BLOCKED-PROVIDER-ACCESS' if blocked else ('STRESS-EPOCH-FAILED' if failed else 'STRESS-EPOCH-PASSED')
    terminal={'object_id':job['object_id'],'terminal_state':state,'executed_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'vps','epoch':'2023-06-01..2023-06-30 UTC','summary':totals,'manifest_sha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()}
    (out/'terminal_result.json').write_text(json.dumps(terminal,sort_keys=True,separators=(',',':')))
    print('SUMMARY='+json.dumps(totals,sort_keys=True))
    print('TERMINAL_STATE='+state)

if __name__=='__main__':
    main()
