# Outcome Intelligence - systemd deploy runbook

This directory contains repo-tracked systemd units and an env-file
template for running `tools/outcome_intelligence/runtime.py` on an
autonomous daily/weekly cadence. **Nothing here is installed or live
until an operator with VPS access performs the steps below** - the
implementing coding agent does not have VPS/systemd/SSH access and
has not deployed, installed, enabled, or restarted anything.

## Files

| File | Purpose |
|---|---|
| `outcome-intelligence-daily.service` / `.timer` | Captures one new run, then delivers the daily change report to Slack if ≥2 runs exist. Runs 06:00 UTC daily. |
| `outcome-intelligence-weekly.service` / `.timer` | Delivers the weekly persistence report if ≥4 runs exist (`PERSISTENCE_MIN_CONSECUTIVE_RUNS + 1`). Does **not** capture. Runs Monday 06:30 UTC. |
| `outcome-intelligence.env.example` | Template for the env file referenced by `EnvironmentFile=` in both `.service` units. Copy it, fill in real values, do not commit the filled-in copy. |

The units assume `User=ubuntu`, `WorkingDirectory=/home/ubuntu/MarketHunter`,
a venv at `/home/ubuntu/MarketHunter/.venv`, and an env file at
`/home/ubuntu/MarketHunter/deploy/systemd/outcome-intelligence.env` -
this layout was reported via the successor bridge as the actual
production configuration. **This has not been independently verified
by the implementing agent** (no VPS access exists in this session) -
confirm it against the real host, and adjust the units if it differs,
before installing.

Both timers pin `OnCalendar=... UTC` explicitly so the schedule does
not silently shift if the server's local timezone differs from UTC.

## Required secrets/config (see `outcome-intelligence.env.example`)

- `OUTCOME_INTELLIGENCE_API_BASE_URL` - base URL of the authoritative
  local MarketHunter API (daily cycle only). Production value:
  `http://127.0.0.1:8000`.
- `OUTCOME_INTELLIGENCE_SLACK_WEBHOOK_URL` - a Slack Incoming Webhook
  URL for the reporting channel (both cycles). **If an approved Slack
  webhook already exists for this MarketHunter deployment, reuse its
  value here instead of creating a new one** - the implementing agent
  has no VPS read access and could not check for one.
- `OUTCOME_INTELLIGENCE_OUTPUT_DIR` - optional, defaults to
  `data/outcome_intelligence` under `WorkingDirectory=`.

No secret is hardcoded anywhere in this repo. `runtime.py` reads these
three names from the process environment only and fails closed
(exit code 2, logged) if either required variable is missing.

## Install steps (run as an operator with VPS access)

```bash
# 1. Place the env file:
mkdir -p /home/ubuntu/MarketHunter/deploy/systemd
cp deploy/systemd/outcome-intelligence.env.example \
    /home/ubuntu/MarketHunter/deploy/systemd/outcome-intelligence.env
$EDITOR /home/ubuntu/MarketHunter/deploy/systemd/outcome-intelligence.env
chown ubuntu:ubuntu /home/ubuntu/MarketHunter/deploy/systemd/outcome-intelligence.env
chmod 600 /home/ubuntu/MarketHunter/deploy/systemd/outcome-intelligence.env

# 2. Install the units (confirm User=/WorkingDirectory=/paths match the
#    real host first - see the note above):
sudo cp deploy/systemd/outcome-intelligence-daily.service \
        deploy/systemd/outcome-intelligence-daily.timer \
        deploy/systemd/outcome-intelligence-weekly.service \
        deploy/systemd/outcome-intelligence-weekly.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload

# 3. Enable + start the timers (NOT the .service units directly):
sudo systemctl enable --now outcome-intelligence-daily.timer
sudo systemctl enable --now outcome-intelligence-weekly.timer
```

This only touches the two new Outcome Intelligence units - it does
not restart `markethunter-api`, any worker/monitor service, nginx, or
touch the database.

## One-shot manual verification (read-only / safe to run any time)

```bash
# Confirm both timers are scheduled and see next/last run:
systemctl list-timers 'outcome-intelligence-*'

# Trigger one daily cycle immediately, outside its schedule, to verify
# end-to-end wiring (this DOES perform a real capture + Slack post):
sudo systemctl start outcome-intelligence-daily.service
systemctl status outcome-intelligence-daily.service
journalctl -u outcome-intelligence-daily.service -n 50 --no-pager

# Same for weekly:
sudo systemctl start outcome-intelligence-weekly.service
journalctl -u outcome-intelligence-weekly.service -n 50 --no-pager

# Confirm captured run artifacts exist on disk:
ls -la /home/ubuntu/MarketHunter/data/outcome_intelligence/runs/
```

A successful daily/weekly run logs `daily cycle: report delivered` /
`weekly cycle: report delivered` (or an explicit `insufficient
history` info line if not enough runs exist yet - this is expected
warm-up behavior, not a failure) via `journalctl`. Any real failure -
missing env var, unreachable API, Slack delivery error, malformed data
- is logged as an `ERROR` line and the service exits non-zero, which
`systemctl status` reports as `Main PID exited, code=exited,
status=<N>/FAILURE`.

## Definition of done

Once the steps above are performed by an operator:
- `outcome-intelligence-daily.timer` fires once a day at 06:00 UTC,
  unattended, captures a fresh snapshot, and (once ≥2 runs exist)
  posts the daily report to the configured Slack channel.
- `outcome-intelligence-weekly.timer` fires once a week, Monday 06:30
  UTC, unattended, and (once ≥4 runs exist) posts the weekly
  persistence report.
- Both are inspectable via `systemctl status` / `journalctl` at any
  time, with no additional tooling.
