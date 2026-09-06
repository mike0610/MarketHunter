from __future__ import annotations
import json,tempfile
from pathlib import Path
from research.autonomous_loop.models import ResearchObject,ResearchVerdict,Stage,StageResult
from research.autonomous_loop.orchestrator import AutonomousResearchOrchestrator
from research.autonomous_loop.repository import AutonomousResearchRepository

def data_pass(row): return StageResult("PASS",{"data":"ok"},Stage.HYPOTHESIS_FREEZE)
def hypothesis_pass(row): return StageResult("PASS",{"frozen":True},Stage.VALIDATION)
def reject(row): return StageResult(ResearchVerdict.REJECTED.value,{"avg_r":-0.2},negative_knowledge={"why":"negative OOS"})
def blocked(row): return StageResult(ResearchVerdict.BLOCKED_EVIDENCE.value,{"reason":"missing data"},negative_knowledge={"gap":"provider"})
def promote(row): return StageResult(ResearchVerdict.PROMOTION_ELIGIBLE.value,{"avg_r":0.2,"pf":1.3})

HANDLER=__name__

def test_three_objects_advance_without_manual_ping_and_preserve_terminal_states():
    with tempfile.TemporaryDirectory() as td:
        repo=AutonomousResearchRepository(Path(td)/"loop.db")
        repo.enqueue(ResearchObject("A","A","LONG","H-A",f"{HANDLER}:data_pass",f"{HANDLER}:hypothesis_pass",f"{HANDLER}:reject",priority=1))
        repo.enqueue(ResearchObject("B","B","LONG",None,f"{HANDLER}:blocked",priority=2))
        repo.enqueue(ResearchObject("C","C","LONG","H-C",f"{HANDLER}:data_pass",f"{HANDLER}:hypothesis_pass",f"{HANDLER}:promote",priority=3))
        out=AutonomousResearchOrchestrator(repo).run_cycle(max_objects=3)
        assert out["completed"]==[("A","REJECTED"),("B","BLOCKED-EVIDENCE"),("C","PROMOTION-ELIGIBLE")]
        assert repo.object("A")["verdict"]=="REJECTED"
        assert repo.object("B")["verdict"]=="BLOCKED-EVIDENCE"
        assert repo.object("C")["verdict"]=="PROMOTION-ELIGIBLE"

def test_restart_resume_and_idempotent_enqueue():
    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/"loop.db";repo=AutonomousResearchRepository(db)
        obj=ResearchObject("A","A","LONG","H-A",f"{HANDLER}:data_pass",f"{HANDLER}:hypothesis_pass",f"{HANDLER}:reject")
        repo.enqueue(obj);repo.enqueue(obj)
        # one small cycle advances but may not terminal; a new process/repository resumes durable state
        AutonomousResearchOrchestrator(repo).run_cycle(max_objects=1)
        repo2=AutonomousResearchRepository(db)
        AutonomousResearchOrchestrator(repo2).run_cycle(max_objects=1)
        AutonomousResearchOrchestrator(repo2).run_cycle(max_objects=1)
        assert repo2.object("A")["verdict"]=="REJECTED"

def test_promotion_creates_candidate_record_but_never_mutates_runtime_manifest():
    from strategies.runtime_release_manifest import STRATEGY_RELEASE_MANIFEST
    with tempfile.TemporaryDirectory() as td:
        repo=AutonomousResearchRepository(Path(td)/"loop.db")
        repo.enqueue(ResearchObject("C","C","LONG","H-C",f"{HANDLER}:data_pass",f"{HANDLER}:hypothesis_pass",f"{HANDLER}:promote"))
        AutonomousResearchOrchestrator(repo).run_cycle(max_objects=1)
        AutonomousResearchOrchestrator(repo).run_cycle(max_objects=1)
        AutonomousResearchOrchestrator(repo).run_cycle(max_objects=1)
        assert STRATEGY_RELEASE_MANIFEST.declarations==()
        with repo._connect() as c:
            assert c.execute("select count(*) from research_release_candidates").fetchone()[0]==1
