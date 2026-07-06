from exchange.base_client import BaseClient
from exchange.endpoints import (
    PING,
    SPOT_BASE_URL,
    SPOT_EXCHANGE_INFO,
)


class BinanceClient(BaseClient):

    def __init__(self):

        super().__init__(SPOT_BASE_URL)

    async def ping(self):

        await self.get(PING)

        return True

    async def get_spot_symbols(self):

        data = await self.get(SPOT_EXCHANGE_INFO)

        return sorted(
            symbol["symbol"]
            for symbol in data["symbols"]
            if symbol["status"] == "TRADING"
            and symbol["quoteAsset"] == "USDT"
        )