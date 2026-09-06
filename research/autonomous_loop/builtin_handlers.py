from __future__ import annotations
from pathlib import Path
from .models import Stage,StageResult

ROOT=Path(__file__).resolve().parents[2]

def futures_roll_data_feasibility(row:dict)->StageResult:
    # V1 capability gate: verify MarketHunter itself has an honest roll-aware path.
    yahoo=(ROOT/"market_data/yahoo_provider.py").read_text()
    markers=("roll","contract_chain","continuous_futures","expiry_calendar")
    found=[m for m in markers if m in yahoo.lower()]
    if len(found)<2:
        return StageResult(
          status="BLOCKED-EVIDENCE",
          evidence={"market":row["market"],"reason":"no-verified-roll-aware-futures-history","provider":"YahooChartDailyProvider","capability_markers":found},
          negative_knowledge={"failure_mode":"data-feasibility","do_not_use":["CL=F as proof","ETF proxy","invented roll mapping"],"reopen_when":"verified roll-aware source + historical active-contract mapping exists"},
        )
    return StageResult(status="PASS",evidence={"market":row["market"],"roll_aware":True},next_stage=Stage.HYPOTHESIS_FREEZE)

def us_equity_data_feasibility(row:dict)->StageResult:
    return StageResult(status="PASS",evidence={"market":row["market"],"provider":"YahooChartDailyProvider","timeframe":"1d"},next_stage=Stage.HYPOTHESIS_FREEZE)
