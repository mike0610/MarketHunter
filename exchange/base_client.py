from __future__ import annotations

from typing import Any

import httpx


class BaseClient:
    """Base async HTTP client."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 20.0,
    ) -> None:

        self.base_url = base_url

        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "MarketHunter/0.1"
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:

        response = await self.client.get(
            f"{self.base_url}{endpoint}",
            params=params,
        )

        response.raise_for_status()

        return response.json()