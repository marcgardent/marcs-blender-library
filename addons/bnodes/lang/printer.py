"""AST -> text, in the one canonical layout.

Printing a parsed canonical file gives it back unchanged. Comments are
not in the AST: `format.py` puts them back.
"""

from . import ast, colors
from .schema import RESERVED, key

INDENT = "  "
WIDTH = 100

# Binding strength, for parentheses: unary minus is 4, `.socket` is 9
PRECEDENCE = {"|>": 1, "or": 2, "xor": 2, "and": 3, "not": 4, "<": 5, "<=": 5, ">": 5, ">=": 5, "==": 5, "!=": 5,
              "+": 6, "-": 6, "*": 7, "/": 7, "⋅": 7, "×": 7}


def to_source(file):
    head = render(line for u in sorted_uses(file.uses) for line in use(u))
    return (head + "\n" if head else "") + "\n".join(render(graph(g)) for g in file.graphs)


def sorted_uses(uses):
    return sorted(uses, key=lambda u: (u.name, u.source or ""))


def use(u):
    """`use name (a, b) from "source"`, one name per line when too long."""
    tail = f' from {quote(u.source)}' if u.source is not None else ""
    line = f"use {u.name}" + (f" ({', '.join(u.names)})" if u.names else "") + tail
    if len(line) <= WIDTH or not u.names:
        return [(u.line, line)]
    return [(u.line, f"use {u.name} (")] + [(u.line, f"{INDENT}{n},") for n in u.names] + [(u.line, ")" + tail)]


def render(lines):
    return "".join(text + "\n" for _origin, text in lines)


def name(n):
    """A declared name: bare when it is its own key, else quoted."""
    return n if key(n) == n else quote(n)


def label(n):
    """An argument or socket name: bare when the lexer reads it as one identifier."""
    return n if n.isidentifier() and n not in RESERVED else quote(n)


def quote(s):
    return f'"{s}"'


def graph(g):
    """A graph as (origin, text) lines; origin is the source line the printed line's code starts on."""
    lines = header(g) + description(g)
    for s in g.body:
        lines += statement(s)
    return lines + [(g.end, "}")]


def header(g):
    params = [param(p) for p in g.params]
    if g.single_output:
        outputs = g.outputs[0].type
    else:
        outputs = "(" + ", ".join(param(o) for o in g.outputs) + ")"
    head = f"{g.kind} graph {name(g.name)}({', '.join(params)}) -> {outputs} {{"
    if len(head) <= WIDTH:
        return [(g.line, head)]
    if params:
        lines = [(g.line, f"{g.kind} graph {name(g.name)}(")] + one_per_line(g.params, params) + \
            [(g.params[-1].line, f") -> {outputs} {{")]
    else:
        lines = [(g.line, f"{g.kind} graph {name(g.name)}() -> {outputs} {{")]
    if len(lines[-1][1]) <= WIDTH or g.single_output:
        return lines
    # Outputs too long for the closing line: one per line as well
    close = ") -> (" if params else f"{g.kind} graph {name(g.name)}() -> ("
    return lines[:-1] + [(lines[-1][0], close)] + one_per_line(g.outputs, [param(o) for o in g.outputs]) + \
        [(g.outputs[-1].line, ") {")]


def one_per_line(items, texts):
    lines = [(p.line, INDENT * 2 + text + ",") for p, text in zip(items, texts)]
    lines[-1] = (lines[-1][0], lines[-1][1][:-1])
    return lines


def description(g):
    return [(g.description_line, INDENT + quote(g.description))] if g.description is not None else []


def param(p):
    text = f"{name(p.name)}: {p.type}"
    if p.options:
        text += f"({args(p.options)})"
    if p.default is not None:
        text += f" = {expr(p.default)}"
    if p.range is not None:
        lo, hi = (expr(b) if b is not None else "" for b in p.range)
        text += f" in {lo}..{hi}"
    return text


def statement(s, pad=INDENT):
    """A statement indented by `pad`; a frame with its body one step further in."""
    if isinstance(s, ast.Frame):
        head = frame_head(s)
        if not s.body:
            return [(s.line, f"{pad}{head}}}")]
        lines = [(s.line, pad + head)]
        for inner in s.body:
            lines += statement(inner, pad + INDENT)
        return lines + [(s.end, pad + "}")]
    if isinstance(s, ast.Assign) and isinstance(s.value, ast.Repeat):
        lines = repeat_head(s, pad)
        for inner in s.value.body:
            lines += statement(inner, pad + INDENT)
        return lines + [(s.value.end, pad + "}")]
    if isinstance(s, ast.Assign):
        return block(f"{pad}{s.name} = ", s.value, s.line, pad)
    if isinstance(s.value, ast.Record):
        line = f"{pad}return ({args(s.value.fields)})"
        if len(line) <= WIDTH:
            return [(s.line, line)]
        return spread(f"{pad}return (", s.value.fields, s.line, pad)
    return block(f"{pad}return ", s.value, s.line, pad)


def repeat_head(s, pad):
    """`name = repeat(count, state: start, …) {`, one argument per line when too long."""
    r = s.value
    items = [ast.Arg(None, r.count, r.line, r.col)] + r.states
    line = f"{pad}{s.name} = repeat({args(items)}) {{"
    if len(line) <= WIDTH:
        return [(s.line, line)]
    lines = spread(f"{pad}{s.name} = repeat(", items, s.line, pad)
    lines[-1] = (lines[-1][0], lines[-1][1] + " {")
    return lines


def frame_head(f):
    """`"Title" #color {`, each part only when there is one."""
    color = f.color if f.color is None or isinstance(f.color, str) else "#" + colors.spell(f.color)
    return "".join(part + " " for part in (f.label is not None and quote(f.label), color) if part) + "{"


def block(lead, e, origin, pad):
    """A statement's value: pipes from the second stage on their own lines, long calls one argument per line."""
    if isinstance(e, ast.Pipe):
        pipes = []
        while isinstance(e, ast.Pipe):
            pipes.append(e)
            e = e.left
        first, *rest = reversed(pipes)
        return [(origin, f"{lead}{expr(e)} |> {expr(first.call)}")] + \
            [(p.line, f"{pad}{INDENT}|> {expr(p.call)}") for p in rest]
    line = lead + expr(e)
    if len(line) > WIDTH and isinstance(e, ast.Call) and e.args:
        return spread(f"{lead}{e.name}(", e.args, origin, pad)
    return [(origin, line)]


def spread(head, items, origin, pad):
    """`head` then one argument per line, the last one closing the parenthesis."""
    lines = [(a.line, pad + INDENT + arg(a) + ",") for a in items]
    lines[-1] = (lines[-1][0], lines[-1][1][:-1] + ")")
    return [(origin, head)] + lines


def args(items):
    return ", ".join(arg(a) for a in items)


def arg(a):
    if a.name is None:
        return expr(a.value)
    options = f"({args(a.options)})" if a.options else ""
    return f"{label(a.name)}{options}: {expr(a.value)}"


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
        # Comparisons do not chain: a comparison on the left takes parentheses. Neither do
        # `⋅ ×` beside `* /` nor `xor` beside `or`, which would be hard to read: `(n ⋅ u) * 2.0`
        mixed = isinstance(e.left, ast.BinOp) and e.left.op != op and {op, e.left.op} & {"⋅", "×", "xor"}
        left = expr(e.left, p + 1 if p == PRECEDENCE["=="] or mixed else p)
        text = f"{left} {op} {expr(right, p + 1)}"
        return f"({text})" if p < outer else text
    raise TypeError(e)
