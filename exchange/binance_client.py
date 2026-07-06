from __future__ import annotations

from typing import Any

import httpx

from exchange.endpoints import (
    PING,
    SPOT_BASE_URL,
    SPOT_EXCHANGE_INFO,
)


class BinanceClient:

    def __init__(self, timeout: float = 20.0):

        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "MarketHunter/0.1"
            },
        )

    async def close(self):

        await self.client.aclose()

    async def _get(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:

        response = await self.client.get(
            f"{base_url}{endpoint}",
            params=params,
        )

        response.raise_for_status()

        return response.json()

    async def ping(self) -> bool:

        await self._get(
            SPOT_BASE_URL,
            PING,
        )

        return True

    async def get_spot_symbols(self) -> list[str]:

        data = await self._get(
            SPOT_BASE_URL,
            SPOT_EXCHANGE_INFO,
        )

        symbols = []

        for symbol in data["symbols"]:

            if symbol["status"] != "TRADING":
                continue

            if symbol["quoteAsset"] != "USDT":
                continue

            symbols.append(symbol["symbol"])

        return sorted(symbols)