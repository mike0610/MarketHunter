from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import median

from market_data.foundation import MarketSeries


@dataclass(frozen=True, slots=True)
class MonthlyUniverseMember:
    symbol: str
    median_daily_dollar_volume: Decimal
    latest_close: Decimal
    valid_observations: int


@dataclass(frozen=True, slots=True)
class MonthlyUniverseSnapshot:
    effective_month: str
    as_of_date: date
    members: tuple[MonthlyUniverseMember,...]
    survivorship_status: str = "CURRENT_SURVIVOR_ONLY"


def build_monthly_universe(
    series_by_symbol: dict[str, MarketSeries],
    *,
    as_of_date: date,
    effective_month: str,
    top_n: int = 100,
) -> MonthlyUniverseSnapshot:
    """Frozen GIL v0.1 monthly liquidity universe over supplied eligible stocks.

    Uses only bars dated on/before as_of_date. Caller is responsible for passing
    an eligible US common-stock master. With the current Twelve Data stock list,
    survivorship status is CURRENT_SURVIVOR_ONLY.
    """
    if top_n != 100:
        raise ValueError("GIL v0.1 universe is frozen at TOP 100")
    eligible: list[MonthlyUniverseMember] = []
    for symbol, series in series_by_symbol.items():
        prior=tuple(b for b in series.bars if b.timestamp.date()<=as_of_date)
        if len(prior)<60: continue
        window=prior[-60:]
        valid=[b for b in window if b.volume>0 and b.close>0]
        if len(valid)<55: continue
        latest=valid[-1].close
        if latest<Decimal("5"): continue
        ddv=[b.close*b.volume for b in valid]
        med=Decimal(str(median(ddv)))
        if med<Decimal("50000000"): continue
        eligible.append(MonthlyUniverseMember(symbol.upper(),med,latest,len(valid)))
    eligible.sort(key=lambda x:(-x.median_daily_dollar_volume,x.symbol))
    return MonthlyUniverseSnapshot(effective_month,as_of_date,tuple(eligible[:100]))
