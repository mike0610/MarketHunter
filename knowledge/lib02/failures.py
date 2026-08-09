from __future__ import annotations
from dataclasses import dataclass


class DomainFailure(Exception):
    """Base domain failure vocabulary."""


class ReopenConditionError(DomainFailure):
    pass


class AuthorizationFailure(DomainFailure):
    pass


class MappingFailure(DomainFailure):
    pass


class ValidationFailure(DomainFailure):
    pass
