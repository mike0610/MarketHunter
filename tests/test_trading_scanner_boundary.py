"""
MarketHunter

The load-bearing proof for GIL Trading Scanner v1's hard boundary:
"Scanner MUST NOT emit BUY/SELL/LONG/SHORT" and "Scanner MUST NOT
create OrderIntent or bypass GIL Decision -> MarketHunter paper
execution boundary." This is checked structurally (every module in
trading_scanner/ is scanned for any reference to the forbidden
names/modules), not just behaviorally - a behavioral test could pass
by accident if a code path is simply never exercised; a structural
scan cannot.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
import unittest

import trading_scanner

_FORBIDDEN_MODULE_PREFIXES = ("experiment1.engine", "experiment1.gil_decision", "experiment1.runtime")
_FORBIDDEN_NAMES = {"submit_intent", "execute_pending", "ingest_gil_decision", "OrderIntent"}


def _iter_trading_scanner_modules():
    for module_info in pkgutil.walk_packages(trading_scanner.__path__, prefix="trading_scanner."):
        yield importlib.import_module(module_info.name)


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _referenced_names(tree: ast.Module) -> set[str]:
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        alias.asname or alias.name.rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


class TradingScannerNeverTouchesExecutionTests(unittest.TestCase):
    """
    Parses each module's real AST (not a naive substring search, which
    would false-positive on a docstring merely mentioning a module
    name in prose) for an actual import statement or referenced name
    matching a forbidden execution symbol.
    """

    def test_no_trading_scanner_module_imports_a_forbidden_execution_module(self) -> None:
        for module in _iter_trading_scanner_modules():
            source = module.__loader__.get_source(module.__name__) or ""
            imported = _imported_module_names(ast.parse(source))
            for forbidden in _FORBIDDEN_MODULE_PREFIXES:
                with self.subTest(module=module.__name__, forbidden=forbidden):
                    matches = {name for name in imported if name == forbidden or name.startswith(forbidden + ".")}
                    self.assertFalse(
                        matches, f"{module.__name__} imports forbidden execution module(s) {matches!r}"
                    )

    def test_no_trading_scanner_module_references_a_forbidden_execution_function_by_name(self) -> None:
        for module in _iter_trading_scanner_modules():
            source = module.__loader__.get_source(module.__name__) or ""
            referenced = _referenced_names(ast.parse(source))
            for forbidden in _FORBIDDEN_NAMES:
                with self.subTest(module=module.__name__, forbidden=forbidden):
                    self.assertNotIn(
                        forbidden, referenced, f"{module.__name__} references forbidden execution symbol {forbidden!r}"
                    )

    def test_trading_scanner_modules_do_not_transitively_import_experiment1_engine(self) -> None:
        # A second, independent proof at the actual loaded-module level
        # rather than pure text search: walk each trading_scanner
        # module's own real __dict__ for any imported name/submodule
        # object that is - or came from - experiment1.engine.
        for module in _iter_trading_scanner_modules():
            for attr_name, attr_value in vars(module).items():
                module_of_attr = getattr(attr_value, "__module__", None)
                with self.subTest(module=module.__name__, attr=attr_name):
                    self.assertNotEqual(module_of_attr, "experiment1.engine")
                    self.assertNotEqual(module_of_attr, "experiment1.gil_decision")


if __name__ == "__main__":
    unittest.main()
