import argparse, csv, hashlib, io, json, re, sqlite3, urllib.error, urllib.request, zipfile
from datetime import datetime, timezone
from pathlib import Path

BASE = 'https://data.binance.vision/data/futures/um/daily'
DATE = '2023-06-01'
DATASETS = ('bookTicker', 'bookDepth')


def get(url, dest=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'MarketHunter-Research/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if dest is None:
                return r.status, r.read()
            h = hashlib.sha256()
            n = 0
            with open(dest, 'wb') as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk); h.update(chunk); n += len(chunk)
            return r.status, {'sha256': h.hexdigest(), 'bytes': n}
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, repr(e).encode()


def parse_ts(v):
    if v is None or v == '': return None
    try: return float(v)
    except Exception: pass
    try: return datetime.fromisoformat(v.replace('Z', '+00:00')).timestamp() * 1000
    except Exception: return None


def inspect_zip(path, dataset, db_path):
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=OFF')
    conn.execute('PRAGMA synchronous=OFF')
    conn.execute('CREATE TABLE seen (h BLOB PRIMARY KEY) WITHOUT ROWID')
    rows = nonmono = duplicates = impossible = 0
    first_ts = last_ts = prev = None
    headers_seen = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        if not names: raise ValueError('empty zip')
        for member in names:
            with z.open(member) as raw:
                txt = io.TextIOWrapper(raw, encoding='utf-8-sig', errors='strict', newline='')
                rdr = csv.reader(txt)
                try: headers = next(rdr)
                except StopIteration: raise ValueError('empty csv member')
                headers_seen.extend(h for h in headers if h not in headers_seen)
                lower = {h.lower(): i for i, h in enumerate(headers)}
                ts_idx = next((i for i,h in enumerate(headers) if 'time' in h.lower() or 'timestamp' in h.lower()), None)
                def num(row, *names):
                    for n in names:
                        i = lower.get(n)
                        if i is not None and i < len(row) and row[i] != '':
                            try: return float(row[i])
                            except Exception: return None
                    return None
                batch = []
                for row in rdr:
                    rows += 1
                    digest = hashlib.sha256(('\x1f'.join(row)).encode('utf-8')).digest()
                    try:
                        conn.execute('INSERT INTO seen(h) VALUES (?)', (digest,))
                    except sqlite3.IntegrityError:
                        duplicates += 1
                    if rows % 5000 == 0: conn.commit()
                    t = parse_ts(row[ts_idx]) if ts_idx is not None and ts_idx < len(row) else None
                    if t is not None:
                        if first_ts is None: first_ts = t
                        last_ts = t
                        if prev is not None and t < prev: nonmono += 1
                        prev = t
                    if dataset == 'bookTicker':
                        bid = num(row,'bid_price','best_bid_price','bidprice','b')
                        ask = num(row,'ask_price','best_ask_price','askprice','a')
                        bq = num(row,'bid_qty','best_bid_qty','bidqty','bq')
                        aq = num(row,'ask_qty','best_ask_qty','askqty','aq')
                        for x in (bid,ask,bq,aq):
                            if x is not None and x < 0: impossible += 1
                        if bid is not None and ask is not None and bid > ask: impossible += 1
                    else:
                        depth = num(row,'depth'); notional = num(row,'notional')
                        for x in (depth,notional):
                            if x is not None and x < 0: impossible += 1
    conn.commit(); conn.close()
    return {'zip_members': names, 'headers': headers_seen, 'row_count': rows, 'timestamp_first': first_ts, 'timestamp_last': last_ts, 'nonmonotonic_timestamps': nonmono, 'duplicate_rows': duplicates, 'impossible_values': impossible}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--job', required=True); ap.add_argument('--output', required=True); args = ap.parse_args()
    job = json.load(open(args.job)); out = Path(args.output); rawdir = out/'raw'; rawdir.mkdir(parents=True, exist_ok=True)
    records = []; blocked = False; failed = False
    for dataset in DATASETS:
        fn = f'BTCUSDT-{dataset}-{DATE}.zip'; url = f'{BASE}/{dataset}/BTCUSDT/{fn}'; c_url = url + '.CHECKSUM'; dest = rawdir/fn
        status, meta = get(url, dest)
        if status is None or status in (403,451,429,500,502,503,504):
            blocked = True; records.append({'dataset':dataset,'path':url,'http_status':status}); continue
        if status != 200:
            failed = True; records.append({'dataset':dataset,'path':url,'http_status':status}); continue
        c_status, c_data = get(c_url)
        expected = None; checksum_ok = False
        if c_status == 200 and c_data:
            (rawdir/(fn+'.CHECKSUM')).write_bytes(c_data)
            m = re.search(rb'([0-9a-fA-F]{64})', c_data); expected = m.group(1).decode().lower() if m else None
            checksum_ok = expected == meta['sha256'] if expected else False
        if not checksum_ok: failed = True
        rec = {'dataset':dataset,'date':DATE,'path':url,'http_status':status,'byte_count':meta['bytes'],'sha256':meta['sha256'],'checksum_path':c_url,'checksum_http_status':c_status,'checksum_expected_sha256':expected,'checksum_valid':checksum_ok}
        try:
            rec.update(inspect_zip(dest, dataset, out/f'{dataset}-seen.sqlite'))
            if rec['row_count'] == 0 or rec['nonmonotonic_timestamps'] or rec['duplicate_rows'] or rec['impossible_values']:
                failed = True
        except Exception as e:
            rec['parse_error'] = repr(e); failed = True
        records.append(rec)
    manifest = {'object_id':job['object_id'],'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'fixture':DATE,'records':records}
    mp = out/'manifest.json'; mp.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    state = 'BLOCKED-PROVIDER-ACCESS' if blocked else ('TOOLING-FEASIBILITY-FAILED' if failed else 'TOOLING-FEASIBILITY-PASSED')
    result = {'object_id':job['object_id'],'terminal_state':state,'executed_at_utc':datetime.now(timezone.utc).isoformat(),'executor':'vps','fixture':DATE,'manifest_sha256':hashlib.sha256(mp.read_bytes()).hexdigest(),'records':records}
    (out/'terminal_result.json').write_text(json.dumps(result, sort_keys=True, separators=(',',':')))
    print('TERMINAL_STATE='+state)
    print('RESULT='+json.dumps(result, sort_keys=True))

if __name__ == '__main__': main()
