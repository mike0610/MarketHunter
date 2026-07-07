"""
Binance REST API endpoints.
"""

SPOT_BASE_URL = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"

# Spot
PING = "/api/v3/ping"
SPOT_EXCHANGE_INFO = "/api/v3/exchangeInfo"
SPOT_KLINES = "/api/v3/klines"
TICKER_24H = "/api/v3/ticker/24hr"

# Futures
FUTURES_EXCHANGE_INFO = "/fapi/v1/exchangeInfo"
FUTURES_KLINES = "/fapi/v1/klines"
FUTURES_TICKER_24H = "/fapi/v1/ticker/24hr"