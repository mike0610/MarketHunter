# Experiment 1 paper-runtime - systemd deploy runbook

This directory (alongside `README.md`, the Outcome Intelligence
runbook) contains repo-tracked systemd units for running
`tools/experiment1_runtime/runtime.py` on a recurring cadence. **Nothing
here is installed or live until an operator with VPS access performs
the steps below** - the implementing coding agent does not have
VPS/systemd/SSH access and has not deployed, installed, enabled, or
restarted anything.

## What this cycle does

Each invocation runs one bounded pass over the existing, already-merged
Experiment 1 paper-trading pipeline, in order:

1. **Market fill cycle** (`experiment1.runtime.run_market_cycle`) -
   fresh evidence for every `PENDING` intent, paper-fills what it can.
2. **Protective exit cycle** (`experiment1.lifecycle.run_protective_exit_cycle`)
   - re-checks every `FILLED` intent carrying a stop-loss/take-profit
   against fresh evidence.
3. **Multi-symbol MTM cycle** (`experiment1.mtm.run_mtm_cycle`), once
   per canonical account (Investments Defensive/Balanced/Growth, Spot,
   Futures) - recomputes NAV/equity/unrealized P&L/drawdown from fresh
   marks; a symbol with no fresh evidence falls back to its own cost
   basis and the account-level result is reported
   `PARTIAL_EVIDENCE_FALLBACK`, never silently presented as complete.
4. **GIL-ingestion cycle** (`experiment1.gil_decision.run_gil_ingestion_cycle`)
   - runs with an empty decision batch. No real GIL-decision transport
   (API endpoint, queue, etc.) exists anywhere in this codebase yet, so
   there is nothing to ingest; this step exists only to prove the
   wiring stays safe every cycle, ready for a real transport later.

No new trading/accounting/quote logic is introduced anywhere in this
path - every step above calls an already-merged, already-tested
function unmodified. See `tools/experiment1_runtime/runtime.py`'s own
module docstring and `tests/test_experiment1_runtime_scheduler.py` for
the full contract, including idempotency/restart-safety proof.

## Files

| File | Purpose |
|---|---|
| `experiment1-runtime.service` / `.timer` | Runs one cycle (above) every 5 minutes. |
| `experiment1-runtime.env.example` | Optional template - `EXPERIMENT1_DB_PATH` already defaults sensibly, so most deployments will not need this file at all. |

The unit assumes `User=ubuntu`, `WorkingDirectory=/home/ubuntu/MarketHunter`,
and a venv at `/home/ubuntu/MarketHunter/.venv` - the same layout
reported via the successor bridge and already used by the Outcome
Intelligence units in this same directory, reused here for consistency.
**This has not been independently verified by the implementing agent**
(no VPS access exists in this session) - confirm it against the real
host, and adjust the unit if it differs, before installing.

`OnCalendar=*:0/5` (every 5 minutes) matches the quote-freshness window
`build_quote_source()` uses by default - if that default changes, keep
the timer's cadence at or below it, or evidence will go stale in the
timer's own gap rather than in the network path.

## Install steps (run as an operator with VPS access)

```bash
# 1. (Optional) place the env file only if EXPERIMENT1_DB_PATH needs to
#    differ from its default (data/experiment1.db under WorkingDirectory=):
cp deploy/systemd/experiment1-runtime.env.example \
    /home/ubuntu/MarketHunter/deploy/systemd/experiment1-runtime.env
$EDITOR /home/ubuntu/MarketHunter/deploy/systemd/experiment1-runtime.env

# 2. Install the unit (confirm User=/WorkingDirectory=/paths match the
#    real host first - see the note above):
sudo cp deploy/systemd/experiment1-runtime.service \
        deploy/systemd/experiment1-runtime.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload

# 3. Enable + start the timer (NOT the .service unit directly):
sudo systemctl enable --now experiment1-runtime.timer
```

This only touches the new `experiment1-runtime` unit/timer - it does
not restart `markethunter-api`, any Outcome Intelligence unit, nginx,
or touch the database beyond what `Experiment1Engine` already owns
(`data/experiment1.db` by default).

## One-shot manual verification (safe to run any time - paper only)

```bash
# Confirm the timer is scheduled and see next/last run:
systemctl list-timers 'experiment1-runtime.*'

# Trigger one cycle immediately, outside its schedule, to verify
# end-to-end wiring (this DOES call the real public Binance REST API
# for any currently-open/pending crypto symbol - still paper-only,
# no live orders, no real capital):
sudo systemctl start experiment1-runtime.service
systemctl status experiment1-runtime.service
journalctl -u experiment1-runtime.service -n 50 --no-pager
```

A successful cycle logs one `market fill:` / `protective exit:` /
`mtm:` / `gil ingestion:` summary line each (see `_log_summary` in
`runtime.py`) followed by `experiment1 runtime cycle complete`. Any
real failure is logged with a full traceback via
`logger.exception(...)` and the service exits non-zero, which
`systemctl status` reports as `Main PID exited, code=exited,
status=1/FAILURE`.

## Restart-safety - what to check after a real restart

Because every underlying cycle function is already idempotent and
restart-safe by its own tests (PRs #70, #74, #76, #77), a controlled
`sudo systemctl restart experiment1-runtime.timer` (or a full host
reboot) should never duplicate an intent, fill, position, exit, or MTM
snapshot. To confirm this on the real host, compare
`GET /experiment1/state`'s `cash`/`positions`/`last_equity` for each
account immediately before and after the restart, with no cycle run in
between - they must be byte-for-byte identical.

## Definition of done

Once the steps above are performed by an operator:
- `experiment1-runtime.timer` fires every 5 minutes, unattended, and
  runs the four-step cycle above.
- Inspectable via `systemctl status` / `journalctl` at any time, with
  no additional tooling.
- A restart of the timer/service, or of the host, does not duplicate
  any Experiment1 state (see "Restart-safety" above).
