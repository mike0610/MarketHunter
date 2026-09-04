from __future__ import annotations

import hashlib

from market_data.foundation import AsyncMarketDataProvider, MarketDataError, MarketInstrument
from trading_scanner.models import CatalystEvidence, IbkrContract, LiquidityContext
from trading_scanner.universe import AsyncIbkrUniverseSource, ContractMarketData


class MarketDataScannerAdapter(AsyncIbkrUniverseSource):
    """
    Compatibility bridge from the broker-independent Stage-1 evidence
    boundary into the existing scanner. It has no execution capability.
    """

    def __init__(self, provider: AsyncMarketDataProvider, *, history_limit: int = 120) -> None:
        self._provider = provider
        self._history_limit = history_limit
        self._instruments: dict[int, MarketInstrument] = {}

    @staticmethod
    def _synthetic_scanner_id(instrument: MarketInstrument) -> int:
        # Scanner identity only, never a broker conid. Stable across restarts.
        raw = "|".join(
            (instrument.symbol, instrument.asset_class, instrument.currency, instrument.exchange or "")
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") & 0x7FFFFFFFFFFFFFFF

    async def resolve_universe(self) -> tuple[IbkrContract, ...]:
        instruments = await self._provider.universe()
        contracts: list[IbkrContract] = []
        for instrument in instruments:
            scanner_id = self._synthetic_scanner_id(instrument)
            self._instruments[scanner_id] = instrument
            contracts.append(
                IbkrContract(
                    conid=scanner_id,
                    symbol=instrument.symbol,
                    sec_type="STK",
                    exchange=instrument.exchange or "MARKET_DATA",
                    currency=instrument.currency,
                    primary_exchange=instrument.exchange,
                    restricted=False,
                )
            )
        return tuple(contracts)

    def _instrument(self, contract: IbkrContract) -> MarketInstrument:
        instrument = self._instruments.get(contract.conid)
        if instrument is None:
            raise MarketDataError(f"unknown scanner contract id {contract.conid}")
        return instrument

    async def market_data_for(self, contract: IbkrContract) -> ContractMarketData | None:
        instrument = self._instrument(contract)
        series = await self._provider.history(
            instrument, timeframe="1d", limit=self._history_limit
        )
        return ContractMarketData(
            conid=contract.conid,
            closes=tuple(bar.close for bar in series.bars),
            highs=tuple(bar.high for bar in series.bars),
            lows=tuple(bar.low for bar in series.bars),
            volumes=tuple(bar.volume for bar in series.bars),
            observed_at=series.observed_at,
        )

    async def liquidity_context_for(self, contract: IbkrContract) -> LiquidityContext | None:
        evidence = await self._provider.liquidity(self._instrument(contract))
        return LiquidityContext(
            average_daily_volume=evidence.average_daily_volume,
            average_daily_dollar_volume=evidence.average_daily_dollar_volume,
            last_price=evidence.last_price,
        )

    async def catalyst_for(self, contract: IbkrContract) -> CatalystEvidence | None:
        # Stage 1 has no governed catalyst/news provider. Never fabricate one.
        return None
