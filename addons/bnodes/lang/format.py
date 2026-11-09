"""Source -> canonical source, keeping the comments and the blank lines between statements."""

from . import ast, printer
from .lexer import tokenize
from .parser import parse


def format_source(source, filename="<text>"):
    """The canonical text of `source`. Raises BnError when it does not parse."""
    file = parse(source, filename)
    rows = source.split("\n")

    comments = [c for c in tokenize(source, filename, strict=False) if c.kind == "COMMENT"]
    alone = {c.line for c in comments if not rows[c.line - 1][:c.col - 1].strip()}

    # (origin, text, starts): `starts` marks a line that may follow a kept blank line
    printed = []

    def walk(statements, pad):
        for s in statements:
            # An empty frame holding comments keeps its braces apart, around them
            if isinstance(s, ast.Frame) and (s.body or any(s.line < n < s.end for n in alone)):
                printed.append((s.line, pad + printer.frame_head(s), True))
                walk(s.body, pad + printer.INDENT)
                printed.append((s.end, pad + "}", False))
            else:
                printed.extend((o, t, k == 0) for k, (o, t) in enumerate(printer.statement(s, pad)))

    for i, g in enumerate(file.graphs):
        if i:
            printed.append((file.graphs[i - 1].end, "", False))
        printed.extend((o, t, k == 0) for k, (o, t) in enumerate(printer.header(g)))
        walk(g.body, printer.INDENT)
        printed.append((g.end, "}", False))

    own, trailing = [], {}
    for c in comments:
        text = c.text.rstrip()
        if c.line not in alone:
            # After code: at the end of the printed line that code went to
            at = max(k for k, (o, t, _s) in enumerate(printed) if o <= c.line and t)
            trailing.setdefault(at, []).append(text)
        else:
            own.append((c.line, text))

    out = []

    def emit(origin, text, starts):
        if starts and out and out[-1] and not out[-1].endswith("{") and blank(rows, origin - 1):
            out.append("")
        out.append(text)

    j = 0
    for k, (origin, text, starts) in enumerate(printed):
        # A comment on its own line goes before the first line whose code came after it
        while j < len(own) and own[j][0] < origin:
            line, comment = own[j]
            emit(line, indent(text) + comment, True)
            j += 1
        emit(origin, "  ".join([text] + trailing.get(k, [])), starts)
    for line, comment in own[j:]:
        emit(line, comment, True)
    return "\n".join(out) + "\n"


def indent(text):
    pad = text[:len(text) - len(text.lstrip())]
    # Before a closing brace, the comment belongs to the block it closes
    return pad + printer.INDENT if text.strip() == "}" else pad


def blank(rows, line):
    return 1 <= line <= len(rows) and not rows[line - 1].strip()
