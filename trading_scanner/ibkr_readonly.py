"""
Read-only IBKR TWS / IB Gateway evidence adapter.

Stage-1 boundary: contract resolution, historical OHLCV and liquidity
evidence only.  This module deliberately exposes no order API.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from trading_scanner.models import CatalystEvidence, IbkrContract, LiquidityContext
from trading_scanner.universe import AsyncIbkrUniverseSource, ContractMarketData


class IbkrReadOnlyError(RuntimeError):
    pass


class IbkrSessionUnavailable(IbkrReadOnlyError):
    pass


class IbkrStaleEvidence(IbkrReadOnlyError):
    pass


class IbkrClient(Protocol):
    async def connect(self, host: str, port: int, client_id: int, *, readonly: bool) -> None: ...
    async def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    async def resolve_contracts(self, symbols: tuple[str, ...]) -> tuple[dict[str, Any], ...]: ...
    async def historical_bars(self, conid: int, *, duration: str, bar_size: str) -> tuple[dict[str, Any], ...]: ...


@dataclass(frozen=True, slots=True)
class IbkrReadOnlyConfig:
    host: str
    port: int
    client_id: int
    symbols: tuple[str, ...]
    max_age_seconds: int = 172800
    pacing_seconds: float = 0.25
    reconnect_attempts: int = 2

    @classmethod
    def from_env(cls) -> "IbkrReadOnlyConfig | None":
        enabled = os.getenv("IBKR_READ_ONLY_ENABLED", "").strip().lower()
        if enabled not in {"1", "true", "yes"}:
            return None
        symbols = tuple(s.strip().upper() for s in os.getenv("IBKR_UNIVERSE_SYMBOLS", "").split(",") if s.strip())
        if not symbols:
            raise IbkrReadOnlyError("IBKR_UNIVERSE_SYMBOLS is required")
        return cls(
            host=os.getenv("IBKR_HOST", "127.0.0.1"),
            port=int(os.getenv("IBKR_PORT", "4002")),
            client_id=int(os.getenv("IBKR_CLIENT_ID", "71")),
            symbols=symbols,
            max_age_seconds=int(os.getenv("IBKR_MAX_AGE_SECONDS", "172800")),
            pacing_seconds=float(os.getenv("IBKR_PACING_SECONDS", "0.25")),
            reconnect_attempts=int(os.getenv("IBKR_RECONNECT_ATTEMPTS", "2")),
        )


class IbkrReadOnlyUniverseSource(AsyncIbkrUniverseSource):
    def __init__(self, client: IbkrClient, config: IbkrReadOnlyConfig):
        self._client = client
        self._config = config
        self._contracts: dict[int, IbkrContract] = {}
        self._bars: dict[int, ContractMarketData] = {}

    async def _ensure_connected(self) -> None:
        if self._client.is_connected():
            return
        last_error: Exception | None = None
        for attempt in range(self._config.reconnect_attempts + 1):
            try:
                await self._client.connect(
                    self._config.host,
                    self._config.port,
                    self._config.client_id,
                    readonly=True,
                )
                if self._client.is_connected():
                    return
            except Exception as exc:
                last_error = exc
            if attempt < self._config.reconnect_attempts:
                await asyncio.sleep(min(2 ** attempt, 4))
        raise IbkrSessionUnavailable("IBKR read-only session unavailable") from last_error

    async def resolve_universe(self) -> tuple[IbkrContract, ...]:
        await self._ensure_connected()
        raw = await self._client.resolve_contracts(self._config.symbols)
        resolved: list[IbkrContract] = []
        for item in raw:
            contract = IbkrContract(
                conid=int(item["conid"]),
                symbol=str(item["symbol"]),
                sec_type=str(item["sec_type"]),
                exchange=str(item["exchange"]),
                currency=str(item["currency"]),
                primary_exchange=item.get("primary_exchange"),
                restricted=bool(item.get("restricted", False)),
            )
            self._contracts[contract.conid] = contract
            resolved.append(contract)
        if not resolved:
            raise IbkrReadOnlyError("IBKR resolved zero contracts")
        return tuple(resolved)

    async def market_data_for(self, contract: IbkrContract) -> ContractMarketData | None:
        await self._ensure_connected()
        if self._config.pacing_seconds:
            await asyncio.sleep(self._config.pacing_seconds)
        raw = await self._client.historical_bars(contract.conid, duration="3 M", bar_size="1 day")
        if not raw:
            return None
        newest = raw[-1]
        observed_at = newest["timestamp"]
        if observed_at.tzinfo is None:
            raise IbkrReadOnlyError("IBKR bar timestamp must be timezone-aware")
        age = (datetime.now(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds()
        if age > self._config.max_age_seconds:
            raise IbkrStaleEvidence(f"IBKR evidence stale by {int(age)} seconds")
        data = ContractMarketData(
            conid=contract.conid,
            closes=tuple(Decimal(str(x["close"])) for x in raw),
            highs=tuple(Decimal(str(x["high"])) for x in raw),
            lows=tuple(Decimal(str(x["low"])) for x in raw),
            volumes=tuple(Decimal(str(x["volume"])) for x in raw),
            observed_at=observed_at,
        )
        self._bars[contract.conid] = data
        return data

    async def liquidity_context_for(self, contract: IbkrContract) -> LiquidityContext | None:
        data = self._bars.get(contract.conid)
        if data is None:
            data = await self.market_data_for(contract)
        if data is None or not data.closes:
            return None
        window = min(20, len(data.closes))
        avg_volume = sum(data.volumes[-window:], Decimal("0")) / Decimal(window)
        last_price = data.closes[-1]
        return LiquidityContext(
            average_daily_volume=avg_volume,
            average_daily_dollar_volume=avg_volume * last_price,
            last_price=last_price,
        )

    async def catalyst_for(self, contract: IbkrContract) -> CatalystEvidence | None:
        return None

    async def close(self) -> None:
        if self._client.is_connected():
            await self._client.disconnect()
