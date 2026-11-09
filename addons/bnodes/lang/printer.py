"""AST -> text, in the one canonical layout.

Printing a parsed canonical file gives it back unchanged; comments are
not in the AST and are lost.
"""

from . import ast
from .schema import RESERVED, key

INDENT = "  "
WIDTH = 100

# Binding strength, for parentheses: unary minus is 4, `.socket` is 9
PRECEDENCE = {"|>": 1, "or": 2, "and": 3, "not": 4, "<": 5, "<=": 5, ">": 5, ">=": 5, "==": 5, "!=": 5,
              "+": 6, "-": 6, "*": 7, "/": 7}


def to_source(file):
    return "\n".join(graph(g) for g in file.graphs)


def name(n):
    """A declared name: bare when it is its own key, else quoted."""
    return n if key(n) == n else quote(n)


def label(n):
    """An argument or socket name: bare when the lexer reads it as one identifier."""
    return n if n.isidentifier() and n not in RESERVED else quote(n)


def quote(s):
    return f'"{s}"'


def graph(g):
    params = [f"{name(p.name)}: {p.type}" for p in g.params]
    if g.single_output:
        outputs = g.outputs[0].type
    else:
        outputs = "(" + ", ".join(f"{name(o.name)}: {o.type}" for o in g.outputs) + ")"
    head = f"{g.kind} graph {name(g.name)}({', '.join(params)}) -> {outputs} {{"
    if len(head) > WIDTH and params:
        lines = ",\n".join(INDENT * 2 + p for p in params)
        head = f"{g.kind} graph {name(g.name)}(\n{lines}\n) -> {outputs} {{"
    return head + "\n" + "".join(statement(s) + "\n" for s in g.body) + "}\n"


def statement(s):
    if isinstance(s, ast.Assign):
        return block(f"{INDENT}{s.name} = ", s.value)
    if isinstance(s.value, ast.Record):
        line = f"{INDENT}return ({args(s.value.fields)})"
        if len(line) > WIDTH:
            line = f"{INDENT}return (\n" + ",\n".join(INDENT * 2 + arg(a) for a in s.value.fields) + ")"
        return line
    return block(f"{INDENT}return ", s.value)


def block(lead, e):
    """A statement's value: pipes one stage per line, long calls one argument per line."""
    inner = INDENT * 2
    if isinstance(e, ast.Pipe):
        stages = []
        while isinstance(e, ast.Pipe):
            stages.append(e.call)
            e = e.left
        return lead + expr(e) + "".join(f"\n{inner}|> {expr(c)}" for c in reversed(stages))
    line = lead + expr(e)
    if len(line) > WIDTH and isinstance(e, ast.Call) and e.args:
        return lead + f"{e.name}(\n" + ",\n".join(inner + arg(a) for a in e.args) + ")"
    return line


def args(items):
    return ", ".join(arg(a) for a in items)


def arg(a):
    return expr(a.value) if a.name is None else f"{label(a.name)}: {expr(a.value)}"


def expr(e, outer=0):
    if isinstance(e, ast.Number):
        return str(int(e.value)) if e.is_int else repr(float(e.value))
    if isinstance(e, ast.String):
        return quote(e.value)
    if isinstance(e, ast.Bool):
        return "true" if e.value else "false"
    if isinstance(e, ast.Tuple):
        return "(" + ", ".join(expr(i) for i in e.items) + ")"
    if isinstance(e, ast.Ref):
        return e.name
    if isinstance(e, ast.Member):
        return f"{expr(e.target, 9)}.{label(e.socket)}"
    if isinstance(e, ast.Call):
        return f"{e.name}({args(e.args)})"
    if isinstance(e, ast.Neg):
        text = "-" + expr(e.value, 9)
        return f"({text})" if outer > 8 else text
    if isinstance(e, ast.Not):
        text = "not " + expr(e.value, PRECEDENCE["not"])
        return f"({text})" if outer > PRECEDENCE["not"] else text
    if isinstance(e, (ast.BinOp, ast.Pipe)):
        op = e.op if isinstance(e, ast.BinOp) else "|>"
        p = PRECEDENCE[op]
        right = e.right if isinstance(e, ast.BinOp) else e.call
        # Comparisons do not chain: a comparison on the left takes parentheses
        text = f"{expr(e.left, p + 1 if p == PRECEDENCE['=='] else p)} {op} {expr(right, p + 1)}"
        return f"({text})" if p < outer else text
    raise TypeError(e)
