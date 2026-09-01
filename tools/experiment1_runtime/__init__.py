"""
MarketHunter

tools/experiment1_runtime

The autonomous entry point a systemd timer invokes on a recurring
cadence to run one bounded Experiment 1 paper-trading cycle (see
deploy/systemd/experiment1-runtime.service). This package adds NO new
trading/accounting/quote logic of its own - it only wires together
already-merged, already-tested cycle functions (experiment1.runtime,
experiment1.lifecycle, experiment1.mtm, experiment1.gil_decision) in
sequence, reading configuration from the environment.

Non-goals:
- No GIL decision is ever manufactured here. The GIL-ingestion step
  runs with an empty decision batch until a real GIL-decision transport
  exists elsewhere - this proves the wiring stays safe on every cycle
  with zero decisions, it never invents one to exercise the path.
- No live broker/exchange execution, no real capital.
- No non-crypto quote provider selection or funding/FX invention -
  anything not recognized as a Binance-style crypto pair fails closed
  (WAITING_EVIDENCE), exactly as the existing quote-provider
  abstraction already guarantees.
- No new DB table, schema change, or persistence beyond what
  Experiment1Engine already owns.
"""
