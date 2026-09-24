# Experimental paper v1: code-only, NOT deployed or connected

This is a separate simulation prototype. It is not the canonical Experiment1
SPOT/FUTURES paper runtime and is not validated strategy performance. It has
no broker/exchange integration, no real order ability and no network calls.

`forward_gate.py` reads the existing `research_strategy_signals.db` using
SQLite `mode=ro`, saves a one-time arm epoch and records only newly first-seen
forward signals in a distinct sandbox SQLite DB. The 96 pre-existing
observations and repeated detections NEVER become paper entries.

`paper_book.py` is a separate virtual $2,000 LONG-only book. It requires
*injected* genuinely fresh USD quotes observed AFTER the signal. Its
hypothetical risk rules are 0.5% equity at risk, <=20% cash per entry,
<=3 concurrent positions, one per symbol, 1x, 2% stop, 4% target and
minimum 5 bps fees and slippage each side. Actual post-gap quote prices
are used for modeled exits instead of fabricated idealized stop prices.

**Not yet done:** evidence-backed live quote adapter with verified instrument,
venue, currency and trading session; recurring worker; SHORT/Futures;
secure mobile UI/API; full event history; integration and VPS runtime proof.
The paper book cannot autonomously open/close positions from real
MarketHunter observations until those requirements are implemented.
Do not arm or deploy the prototype on VPS prematurely; it must not
write to the production Experiment1 database. The unit tests use synthetic
fixtures, not financial returns.

Offline test command from this folder:
`python -m unittest -v test_forward_gate.py test_paper_book.py`.
