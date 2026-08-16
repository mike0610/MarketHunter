"""
MarketHunter

research/validation

Slice 1 immutable boundary/value objects for strategy mathematical
validation. No canonical lifecycle, persistence, or API owner is
exported here.
"""

from research.validation.contracts import (
    CheckApplicability,
    CheckOutcome,
    ReferenceState,
    ValidationCheckEvidence,
    ValidationCheckId,
    ValidationEvidence,
    ValidationPolicyRef,
    ValidationRunRequest,
)

__all__ = [
    "CheckApplicability",
    "CheckOutcome",
    "ReferenceState",
    "ValidationCheckEvidence",
    "ValidationCheckId",
    "ValidationEvidence",
    "ValidationPolicyRef",
    "ValidationRunRequest",
]
