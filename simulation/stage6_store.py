from __future__ import annotations
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from simulation.stage6_engine import realized_pnl
from simulation.stage6_models import *

class Stage6PositionStore:
 def __init__(self,db_path:str|Path)->None:
  self.db_path=Path(db_path)
  with sqlite3.connect(self.db_path) as c:
   c.executescript("""
   CREATE TABLE IF NOT EXISTS stage6_exit_fills(
    exit_fill_id TEXT PRIMARY KEY,position_id TEXT NOT NULL,reason TEXT NOT NULL,quantity TEXT NOT NULL,
    reference_price TEXT NOT NULL,fill_price TEXT NOT NULL,fee_amount TEXT NOT NULL,slippage_amount TEXT NOT NULL,
    observed_at TEXT NOT NULL,provider TEXT NOT NULL,source_reference TEXT NOT NULL,
    UNIQUE(position_id,reason,source_reference,quantity));
   CREATE TABLE IF NOT EXISTS stage6_position_state(
    position_id TEXT PRIMARY KEY,original_quantity TEXT NOT NULL,remaining_quantity TEXT NOT NULL,
    partial_done INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL,updated_at TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS stage6_closed_trades(
    closed_trade_id TEXT PRIMARY KEY,position_id TEXT NOT NULL UNIQUE,symbol TEXT NOT NULL,direction TEXT NOT NULL,
    entry_price TEXT NOT NULL,exit_price TEXT NOT NULL,quantity TEXT NOT NULL,gross_pnl TEXT NOT NULL,
    entry_fees TEXT NOT NULL,exit_fees TEXT NOT NULL,realized_pnl TEXT NOT NULL,opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,exit_reason TEXT NOT NULL,strategy_id TEXT NOT NULL,strategy_version TEXT NOT NULL,
    strategy_decision_id TEXT NOT NULL,candidate_dedupe_key TEXT NOT NULL);
   """)

 def restore(self,p:ManagedPosition)->tuple[Decimal,bool,str]:
  with sqlite3.connect(self.db_path) as c:
   row=c.execute("select remaining_quantity,partial_done,status from stage6_position_state where position_id=?",(p.position_id,)).fetchone()
   if row is None:
    c.execute("insert into stage6_position_state values (?,?,?,?,?,?)",(p.position_id,str(p.quantity),str(p.quantity),0,"OPEN",p.opened_at.isoformat()))
    return p.quantity,False,"OPEN"
   return Decimal(row[0]),bool(row[1]),row[2]

 def apply_exit(self,p:ManagedPosition,f:SimulatedExitFill)->tuple[Decimal,str]:
  remaining,partial_done,status=self.restore(p)
  if status=="CLOSED":return Decimal("0"),"CLOSED"
  with sqlite3.connect(self.db_path) as c:
   exists=c.execute("select 1 from stage6_exit_fills where exit_fill_id=?",(f.exit_fill_id,)).fetchone()
   if exists:
    row=c.execute("select remaining_quantity,status from stage6_position_state where position_id=?",(p.position_id,)).fetchone()
    return Decimal(row[0]),row[1]
   if f.quantity<=0 or f.quantity>remaining:raise ValueError("exit quantity exceeds remaining position")
   c.execute("insert into stage6_exit_fills values (?,?,?,?,?,?,?,?,?,?,?)",(f.exit_fill_id,f.position_id,f.reason.value,str(f.quantity),str(f.reference_price),str(f.fill_price),str(f.fee_amount),str(f.slippage_amount),f.observed_at.isoformat(),f.provider,f.source_reference))
   new_remaining=remaining-f.quantity
   new_status="CLOSED" if new_remaining==0 else "OPEN"
   new_partial=partial_done or f.reason is ExitReason.PARTIAL_TAKE_PROFIT
   c.execute("update stage6_position_state set remaining_quantity=?,partial_done=?,status=?,updated_at=? where position_id=?",(str(new_remaining),1 if new_partial else 0,new_status,f.observed_at.isoformat(),p.position_id))
   if new_status=="CLOSED":
    fills=c.execute("select quantity,fill_price,fee_amount,reason,observed_at from stage6_exit_fills where position_id=? order by observed_at,exit_fill_id",(p.position_id,)).fetchall()
    total_qty=sum(Decimal(r[0]) for r in fills);exit_notional=sum(Decimal(r[0])*Decimal(r[1]) for r in fills)
    weighted_exit=exit_notional/total_qty
    exit_fees=sum(Decimal(r[2]) for r in fills)
    gross=(weighted_exit-p.average_price)*total_qty if p.direction=="LONG" else (p.average_price-weighted_exit)*total_qty
    realized=gross-p.entry_fees-exit_fees
    last=fills[-1];cid="closed:"+p.position_id.split(":",1)[-1]
    c.execute("insert or ignore into stage6_closed_trades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cid,p.position_id,p.symbol,p.direction,str(p.average_price),str(weighted_exit),str(total_qty),str(gross),str(p.entry_fees),str(exit_fees),str(realized),p.opened_at.isoformat(),last[4],last[3],p.strategy_id,p.strategy_version,p.strategy_decision_id,p.candidate_dedupe_key))
   return new_remaining,new_status

 def closed_trade(self,position_id:str)->ClosedTradeRecord|None:
  with sqlite3.connect(self.db_path) as c:r=c.execute("select * from stage6_closed_trades where position_id=?",(position_id,)).fetchone()
  if r is None:return None
  return ClosedTradeRecord(r[0],r[1],r[2],r[3],Decimal(r[4]),Decimal(r[5]),Decimal(r[6]),Decimal(r[7]),Decimal(r[8]),Decimal(r[9]),Decimal(r[10]),datetime.fromisoformat(r[11]),datetime.fromisoformat(r[12]),ExitReason(r[13]),r[14],r[15],r[16],r[17])
