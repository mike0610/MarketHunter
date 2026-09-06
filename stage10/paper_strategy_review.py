from __future__ import annotations
import sqlite3
from dataclasses import dataclass
from datetime import datetime,timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path

class PaperReviewStatus(str,Enum):
    PAPER_ACTIVE="PAPER_ACTIVE"
    KEEP="KEEP"
    PAUSE="PAUSE"
    REVIEW_REQUIRED="REVIEW_REQUIRED"

@dataclass(frozen=True,slots=True)
class PaperReviewPolicy:
    min_closed_trades:int=30
    def __post_init__(self):
        if self.min_closed_trades<=0: raise ValueError("min_closed_trades must be positive")

@dataclass(frozen=True,slots=True)
class AttributedPaperTrade:
    object_id:str
    research_track:str|None
    strategy_id:str
    strategy_version:str
    hypothesis_id:str
    decision_id:str
    intent_id:str
    account:str
    symbol:str
    opened_at:datetime
    closed_at:datetime
    realized_pnl:Decimal
    fees_paid:Decimal
    net_pnl:Decimal
    risk_amount:Decimal|None
    net_r:Decimal|None

@dataclass(frozen=True,slots=True)
class PaperStrategyReview:
    object_id:str
    research_track:str|None
    strategy_id:str
    strategy_version:str
    hypothesis_id:str
    closed_trades:int
    r_covered_trades:int
    wins:int
    losses:int
    breakeven:int
    average_net_r:Decimal|None
    profit_factor_r:Decimal|None
    max_cumulative_r_drawdown:Decimal|None
    net_pnl:Decimal
    fees_paid:Decimal
    status:PaperReviewStatus
    reason:str
    evaluated_at:datetime

