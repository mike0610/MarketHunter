"""
MarketHunter

Module:
Market Data Service

Responsibilities:
- Load Spot and Futures symbol metadata.
- Select liquid USDT perpetual Futures contracts.
- Load OHLCV candles from Binance.
"""

from __future__ import annotations

import asyncio

from exchange.binance_client import BinanceClient
from models.candle import Candle
from models.market_symbol import MarketSymbol


STABLECOIN_BASE_ASSETS = frozenset(
    {
        "USD1",
        "USDC",
        "RLUSD",
        "BFUSD",
        "FDUSD",
        "TUSD",
        "BUSD",
        "DAI",
        "USDP",
        "USDS",
        "USDE",
        "USDD",
        "PYUSD",
        "GUSD",
        "LUSD",
        "FRAX",
        "USTC",
        "EUR",
        "EURI",
        "AEUR",
        "EURC",
        "XUSD",
    }
)

BLOCKED_SYMBOLS = frozenset(
    {
        "USD1USDT",
        "USDCUSDT",
        "RLUSDUSDT",
        "BFUSDUSDT",
        "FDUSDUSDT",
        "TUSDUSDT",
        "BUSDUSDT",
        "DAIUSDT",
        "USDPUSDT",
        "USDSUSDT",
        "USDEUSDT",
        "USDDUSDT",
        "PYUSDUSDT",
        "GUSDUSDT",
        "LUSDUSDT",
        "FRAXUSDT",
        "USTCUSDT",
        "EURUSDT",
        "EURIUSDT",
        "AEURUSDT",
        "EURCUSDT",
        "XUSDUSDT",
    }
)


ALLOWED_SPOT_QUOTE_ASSETS = frozenset(
    {
        "USDT",
        "BTC",
        "ETH",
        "BNB",
    }
)

SPOT_QUOTE_TO_USDT_SYMBOL = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "BNB": "BNBUSDT",
}


BLOCKED_SPOT_PROXY_BASE_ASSETS = frozenset(
    {
        "WBTC",
        "WBETH",
        "BNSOL",
    }
)


def is_stock_like_spot_base_asset(
    base_asset: str,
) -> bool:
    """
    Detect Binance spot stock/proxy-like tickers such as NVDAB, TSLAB, MSTRB.
    """

    normalized_base = str(base_asset or "").upper()

    return (
        len(normalized_base) > 3
        and normalized_base.endswith("B")
    )


def is_blocked_spot_proxy_base_asset(
    base_asset: str,
) -> bool:
    """
    Block wrapped/staking/proxy assets that duplicate major exposure.
    """

    normalized_base = str(base_asset or "").upper()

    return (
        normalized_base in BLOCKED_SPOT_PROXY_BASE_ASSETS
        or is_stock_like_spot_base_asset(normalized_base)
    )


def is_allowed_spot_quote_asset(
    quote_asset: str,
) -> bool:
    """
    Return True when Spot quote asset is allowed for scanning.
    """

    return str(quote_asset or "").upper() in ALLOWED_SPOT_QUOTE_ASSETS


def convert_spot_quote_volume_to_usdt(
    quote_asset: str,
    quote_volume: float,
    last_price_by_symbol: dict[str, float],
) -> float:
    """
    Convert Binance Spot quoteVolume to approximate USDT volume.
    """

    normalized_quote = str(quote_asset or "").upper()

    if normalized_quote == "USDT":
        return quote_volume

    conversion_symbol = SPOT_QUOTE_TO_USDT_SYMBOL.get(
        normalized_quote,
    )

    if not conversion_symbol:
        return 0.0

    conversion_price = last_price_by_symbol.get(
        conversion_symbol,
        0.0,
    )

    if conversion_price <= 0:
        return 0.0

    return quote_volume * conversion_price


def is_blocked_market_symbol(
    symbol: str,
    base_asset: str,
    quote_asset: str,
) -> bool:
    """
    Return True for stablecoin, fiat-like and explicitly blocked USDT pairs.
    """

    normalized_symbol = str(symbol or "").upper()
    normalized_base = str(base_asset or "").upper()

    return (
        normalized_symbol in BLOCKED_SYMBOLS
        or normalized_base in STABLECOIN_BASE_ASSETS
        or is_blocked_spot_proxy_base_asset(normalized_base)
    )


FUTURES_BASE_MULTIPLIERS = (
    "1000000",
    "100000",
    "10000",
    "1000",
    "1M",
)


def normalize_underlying_base_asset(
    base_asset: str,
) -> str:
    """
    Normalize Binance futures multiplier contracts to their underlying asset.

    Examples:
    - 1000PEPE -> PEPE
    - 1000SHIB -> SHIB
    - 1MBABYDOGE -> BABYDOGE
    """

    normalized = str(base_asset or "").upper()

    for prefix in FUTURES_BASE_MULTIPLIERS:
        if normalized.startswith(prefix) and len(normalized) > len(prefix):
            return normalized[len(prefix):]

    return normalized


