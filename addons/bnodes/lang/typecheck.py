"""AST -> ir.Graph, checked against a Schema.

Every error is collected with its position, so one pass reports them all.
"""

import difflib
from dataclasses import dataclass

from . import ast, ir
from .errors import BnError, Diagnostic
from .schema import STRICT, TREE_KINDS, TYPES, Socket, can_link

GROUP_NODES = {
    "geometry": "GeometryNodeGroup",
    "shader": "ShaderNodeGroup",
    "compositor": "CompositorNodeGroup",
}


@dataclass
class Out:
    """A node's output. `chosen` is None until `.socket` picks one: the first is used."""
    node: str
    outputs: list
    chosen: Socket | None
    label: str

    @property
    def socket(self):
        return self.chosen or (self.outputs[0] if self.outputs else None)


@dataclass
class Lit:
    value: object
    type: str


@dataclass
class Sym:
    """A name bound to nothing: an enum value, such as POWER or FACE."""
    name: str


def check(file, schema, filename="<text>"):
    """Checked graphs, callees before callers. Raises BnError."""
    diags = []
    by_name = {}
    for g in file.graphs:
        if g.name in by_name:
            diags.append(Diagnostic(filename, g.line, g.col, f"graph « {g.name} » défini deux fois"))
        by_name[g.name] = g

    checked, calls = {}, {}
    for g in file.graphs:
        c = GraphChecker(g, by_name, schema, filename, diags)
        checked[g.name] = c.run()
        calls[g.name] = c.calls

    order = []
    state = {}

    def visit(name, via):
        if state.get(name) == "done":
            return
        if state.get(name) == "open":
            g = by_name[via]
            diags.append(Diagnostic(filename, g.line, g.col, f"appel récursif : « {via} » rappelle « {name} »"))
            return
        state[name] = "open"
        for callee in calls.get(name, ()):
            visit(callee, name)
        state[name] = "done"
        if checked.get(name):
            order.append(checked[name])

    for g in file.graphs:
        visit(g.name, g.name)

    if diags:
        raise BnError(diags)
    return order


