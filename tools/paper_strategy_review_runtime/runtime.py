from __future__ import annotations
import argparse,json,os
from decimal import Decimal
from pathlib import Path

from stage10.paper_strategy_review import PaperReviewPolicy,run_review_cycle

def _p(name,default):return Path(os.getenv(name,default))
def run_once():
    root=_p("PROMOTED_PAPER_STATE_DIR","data")
    reviews=run_review_cycle(
      dispatch_db=_p("PROMOTED_PAPER_DISPATCH_DB_PATH",str(root/"promoted_paper_dispatch.db")),
      experiment_db=_p("EXPERIMENT1_DB_PATH",str(root/"experiment1.db")),
      review_db=_p("PAPER_STRATEGY_REVIEW_DB_PATH",str(root/"paper_strategy_review.db")),
      policy=PaperReviewPolicy(min_closed_trades=int(os.getenv("PAPER_REVIEW_MIN_CLOSED_TRADES","30"))),
    )
    return [{
      "object_id":r.object_id,"research_track":r.research_track,"strategy_id":r.strategy_id,"version":r.strategy_version,
      "closed_trades":r.closed_trades,"r_covered_trades":r.r_covered_trades,
      "average_net_r":None if r.average_net_r is None else str(r.average_net_r),
      "profit_factor_r":None if r.profit_factor_r is None else str(r.profit_factor_r),
      "max_cumulative_r_drawdown":None if r.max_cumulative_r_drawdown is None else str(r.max_cumulative_r_drawdown),
      "net_pnl":str(r.net_pnl),"fees_paid":str(r.fees_paid),"status":r.status.value,"reason":r.reason
    } for r in reviews]
def main(argv=None):
    argparse.ArgumentParser(prog="paper-strategy-review-runtime").parse_args(argv)
    print(json.dumps(run_once(),sort_keys=True))
if __name__=="__main__":main()
