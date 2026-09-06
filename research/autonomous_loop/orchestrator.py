from __future__ import annotations
from .handlers import run_handler
from .models import ResearchVerdict,Stage,TechnicalFailure
from .repository import AutonomousResearchRepository

class AutonomousResearchOrchestrator:
    def __init__(self,repo:AutonomousResearchRepository): self.repo=repo

    def run_cycle(self,max_objects:int=3)->dict:
        completed=[]; attempts=0
        while len(completed)<max_objects:
            row=self.repo.next_object()
            if row is None: break
            attempts+=1
            oid=row["object_id"]; stage=Stage(row["stage"]); self.repo.mark_running(oid)
            handler={Stage.DATA_FEASIBILITY:row["data_handler"],Stage.HYPOTHESIS_FREEZE:row["hypothesis_handler"],Stage.VALIDATION:row["validation_handler"]}.get(stage)
            try:
                result=run_handler(handler,object_row=dict(row))
            except Exception as exc:
                self.repo.technical_failure(oid,TechnicalFailure.TOOLING_FAILURE.value,{"error":repr(exc),"stage":stage.value})
                # One bounded retry per cycle; do not spin forever.
                if attempts>=max_objects: break
                continue

            if result.status in {v.value for v in ResearchVerdict}:
                self.repo.terminal(oid,result.status,result.evidence,result.negative_knowledge,row["hypothesis_id"])
                completed.append((oid,result.status)); continue
            if result.status in {v.value for v in TechnicalFailure}:
                self.repo.technical_failure(oid,result.status,result.evidence)
                if attempts>=max_objects: break
                continue
            if result.status!="PASS" or result.next_stage is None:
                self.repo.technical_failure(oid,TechnicalFailure.TOOLING_FAILURE.value,{"reason":"invalid-handler-result","status":result.status})
                if attempts>=max_objects: break
                continue
            self.repo.advance(oid,result.next_stage,result.evidence)
            # Same object can continue immediately without manual ping.
        return {"completed":completed,"attempts":attempts,"counts":self.repo.counts()}
