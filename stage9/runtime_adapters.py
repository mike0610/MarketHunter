from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Callable
from experiment1.engine import Experiment1Engine
from experiment1.lifecycle import run_protective_exit_cycle
from experiment1.mtm import run_mtm_cycle
from experiment1.runtime import run_market_cycle
from tools.experiment1_runtime.runtime import _protective_exit_candidates
from tools.gil_trading_scanner_runtime.runtime import run_once as run_scanner_once

@dataclass(frozen=True,slots=True)
class RuntimeAdapters:
 engine:Experiment1Engine
 quote_source:object
 scanner_cycle_fn:Callable[[],object]=run_scanner_once

 def trading_scanner_cycle(self)->None:
  self.scanner_cycle_fn()

 def execution_cycle(self)->None:
  asyncio.run(run_market_cycle(self.engine,self.quote_source))

 def position_monitor_cycle(self)->None:
  asyncio.run(run_protective_exit_cycle(self.engine,self.quote_source,_protective_exit_candidates(self.engine)))

 def mtm_cycle(self)->None:
  async def run():
   from experiment1.engine import STARTING_CASH,Experiment1Error
   for account in STARTING_CASH:
    try:await run_mtm_cycle(self.engine,self.quote_source,account)
    except Experiment1Error:pass
  asyncio.run(run())
