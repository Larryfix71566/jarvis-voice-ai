"""Every global name a function in ``jarvis/`` looks up must exist at module
level in that file.

2026-09-23: PR #80 moved the Command Console handlers into ``run_session()``
while their state (``command_console_enabled``, ``console_generation``,
``console_ready``, ``console_inventory_revision``, ``console_waiters``) stayed
local to ``build_pipeline()``. Python compiles such a name as a global lookup,
so it fails only when the handler runs: every app connect raised NameError in
production, the greeting never ran, and 2,645 passing tests never touched the
handler. This test reads the compiled bytecode instead of running anything,
so an unreachable handler cannot hide the bug.
"""
from __future__ import annotations

import ast
import builtins
import dis
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted((ROOT / "jarvis").rglob("*.py"))


def _module_bindings(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    def bind(node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                names.add(sub.id)
            elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                for alias in sub.names:
                    names.add((alias.asname or alias.name).split(".")[0])

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign,
                               ast.AugAssign, ast.If, ast.Try, ast.With, ast.For)):
            bind(node)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(sub.name)
    for sub in ast.walk(tree):          # `global x` inside a function creates x
        if isinstance(sub, ast.Global):
            names.update(sub.names)
    return names


def _global_loads(code: types.CodeType, where: str):
    line = code.co_firstlineno
    for ins in dis.get_instructions(code):
        pos = getattr(ins, "positions", None)
        if pos is not None and pos.lineno:
            line = pos.lineno
        elif isinstance(ins.starts_line, int) and not isinstance(ins.starts_line, bool):
            line = ins.starts_line
        if ins.opname == "LOAD_GLOBAL" and isinstance(ins.argval, str):
            yield ins.argval, f"{where}:{line}"
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _global_loads(const, f"{where}.{const.co_name}" if where else const.co_name)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_every_global_lookup_resolves(path: Path) -> None:
    source = path.read_text()
    defined = _module_bindings(ast.parse(source)) | set(dir(builtins)) | {"__file__", "__name__"}
    missing = sorted({f"{name} ({where})"
                      for name, where in _global_loads(compile(source, str(path), "exec"), "")
                      if name not in defined})
    assert not missing, "names that raise NameError when reached:\n  " + "\n  ".join(missing)
