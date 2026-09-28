"""Every global name the pipeline module's functions read must exist.

A local of build_pipeline read from run_session's handlers compiles fine and
only fails at runtime with NameError (it did, for five console names, from
88b206f). symtable sees the same thing a linter's undefined-name check does.
"""
import builtins
import symtable
from pathlib import Path

import jarvis.bot.pipeline as pipeline


def _global_refs(table):
    for sym in table.get_symbols():
        if sym.is_global() and sym.is_referenced() and not sym.is_assigned():
            yield table.get_name(), sym.get_name()
    for child in table.get_children():
        yield from _global_refs(child)


def test_no_function_reads_an_undefined_global():
    src = Path(pipeline.__file__).read_text()
    top = symtable.symtable(src, pipeline.__file__, "exec")
    missing = sorted({
        (fn, name) for fn, name in _global_refs(top)
        if not hasattr(pipeline, name) and not hasattr(builtins, name)
    })
    assert missing == []
