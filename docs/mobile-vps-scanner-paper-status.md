# MarketHunter mobile / VPS Scanner + experimental paper status (2026-09-25)

## User intent
Use MarketHunter from a smartphone. Enable (1) remote manual Binance/WEEX Scanner and
(2) separate autonomous experimental paper simulation based on NEW forward signals.
No Claude Code. Never submit real orders, transfer capital, or reinterpret the
existing Experiment1/Investments ledger. Keep canonical Research strategy code intact.

## Verified at VPS preflight
- Main production checkout SHA at audit: daf93bc (NOT the backup branch HEAD).
- Existing Experiment1 timer: active.
- Existing scanner observations: 96 (US Research-strategy observations).
- Existing manual scanner port 8010: no listener before this deployment.
- Existing scanner Nginx route: missing.
- Nginx auth_basic/auth_request directive search: absent in sampled active config.
  **This is not a complete security review.** Public manual scan control MUST NOT
  be proxied unauthenticated.

## Work on branch feature/mobile-scanner-paper-vps-prep-20260925
Based on backup/mobile-ready-2026-09-24 (b8b2214) rather than master.
- Dashboard Scanner.jsx and ManualScannerPanel.jsx choose localhost:8010 for
  local development; the remote browser uses same-origin /api/manual-scanner.
  This remote route DOES NOT exist yet, so remote use is BLOCKED-INGRESS.
- Separate standalone-manual-scanner.service, bound to 127.0.0.1:8010, own
  directory /home/ubuntu/markethunter-manual-scanner-v1 and own SQLite under
  /home/ubuntu/markethunter-manual-scanner-state.
- An isolated GitHub Actions deployment checks existing prerequisites and
  installs only the new service. Never pulls/reset/restarts the production
  checkout or touches its databases or other systemd units.
- GitHub Actions deployment proof: LOCAL_MANUAL_SCANNER_API=OK, ingress not
  configured, paper trading not installed. The service was tested only with
  local GET /manual-scanner/runs; a real manual scan and mobile browser remain
  unverified.

## Next gates
1. Pick and implement an authenticated, HTTPS smartphone ingress for the scanner
   (or a user-controlled VPN / authenticated tunnel); inspect the real active
   Nginx server location and test access control before allowing POST.
2. Build and test an isolated experimental paper pipeline from
   data/research_strategy_signals.db (READ ONLY), not the standalone manual
   scanner's observations.db. Persist a one-time forward epoch, accept only
   genuinely NEW and post-arming signals and never retroactively count 96 old
   signals. Store virtual balances and fills in an independent new SQLite DB.
3. Supply verified, contemporaneous post-signal quotes and documented
   reference/fill cost model before simulated OPEN/CLOSE. Preserve signal-to-fill
   provenance, idempotency, position limits, stop/target, exits and statistics.
   Research observations alone are not fill quotes. Do not manufacture fills or
   silently promote strategies into the canonical Experiment1 account.
4. Run offline tests and read-only runtime preflight; stage isolated simulation
   before any recurring VPS service. Only then expose paper state read-only in
   UI with a clear EXPERIMENTAL badge.

No paper trades, no public manual Scanner route, and no verified mobile access
are claimed by this document.
