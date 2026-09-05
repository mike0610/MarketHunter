import argparse,json,os,sqlite3,subprocess
from pathlib import Path

OID="STAGE10-AUTOMATION-RUNTIME-REPAIR-001"
EXPECTED_SHA="eac9e629ad31bdfef1a4f65b73360567517984f0"
REPO=Path("/home/ubuntu/MarketHunter")
EXP_ENV=REPO/"deploy/systemd/experiment1-runtime.env"
SCANNER_ENV=REPO/"deploy/systemd/gil-trading-scanner-runtime.env"

def cmd(args, *, check=False, timeout=90):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and p.returncode!=0:
        raise RuntimeError(f"command failed rc={p.returncode}: {args!r}; stderr={p.stderr.strip()}")
    return {"rc":p.returncode,"stdout":p.stdout.strip(),"stderr":p.stderr.strip()}

def sh(script, *, check=False, timeout=90):
    return cmd(["bash","-lc",script],check=check,timeout=timeout)

def unit_show(unit):
    return cmd(["systemctl","show",unit,
        "--property=LoadState,ActiveState,SubState,UnitFileState,Result,ExecMainStatus,NextElapseUSecRealtime,LastTriggerUSec",
        "--no-pager"])

def table_count(db_path, table):
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as c:
        names={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        if table not in names:
            return None
        return c.execute(f"select count(*) from {table}").fetchone()[0]

def write_terminal(out, state, **extra):
    p=Path(out);p.mkdir(parents=True,exist_ok=True)
    payload={"object_id":OID,"terminal_state":state,**extra}
    (p/"terminal_result.json").write_text(json.dumps(payload,sort_keys=True))
    (p/"runtime-repair-evidence.json").write_text(json.dumps(payload,indent=2,sort_keys=True))

def main(job,out):
    evidence={}
    try:
        cmd(["git","-C",str(REPO),"fetch","origin","master"],check=True,timeout=120)
        cmd(["git","-C",str(REPO),"checkout","master"],check=True)
        cmd(["git","-C",str(REPO),"pull","--ff-only","origin","master"],check=True,timeout=120)
        sha=cmd(["git","-C",str(REPO),"rev-parse","HEAD"],check=True)["stdout"]
        evidence["deployed_sha"]=sha
        if sha!=EXPECTED_SHA:
            raise RuntimeError(f"unexpected deployed SHA {sha}; expected {EXPECTED_SHA}")

        # Preserve GIL transport and all other environment. Disable only the
        # obsolete Active-Trading Slack intake. Durable inbox drain remains.
        EXP_ENV.parent.mkdir(parents=True,exist_ok=True)
        EXP_ENV.touch(exist_ok=True)
        lines=EXP_ENV.read_text().splitlines()
        lines=[x for x in lines if not x.startswith("TRADING_SLACK_TRANSPORT_ENABLED=")]
        lines.append("TRADING_SLACK_TRANSPORT_ENABLED=0")
        EXP_ENV.write_text("\n".join(lines)+"\n")
        os.chmod(EXP_ENV,0o600)
        sh(f"sudo chown ubuntu:ubuntu '{EXP_ENV}'",check=True)

        SCANNER_ENV.write_text(
            "TRADING_SCANNER_DB_PATH=/home/ubuntu/MarketHunter/data/trading_scanner.db\n"
            "TRADING_SCANNER_MARKET_DATA_PROVIDER=stooq\n"
            "TRADING_SCANNER_UNIVERSE_SYMBOLS=SPY,QQQ,AAPL,MSFT,NVDA\n"
            "TRADING_SCANNER_MAX_DATA_AGE_SECONDS=345600\n"
        )
        os.chmod(SCANNER_ENV,0o600)
        sh(f"sudo chown ubuntu:ubuntu '{SCANNER_ENV}'",check=True)

        cmd(["sudo","install","-m","0644",
             str(REPO/"deploy/systemd/gil-trading-scanner-runtime.service"),
             "/etc/systemd/system/gil-trading-scanner-runtime.service"],check=True)
        cmd(["sudo","install","-m","0644",
             str(REPO/"deploy/systemd/gil-trading-scanner-runtime.timer"),
             "/etc/systemd/system/gil-trading-scanner-runtime.timer"],check=True)
        cmd(["sudo","systemctl","daemon-reload"],check=True)
        cmd(["sudo","systemctl","enable","--now","gil-trading-scanner-runtime.timer"],check=True)
        cmd(["sudo","systemctl","restart","experiment1-runtime.timer"],check=True)

        # Run each existing cycle once now; no broker/live execution exists.
        cmd(["sudo","systemctl","reset-failed","gil-trading-scanner-runtime.service"])
        scanner_start=cmd(["sudo","systemctl","start","gil-trading-scanner-runtime.service"],timeout=180)
        evidence["scanner_start"]=scanner_start
        evidence["scanner_unit"]=unit_show("gil-trading-scanner-runtime.service")
        evidence["scanner_timer"]=unit_show("gil-trading-scanner-runtime.timer")
        evidence["scanner_journal"]=cmd(["journalctl","-u","gil-trading-scanner-runtime.service","-n","80","--no-pager","-o","short-iso"])

        cmd(["sudo","systemctl","reset-failed","experiment1-runtime.service"])
        experiment_start=cmd(["sudo","systemctl","start","experiment1-runtime.service"],timeout=180)
        evidence["experiment_start"]=experiment_start
        evidence["experiment_unit"]=unit_show("experiment1-runtime.service")
        evidence["experiment_timer"]=unit_show("experiment1-runtime.timer")
        evidence["experiment_journal"]=cmd(["journalctl","-u","experiment1-runtime.service","-n","100","--no-pager","-o","short-iso"])

        evidence["crypto_timer"]=unit_show("crypto-paper-observer.timer")
        evidence["scanner_candidates"]=table_count(REPO/"data/trading_scanner.db","trading_scanner_candidates")
        evidence["scanner_cycles"]=table_count(REPO/"data/trading_scanner.db","trading_scanner_scan_cycles")
        evidence["experiment_intents"]=table_count(REPO/"data/experiment1.db","experiment1_intents")
        evidence["experiment_fills"]=table_count(REPO/"data/experiment1.db","experiment1_fills")

        scanner_ok=(scanner_start["rc"]==0 and "Result=success" in evidence["scanner_unit"]["stdout"])
        experiment_ok=(experiment_start["rc"]==0 and "Result=success" in evidence["experiment_unit"]["stdout"])
        scanner_timer_ok=("ActiveState=active" in evidence["scanner_timer"]["stdout"] and "UnitFileState=enabled" in evidence["scanner_timer"]["stdout"])
        experiment_timer_ok=("ActiveState=active" in evidence["experiment_timer"]["stdout"] and "UnitFileState=enabled" in evidence["experiment_timer"]["stdout"])
        crypto_ok="ActiveState=active" in evidence["crypto_timer"]["stdout"]
        no_trading_slack_failure="not_in_channel" not in evidence["experiment_journal"]["stdout"].splitlines()[-30:]

        if all((scanner_ok,experiment_ok,scanner_timer_ok,experiment_timer_ok,crypto_ok,no_trading_slack_failure)):
            write_terminal(out,"PASS",
                verdict="AUTOMATION_RUNTIME_REPAIRED",
                evidence=evidence,
                broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
        else:
            write_terminal(out,"BLOCKED-RUNTIME",
                reason="post-repair verification failed",
                checks={
                    "scanner_service":scanner_ok,
                    "experiment_service":experiment_ok,
                    "scanner_timer":scanner_timer_ok,
                    "experiment_timer":experiment_timer_ok,
                    "crypto_timer_preserved":crypto_ok,
                    "trading_slack_failure_absent":no_trading_slack_failure,
                },
                evidence=evidence,
                broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")
    except Exception as exc:
        write_terminal(out,"BLOCKED-RUNTIME",reason=repr(exc),evidence=evidence,
            broker_execution="ZERO",ibkr="ZERO",live_money="ZERO")

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--job",required=True);ap.add_argument("--output",required=True)
    a=ap.parse_args();main(a.job,a.output)
