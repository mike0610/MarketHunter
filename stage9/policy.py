from __future__ import annotations
from datetime import timedelta
from stage9.models import PipelineSpec

DEFAULT_PIPELINES=(
 PipelineSpec("trading_scanner",timedelta(minutes=30),timedelta(hours=4)),
 PipelineSpec("execution_monitor",timedelta(minutes=5),timedelta(hours=1)),
 PipelineSpec("position_monitor",timedelta(minutes=5),timedelta(hours=1)),
 PipelineSpec("portfolio_mtm",timedelta(minutes=5),timedelta(hours=1)),
 PipelineSpec("investment_discovery",timedelta(hours=6),timedelta(days=1)),
)