class PaperStrategyReviewStore:
    def __init__(self,path:str|Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS paper_strategy_reviews(
              object_id TEXT NOT NULL,strategy_id TEXT NOT NULL,strategy_version TEXT NOT NULL,
              research_track TEXT,hypothesis_id TEXT NOT NULL,closed_trades INTEGER NOT NULL,
              r_covered_trades INTEGER NOT NULL,wins INTEGER NOT NULL,losses INTEGER NOT NULL,breakeven INTEGER NOT NULL,
              average_net_r TEXT,profit_factor_r TEXT,max_cumulative_r_drawdown TEXT,
              net_pnl TEXT NOT NULL,fees_paid TEXT NOT NULL,status TEXT NOT NULL,reason TEXT NOT NULL,
              evaluated_at TEXT NOT NULL,PRIMARY KEY(object_id,strategy_id,strategy_version));
            CREATE TABLE IF NOT EXISTS paper_strategy_review_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT,object_id TEXT NOT NULL,strategy_id TEXT NOT NULL,
              strategy_version TEXT NOT NULL,old_status TEXT,new_status TEXT NOT NULL,reason TEXT NOT NULL,
              created_at TEXT NOT NULL);
            """)
    def is_paused(self,object_id:str,strategy_id:str,version:str)->bool:
        with sqlite3.connect(self.path) as c:
            row=c.execute("select status from paper_strategy_reviews where object_id=? and strategy_id=? and strategy_version=?",
                          (object_id,strategy_id,version)).fetchone()
        return row is not None and row[0]==PaperReviewStatus.PAUSE.value
    def upsert(self,r:PaperStrategyReview)->None:
        with sqlite3.connect(self.path) as c:
            old=c.execute("select status from paper_strategy_reviews where object_id=? and strategy_id=? and strategy_version=?",
                          (r.object_id,r.strategy_id,r.strategy_version)).fetchone()
            vals=(r.object_id,r.strategy_id,r.strategy_version,r.research_track,r.hypothesis_id,r.closed_trades,r.r_covered_trades,
                  r.wins,r.losses,r.breakeven,None if r.average_net_r is None else str(r.average_net_r),
                  None if r.profit_factor_r is None else str(r.profit_factor_r),
                  None if r.max_cumulative_r_drawdown is None else str(r.max_cumulative_r_drawdown),
                  str(r.net_pnl),str(r.fees_paid),r.status.value,r.reason,r.evaluated_at.isoformat())
            c.execute("""INSERT INTO paper_strategy_reviews VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(object_id,strategy_id,strategy_version) DO UPDATE SET
              research_track=excluded.research_track,hypothesis_id=excluded.hypothesis_id,closed_trades=excluded.closed_trades,
              r_covered_trades=excluded.r_covered_trades,wins=excluded.wins,losses=excluded.losses,breakeven=excluded.breakeven,
              average_net_r=excluded.average_net_r,profit_factor_r=excluded.profit_factor_r,
              max_cumulative_r_drawdown=excluded.max_cumulative_r_drawdown,net_pnl=excluded.net_pnl,
              fees_paid=excluded.fees_paid,status=excluded.status,reason=excluded.reason,evaluated_at=excluded.evaluated_at""",vals)
            old_status=None if old is None else old[0]
            if old_status!=r.status.value:
                c.execute("""INSERT INTO paper_strategy_review_events
                  (object_id,strategy_id,strategy_version,old_status,new_status,reason,created_at)
                  VALUES(?,?,?,?,?,?,?)""",(r.object_id,r.strategy_id,r.strategy_version,old_status,r.status.value,r.reason,r.evaluated_at.isoformat()))
    def list_reviews(self)->tuple[sqlite3.Row,...]:
        with sqlite3.connect(self.path) as c:
            c.row_factory=sqlite3.Row
            return tuple(c.execute("select * from paper_strategy_reviews order by research_track,object_id,strategy_id,strategy_version").fetchall())

def _signed(action:str,quantity:Decimal)->Decimal:
    return quantity if action in ("BUY","LONG") else -quantity

def collect_attributed_trades(dispatch_db:str|Path,experiment_db:str|Path)->tuple[AttributedPaperTrade,...]:
    dispatch_path=Path(dispatch_db);experiment_path=Path(experiment_db)
    if not dispatch_path.exists() or not experiment_path.exists(): return ()
    with sqlite3.connect(dispatch_path) as dc:
        dc.row_factory=sqlite3.Row
        rows=dc.execute("select * from promoted_paper_dispatches order by created_at,decision_id").fetchall()
    out=[]
    with sqlite3.connect(experiment_path) as ec:
        ec.row_factory=sqlite3.Row
        for d in rows:
            inbox=ec.execute("select intent_id from experiment1_trading_decision_inbox where decision_id=?",(d["decision_id"],)).fetchone()
            if inbox is None or inbox["intent_id"] is None: continue
            intent_id=inbox["intent_id"];prefix=intent_id+":protective:"
            fills=ec.execute("""select * from experiment1_fills
              where intent_id=? or substr(intent_id,1,?)=? order by id""",(intent_id,len(prefix),prefix)).fetchall()
            if len(fills)<2: continue
            running=Decimal("0")
            for f in fills: running+=_signed(f["action"],Decimal(f["quantity"]))
            if running!=0: continue
            realized=sum((Decimal(f["realized_pnl_delta"]) for f in fills),Decimal("0"))
            fees=sum((Decimal(f["fee"]) for f in fills),Decimal("0"))
            net=realized-fees
            risk_raw=d["risk_amount"] if "risk_amount" in d.keys() else None
            risk=Decimal(risk_raw) if risk_raw not in (None,"") and Decimal(risk_raw)>0 else None
            out.append(AttributedPaperTrade(
                d["object_id"],d["research_track"] if "research_track" in d.keys() else None,d["strategy_id"],d["strategy_version"],
                d["hypothesis_id"],d["decision_id"],intent_id,fills[0]["account"],fills[0]["symbol"],
                datetime.fromisoformat(fills[0]["observed_at"]),datetime.fromisoformat(fills[-1]["observed_at"]),
                realized,fees,net,risk,None if risk is None else net/risk))
    return tuple(out)

def evaluate_reviews(trades:tuple[AttributedPaperTrade,...],policy:PaperReviewPolicy,*,now:datetime|None=None)->tuple[PaperStrategyReview,...]:
    moment=now or datetime.now(timezone.utc)
    groups={}
    for t in trades:
        key=(t.object_id,t.research_track,t.strategy_id,t.strategy_version,t.hypothesis_id)
        groups.setdefault(key,[]).append(t)
    reviews=[]
    for key,items in groups.items():
        items.sort(key=lambda x:(x.closed_at,x.decision_id))
        rs=[x.net_r for x in items if x.net_r is not None]
        wins=sum(1 for x in rs if x>0);losses=sum(1 for x in rs if x<0);breakeven=sum(1 for x in rs if x==0)
        avg=None if not rs else sum(rs,Decimal("0"))/Decimal(len(rs))
        pos=sum((x for x in rs if x>0),Decimal("0"));neg=sum((x for x in rs if x<0),Decimal("0"))
        pf=None if neg==0 else pos/abs(neg)
        equity=peak=Decimal("0");max_dd=Decimal("0")
        for x in rs:
            equity+=x;peak=max(peak,equity);max_dd=min(max_dd,equity-peak)
        dd=None if not rs else max_dd
        n=len(items);covered=len(rs)
        if n<policy.min_closed_trades:
            status=PaperReviewStatus.PAPER_ACTIVE;reason=f"closed sample {n} < minimum {policy.min_closed_trades}"
        elif covered<n:
            status=PaperReviewStatus.REVIEW_REQUIRED;reason=f"risk attribution incomplete: {covered}/{n} trades have R"
        elif avg is not None and avg<0 and pf is not None and pf<1:
            status=PaperReviewStatus.PAUSE;reason="minimum sample reached with negative average R and profit factor below 1"
        elif avg is not None and avg>0 and (pf is None or pf>1):
            status=PaperReviewStatus.KEEP;reason="minimum sample reached with positive average R and profit factor above break-even"
        else:
            status=PaperReviewStatus.REVIEW_REQUIRED;reason="minimum sample reached but evidence is mixed or at break-even"
        reviews.append(PaperStrategyReview(
            *key,n,covered,wins,losses,breakeven,avg,pf,dd,
            sum((x.net_pnl for x in items),Decimal("0")),sum((x.fees_paid for x in items),Decimal("0")),
            status,reason,moment))
    return tuple(reviews)

def run_review_cycle(*,dispatch_db:str|Path,experiment_db:str|Path,review_db:str|Path,policy:PaperReviewPolicy)->tuple[PaperStrategyReview,...]:
    trades=collect_attributed_trades(dispatch_db,experiment_db)
    reviews=evaluate_reviews(trades,policy)
    store=PaperStrategyReviewStore(review_db)
    for review in reviews:store.upsert(review)
    return reviews
