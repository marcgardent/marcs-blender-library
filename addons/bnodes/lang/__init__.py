"""The .bn language: text to a resolved node graph, without bpy."""

from .errors import BnError, Diagnostic
from .parser import parse
from .typecheck import check


def compile_source(source, schema, filename="<text>"):
    """Parse and check a .bn source. Returns the graphs, raises BnError."""
    return check(parse(source, filename), schema, filename)


__all__ = ["BnError", "Diagnostic", "parse", "check", "compile_source"]
