"""
MarketHunter

trading_scanner/

Module:
GIL Trading Scanner v1 - discovers, classifies, and ranks non-crypto
(US stocks/liquid ETFs) trading setups for GIL's review. This package
NEVER decides LONG/SHORT/WAIT and NEVER creates a paper OrderIntent -
see trading_scanner/scan.py's own docstring for the exact boundary and
tests/test_trading_scanner_boundary.py for the structural proof.
"""

from __future__ import annotations