def collect_futures_underlying_assets(
    futures_symbols: list[dict],
) -> set[str]:
    """
    Return normalized base assets available as active USDT perpetual futures.
    """

    assets: set[str] = set()

    for item in futures_symbols:
        if item.get("status") != "TRADING":
            continue

        if item.get("quoteAsset") != "USDT":
            continue

        if item.get("contractType") != "PERPETUAL":
            continue

        symbol_name = str(item.get("symbol", ""))
        base_asset = str(item.get("baseAsset", ""))
        quote_asset = str(item.get("quoteAsset", ""))

        if not symbol_name or not base_asset:
            continue

        if is_blocked_market_symbol(
            symbol=symbol_name,
            base_asset=base_asset,
            quote_asset=quote_asset,
        ):
            continue

        assets.add(
            normalize_underlying_base_asset(base_asset),
        )

    return assets


def is_spot_duplicate_of_futures(
    base_asset: str,
    futures_underlying_assets: set[str],
) -> bool:
    """
    Return True when a Spot asset already exists in the Futures universe.
    """

    normalized_base = normalize_underlying_base_asset(base_asset)

    return normalized_base in futures_underlying_assets


class MarketDataService:
    """
    Service for loading public market data from Binance.
    """

    def __init__(
        self,
        client: BinanceClient | None = None,
    ) -> None:
        self.client = client or BinanceClient()

    async def ping(self) -> bool:
        """
        Check Binance API availability.
        """

        return await self.client.ping()

    async def load_symbols(self) -> list[MarketSymbol]:
        """
        Load all active Spot and Futures USDT symbols.

        This method keeps the broad universe available for future use.
        Scanner should normally use load_liquid_futures_symbols().
        """

        symbols: list[MarketSymbol] = []

        spot_info, futures_info = await asyncio.gather(
            self.client.get(
                "/api/v3/exchangeInfo",
            ),
            self.client.get_futures_exchange_info(),
        )

        futures_underlying_assets = collect_futures_underlying_assets(
            futures_info["symbols"],
        )

        for item in spot_info["symbols"]:
            if item["status"] != "TRADING":
                continue

            symbol_name = str(item.get("symbol", ""))
            base_asset = str(item.get("baseAsset", ""))
            quote_asset = str(item.get("quoteAsset", ""))

            if not is_allowed_spot_quote_asset(
                quote_asset,
            ):
                continue

            if is_blocked_market_symbol(
                symbol=symbol_name,
                base_asset=base_asset,
                quote_asset=quote_asset,
            ):
                continue

            if is_spot_duplicate_of_futures(
                base_asset=base_asset,
                futures_underlying_assets=futures_underlying_assets,
            ):
                continue

            symbols.append(
                MarketSymbol(
                    symbol=symbol_name,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    market="spot",
                )
            )

        for item in futures_info["symbols"]:
            if item["status"] != "TRADING":
                continue

            symbol_name = str(item.get("symbol", ""))
            base_asset = str(item.get("baseAsset", ""))
            quote_asset = str(item.get("quoteAsset", ""))

            if quote_asset != "USDT":
                continue

            if is_blocked_market_symbol(
                symbol=symbol_name,
                base_asset=base_asset,
                quote_asset=quote_asset,
            ):
                continue

            symbols.append(
                MarketSymbol(
                    symbol=symbol_name,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    market="futures",
                )
            )

        return sorted(
            symbols,
            key=lambda item: (
                item.market,
                item.symbol,
            ),
        )

    async def load_liquid_symbols(
        self,
        market: str,
        min_quote_volume_usdt: float,
        max_symbols: int | None = None,
    ) -> list[MarketSymbol]:
        """
        Return liquid symbols for the requested market.
        """

        normalized_market = str(market or "").strip().lower()

        if normalized_market == "futures":
            return await self.load_liquid_futures_symbols(
                min_quote_volume_usdt=min_quote_volume_usdt,
                max_symbols=max_symbols,
            )

        if normalized_market == "spot":
            return await self.load_liquid_spot_symbols(
                min_quote_volume_usdt=min_quote_volume_usdt,
                max_symbols=max_symbols,
            )

        raise ValueError(
            f"Unsupported market: {market}"
        )

    async def load_liquid_spot_symbols(
        self,
        min_quote_volume_usdt: float,
        max_symbols: int | None = None,
    ) -> list[MarketSymbol]:
        """
        Return liquid Spot USDT symbols that do not duplicate Futures.

        Stablecoin / fiat-like pairs are excluded. Spot assets that already
        exist as USDT perpetual Futures are excluded as well.
        """

        if min_quote_volume_usdt <= 0:
            raise ValueError(
                "Minimum quote volume must be greater than zero."
            )

        if max_symbols is not None and max_symbols <= 0:
            raise ValueError(
                "Maximum symbol count must be greater than zero."
            )

        spot_info, tickers, futures_info = await asyncio.gather(
            self.client.get(
                "/api/v3/exchangeInfo",
            ),
            self.client.get(
                "/api/v3/ticker/24hr",
            ),
            self.client.get_futures_exchange_info(),
        )

        futures_underlying_assets = collect_futures_underlying_assets(
            futures_info["symbols"],
        )

        quote_volume_by_symbol = {
            str(item.get("symbol", "")): self._to_float(
                item.get("quoteVolume", 0.0)
            )
            for item in tickers
        }

        last_price_by_symbol = {
            str(item.get("symbol", "")): self._to_float(
                item.get("lastPrice", 0.0)
            )
            for item in tickers
        }

        liquid_symbols: list[tuple[MarketSymbol, float]] = []

        for item in spot_info["symbols"]:
            if item.get("status") != "TRADING":
                continue

            symbol_name = str(item.get("symbol", ""))
            base_asset = str(item.get("baseAsset", ""))
            quote_asset = str(item.get("quoteAsset", ""))

            if not is_allowed_spot_quote_asset(
                quote_asset,
            ):
                continue

            if not symbol_name:
                continue

            if is_blocked_market_symbol(
                symbol=symbol_name,
                base_asset=base_asset,
                quote_asset=quote_asset,
            ):
                continue

            if is_spot_duplicate_of_futures(
                base_asset=base_asset,
                futures_underlying_assets=futures_underlying_assets,
            ):
                continue

            quote_volume = quote_volume_by_symbol.get(
                symbol_name,
                0.0,
            )

            quote_volume_usdt = convert_spot_quote_volume_to_usdt(
                quote_asset=quote_asset,
                quote_volume=quote_volume,
                last_price_by_symbol=last_price_by_symbol,
            )

            if quote_volume_usdt < min_quote_volume_usdt:
                continue

            liquid_symbols.append(
                (
                    MarketSymbol(
                        symbol=symbol_name,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        market="spot",
                    ),
                    quote_volume_usdt,
                )
            )

        liquid_symbols.sort(
            key=lambda item: (
                -item[1],
                item[0].symbol,
            )
        )

        symbols = [
            market_symbol
            for market_symbol, _ in liquid_symbols
        ]

        if max_symbols is None:
            return symbols

        return symbols[:max_symbols]

    async def load_liquid_futures_symbols(
        self,
        min_quote_volume_usdt: float,
        max_symbols: int | None = None,
    ) -> list[MarketSymbol]:
        """
        Return liquid USDT perpetual Futures contracts.

        Symbols are sorted by 24-hour quote volume, highest first.
        Delivery contracts, inactive symbols and low-volume contracts
        are excluded before scanning begins.
        """

        if min_quote_volume_usdt <= 0:
            raise ValueError(
                "Minimum quote volume must be greater than zero."
            )

        if max_symbols is not None and max_symbols <= 0:
            raise ValueError(
                "Maximum symbol count must be greater than zero."
            )

        futures_info, tickers = await asyncio.gather(
            self.client.get_futures_exchange_info(),
            self.client.get_futures_ticker_24h(),
        )

        quote_volume_by_symbol = {
            str(item.get("symbol", "")): self._to_float(
                item.get("quoteVolume", 0.0)
            )
            for item in tickers
        }

        liquid_symbols: list[tuple[MarketSymbol, float]] = []

        for item in futures_info["symbols"]:
            if item.get("status") != "TRADING":
                continue

            if item.get("quoteAsset") != "USDT":
                continue

            if item.get("contractType") != "PERPETUAL":
                continue

            symbol_name = str(item.get("symbol", ""))
            base_asset = str(item.get("baseAsset", ""))
            quote_asset = str(item.get("quoteAsset", ""))

            if not symbol_name:
                continue

            if is_blocked_market_symbol(
                symbol=symbol_name,
                base_asset=base_asset,
                quote_asset=quote_asset,
            ):
                continue

            quote_volume = quote_volume_by_symbol.get(
                symbol_name,
                0.0,
            )

            if quote_volume < min_quote_volume_usdt:
                continue

            liquid_symbols.append(
                (
                    MarketSymbol(
                        symbol=symbol_name,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        market="futures",
                    ),
                    quote_volume,
                )
            )

        liquid_symbols.sort(
            key=lambda item: (
                -item[1],
                item[0].symbol,
            )
        )

        symbols = [
            market_symbol
            for market_symbol, _ in liquid_symbols
        ]

        if max_symbols is None:
            return symbols

        return symbols[:max_symbols]

    async def load_candles(
        self,
        symbol: MarketSymbol,
        interval: str = "1d",
        limit: int = 365,
    ) -> list[Candle]:
        """
        Load historical candles.
        """

        return await self.client.get_klines(
            symbol=symbol.symbol,
            interval=interval,
            limit=limit,
            futures=symbol.is_futures,
        )

    async def close(self) -> None:
        """
        Close Binance client.
        """

        await self.client.close()

    @staticmethod
    def _to_float(
        value: object,
    ) -> float:
        """
        Convert Binance numeric values safely.
        """

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0