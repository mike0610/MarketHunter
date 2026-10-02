# Losing strategy disposition | 2026-09-24

Research decision only. This document does not change strategy registration, production runtime, or live/paper execution.

## VolumeConfirmedBreakout: ARCHIVE FROM PROMOTION / NEW PAPER ALLOCATION

Evidence: latest available Research snapshot captured 2026-09-24 04:57:39 UTC: 33 completed, 8 wins, 21 losses, 4 breakeven, net -74.14814536128915 USDT. This is a small, historically selected sample, not a population performance estimate.

Historical replay: GitHub Actions run 35971074609, research/volume-breakout-empirical-run at 1fea0b309b9ff3a48e7e1f7c8104c7dc0c782d3d. Revised entry filters, 10 symbols × spot/futures × 1h, next-candle open, nonoverlapping positions, $100 notional, 4 bps fees plus 2 bps slippage each side, 70/30 chronological split: DEV 1119 trades net -360.4047222988345; OOS 387 trades net +47.49849431396487. Quarterly revised DEV: 2025-Q4 -158.19679309851276, 2026-Q1 -101.3311587802355, 2026-Q2 -100.87677042008627; OOS 2026-Q2 -11.266454766964696, 2026-Q3 +58.76494908092957. Positive aggregate OOS is insufficient to establish durable edge because performance is regime-dependent, the historical sampling window slides with run date, and LIVE_* historical exits cannot be reproduced from the current research monitor.

Disposition: do not promote, allocate fresh simulated capital, or claim profitability on this evidence. Preserve strategy code, tests and historical results for retest. This is a research archive recommendation, NOT a claim that the production scanner has been disabled.

Reopen only with: frozen dated candle set and provenance/hash, replay of the same strategy version, matching spot/futures and symbol universe, costs, realistic fills and gap assumptions, independent forward period with positive net P&L and risk behavior, and documented explanation of LIVE_* historical exit provenance. If these conditions are not met, retain archive disposition.

## TrendPullback: BLOCKED-EVIDENCE / NO PROMOTION; next validation target

Latest snapshot: 43 clean terminal trades, 8 positive, 28 negative, 7 zero, net -62.09164344655106 USDT. Eleven closed stop-exit trades are tagged negative despite nonnegative realized profit_percent; correcting these tags changes group statistics, NOT net P&L. Several losing trades recorded positive maximum favorable excursion; OHLC extrema alone cannot prove a realizable earlier exit or a profitable trailing stop.

Do not tune exits to the 43 observed outcomes. First reproduce entry and exit semantics and LIVE_* provenance, then run a frozen chronological baseline with identical costs, spot/futures separation, 1h/1d separation, nonoverlapping fills and independent OOS. Evaluate one predeclared modification only after baseline; archive from promotion if independent evidence remains negative or execution cannot be reproduced.

## Boundary

No automatic production mutation, strategy deletion, paper-position closure, broker action or capital allocation. These decisions require separate runtime routing. Outcome classification PR #234 is a separate data-integrity repair, not a strategy fix.
