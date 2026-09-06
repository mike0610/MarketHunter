from __future__ import annotations
import argparse,json,os
from pathlib import Path
from .models import ResearchObject
from .orchestrator import AutonomousResearchOrchestrator
from .repository import AutonomousResearchRepository

DEFAULT_DB=Path("data/autonomous_research.db")
DEFAULT_QUEUE=Path("research/autonomous_queue.json")

def load_queue(path:Path):
    raw=json.loads(path.read_text())
    if not isinstance(raw,list): raise ValueError("queue must be a list")
    return tuple(ResearchObject(**item) for item in raw)

def run_cycle(db_path:Path=DEFAULT_DB,queue_path:Path=DEFAULT_QUEUE,max_objects:int=3):
    repo=AutonomousResearchRepository(db_path)
    for obj in load_queue(queue_path): repo.enqueue(obj)
    return AutonomousResearchOrchestrator(repo).run_cycle(max_objects=max_objects)

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--db",default=os.getenv("AUTONOMOUS_RESEARCH_DB_PATH",str(DEFAULT_DB)));p.add_argument("--queue",default=os.getenv("AUTONOMOUS_RESEARCH_QUEUE_PATH",str(DEFAULT_QUEUE)));p.add_argument("--max-objects",type=int,default=3)
    a=p.parse_args(argv);print(json.dumps(run_cycle(Path(a.db),Path(a.queue),a.max_objects),sort_keys=True))

if __name__=="__main__":main()
