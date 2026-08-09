from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from .failures import AuthorizationFailure


class Role(Enum):
    SYSTEM_ARCHITECT = "SYSTEM_ARCHITECT"
    GOVERNANCE_MONITOR = "GOVERNANCE_MONITOR"
    STRATEGY_LAB = "STRATEGY_LAB"
    GLOBAL_INVESTMENT_LAB = "GLOBAL_INVESTMENT_LAB"


class Lab(Enum):
    STRATEGY = "STRATEGY"
    GLOBAL_INVESTMENT = "GLOBAL_INVESTMENT"
    RESEARCH = "RESEARCH"


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    role: Role
    lab: Optional[Lab] = None

    def authorize_mutation(self, target_lab: Lab):
        """Enforce lab-scoped authorization rules.

        - Strategy Lab cannot mutate Global Investment Lab and vice versa.
        - System Architect may governance-hold/conflict/request reconciliation, but cannot author research semantics or routing.
        - Governance Monitor and Reports are read-only.
        - Canonical Sync is transport-only and cannot author semantic mutations.
        """

        if self.role == Role.GOVERNANCE_MONITOR:
            raise AuthorizationFailure("Governance Monitor is read-only")

        if self.lab == Lab.STRATEGY and target_lab == Lab.GLOBAL_INVESTMENT:
            raise AuthorizationFailure("Strategy Lab cannot mutate Global Investment Lab")

        if self.lab == Lab.GLOBAL_INVESTMENT and target_lab == Lab.STRATEGY:
            raise AuthorizationFailure("Global Investment Lab cannot mutate Strategy Lab")

        if self.role == Role.SYSTEM_ARCHITECT and target_lab in (Lab.RESEARCH,):
            raise AuthorizationFailure("System Architect cannot author research semantics or routing")

        # otherwise allowed
