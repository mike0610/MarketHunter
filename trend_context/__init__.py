"""
MarketHunter

trend_context

Trend Context Foundation - Slice 1 public surface. Re-exports the
immutable contracts and error taxonomy from
trend_context.foundation.
"""

from trend_context.foundation import (
    TrendContextConflictError,
    TrendContextDisposition,
    TrendContextFoundationError,
    TrendContextHistory,
    TrendContextIdentity,
    TrendContextInvariantError,
    TrendContextLineageError,
    TrendContextNotFoundError,
    TrendContextReference,
    TrendContextReleaseRef,
    TrendContextRecord,
    TrendDirection,
    TrendEvidenceRef,
)

__all__ = [
    "TrendContextConflictError",
    "TrendContextDisposition",
    "TrendContextFoundationError",
    "TrendContextHistory",
    "TrendContextIdentity",
    "TrendContextInvariantError",
    "TrendContextLineageError",
    "TrendContextNotFoundError",
    "TrendContextReference",
    "TrendContextReleaseRef",
    "TrendContextRecord",
    "TrendDirection",
    "TrendEvidenceRef",
]
