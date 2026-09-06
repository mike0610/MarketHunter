from __future__ import annotations
import importlib
from .models import StageResult

def run_handler(handler_path:str|None, *, object_row:dict)->StageResult:
    if not handler_path:
        return StageResult(
            status="BLOCKED-EVIDENCE",
            evidence={"reason":"missing-predeclared-handler","stage":object_row["stage"]},
            negative_knowledge={"do_not_infer":"missing research semantics is not a rejected strategy"},
        )
    if ":" not in handler_path: raise ValueError("handler must be module:function")
    module_name,func_name=handler_path.split(":",1)
    func=getattr(importlib.import_module(module_name),func_name)
    result=func(dict(object_row))
    if not isinstance(result,StageResult): raise TypeError("handler must return StageResult")
    return result
