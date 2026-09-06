"""Autonomous, fail-closed strategy research orchestration.

This package coordinates predeclared research objects only. It never invents
strategy semantics, mutates the runtime release manifest, or executes orders.
"""
from .models import ResearchObject, ResearchVerdict, Stage
from .orchestrator import AutonomousResearchOrchestrator
from .repository import AutonomousResearchRepository

__all__ = ["ResearchObject","ResearchVerdict","Stage","AutonomousResearchOrchestrator","AutonomousResearchRepository"]