class GraphChecker:
    def __init__(self, graph, graphs, schema, filename, diags):
        self.g = graph
        self.graphs = graphs
        self.schema = schema
        self.filename = filename
        self.diags = diags
        self.nodes = []
        self.env = {}
        self.calls = set()

    def error(self, at, message):
        self.diags.append(Diagnostic(self.filename, at.line, at.col, message))

    def run(self):
        g = self.g
        if g.kind == "pixel":
            self.error(g, "pixel est un type d'arbre de Blade ; dans Blender : geometry, shader, compositor")
            return None
        if g.kind not in TREE_KINDS:
            self.error(g, f"type d'arbre « {g.kind} » inconnu ; types : {', '.join(TREE_KINDS)}")
            return None

        ok = True
        for p in g.params + g.outputs:
            if p.type not in TYPES:
                self.error(p, f"type « {p.type} » inconnu ; types : {', '.join(TYPES)}")
                ok = False
        if not ok:
            return None

        gin = ir.Node(ir.GROUP_INPUT, "NodeGroupInput", n_outputs=len(g.params), line=g.line, col=g.col)
        gout = ir.Node(ir.GROUP_OUTPUT, "NodeGroupOutput", n_inputs=len(g.outputs), line=g.line, col=g.col)
        self.nodes += [gin, gout]
        for p in g.params:
            if p.name in self.env:
                self.error(p, f"paramètre « {p.name} » défini deux fois")
            sock = Socket(p.name, p.name, p.type)
            self.env[p.name] = Out(ir.GROUP_INPUT, [sock], sock, p.name)

        returned = None
        for stmt in g.body:
            if returned:
                self.error(stmt, "instruction après return")
                break
            if isinstance(stmt, ast.Assign):
                self.assign_stmt(stmt)
            else:
                self.return_stmt(stmt, gout)
                returned = stmt
        if not returned:
            self.error(g, f"return manquant dans « {g.name} »")

        return ir.Graph(g.kind, g.name, [(p.name, p.type) for p in g.params],
                        [(o.name, o.type) for o in g.outputs], self.nodes, g.line, g.col)

    # Statements

    def assign_stmt(self, stmt):
        if stmt.name in self.env:
            self.error(stmt, f"« {stmt.name} » est déjà défini")
            return
        created = len(self.nodes)
        value = self.eval(stmt.value)
        if value is None:
            # Keep the name known, so later uses do not report it again
            self.env[stmt.name] = None
            return
        if isinstance(value, Out) and value.node in {n.id for n in self.nodes[created:]}:
            node = next(n for n in self.nodes if n.id == value.node)
            if node.name is None:
                node.name = stmt.name
        self.env[stmt.name] = value

    def return_stmt(self, stmt, gout):
        outs = [Socket(o.name, o.name, o.type) for o in self.g.outputs]
        if isinstance(stmt.value, ast.Record):
            if self.g.single_output:
                self.error(stmt, "ce graph a une seule sortie : return valeur")
                return
            given = {}
            for f in stmt.value.fields:
                sock = next((s for s in outs if s.name == f.name), None)
                if sock is None:
                    self.error(f, f"« {f.name} » n'est pas une sortie ; sorties : {', '.join(s.name for s in outs)}")
                    continue
                if f.name in given:
                    self.error(f, f"sortie « {f.name} » donnée deux fois")
                    continue
                given[f.name] = f
                value = self.eval(f.value)
                if value is not None:
                    self.connect(gout, sock, value, f, "return")
            missing = [s.name for s in outs if s.name not in given]
            if missing:
                self.error(stmt, f"sorties sans valeur : {', '.join(missing)}")
            return
        if not self.g.single_output:
            self.error(stmt, f"ce graph a plusieurs sorties : return ({', '.join(s.name + ': …' for s in outs)})")
            return
        value = self.eval(stmt.value)
        if value is not None:
            self.connect(gout, outs[0], value, stmt.value, "return")

    # Expressions

    def eval(self, e):
        if isinstance(e, ast.Number):
            return Lit(e.value, "Int" if e.is_int else "Float")
        if isinstance(e, ast.String):
            return Lit(e.value, "String")
        if isinstance(e, ast.Bool):
            return Lit(e.value, "Bool")
        if isinstance(e, ast.Tuple):
            return self.tuple(e)
        if isinstance(e, ast.Ref):
            if e.name in self.env:
                return self.env[e.name]
            return Sym(e.name)
        if isinstance(e, ast.Member):
            return self.member(e, self.eval(e.target))
        if isinstance(e, ast.Call):
            return self.call(e)
        if isinstance(e, ast.Pipe):
            left = self.eval(e.left)
            if left is None:
                return None
            if isinstance(e.call, ast.Member):
                return self.member(e.call, self.call(e.call.target, piped=left))
            return self.call(e.call, piped=left)
        if isinstance(e, (ast.BinOp, ast.Neg)):
            self.error(e, "les formules arrivent en v2 ; écrivez Math(a, b, operation: ADD)")
            return None
        raise TypeError(e)

    def tuple(self, e):
        values = []
        for item in e.items:
            v = self.eval(item)
            if not (isinstance(v, Lit) and v.type in ("Int", "Float")):
                self.error(item, "un tuple ne contient que des nombres")
                return None
            values.append(float(v.value))
        if len(values) not in (2, 3, 4):
            self.error(e, "un tuple a 2, 3 ou 4 nombres")
            return None
        return Lit(tuple(values), "Color" if len(values) == 4 else "Vector")

    def member(self, e, target):
        if target is None:
            return None
        if isinstance(target, Sym):
            self.error(e.target, f"nom inconnu « {target.name} »")
            return None
        if not isinstance(target, Out):
            self.error(e, f"« .{e.socket} » ne s'applique qu'à un nœud")
            return None
        if target.chosen is not None:
            self.error(e, f"« {target.label} » est déjà une sortie ({target.chosen.type}) ; « .{e.socket} » n'existe pas")
            return None
        sock = find_socket(target.outputs, e.socket)
        if isinstance(sock, list):
            self.error(e, f"« {e.socket} » est ambigu ; utilisez l'identifiant : {', '.join(s.identifier for s in sock)}")
            return None
        if sock is None:
            self.error(e, f"{target.label} n'a pas de sortie « {e.socket} » ; sorties : {socket_keys(target.outputs)}")
            return None
        return Out(target.node, target.outputs, sock, f"{target.label}.{e.socket}")

    def call(self, c, piped=None):
        positional = [(piped, c)] if piped is not None else []
        named = []
        failed = False
        for a in c.args:
            v = self.eval(a.value)
            failed |= v is None
            if a.name is None:
                positional.append((v, a.value))
            else:
                named.append((a.name, v, a))

        node = ir.Node(f"n{len(self.nodes)}", "", line=c.line, col=c.col)
        if c.name in self.graphs:
            inputs, outputs = self.group_signature(c, node)
            if inputs is None:
                return None
        else:
            spec = self.schema.node(self.g.kind, c.name)
            if spec is None:
                close = difflib.get_close_matches(c.name, self.schema.node_names(self.g.kind), 3)
                hint = f" ; voulez-vous dire {', '.join(close)} ?" if close else ""
                self.error(c, f"nœud « {c.name} » inconnu dans un arbre {self.g.kind}{hint}")
                return None
            node.bl_idname = spec.bl_idname
            rest = []
            for name, v, a in named:
                if name in spec.props and isinstance(v, (Lit, Sym)):
                    self.prop(node, spec.props[name], v, a)
                else:
                    rest.append((name, v, a))
            named = rest
            inputs, outputs = self.schema.sockets(self.g.kind, spec, node.props)

        node.n_inputs, node.n_outputs = len(inputs), len(outputs)
        self.nodes.append(node)
        if failed:
            positional = [(v, a) for v, a in positional if v is not None]
            named = [(n, v, a) for n, v, a in named if v is not None]

        given = set()
        i = 0
        for v, a in positional:
            if i >= len(inputs):
                self.error(a, f"{c.name} prend {len(inputs)} entrée(s) : {socket_keys(inputs)}")
                break
            sock = inputs[i]
            self.connect(node, sock, v, a, c.name)
            given.add(sock.identifier)
            if not sock.multi_input:
                i += 1

        for name, v, a in named:
            sock = find_socket(inputs, name)
            if isinstance(sock, list):
                self.error(a, f"« {name} » est ambigu ; utilisez l'identifiant : {', '.join(s.identifier for s in sock)}")
                continue
            if sock is None:
                self.error(a, f"{c.name} n'a pas d'entrée « {name} » ; entrées : {socket_keys(inputs)}")
                continue
            if sock.identifier in given and not sock.multi_input:
                self.error(a, f"entrée « {name} » donnée deux fois")
                continue
            given.add(sock.identifier)
            self.connect(node, sock, v, a, c.name)

        return Out(node.id, outputs, None, c.name)

    def group_signature(self, c, node):
        callee = self.graphs[c.name]
        if callee.kind != self.g.kind:
            self.error(c, f"« {c.name} » est un graph {callee.kind}, pas {self.g.kind}")
            return None, None
        self.calls.add(c.name)
        node.bl_idname = GROUP_NODES[self.g.kind]
        node.group = c.name
        return ([Socket(p.name, p.name, p.type) for p in callee.params],
                [Socket(o.name, o.name, o.type) for o in callee.outputs])

    def prop(self, node, prop, v, a):
        if prop.kind == "ENUM":
            value = v.name if isinstance(v, Sym) else v.value if v.type == "String" else None
            if value is None:
                self.error(a, f"{prop.name} attend une valeur comme {prop.items[0] if prop.items else 'MODE'}")
                return
            if prop.items and value not in prop.items:
                close = difflib.get_close_matches(value, prop.items, 1)
                hint = f" ; voulez-vous dire {close[0]} ?" if close else ""
                self.error(a, f"{prop.name}: {value} inconnu{hint} ; valeurs : {short_list(prop.items)}")
                return
        elif prop.kind == "BOOLEAN" and isinstance(v, Lit) and v.type == "Bool":
            value = v.value
        elif prop.kind == "INT" and isinstance(v, Lit) and v.type == "Int":
            value = v.value
        elif prop.kind == "FLOAT" and isinstance(v, Lit) and v.type in ("Int", "Float"):
            value = float(v.value)
        elif prop.kind == "STRING" and isinstance(v, Lit) and v.type == "String":
            value = v.value
        else:
            self.error(a, f"{prop.name} attend une valeur {prop.kind.lower()}")
            return
        node.props[prop.name] = value

    def connect(self, node, sock, v, at, label):
        """Link or set one input of `node` from a value."""
        where = f"{label}.{sock.key}" if label != "return" else f"la sortie « {sock.name} »"
        if isinstance(v, Out):
            src = v.socket
            if src is None:
                self.error(at, f"« {v.label} » n'a pas de sortie")
            elif not can_link(src.type, sock.type):
                self.error(at, f"{where} attend {sock.type}, reçoit {src.type} ({v.label})")
            else:
                node.links.append((sock.identifier, ir.Link(v.node, src.identifier)))
            return
        if sock.multi_input:
            self.error(at, f"{where} n'accepte que des liens")
            return
        if isinstance(v, Sym):
            if sock.type == "Menu":
                node.values[sock.identifier] = v.name
            else:
                self.error(at, f"nom inconnu « {v.name} »")
            return
        ok = (v.type == sock.type
              or (sock.type == "Menu" and v.type == "String")
              or (sock.type not in STRICT and v.type not in STRICT))
        if not ok:
            self.error(at, f"{where} attend {sock.type}, reçoit {v.type}")
            return
        node.values[sock.identifier] = v.value


def find_socket(sockets, name):
    """By identifier, then UI name, then snake_case key. A list when ambiguous."""
    for attr in ("identifier", "name", "key"):
        found = [s for s in sockets if getattr(s, attr) == name]
        if len(found) == 1:
            return found[0]
        if found:
            return found
    return None


def socket_keys(sockets):
    """How to name each socket in text: its key, or its identifier when the key repeats."""
    keys = [s.key for s in sockets]
    return ", ".join(k if keys.count(k) == 1 else s.identifier for k, s in zip(keys, sockets)) or "aucune"


def short_list(items, limit=12):
    items = list(items)
    return ", ".join(items[:limit]) + (", …" if len(items) > limit else "")
