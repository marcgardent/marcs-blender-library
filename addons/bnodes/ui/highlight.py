"""Highlighting of .bn texts: translucent boxes over keywords, calls, types and values.

The Text Editor colors only the languages it knows, in C; this draws over
the text instead of recoloring it. Types take the color of their socket.
"""

import bpy

from ..lang.colors import rgb
from ..lang.lexer import tokenize
from ..lang.schema import TREE_KINDS, TYPES
from ..lang.sugar import FUNCS
from . import actions, draw, prefs

ALPHA = 0.22
SWATCH = 0.6  # a frame color shows itself, more opaque

COLORS = {
    "keyword": (0.65, 0.40, 0.95),
    "node": (0.30, 0.55, 1.00),
    "function": (0.20, 0.80, 0.80),
    "literal": (1.00, 0.60, 0.20),
    "comment": (0.50, 0.50, 0.50),
}

# Blender's default socket colors
SOCKETS = {
    "Float": (0.63, 0.63, 0.63), "Int": (0.35, 0.55, 0.36), "Bool": (0.80, 0.65, 0.84),
    "Vector": (0.39, 0.39, 0.78), "Color": (0.78, 0.78, 0.16), "Rotation": (0.65, 0.39, 0.78),
    "Matrix": (0.72, 0.20, 0.52), "String": (0.44, 0.70, 1.00), "Menu": (0.40, 0.40, 0.40),
    "Geometry": (0.00, 0.84, 0.64), "Shader": (0.39, 0.78, 0.39), "Object": (0.93, 0.62, 0.36),
    "Collection": (0.96, 0.96, 0.96), "Material": (0.92, 0.46, 0.51), "Image": (0.39, 0.22, 0.39),
    "Texture": (0.62, 0.31, 0.64), "Bundle": (0.50, 0.50, 0.50), "Closure": (0.50, 0.50, 0.50),
}


def classify(tokens):
    """(token, color key) for the tokens worth a box, from one line's tokens."""
    out = []
    for i, t in enumerate(tokens):
        prev = tokens[i - 1].kind if i else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if t.kind == "KEYWORD":
            out.append((t, "literal" if t.text in ("true", "false") else "keyword"))
        elif t.kind in ("NUMBER", "STRING", "OPEN_STRING"):
            out.append((t, "literal"))
        elif t.kind == "COMMENT":
            out.append((t, "comment"))
        elif t.kind == "COLOR" and rgb(t.text[1:]):
            out.append((t, rgb(t.text[1:])))
        elif t.kind == "IDENT":
            # `use` and `from` are keywords only on a use line: `use maths from "…"`
            if t.text == "use" and i == 0 and nxt is not None and nxt.kind == "IDENT" \
                    or t.text == "from" and nxt is not None and nxt.kind in ("STRING", "OPEN_STRING") \
                    and tokens[0].text in ("use", ")"):
                out.append((t, "keyword"))
            elif t.text in TREE_KINDS and nxt is not None and nxt.text == "graph":
                out.append((t, "keyword"))
            elif t.text in TYPES and prev in (":", "->"):
                out.append((t, t.text))
            elif nxt is not None and nxt.kind == "(" or prev == "KEYWORD" and tokens[i - 1].text == "graph":
                out.append((t, "function" if t.text in FUNCS else "node"))
    return out


def boxes(space, row, tokens):
    """{color key: [(x0, y0, x1, y1)]} for one 0-based text line."""
    lh = draw.line_height(space)
    out = {}
    for t, color in classify(tokens):
        start = t.col - 1
        length = len(t.text) + (2 if t.kind == "STRING" else 1 if t.kind == "OPEN_STRING" else 0)
        x0, y0 = draw.char_box(space, row, start)
        x1, y1 = draw.char_box(space, row, start + length)
        if y1 != y0:
            # Wrapped: one box per character keeps each on its row
            for c in range(start, start + length):
                cx, cy = draw.char_box(space, row, c)
                nx, ny = draw.char_box(space, row, c + 1)
                if ny == cy:
                    out.setdefault(color, []).append((cx, cy, nx, cy + lh))
            continue
        out.setdefault(color, []).append((x0, y0, x1, y0 + lh))
    return out


def draw_highlight():
    space = bpy.context.space_data
    text = space.text
    if not actions.is_bn(text) or not prefs.get().highlight:
        return
    region = bpy.context.region
    lh = draw.line_height(space)
    found = {}
    # With word wrap, `top` counts screen rows, which are at least as many as lines
    first = 0 if space.show_word_wrap else max(0, space.top - 1)
    for row in range(first, len(text.lines)):
        _, y = draw.char_box(space, row, 0)
        if y > region.height + lh:
            continue
        if y < -lh:
            break
        tokens = tokenize(text.lines[row].body, strict=False)[:-1]
        for color, rects in boxes(space, row, tokens).items():
            found.setdefault(color, []).extend(rects)
    for color, rects in found.items():
        if isinstance(color, tuple):
            draw.rects(rects, (*color, SWATCH))
        else:
            draw.rects(rects, (*(COLORS.get(color) or SOCKETS.get(color, COLORS["comment"])), ALPHA))


_handler = None


def register():
    global _handler
    _handler = bpy.types.SpaceTextEditor.draw_handler_add(draw_highlight, (), "WINDOW", "POST_PIXEL")


def unregister():
    global _handler
    if _handler is not None:
        bpy.types.SpaceTextEditor.draw_handler_remove(_handler, "WINDOW")
        _handler = None
