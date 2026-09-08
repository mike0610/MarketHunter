from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date
from market_data.foundation import MarketInstrument
from market_data.twelve_data_provider import TwelveDataDailyProvider
from market_data.twelve_data_stocks import TwelveDataStockListProvider
from research.earnings_volume_universe import build_monthly_universe


async def dry_run(months: tuple[tuple[int,int],...]) -> None:
    stocks=await TwelveDataStockListProvider().us_common_stocks()
    symbols=tuple(x.symbol for x in stocks)
    provider=TwelveDataDailyProvider(symbols,history_limit=120)
    series={}
    for stock in stocks:
        instrument=MarketInstrument(stock.symbol,"US_STOCK","USD",stock.exchange)
        try:
            series[stock.symbol]=await provider.history(instrument,limit=120)
        except Exception:
            continue
    for year,month in months:
        # Research dry-run only: use last calendar date; builder itself only accepts completed bars <= date.
        as_of=date(year,month,monthrange(year,month)[1])
        next_year,next_month=(year+1,1) if month==12 else (year,month+1)
        snap=build_monthly_universe(series,as_of_date=as_of,effective_month=f"{next_year:04d}-{next_month:02d}")
        print(snap.effective_month,snap.as_of_date,len(snap.members),snap.survivorship_status)
        print(",".join(x.symbol for x in snap.members[:10]))


if __name__=="__main__":
    asyncio.run(dry_run(((2026,6),(2026,7),(2026,8))))
