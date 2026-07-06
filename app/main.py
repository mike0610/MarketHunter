import asyncio

from exchange.binance_client import BinanceClient
from utils.logger import logger


async def main():

    logger.info("=" * 60)
    logger.info("MarketHunter started")
    logger.info("=" * 60)

    client = BinanceClient()

    logger.info("Connecting to Binance...")

    ok = await client.ping()

    logger.info(f"Binance API: {ok}")

    symbols = await client.get_spot_symbols()

    logger.info(f"Spot pairs: {len(symbols)}")

    logger.info(symbols[:10])

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())