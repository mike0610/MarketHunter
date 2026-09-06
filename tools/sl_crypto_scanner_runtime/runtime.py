"""Autonomous SL crypto discovery cycle. Public Binance data only, no execution."""
from __future__ import annotations
import argparse,asyncio,logging,os,sys
from decimal import Decimal
from pathlib import Path

from api.trading_scanner_api import DEFAULT_DB_PATH,ENV_DB_PATH
from experiment1.models import SessionState
from market_data.binance_provider import BinanceDailyProvider
from trading_scanner.gates import LiquidityThresholds
from trading_scanner.market_data_adapter import MarketDataScannerAdapter
from trading_scanner.scan import run_scan_cycle
from trading_scanner.store import TradingScannerStore

logger=logging.getLogger("sl_crypto_scanner_runtime.runtime")
EXIT_OK=0;EXIT_FAILURE=1

def _db()->Path:
    raw=os.getenv(ENV_DB_PATH)
    return Path(raw) if raw else Path(DEFAULT_DB_PATH)

def _thresholds()->LiquidityThresholds:
    return LiquidityThresholds(
        min_last_price=Decimal(os.getenv("SL_CRYPTO_MIN_LAST_PRICE","0.00000001")),
        min_average_daily_dollar_volume=Decimal(os.getenv("SL_CRYPTO_MIN_24H_QUOTE_VOLUME","5000000")),
    )

async def _scan_market(*,futures:bool,store:TradingScannerStore):
    top_n=int(os.getenv("SL_CRYPTO_TOP_N","30"))
    max_age=int(os.getenv("SL_CRYPTO_MAX_DATA_AGE_SECONDS",str(36*3600)))
    source=MarketDataScannerAdapter(
        BinanceDailyProvider(futures=futures,top_n=top_n,max_age_seconds=max_age),
        history_limit=int(os.getenv("SL_CRYPTO_HISTORY_BARS","120")),
    )
    market="futures" if futures else "spot"
    result=await run_scan_cycle(
        source,store,
        scan_cycle_id=f"sl-crypto-{market}:{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}",
        session_state=SessionState.CLOSED,
        liquidity_thresholds=_thresholds(),
        require_regular_session=False,
    )
    logger.info("SL crypto %s scan complete contracts=%d candidates=%d",market,result.contracts_seen,len(result.candidates_recorded))
    return result

def run_once():
    store=TradingScannerStore(_db())
    async def run():
        spot=await _scan_market(futures=False,store=store)
        futures=await _scan_market(futures=True,store=store)
        return spot,futures
    return asyncio.run(run())

def main(argv=None):
    argparse.ArgumentParser(prog="sl-crypto-scanner-runtime").parse_args(argv)
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:run_once()
    except Exception:
        logger.exception("SL crypto scanner failed closed");sys.exit(EXIT_FAILURE)
    sys.exit(EXIT_OK)

if __name__=="__main__":main()
