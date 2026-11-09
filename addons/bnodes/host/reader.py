"""Node group -> AST, the other way round from builder.py.

A node becomes a named statement when several links use it or when its
name was given by hand; otherwise it is written inline where it is used.
Reroutes are followed, frames dropped. What text cannot hold yet is
reported as warnings, never as a failed export.
"""

import heapq
import re

import bpy

from ..lang import ast, sugar
from ..lang.printer import to_source
from ..lang.schema import RESERVED, TYPES, key, snake
from .schema import SOCKET_TYPES, TREE_TYPES, BlenderSchema, snapshot, text_name

KINDS = {v: k for k, v in TREE_TYPES.items()}
INTERFACE_TYPES = {v: k for k, v in TYPES.items()}
GROUP_NODES = {"GeometryNodeGroup", "ShaderNodeGroup", "CompositorNodeGroup"}
SKIP = {"NodeFrame", "NodeReroute"}

# Kept for statements even when they hold their default
ALWAYS = {"operation"}

FORMULA_NODES = {"ShaderNodeMath": "Math", "ShaderNodeVectorMath": "VectorMath"}
COMPONENT = {"X": "x", "Y": "y", "Z": "z"}


def export_tree(tree):
    """(text, warnings) for a node group and every group it calls, callees first."""
    with BlenderSchema() as schema:
        file, warnings = read_tree(tree, schema)
    return to_source(file), warnings


def read_tree(tree, schema):
    warnings = []
    graphs = {}
    order = []

    def visit(t, seen):
        if t in graphs or t in seen:
            return
        reader = GraphReader(t, schema, warnings)
        graph = reader.read()
        # Only the groups that reach the output are exported with it
        for callee in sorted(reader.callees, key=lambda c: c.name):
            visit(callee, seen | {t})
        graphs[t] = graph
        order.append(graph)

    visit(tree, frozenset())
    return ast.File(order), warnings


