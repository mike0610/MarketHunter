from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal

from exchange.binance_client import BinanceClient
from market_data.foundation import (
    AsyncMarketDataProvider,LiquidityEvidence,MarketBar,MarketDataStale,
    MarketDataUnavailable,MarketInstrument,MarketSeries,
)

class BinanceDailyProvider(AsyncMarketDataProvider):
    """Read-only Binance daily OHLCV provider for SL crypto discovery.

    Universe is bounded to the most liquid active USDT markets by provider-reported
    24h quote volume. Spot and perpetual futures are distinct provider instances.
    No orders, accounts, keys, or private endpoints are used.
    """

    PROVIDER="BINANCE_PUBLIC_REST"

    def __init__(self,*,futures:bool=False,top_n:int=30,max_age_seconds:int=36*3600,client:BinanceClient|None=None):
        if top_n<=0: raise ValueError("top_n must be positive")
        if max_age_seconds<=0: raise ValueError("max_age_seconds must be positive")
        self._futures=futures;self._top_n=top_n;self._max_age_seconds=max_age_seconds
        self._client=client or BinanceClient();self._ticker:dict[str,dict]={};self._cache:dict[str,MarketSeries]={}

    @property
    def asset_class(self)->str:
        return "CRYPTO_FUTURES" if self._futures else "CRYPTO_SPOT"

    async def _refresh_tickers(self)->None:
        rows=await (self._client.get_futures_ticker_24h() if self._futures else self._client.get_ticker_24h())
        self._ticker={str(r.get("symbol","")).upper():r for r in rows if isinstance(r,dict) and r.get("symbol")}

    async def universe(self)->tuple[MarketInstrument,...]:
        symbols=set(await (self._client.get_futures_symbols() if self._futures else self._client.get_spot_symbols()))
        await self._refresh_tickers()
        ranked=[]
        for symbol in symbols:
            row=self._ticker.get(symbol)
            if not row: continue
            try:qv=Decimal(str(row.get("quoteVolume","0")))
            except Exception:continue
            if qv<=0:continue
            ranked.append((qv,symbol))
        ranked.sort(reverse=True)
        return tuple(MarketInstrument(symbol=s,asset_class=self.asset_class,currency="USDT",exchange="BINANCE") for _,s in ranked[:self._top_n])

    async def history(self,instrument:MarketInstrument,*,timeframe:str="1d",limit:int=120)->MarketSeries:
        if timeframe!="1d": raise MarketDataUnavailable("SL Binance scanner currently supports 1d only")
        if limit<=0: raise ValueError("limit must be positive")
        candles=await self._client.get_klines(instrument.symbol,interval="1d",limit=limit+1,futures=self._futures)
        now=datetime.now(timezone.utc)
        closed=[x for x in candles if x.close_time<=now]
        if not closed: raise MarketDataUnavailable(f"no closed Binance history for {instrument.symbol}")
        bars=tuple(MarketBar(
            timestamp=x.close_time,open=Decimal(str(x.open)),high=Decimal(str(x.high)),
            low=Decimal(str(x.low)),close=Decimal(str(x.close)),volume=Decimal(str(x.volume))
        ) for x in closed[-limit:])
        newest=bars[-1].timestamp;age=(now-newest).total_seconds()
        if age<0 or age>self._max_age_seconds:
            raise MarketDataStale(f"{instrument.symbol} Binance daily evidence age={int(age)}s exceeds max={self._max_age_seconds}s")
        market="futures" if self._futures else "spot"
        series=MarketSeries(instrument,"1d",bars,self.PROVIDER,f"binance:{market}:klines:{instrument.symbol}:1d",newest,now)
        self._cache[instrument.symbol]=series
        return series

    async def liquidity(self,instrument:MarketInstrument)->LiquidityEvidence:
        if not self._ticker: await self._refresh_tickers()
        row=self._ticker.get(instrument.symbol)
        if row is None: raise MarketDataUnavailable(f"no Binance 24h ticker for {instrument.symbol}")
        try:
            quote_volume=Decimal(str(row["quoteVolume"]));last=Decimal(str(row["lastPrice"]))
        except (KeyError,ValueError,TypeError) as exc:
            raise MarketDataUnavailable(f"invalid Binance 24h ticker for {instrument.symbol}") from exc
        if quote_volume<0 or last<=0: raise MarketDataUnavailable(f"invalid Binance liquidity values for {instrument.symbol}")
        # quoteVolume is provider-reported rolling 24h notional. Convert to an
        # explainable base-volume equivalent only for the scanner's existing shape.
        base_volume=quote_volume/last if last>0 else Decimal("0")
        now=datetime.now(timezone.utc)
        market="futures" if self._futures else "spot"
        return LiquidityEvidence(instrument,base_volume,quote_volume,last,self.PROVIDER,now,f"binance:{market}:ticker24h:{instrument.symbol}")
