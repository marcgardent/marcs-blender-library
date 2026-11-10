"""Suggestions at the text cursor, from the schema and the graph being written.

The text around the cursor is half typed, so only tokens are read, never
the parse tree: what comes just before the cursor says what may follow.
"""

from dataclasses import dataclass

from .colors import CSS
from .lexer import tokenize
from .schema import TREE_KINDS, TYPES, key, snake
from .sugar import COMPONENTS, FUNCS, VECTOR, WORDS

# Typing one of these opens the suggestions by itself
OPENERS = ("(", ".", ":", "#")

# Keywords that a value follows
KEYWORDS = ("return", "and", "or", "xor", "not")
OPERATORS = ("=", "+", "-", "*", "/", "<", "<=", ">", ">=", "==", "!=", "⋅", "·", "×")


@dataclass(frozen=True)
class Item:
    label: str
    insert: str     # replaces the word being typed
    detail: str = ""
    kind: str = ""  # node, graph, function, input, prop, enum, output, local, param, type, keyword, color


@dataclass
class Outline:
    """A graph as far as its header can be read: enough to suggest its inputs."""
    kind: str
    name: str
    params: list   # (name, type), as declared
    outputs: list  # (name, type)
    body: int      # index of `{` in the token list, or None


def complete(source, line, col, schema, load=None):
    """(start column, items) at a 1-based cursor; an item replaces line[start:col].

    With `load` (see typecheck.check), the graphs of the `use` lines are suggested too."""
    lines = source.split("\n")
    if not 1 <= line <= len(lines):
        return col, []
    typed = lines[line - 1][:col - 1]
    prefix = typed[len(typed.rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")):]
    start = col - len(prefix)
    if prefix[:1].isdigit():
        return start, []
    tokens = tokenize("\n".join(lines[:line - 1] + [typed[:len(typed) - len(prefix)]]), strict=False)[:-1]
    if tokens and tokens[-1].kind in ("COMMENT", "OPEN_STRING"):
        return start, []
    if tokens and tokens[-1].kind == "COLOR":
        return start, matching([Item(name, name, "#" + code, "color") for name, code in CSS.items()], prefix)
    tokens = [t for t in tokens if t.kind != "COMMENT"]
    everything = [t for t in tokenize(source, strict=False) if t.kind != "COMMENT"]
    # The file's own graphs last: they win over a group or a module graph of the same key
    graphs = existing(schema) + imported(everything, load) + outlines(everything)
    items = Context(tokens, line, graphs, schema).items()
    return start, matching(items, prefix)


def product_sign(typed):
    """(start, end, sign) when `typed`, a line up to the cursor, ends with `dot ` or `cross ` used as a product.

    Only after an operand: `dot(a, b)` and a comment stay as they are.
    """
    if not typed.endswith(" "):
        return None
    tokens = tokenize(typed, strict=False)[:-1]
    if len(tokens) < 2:
        return None
    before, word = tokens[-2:]
    start, end = word.col - 1, word.col - 1 + len(word.text)
    operand = before.kind in ("IDENT", "NUMBER", "STRING", ")") or before.text in ("true", "false")
    if word.kind == "IDENT" and word.text in WORDS and operand and end == len(typed) - 1:
        return start, end, WORDS[word.text]
    return None


def matching(items, prefix):
    """Items whose label starts with the prefix, then those containing it, then by initials."""
    seen, out = set(), []
    p = prefix.lower()
    tiers = (
        lambda s: s.lower().startswith(p),
        lambda s: p in s.lower(),
        lambda s: "".join(c for c in s if c.isupper()).lower().startswith(p),
    )
    for test in tiers if p else tiers[:1]:
        for item in items:
            if item.label not in seen and test(item.label):
                seen.add(item.label)
                out.append(item)
    return out


def outlines(tokens):
    """Every graph of the file, from its header tokens."""
    found = []
    for i, t in enumerate(tokens):
        if t.kind != "KEYWORD" or t.text != "graph" or i + 1 >= len(tokens):
            continue
        kind = tree_kind(tokens, i)
        name = tokens[i + 1].text if tokens[i + 1].kind in ("IDENT", "STRING") else ""
        params, outputs, body = header(tokens, i)
        found.append(Outline(kind, name, params, outputs, body))
    return found


def tree_kind(tokens, i):
    """The tree kind before the `graph` at i, its settings `geometry(is_tool: true)` passed over."""
    j = i - 1
    if j >= 0 and tokens[j].kind == ")":
        depth = 0
        while j >= 0:
            depth += {")": 1, "(": -1}.get(tokens[j].kind, 0)
            if depth == 0:
                break
            j -= 1
        j -= 1
    return tokens[j].text if j >= 0 and tokens[j].kind == "IDENT" else ""


def header(tokens, i):
    """(params, outputs, index of the body's `{` or None) of the graph whose `graph` is at i."""
    params, outputs, body = [], [], None
    j = i + 2
    if j < len(tokens) and tokens[j].kind == "(":
        j, params = typed_names(tokens, j)
    if j < len(tokens) and tokens[j].kind == "->":
        j += 1
        if j < len(tokens) and tokens[j].kind == "(":
            j, outputs = typed_names(tokens, j)
        elif j < len(tokens) and tokens[j].kind == "IDENT":
            outputs = [(tokens[j].text, tokens[j].text)]
            j += 1
    if j < len(tokens) and tokens[j].kind == "{":
        body = j
    return params, outputs, body


def imported(tokens, load):
    """Outlines of the graphs that the `use` lines at the head of the file bring."""
    found = []
    i = 0
    while load and i + 1 < len(tokens) and tokens[i].text == "use" and tokens[i + 1].kind == "IDENT":
        name, names, source = tokens[i + 1].text, None, None
        i += 2
        if i < len(tokens) and tokens[i].kind == "(":
            names = set()
            while i < len(tokens) and tokens[i].kind != ")":
                if tokens[i].kind == "IDENT":
                    names.add(tokens[i].text)
                i += 1
            i += 1
        if i + 1 < len(tokens) and tokens[i].text == "from" and tokens[i + 1].kind == "STRING":
            source = tokens[i + 1].text
            i += 2
        try:
            text, _filename = load(name, source)
        except LookupError:
            continue
        module = [t for t in tokenize(text, strict=False) if t.kind != "COMMENT"]
        found += [g for g in outlines(module) if names is None or key(g.name) in names]
    return found


def existing(schema):
    """Outlines of the node groups already in the file, from the schema when it has them."""
    groups = getattr(schema, "groups", None)
    if groups is None:
        return []
    # By key: two sockets of one name are told apart as in a call
    return [Outline(kind, g.name, [(k, t) for _n, k, t in g.keys("INPUT")],
                    [(k, t) for _n, k, t in g.keys("OUTPUT")], None)
            for kind in TREE_KINDS for g in groups(kind).values() if not isinstance(g, list)]


def typed_names(tokens, j):
    """`(name: Type, ...)` from the `(` at j: (index after `)`, [(name, type)]).

    Panels are opened: `"Title" { … }` gives its sockets. A socket named with
    `"Seed" as seed_2: Int` gives its key, seed_2."""
    pairs = []
    j += 1
    braces = 0  # panels open
    while j < len(tokens) and (braces or tokens[j].kind not in (")", "{")):
        t = tokens[j]
        if t.kind == "STRING" and j + 1 < len(tokens) and tokens[j + 1].kind in ("{", "("):
            # A panel, its settings passed over
            j += 1
            if tokens[j].kind == "(":
                while j < len(tokens) and tokens[j].kind not in (")", "{"):
                    j += 1
                j += tokens[j].kind == ")" if j < len(tokens) else 0
            if j < len(tokens) and tokens[j].kind == "{":
                braces += 1
                j += 1
            continue
        if t.kind == "}":
            braces -= 1
            j += 1
            continue
        named = t.kind in ("IDENT", "STRING") and j + 2 < len(tokens)
        if named and tokens[j + 1].text == "as" and j + 4 < len(tokens) and tokens[j + 2].kind == "IDENT" \
                and tokens[j + 3].kind == ":" and tokens[j + 4].kind == "IDENT":
            pairs.append((tokens[j + 2].text, tokens[j + 4].text))
            j += 5
        elif named and tokens[j + 1].kind == ":" and tokens[j + 2].kind == "IDENT":
            pairs.append((t.text, tokens[j + 2].text))
            j += 3
        else:
            j += 1
    return (j + 1 if j < len(tokens) and tokens[j].kind == ")" else j), pairs


class Context:
    def __init__(self, tokens, line, graphs, schema):
        self.t = tokens
        self.line = line
        self.schema = schema
        self.graphs = {key(g.name): g for g in graphs if g.name}
        starts = [i for i, t in enumerate(tokens) if t.kind == "KEYWORD" and t.text == "graph"]
        self.g = None
        if starts:
            self.g = next((g for g in reversed(graphs) if g.name == tokens[starts[-1] + 1].text), None) \
                if starts[-1] + 1 < len(tokens) else None
        self.head = starts[-1] if starts else None
        self.kind = self.g.kind if self.g else "geometry"

    # Where the cursor is

    def items(self):
        t = self.t
        if self.head is None:
            return self.top_level()
        _params, _outputs, body = header(t, self.head)
        if body is None:
            # In the header: only types are ours to suggest
            return self.types() if t[-1].kind in (":", "->") else []
        depth = 0
        for tok in t[body:]:
            depth += {"{": 1, "}": -1}.get(tok.kind, 0)
        if depth <= 0:
            return self.top_level()
        return self.in_body(body)

    def top_level(self):
        t = self.t
        if t and t[-1].kind == "IDENT" and t[-1].text in TREE_KINDS and (len(t) == 1 or t[-2].kind == "}"):
            return [Item("graph", "graph ", kind="keyword")]
        if t and t[-1].kind not in ("}",):
            return []
        return [Item(k, k + " graph ", "arbre", "keyword") for k in TREE_KINDS]

    def in_body(self, body):
        t = self.t
        last = t[-1]
        new_line = last.line < self.line
        call = self.open_call(body)

        if last.kind == ".":
            return self.members(len(t) - 2, body)
        if last.kind == "|>":
            return [i for i in self.values(body) if i.kind in ("node", "graph", "function")]
        if call is not None and last.kind == ":" and len(t) >= 3 and t[-2].kind == "IDENT" \
                and t[-3].kind in ("(", ","):
            return self.arg_values(call, t[-2].text, body)
        if last.kind in ("(", ","):
            return (self.args(call) if call is not None else []) + self.values(body)
        if last.kind in OPERATORS or last.kind == ":" or (last.kind == "KEYWORD" and last.text in KEYWORDS):
            return self.values(body)
        if (new_line or last.kind == "{") and self.depth(body) == 0:
            return self.values(body) + [Item("return", "return ", kind="keyword")]
        return []

    def depth(self, body):
        d = 0
        for tok in self.t[body + 1:]:
            d += {"(": 1, ")": -1}.get(tok.kind, 0)
        return d

    def open_call(self, body):
        """Index of the name of the innermost unclosed call, or None."""
        stack = []
        for i in range(body + 1, len(self.t)):
            k = self.t[i].kind
            if k == "(":
                stack.append(i)
            elif k == ")" and stack:
                stack.pop()
        if not stack:
            return None
        i = stack[-1] - 1
        return i if self.t[i].kind == "IDENT" else None

    # What may come there

    def values(self, body):
        out = [Item(name, name, self.t[call].text if call is not None else "", "local")
               for name, call in self.locals(body)]
        out += [Item(key(n), key(n), ty, "param") for n, ty in (self.g.params if self.g else [])]
        current = key(self.g.name) if self.g else None
        out += [Item(k, k + "(", "groupe", "graph") for k in sorted(self.graphs) if k != current]
        out += [Item(f, f + "(", "formule", "function") for f in sorted(FUNCS)]
        out += [Item(n, n + "(", "nœud", "node") for n in self.schema.node_names(self.kind)]
        out += [Item(b, b, kind="keyword") for b in ("true", "false")]
        out += [Item("not", "not ", kind="keyword")]
        return out

    def locals(self, body):
        """(name, index of the call it is bound to or None) of each binding before the cursor."""
        t = self.t
        out = []
        for i in range(body + 1, len(t) - 1):
            # The binding being written is not a name yet
            if t[i].kind == "IDENT" and t[i + 1].kind == "=" and t[i].line < self.line \
                    and (t[i - 1].kind == "{" or t[i - 1].line < t[i].line):
                out.append((t[i].text, self.bound_call(i + 2)))
        return out

    def bound_call(self, i):
        """Index of the call a binding's value ends with, None for a formula or a plain name."""
        t = self.t
        depth, name = 0, None
        start_line = t[i - 1].line
        while i < len(t):
            tok = t[i]
            if depth == 0 and tok.line > start_line and tok.kind != "|>" and t[i - 1].kind not in ("|>", ","):
                break
            if tok.kind == "(":
                if depth == 0 and t[i - 1].kind == "IDENT":
                    name = i - 1
                depth += 1
            elif tok.kind == ")":
                depth -= 1
            elif depth == 0 and tok.kind in ("+", "-", "*", "/"):
                return None
            i += 1
        return name

    def call_props(self, name_at):
        """Props written in the call at `name_at`, for the sockets they make available."""
        t = self.t
        spec = self.schema.node(self.kind, t[name_at].text)
        props, given = {}, set()
        depth = 0
        for i in range(name_at + 1, len(t)):
            k = t[i].kind
            depth += {"(": 1, ")": -1}.get(k, 0)
            if depth == 0:
                break
            if depth == 1 and k == "IDENT" and i + 1 < len(t) and t[i + 1].kind == ":" and t[i - 1].kind in ("(", ","):
                given.add(t[i].text)
                prop = spec.props.get(t[i].text) if spec else None
                if prop and i + 2 < len(t):
                    v = t[i + 2]
                    if prop.kind == "ENUM" and v.kind in ("IDENT", "STRING") and (not prop.items or v.text in prop.items):
                        props[prop.name] = v.text
                    elif prop.kind == "BOOLEAN" and v.text in ("true", "false"):
                        props[prop.name] = v.text == "true"
        return spec, props, given

    def args(self, call):
        name = self.t[call].text
        if key(name) in self.graphs:
            # A group's sockets are named like a node's: snake_case
            return [Item(snake(n), snake(n) + ": ", ty, "input") for n, ty in self.graphs[key(name)].params]
        spec, props, given = self.call_props(call)
        if spec is None:
            return []
        inputs, _ = self.schema.sockets(self.kind, spec, props)
        out = [Item(k, k + ": ", s.type, "input") for k, s in keyed(inputs) if k not in given]
        out += [Item(p.name, p.name + ": ", p.kind.lower(), "prop") for p in spec.props.values() if p.name not in given]
        return out

    def arg_values(self, call, arg, body):
        spec = self.schema.node(self.kind, self.t[call].text)
        prop = spec.props.get(arg) if spec else None
        if prop and prop.kind == "ENUM" and prop.items:
            return [Item(v, v if v.isidentifier() else f'"{v}"', prop.name, "enum") for v in prop.items]
        if prop and prop.kind == "BOOLEAN":
            return [Item(b, b, kind="keyword") for b in ("true", "false")]
        return self.values(body)

    def members(self, at, body):
        t = self.t
        if at < 0:
            return []
        target = t[at]
        if target.kind == ")":
            depth = 0
            for i in range(at, body, -1):
                depth += {")": 1, "(": -1}.get(t[i].kind, 0)
                if depth == 0:
                    return self.outputs(i - 1) if t[i - 1].kind == "IDENT" else []
            return []
        if target.kind != "IDENT":
            return []
        for name, call in reversed(self.locals(body)):
            if name == target.text:
                return self.outputs(call) if call is not None else []
        for n, ty in self.g.params if self.g else []:
            if key(n) == target.text and ty in VECTOR:
                return components()
        return []

    def outputs(self, call):
        name = self.t[call].text
        if key(name) in self.graphs:
            outs = self.graphs[key(name)].outputs
            out = [Item(snake(n), snake(n), ty, "output") for n, ty in outs]
            return out + (components() if len(outs) == 1 and outs[0][1] in VECTOR else [])
        if name in FUNCS:
            return components() if name in ("normalize", "cross") else []
        spec, props, _ = self.call_props(call)
        if spec is None:
            return []
        _, outs = self.schema.sockets(self.kind, spec, props)
        out = [Item(k, k, s.type, "output") for k, s in keyed(outs)]
        return out + (components() if len(outs) == 1 and outs[0].type in VECTOR else [])

    def types(self):
        return [Item(ty, ty, kind="type") for ty in TYPES]


def keyed(sockets):
    """(text name, socket): the key, or the identifier when the key repeats."""
    keys = [s.key for s in sockets]
    return [(k if keys.count(k) == 1 else s.identifier, s) for k, s in zip(keys, sockets)]


def components():
    return [Item(c, c, "Float", "output") for c in COMPONENTS]