class GraphReader:
    def __init__(self, tree, schema, warnings):
        self.tree = tree
        self.schema = schema
        self.kind = KINDS.get(tree.bl_idname)
        self.warnings = warnings
        self.index = {n.name: i for i, n in enumerate(tree.nodes)}
        self.exprs = {}
        self.chain_heads = set()  # ids of calls whose first argument is a geometry name

    def warn(self, message):
        self.warnings.append(f"{self.tree.name} : {message}")

    def read(self):
        tree = self.tree
        if self.kind is None:
            raise ValueError(f"{tree.name} n'est pas un arbre de nœuds lisible")
        items = [i for i in tree.interface.items_tree if i.item_type == "SOCKET"]
        params = [self.param(i) for i in items if i.in_out == "INPUT"]
        outputs = [self.param(i) for i in items if i.in_out == "OUTPUT"]
        self.param_keys = [key(p.name) for p in params]
        single = len(outputs) == 1 and outputs[0].name == outputs[0].type

        outs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
        out = next((n for n in outs if n.is_active_output), outs[0] if outs else None)

        self.incoming = self.resolve_links()
        reached = self.reach(out)
        dead = [n for n in tree.nodes if n.bl_idname not in SKIP and n not in reached
                and n.bl_idname != "NodeGroupInput"]
        if dead:
            self.warn(f"{len(dead)} nœud(s) sans effet sur la sortie, non exportés")
        for n in reached:
            if n.mute:
                self.warn(f"« {n.name} » est désactivé (mute) ; le texte l'exporte actif")

        self.callees = {n.node_tree for n in reached if n.bl_idname in GROUP_NODES and n.node_tree is not None}
        uses = {}
        for n in reached:
            for links in self.incoming.get(n.name, {}).values():
                for src, _sock in links:
                    uses[src.name] = uses.get(src.name, 0) + 1
        # A Separate XYZ reads as v.x: it vanishes, and v is written once per component
        self.separates = {}
        for n in reached:
            vector = self.incoming.get(n.name, {}).get("Vector")
            if n.bl_idname == "ShaderNodeSeparateXYZ" and vector and not self.hand_named(n):
                self.separates[n.name] = vector[0]
                src = vector[0][0].name
                uses[src] = uses.get(src, 0) + uses.get(n.name, 0) - 1
        taken = set(self.param_keys)
        self.bound = {}
        for n in sorted(reached, key=lambda n: self.index[n.name]):
            if n.bl_idname in ("NodeGroupInput", "NodeGroupOutput") or n.name in self.separates:
                continue
            if uses.get(n.name, 0) > 1 or self.hand_named(n):
                self.bound[n.name] = unique(self.binding_name(n), taken)

        body = []
        fields = []
        if out is not None:
            out_inputs = [s for s in out.inputs if s.type != "CUSTOM"]
            for sock, (o_name, _o_type) in zip(out_inputs, [(o.name, o.type) for o in outputs]):
                links = self.incoming.get(out.name, {}).get(sock.identifier)
                if links:
                    fields.append((o_name, self.use(*links[0])))
        for name in self.statement_order():
            node = self.tree.nodes[name]
            body.append(ast.Assign(self.bound[name], self.expr(node), 0, 0))
        if single and fields:
            value = fields[0][1]
        else:
            value = ast.Record([ast.Arg(n, v, 0, 0) for n, v in fields], 0, 0)
        body.append(ast.Return(value, 0, 0))
        return ast.Graph(self.kind, tree.name, params, outputs, single, body, 0, 0)

    def param(self, item):
        type = INTERFACE_TYPES.get(item.socket_type)
        if type is None:
            type = item.socket_type.removeprefix("NodeSocket")
            self.warn(f"type d'interface {item.socket_type} inconnu du texte")
        return ast.Param(item.name, type, 0, 0)

    # Links

    def resolve_links(self):
        """{node name: {input identifier: [(source node, source socket)]}}, reroutes followed."""
        incoming = {}
        for link in self.tree.links:
            if link.is_muted or link.to_node.bl_idname in SKIP or link.to_socket.is_unavailable:
                continue
            if not link.is_valid:
                self.warn(f"lien invalide vers « {link.to_node.name} » ignoré")
                continue
            src = self.source(link)
            if src is None:
                continue
            per = incoming.setdefault(link.to_node.name, {})
            per.setdefault(link.to_socket.identifier, []).append((link.multi_input_sort_id, src))
        for per in incoming.values():
            for ident, links in per.items():
                per[ident] = [src for _order, src in sorted(links, key=lambda x: x[0])]
        return incoming

    def source(self, link, depth=0):
        node, sock = link.from_node, link.from_socket
        while node.bl_idname == "NodeReroute":
            links = [l for l in node.inputs[0].links if not l.is_muted]
            if not links or depth > 1000:
                return None
            node, sock = links[0].from_node, links[0].from_socket
            depth += 1
        if node.bl_idname in SKIP:
            return None
        return node, sock

    def reach(self, out):
        reached = []
        stack = [out] if out is not None else []
        seen = set()
        while stack:
            n = stack.pop()
            if n.name in seen:
                continue
            seen.add(n.name)
            reached.append(n)
            for links in self.incoming.get(n.name, {}).values():
                stack.extend(src for src, _sock in links)
        return reached

    # Names

    def hand_named(self, node):
        if not node.name.isidentifier() or node.name in RESERVED:
            return False
        labels = {node.bl_label, bpy.app.translations.pgettext_data(node.bl_label)}
        return not any(re.fullmatch(re.escape(lb) + r"(\.\d+)?", node.name) for lb in labels)

    def binding_name(self, node):
        if self.hand_named(node):
            return node.name
        spec = self.spec(node)
        base = spec.name if spec else text_name(node.bl_idname)
        return snake(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", base))

    def spec(self, node):
        return self.schema.node(self.kind, node.bl_idname)

    # Expressions

    def use(self, node, sock):
        """The expression for one output of a node, at the place it is used."""
        if node.bl_idname == "NodeGroupInput":
            i = [s for s in node.outputs if s.type != "CUSTOM"].index(sock)
            return ast.Ref(self.param_keys[i], 0, 0)
        if node.name in self.separates:
            return member(self.use(*self.separates[node.name]), COMPONENT[sock.identifier])
        outputs = [s for s in node.outputs if not s.is_unavailable and s.type != "CUSTOM"]
        if node.name in self.bound:
            target = ast.Ref(self.bound[node.name], 0, 0)
        else:
            target = self.expr(node)
        # With one output there is nothing to pick; with several, say which
        if len(outputs) == 1 and sock == outputs[0]:
            return target
        return member(target, socket_name(sock, outputs, node.bl_idname in GROUP_NODES))

    def expr(self, node):
        if node.name not in self.exprs:
            self.exprs[node.name] = self.call(node)
        return self.exprs[node.name]

    def call(self, node):
        group = node.bl_idname in GROUP_NODES
        spec = None if group else self.spec(node)
        if group:
            if node.node_tree is None:
                self.warn(f"« {node.name} » n'a pas d'arbre ; écrit comme un appel vide")
                return ast.Call("missing_group", [], 0, 0)
            name = key(node.node_tree.name)
        elif spec is None:
            name = text_name(node.bl_idname)
            self.warn(f"{name} (« {node.name} ») n'est pas encore pris en charge par le texte")
        else:
            name = spec.name
            if has_items(node):
                self.warn(f"{name} (« {node.name} ») a des sockets ajoutés à la main, "
                          "pas encore pris en charge par le texte")

        args = []
        props = {}
        if spec is not None:
            _values, prop_defaults = self.schema.defaults(self.kind, spec, {})
            for p in spec.props.values():
                value = getattr(node, p.name)
                if p.name in ALWAYS or not same(value, prop_defaults.get(p.name)):
                    props[p.name] = value
        if spec is not None and spec.bl_idname in FORMULA_NODES and list(props) == ["operation"]:
            formula = self.formula(node, FORMULA_NODES[spec.bl_idname], props["operation"])
            if formula is not None:
                return formula
        if group:
            defaults = {i.identifier: snapshot(i) for i in node.node_tree.interface.items_tree
                        if i.item_type == "SOCKET" and i.in_out == "INPUT"}
        elif spec is not None:
            defaults, _ = self.schema.defaults(self.kind, spec, props)
        else:
            defaults = {}

        inputs = [s for s in node.inputs if not s.is_unavailable and s.type != "CUSTOM"]
        incoming = self.incoming.get(node.name, {})
        positional = True
        geometry_first = False
        for i, sock in enumerate(inputs):
            links = incoming.get(sock.identifier)
            if links:
                values = [self.use(*src) for src in links]
            else:
                lit = self.literal(node, sock, defaults)
                values = [lit] if lit is not None else []
            if not values:
                positional = False
                continue
            label = None if positional else socket_name(sock, inputs, group)
            if i == 0 and sock.type == "GEOMETRY" and not sock.is_multi_input and links:
                geometry_first = True
            for v in values:
                args.append(ast.Arg(label, v, 0, 0))
        for pname, value in props.items():
            args.append(ast.Arg(pname, prop_literal(spec.props[pname], value), 0, 0))

        call = ast.Call(name, args, 0, 0)
        if not (geometry_first and args and args[0].name is None):
            return call
        # Geometry passed from call to call reads as a pipe
        first = args[0].value
        rest = ast.Call(name, args[1:], 0, 0)
        if isinstance(first, ast.Pipe):
            return ast.Pipe(first, rest, 0, 0)
        if isinstance(first, ast.Call):
            if id(first) in self.chain_heads:
                # The chain starts from the inner call's own geometry
                first = ast.Pipe(first.args[0].value, ast.Call(first.name, first.args[1:], 0, 0), 0, 0)
            return ast.Pipe(first, rest, 0, 0)
        self.chain_heads.add(id(call))
        return call

    def formula(self, node, name, operation):
        """`a * 2.0 + sin(t)` for a Math or Vector Math node, when it reads back as that node."""
        operands = []
        for sock in [s for s in node.inputs if not s.is_unavailable]:
            links = self.incoming.get(node.name, {}).get(sock.identifier)
            if links:
                src = links[0][1]
                operands.append([(self.use(*links[0]), SOCKET_TYPES.get(src.type, src.type))])
                continue
            value = snapshot(sock)
            if sock.type == "VALUE":
                operands.append([(number(value), "Float")])
            elif sock.type == "VECTOR":
                lit = [(ast.Tuple([number(v) for v in value], 0, 0), "Vector")]
                if len(set(value)) == 1:
                    lit.insert(0, (number(value[0]), "Float"))  # (1, 1, 1) reads as 1.0 where it means the same
                operands.append(lit)
            else:
                return None

        def means(op, types):
            try:
                return sugar.choose(op, types) == (name, operation, tuple(range(len(types))))
            except ValueError:
                return False

        if (name, operation) in (("Math", "MULTIPLY"), ("VectorMath", "SCALE")) and len(operands) == 2:
            last = operands[1][-1][0]
            if isinstance(last, ast.Number) and last.value == -1.0 and not self.incoming.get(
                    node.name, {}).get(node.inputs[1].identifier if name == "Math" else "Scale"):
                expr, t = operands[0][0]
                if means("neg", [t, "Float"]):
                    return ast.Neg(expr, 0, 0)

        for op in sugar.spellings(name, operation):
            for choice in combinations(operands):
                if not means(op, [t for _e, t in choice]):
                    continue
                exprs = [e for e, _t in choice]
                if op in sugar.BINOPS:
                    if len(exprs) == 2:
                        return ast.BinOp(op, exprs[0], exprs[1], 0, 0)
                    continue
                return ast.Call(op, [ast.Arg(None, e, 0, 0) for e in exprs], 0, 0)
        return None

    def literal(self, node, sock, defaults):
        if not hasattr(sock, "default_value") or node.bl_idname == "NodeGroupOutput":
            return None
        value = snapshot(sock)
        if sock.identifier in defaults and same(value, defaults[sock.identifier]):
            return None
        if value is None:
            return None
        t = sock.type
        if t == "VALUE":
            return number(value)
        if t == "INT":
            return ast.Number(int(value), True, 0, 0)
        if t == "BOOLEAN":
            return ast.Bool(bool(value), 0, 0)
        if t in ("VECTOR", "RGBA", "ROTATION") and isinstance(value, tuple):
            return ast.Tuple([number(v) for v in value], 0, 0)
        if t == "MENU":
            return enum_literal(value)
        if t in ("STRING",) or SOCKET_TYPES.get(t) in ("Object", "Collection", "Material", "Image", "Texture"):
            return self.string(value, node, sock)
        self.warn(f"valeur de « {node.name}.{sock.name} » ({t}) non exportée")
        return None

    def string(self, value, node, sock):
        if '"' in value or "\n" in value:
            self.warn(f"« {node.name}.{sock.name} » : guillemets et retours à la ligne remplacés")
            value = value.replace('"', "'").replace("\n", " ")
        return ast.String(value, 0, 0)

    def statement_order(self):
        """Bound nodes, each after the ones it uses, otherwise in tree order."""
        deps = {}
        for name in self.bound:
            deps[name] = {r for r in refs(self.expr(self.tree.nodes[name]))
                          if r in self.bound.values()}
        by_binding = {b: n for n, b in self.bound.items()}
        waiting = {n: {by_binding[d] for d in ds if by_binding[d] != n} for n, ds in deps.items()}
        ready = [(self.index[n], n) for n, ds in waiting.items() if not ds]
        heapq.heapify(ready)
        order = []
        while ready:
            _i, n = heapq.heappop(ready)
            order.append(n)
            for m, ds in waiting.items():
                if n in ds:
                    ds.discard(n)
                    if not ds:
                        heapq.heappush(ready, (self.index[m], m))
        return order


def member(target, name):
    """`target.name`, put inside a pipe's last call rather than around the pipe."""
    if isinstance(target, ast.Pipe):
        return ast.Pipe(target.left, ast.Member(target.call, name, 0, 0), 0, 0)
    return ast.Member(target, name, 0, 0)


def combinations(operands):
    """Every pick of one spelling per operand, the plainest first."""
    if not operands:
        yield []
        return
    for first in operands[0]:
        for rest in combinations(operands[1:]):
            yield [first] + rest


def has_items(node):
    """Nodes whose sockets are a user-edited list: Capture Attribute, Menu Switch, Bake…"""
    return any(p.type == "COLLECTION" and p.identifier.endswith("items") for p in node.bl_rna.properties)


def unique(name, taken):
    base, i = name, 2
    while name in taken:
        name, i = f"{base}_{i}", i + 1
    taken.add(name)
    return name


def socket_name(sock, sockets, group):
    """How text names this socket: its key when unique, else what tells it apart."""
    keys = [snake(s.name) for s in sockets]
    if keys.count(snake(sock.name)) == 1:
        return snake(sock.name)
    return sock.name if group else sock.identifier


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-6
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if hasattr(a, "__len__") and not isinstance(a, str) and hasattr(b, "__len__"):
        return same(tuple(a), tuple(b))
    return a == b


def number(v):
    return ast.Number(float(f"{float(v):.7g}"), False, 0, 0)


def enum_literal(value):
    if value.isidentifier():
        return ast.Ref(value, 0, 0)
    return ast.String(value, 0, 0)


def prop_literal(prop, value):
    if prop.kind == "ENUM":
        return enum_literal(value)
    if prop.kind == "BOOLEAN":
        return ast.Bool(bool(value), 0, 0)
    if prop.kind == "INT":
        return ast.Number(int(value), True, 0, 0)
    if prop.kind == "FLOAT":
        return number(value)
    return ast.String(str(value), 0, 0)


def refs(e):
    """Every bare name an expression uses."""
    if isinstance(e, ast.Ref):
        yield e.name
    elif isinstance(e, ast.Member):
        yield from refs(e.target)
    elif isinstance(e, ast.Call):
        for a in e.args:
            yield from refs(a.value)
    elif isinstance(e, ast.Pipe):
        yield from refs(e.left)
        yield from refs(e.call)
    elif isinstance(e, ast.Tuple):
        for i in e.items:
            yield from refs(i)
    elif isinstance(e, ast.BinOp):
        yield from refs(e.left)
        yield from refs(e.right)
    elif isinstance(e, ast.Neg):
        yield from refs(e.value)
