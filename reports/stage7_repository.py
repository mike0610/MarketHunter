from __future__ import annotations
import sqlite3
from decimal import Decimal
from pathlib import Path
from reports.stage7_analytics import ClosedTradeSample

class Stage7ClosedTradeReader:
 """Read-only analytics seam over Stage 6 canonical closed trades."""
 def __init__(self,db_path:str|Path)->None:self.db_path=Path(db_path)

 def read_all(self)->tuple[ClosedTradeSample,...]:
  if not self.db_path.exists():return ()
  with sqlite3.connect(self.db_path) as c:
   exists=c.execute("select 1 from sqlite_master where type='table' and name='stage6_closed_trades'").fetchone()
   if not exists:return ()
   rows=c.execute("""select symbol,direction,strategy_id,strategy_version,exit_reason,quantity,
      entry_price,exit_price,gross_pnl,entry_fees,exit_fees,realized_pnl
      from stage6_closed_trades order by closed_at,closed_trade_id""").fetchall()
  return tuple(ClosedTradeSample(r[0],r[1],r[2],r[3],r[4],Decimal(r[5]),Decimal(r[6]),Decimal(r[7]),Decimal(r[8]),Decimal(r[9]),Decimal(r[10]),Decimal(r[11])) for r in rows)
