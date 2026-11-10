"""The .bn language: text to a resolved node graph, without bpy."""

from .errors import BnError, Diagnostic
from .parser import parse
from .typecheck import check


def compile_source(source, schema, filename="<text>", load=None):
    """Parse and check a .bn source. Returns the graphs, raises BnError.

    `load(name, source)` finds the modules of its `use` lines: see typecheck.check."""
    return check(parse(source, filename), schema, filename, load)


__all__ = ["BnError", "Diagnostic", "parse", "check", "compile_source"]
