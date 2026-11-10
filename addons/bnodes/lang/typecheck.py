"""AST -> ir.Graph, checked against a Schema.

Every error is collected with its position, so one pass reports them all.
"""

import difflib
from dataclasses import dataclass, field

from . import ast, colors, ir, sugar
from .errors import BnError, Diagnostic
from .parser import parse
from .schema import (CLOSURE_INPUT, CLOSURE_OUTPUT, COMBINE_BUNDLE, DATABLOCKS, EVALUATE_CLOSURE, FIELD_TYPES, IMPLICIT,
                     ITEM_NODES, ITEM_TYPES, NO_DEFAULT, NO_VALUE, RANGED, SEPARATE_BUNDLE, SIGNATURE_NODES, STRICT,
                     TREE_KINDS, TYPES, Socket, can_link, key, snake)

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
class Empty:
    """A zone item with no value, written by its type alone: `cache: Bundle`."""
    type: str


@dataclass
class Typed:
    """An item's value given its type: `hauteur: Float = 1`."""
    value: object
    type: str


@dataclass
class Zone:
    """The zone whose body is being checked."""
    word: str        # repeat, simulate, foreach or closure
    out: object      # its output node
    states: list     # of Socket: what its return may give (repeat, simulate)
    skip: object     # the Skip socket of a simulation
    given: set = field(default_factory=set)  # what the return gave
    outputs: list = field(default_factory=list)  # a foreach's output sockets, once returned


@dataclass
class Sym:
    """A name bound to nothing: an enum value, such as POWER or FACE."""
    name: str


def check(file, schema, filename="<text>", load=None):
    """Checked graphs, callees before callers, those of the modules first. Raises BnError.

    `load(name, source)` gives a module's (text, filename) for a `use`, or raises
    LookupError with the reason; without it, a `use` is an error.
    """
    return Modules(schema, load).check(file, filename).order


@dataclass
class Unit:
    """A checked file: its graphs by key, and every graph it needs, callees first."""
    graphs: dict  # key -> ast.Graph
    order: list   # of ir.Graph, those of its own modules included


class Modules:
    """Checks a file and the modules it uses, each module once."""

    def __init__(self, schema, load):
        self.schema = schema
        self.load = load
        self.done = {}  # (name, source) -> Unit
        self.units = {}  # id of a Use -> the Unit it loaded

    def check(self, file, filename, ident=None, stack=()):
        diags = []
        imported = self.imports(file, filename, stack, diags)
        by_name = {}
        # Graphs are called by their key: "Smooth by Angle" is called as smooth_by_angle(...)
        for g in file.graphs:
            if key(g.name) in by_name:
                diags.append(Diagnostic(filename, g.line, g.col, f"graph « {key(g.name)} » défini deux fois"))
            elif key(g.name) in imported:
                diags.append(Diagnostic(filename, g.line, g.col, f"« {key(g.name)} » est défini ici et importé de "
                                                                 f"{imported[key(g.name)][1].name}"))
            by_name[key(g.name)] = g
        callable_ = {k: g for k, (g, _u) in imported.items()} | by_name
        order = self.needed(file.uses, imported)
        # A module that failed would make every call to it an unknown node too
        unsure = any(id(u) not in self.units for u in file.uses)
        own = check_graphs(file.graphs, by_name, callable_, self.schema, filename, diags, unsure)
        if diags:
            raise BnError(diags)
        for g in own:
            g.module = ident
        seen = set()
        return Unit(by_name, [g for g in order + own if not (g.name in seen or seen.add(g.name))])

    def imports(self, file, filename, stack, diags):
        """{key: (ast.Graph, its Use)} of the graphs the uses bring."""
        imported = {}
        names = set()
        for u in file.uses:
            def error(message):
                diags.append(Diagnostic(filename, u.line, u.col, message))
            if u.name in names:
                error(f"module « {u.name} » importé deux fois : un seul use par module")
                continue
            names.add(u.name)
            unit = self.unit(u, stack, error)
            if unit is None:
                continue
            self.units[id(u)] = unit
            wanted = u.names if u.names is not None else list(unit.graphs)
            for k in wanted:
                if k not in unit.graphs:
                    error(f"« {k} » n'est pas dans le module {u.name} ; graphs : {short_list(sorted(unit.graphs))}")
                elif k in imported and imported[k][1].name != u.name:
                    error(f"« {k} » est dans {imported[k][1].name} et dans {u.name} : "
                          f"choisir avec use {u.name} (…)")
                else:
                    imported[k] = (unit.graphs[k], u)
        return imported

    def unit(self, u, stack, error):
        ident = (u.name, u.source)
        if ident in stack:
            error("import circulaire : " + " → ".join(n for n, _s in stack + (ident,)))
            return None
        if ident in self.done:
            return self.done[ident]
        if self.load is None:
            error("use : aucun module à charger ici")
            return None
        try:
            text, filename = self.load(u.name, u.source)
        except LookupError as e:
            error(f"module « {u.name} » : {e.args[0] if e.args else e}")
            return None
        try:
            unit = self.check(parse(text, filename), filename, ident, stack + (ident,))
        except BnError as e:
            first, n = e.diagnostics[0], len(e.diagnostics)
            error(f"module « {u.name} » : {first}" + (f" (+{n - 1} erreur(s))" if n > 1 else ""))
            return None
        self.done[ident] = unit
        return unit

    def needed(self, uses, imported):
        """The modules' graphs to build: a whole module, or the names listed and what they call."""
        out = []
        for u in uses:
            unit = self.units.get(id(u))
            if unit is None:
                continue
            if u.names is None:
                out += unit.order
                continue
            by_ir = {g.name: g for g in unit.order}
            keep = set()
            todo = [unit.graphs[k].name for k in u.names if k in unit.graphs]
            while todo:
                name = todo.pop()
                if name in keep or name not in by_ir:
                    continue
                keep.add(name)
                todo += [n.group for n in by_ir[name].nodes if n.group]
            out += [g for g in unit.order if g.name in keep]
        return out


def check_graphs(graphs, by_name, callable_, schema, filename, diags, unsure=False):
    """The file's own graphs, checked, callees before callers."""
    checked, calls = {}, {}
    for g in graphs:
        c = GraphChecker(g, callable_, schema, filename, diags)
        c.unsure = unsure
        checked[key(g.name)] = c.run()
        calls[key(g.name)] = c.calls

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

    for g in graphs:
        visit(key(g.name), key(g.name))
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
        self.separated = {}  # (node id, output identifier) -> SeparateXYZ node id, for p.x
        self.frames = []
        self.last_frame = {}  # (parent frame id, title) -> id of the last frame opened so
        self.returned = None
        self.zone = None  # inside a zone's body: the Zone
        self.signatures = {}  # Closure Output id -> (input items, output items, item options) it defines
        self.frame_now = None
        self.unsure = False  # a module failed to load: an unknown call may be one of its graphs

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

        defaults = self.defaults()
        gin = ir.Node(ir.GROUP_INPUT, "NodeGroupInput", n_outputs=len(g.params), line=g.line, col=g.col)
        gout = ir.Node(ir.GROUP_OUTPUT, "NodeGroupOutput", n_inputs=len(g.outputs), line=g.line, col=g.col)
        self.nodes += [gin, gout]
        for p in g.params:
            if p.key in self.env:
                self.error(p, f"paramètre « {p.key} » défini deux fois" + twice_hint(p))
            sock = Socket(p.name, p.key, p.type)
            self.env[p.key] = Out(ir.GROUP_INPUT, [sock], sock, p.key)
        keys = set()
        for o in g.outputs:
            if o.key in keys:
                self.error(o, f"sortie « {o.key} » définie deux fois" + twice_hint(o))
            keys.add(o.key)

        self.statements(g.body, gout, None)
        if not self.returned:
            self.error(g, f"return manquant dans « {g.name} »")

        graph = ir.Graph(g.kind, g.name, [(p.name, p.type) for p in g.params],
                         [(o.name, o.type) for o in g.outputs], self.nodes, g.line, g.col, self.frames, defaults)
        graph.options = self.options()
        graph.description = g.description
        graph.input_keys = [p.key for p in g.params]
        graph.output_keys = [o.key for o in g.outputs]
        graph.panels, graph.panel_of = self.panels()
        graph.settings = self.literal_options(g.settings, "réglage")
        return graph

    def panels(self):
        """(ir panels, {(side, key): panel id}) from the panels of both lists, one per path of names."""
        found = {}  # path of names -> (ir.Panel, whether its settings were given)
        panel_of = {}

        def walk(items, side, path, parent):
            seen_panel = None
            names = set()
            for n, item in enumerate(items):
                if isinstance(item, ast.Param):
                    if seen_panel is not None:
                        self.error(item, f"« {item.name} » vient après le panneau « {seen_panel.name} » : "
                                         "Blender range les sockets d'un niveau avant ses panneaux")
                    if parent is not None:
                        panel_of[(side, item.key)] = parent.id
                    self.toggle(item, side, parent, n)
                    continue
                seen_panel = item
                if item.name in names:
                    self.error(item, f"panneau « {item.name} » écrit deux fois dans la même liste")
                    continue
                names.add(item.name)
                here = path + (item.name,)
                if here not in found:
                    panel = ir.Panel(f"p{len(found)}", item.name, parent.id if parent else None,
                                     line=item.line, col=item.col)
                    found[here] = (panel, False)
                panel, given = found[here]
                if item.options:
                    if given:
                        self.error(item, f"réglages du panneau « {item.name} » donnés deux fois : "
                                         "une seule fois, dans la première liste où il paraît")
                    else:
                        panel.options = self.literal_options(item.options, "réglage")
                        found[here] = (panel, True)
                walk(item.items, side, here, panel)

        walk(self.g.tree("INPUT"), "INPUT", (), None)
        if not self.g.single_output:
            walk(self.g.tree("OUTPUT"), "OUTPUT", (), None)
        return [p for p, _given in found.values()], panel_of

    def toggle(self, p, side, panel, position):
        """`"Réglages": Bool(is_panel_toggle: true)` turns its panel on and off, as Blender has it."""
        flag = next((a for a in p.options if a.name == "is_panel_toggle"), None)
        if flag is None or not (isinstance(flag.value, ast.Bool) and flag.value.value):
            return
        if side != "INPUT" or panel is None or p.type != "Bool":
            self.error(flag, "is_panel_toggle : une entrée Bool, la première d'un panneau")
        elif position != 0:
            self.error(flag, f"is_panel_toggle : l'interrupteur vient en premier dans le panneau « {panel.name} »")
        elif p.name != panel.name:
            self.error(flag, f"is_panel_toggle : l'interrupteur porte le nom de son panneau, "
                             f"« {panel.name} » (Blender le renomme ainsi)")

    def literal_options(self, items, what):
        """{name: value} of `(name: value, …)` settings, each a plain value: Blender checks the names."""
        found = {}
        for a in items:
            if a.name in found:
                self.error(a, f"{what} « {a.name} » donné deux fois")
                continue
            v = a.value
            if isinstance(v, ast.Ref):
                found[a.name] = v.name
            elif isinstance(v, (ast.Number, ast.String, ast.Bool, ast.Neg)) and isinstance(self.eval(v), Lit):
                found[a.name] = self.eval(v).value
            else:
                self.error(a, f"{what} « {a.name} » : un nombre, true/false, un texte ou une valeur comme FACTOR")
        return found

    # Interface

    def defaults(self):
        """{input key: {"value", "min", "max", "implicit"}} from `name: Type = default in lo..hi`."""
        for o in self.g.outputs:
            if o.default is not None or o.range is not None:
                self.error(o, f"la sortie « {o.name} » n'a ni valeur par défaut ni bornes")
        out = {}
        for p in self.g.params:
            spec = {}
            d = p.default
            if isinstance(d, ast.Call) and d.name in IMPLICIT:
                mode, wanted = IMPLICIT[d.name]
                if d.args:
                    self.error(d, f"{d.name}() en valeur par défaut ne prend pas d'argument")
                elif p.type != wanted:
                    self.error(d, f"{d.name}() ne sert de valeur par défaut qu'à une entrée {wanted}")
                else:
                    spec["implicit"] = mode
            elif d is not None:
                value = self.default_value(p, d)
                if value is not None:
                    spec["value"] = value
            if p.range is not None:
                bounds = self.bounds(p)
                if bounds is not None:
                    spec.update((k, v) for k, v in zip(("min", "max"), bounds) if v is not None)
            if spec:
                out[p.key] = spec
        return out

    def options(self):
        """{(side, name): {property: value}} from `x: Float(subtype: FACTOR, …)`.

        The property names are Blender's, checked by the builder; here only their values are."""
        out = {}
        for side, params in (("INPUT", self.g.params), ("OUTPUT", self.g.outputs)):
            for p in params:
                found = {}
                for a in p.options:
                    if a.name in WRITTEN_ELSEWHERE:
                        self.error(a, f"{a.name} s'écrit {WRITTEN_ELSEWHERE[a.name]}")
                        continue
                    if a.name in found:
                        self.error(a, f"option « {a.name} » donnée deux fois")
                        continue
                    value = self.option_value(a)
                    if value is not None:
                        found[a.name] = value
                if found:
                    out[(side, p.key)] = found
        return out

    def option_value(self, a):
        """The value of `option: value`, a literal or an enum name; None after an error."""
        v = a.value
        if isinstance(v, ast.Ref):
            return v.name
        if isinstance(v, (ast.Number, ast.String, ast.Bool, ast.Neg)) and isinstance(self.eval(v), Lit):
            return self.eval(v).value
        self.error(a, f"option « {a.name} » : un nombre, true/false, un texte ou une valeur comme FACTOR")
        return None

    def item_options(self, c, a):
        """{option: value} from `nom(option: valeur): …`, by the item's Blender property names.

        The names are checked by the builder, against the item; here only the values are."""
        found = {}
        for o in a.options:
            if o.name in ("name", "socket_type", "data_type", "type"):
                self.error(o, f"{c.name} : le nom et le type d'un item s'écrivent « nom: valeur »")
                continue
            if o.name in found:
                self.error(o, f"option « {o.name} » donnée deux fois")
                continue
            value = self.option_value(o)
            if value is not None:
                found[o.name] = value
        return found

    def default_value(self, p, d):
        t = p.type
        if t in NO_DEFAULT:
            self.error(d, f"une entrée {t} n'a pas de valeur par défaut")
            return None
        if t == "Menu" and isinstance(d, (ast.Ref, ast.String)):
            return d.name if isinstance(d, ast.Ref) else d.value
        if not isinstance(d, (ast.Number, ast.String, ast.Bool, ast.Tuple, ast.Neg)):
            self.error(d, f"valeur par défaut de « {p.name} » : un nombre, un tuple, true/false, un texte"
                          f" ou {', '.join(n + '()' for n in IMPLICIT)}")
            return None
        v = self.eval(d)
        if v is None:
            return None
        if t == "Float" and v.type in ("Int", "Float"):
            return float(v.value)
        if t in ("Int", "Bool") and v.type == t:
            return v.value
        # A Vector of 2 or 4 numbers sets the socket's dimensions
        if t == "Vector" and isinstance(v.value, tuple) or t == "Rotation" and v.type == "Vector" and len(v.value) == 3:
            return v.value
        if t == "Color" and v.type in ("Vector", "Color") and len(v.value) in (3, 4):
            return v.value
        if (t == "String" or t in DATABLOCKS) and v.type == "String":
            return v.value
        self.error(d, f"valeur par défaut de type {v.type} pour une entrée {t}")
        return None

    def bounds(self, p):
        at = p.range[0] or p.range[1]
        if p.type not in RANGED:
            self.error(at, f"une entrée {p.type} n'a pas de bornes ; bornes pour : {', '.join(sorted(RANGED))}")
            return None
        values = []
        for b in p.range:
            if b is None:
                values.append(None)
                continue
            v = self.eval(b) if isinstance(b, (ast.Number, ast.Neg)) else None
            if not (isinstance(v, Lit) and v.type in ("Int", "Float")) or p.type == "Int" and v.type != "Int":
                self.error(b, f"borne de « {p.name} » : un nombre{' entier' if p.type == 'Int' else ''}")
                return None
            values.append(v.value if p.type == "Int" else float(v.value))
        if None not in values and values[0] > values[1]:
            self.error(at, f"bornes de « {p.name} » : le min dépasse le max")
            return None
        return tuple(values)

    # Statements

    def statements(self, body, gout, frame):
        """Check a block; the nodes each statement makes go into `frame`."""
        for stmt in body:
            if self.returned and not (isinstance(stmt, ast.Frame) and not stmt.body):
                self.error(stmt, "instruction après return")
                return
            created = len(self.nodes)
            self.frame_now = frame
            if isinstance(stmt, ast.Frame):
                self.frame_stmt(stmt, gout, frame)
                continue
            if isinstance(stmt, ast.Assign):
                self.assign_stmt(stmt)
            elif self.zone is not None:
                self.zone_return(stmt)
                self.returned = stmt
                self.zone.out.frame = frame
                self.look(self.zone.out, stmt.look)
            else:
                self.return_stmt(stmt, gout)
                self.returned = stmt
                gout.frame = frame
                self.look(gout, stmt.look)
            for n in self.nodes[created:]:
                # A repeat body has placed its own nodes, frames included
                if n.frame is None:
                    n.frame = frame

    def frame_stmt(self, f, gout, parent):
        color = None
        if f.color is not None:
            color = colors.rgb(f.color[1:])
            if color is None:
                self.error(f, f"couleur « {f.color} » inconnue : #rrggbb, #rgb ou un nom CSS (#orange, #teal…)")
        if f.continued:
            # The statements go on in the last frame of that title opened in the same block
            known = self.last_frame.get((parent, f.label))
            if known is None:
                title = f"« {f.label} »" if f.label is not None else "sans titre"
                self.error(f, f"pas de frame {title} plus haut dans ce bloc à continuer")
                return
            self.statements(f.body, gout, known)
            return
        frame = ir.Frame(f"f{len(self.frames)}", f.label, color, parent, f.line, f.col)
        self.frames.append(frame)
        if f.body:
            # A note is not continued: the frames around statements are
            self.last_frame[(parent, f.label)] = frame.id
        self.statements(f.body, gout, frame.id)

    def assign_stmt(self, stmt):
        if stmt.name in self.env:
            self.error(stmt, f"« {stmt.name} » est déjà défini")
            return
        created = len(self.nodes)
        if isinstance(stmt.value, ast.Repeat):
            value = self.state_zone(stmt.value, stmt.name, "repeat")
        elif isinstance(stmt.value, ast.Simulate):
            value = self.state_zone(stmt.value, stmt.name, "simulate")
        elif isinstance(stmt.value, ast.Foreach):
            value = self.foreach(stmt.value, stmt.name)
        elif isinstance(stmt.value, ast.Closure):
            value = self.closure(stmt.value, stmt.name)
        else:
            value = self.eval(stmt.value)
        if value is None:
            # Keep the name known, so later uses do not report it again
            self.env[stmt.name] = None
            return
        made = isinstance(value, Out) and value.node in {n.id for n in self.nodes[created:]}
        if made:
            node = next(n for n in self.nodes if n.id == value.node)
            if node.name is None:
                node.name = stmt.name
            self.look(node, stmt.look)
        elif stmt.look is not None:
            self.error(stmt.look, f"@ : « {stmt.name} » ne fait pas de nœud à lui")
        self.env[stmt.name] = value

    def look(self, node, look):
        """`@ "Label" #color hide mute`: the Blender properties of how a node is shown."""
        if look is None:
            return
        if look.label is not None:
            node.look["label"] = look.label
        if look.color is not None:
            color = colors.rgb(look.color[1:])
            if color is None:
                self.error(look, f"couleur « {look.color} » inconnue : #rrggbb, #rgb ou un nom CSS (#orange, #teal…)")
            else:
                node.look["use_custom_color"] = True
                node.look["color"] = color
        node.look.update((flag, True) for flag in look.flags)

    def return_stmt(self, stmt, gout):
        gout.line, gout.col = stmt.line, stmt.col
        outs = [Socket(o.name, o.key, o.type) for o in self.g.outputs]
        if isinstance(stmt.value, ast.Record):
            # Outputs left out stay unlinked, as Blender allows
            given = {}
            for f in self.untyped(stmt.value.fields):
                sock = find_socket(outs, f.name)
                if isinstance(sock, list):
                    self.error(f, f"« {f.name} » est ambigu ; sorties : {', '.join(s.identifier for s in sock)}")
                    continue
                if sock is None:
                    self.error(f, f"« {f.name} » n'est pas une sortie ; sorties : {', '.join(s.name for s in outs)}")
                    continue
                if sock.identifier in given:
                    self.error(f, f"sortie « {f.name} » donnée deux fois")
                    continue
                given[sock.identifier] = f
                value = self.eval(f.value)
                if value is not None:
                    self.connect(gout, sock, value, f, "return")
            return
        if not self.g.single_output:
            self.error(stmt, f"ce graph a plusieurs sorties : return ({', '.join(s.name + ': …' for s in outs)})")
            return
        value = self.eval(stmt.value)
        if value is not None:
            self.connect(gout, outs[0], value, stmt.value, "return")

    # Zones

    def state_zone(self, e, name, word):
        """A Repeat or a Simulation zone: its input node takes the starting states (and a
        Repeat its count), its body computes the next states from the current ones, its
        output node gives the last."""
        repeat = word == "repeat"
        zin = ir.Node(f"n{len(self.nodes)}", ir.REPEAT_INPUT if repeat else ir.SIMULATION_INPUT,
                      line=e.line, col=e.col)
        zout = ir.Node(f"n{len(self.nodes) + 1}", ir.REPEAT_OUTPUT if repeat else ir.SIMULATION_OUTPUT,
                       line=e.line, col=e.col)
        zin.pair = zout.id
        self.nodes += [zin, zout]
        count = self.eval(e.count) if repeat else None
        allowed = REPEAT_ITEMS if repeat else SIMULATION_ITEMS
        starts, items = [], []
        for a in e.states:
            v = self.zone_value(a)
            if key(a.name) in {key(n) for n, _t in items}:
                self.error(a, f"état « {a.name} » déclaré deux fois")
                continue
            if key(a.name) in STATE_NAMES[word]:
                self.error(a, STATE_NAMES[word][key(a.name)])
                continue
            if v is None:
                continue
            if isinstance(v, Sym):
                self.error(a, f"nom inconnu « {v.name} »")
                continue
            t = value_type(v)
            if t not in allowed:
                self.error(a, f"un état de {word} ne peut pas être de type {t}")
                continue
            items.append((a.name, t))
            starts.append((a, v))
        zin.items = zout.items = items
        states = [Socket(n, n, t) for n, t in items]
        if repeat:
            zin_inputs = [Socket("Iterations", "Iterations", "Int")] + states
            zin_outputs = [Socket("Iteration", "Iteration", "Int")] + states
            skip = None
        else:
            zin_inputs = states
            zin_outputs = [Socket("Delta Time", "Delta Time", "Float")] + states
            skip = Socket("Skip", "Skip", "Bool")
        zin.n_inputs, zin.n_outputs = len(zin_inputs), len(zin_outputs)
        zout.n_inputs, zout.n_outputs = len(states) + (skip is not None), len(states)
        if count is not None:
            self.connect(zin, zin_inputs[0], count, e.count, word)
        for (a, v), sock in zip(starts, states):
            if not isinstance(v, Empty):
                self.connect(zin, sock, v, a, word)

        # The body sees the outer names, the states and the input's own output; its names stay inside
        zone = Zone(word, zout, states, skip)
        names = {key(s.name): s for s in states}
        names["iteration" if repeat else "delta_time"] = zin_outputs[0]
        self.body(e, name, zone, zin, zin_outputs, names)
        # A state the body does not return goes on unchanged
        for sock in states:
            if sock.name not in zone.given:
                zout.links.append((sock.identifier, ir.Link(zin.id, sock.identifier)))
        # With no state left, uses of the name would only repeat the error
        return Out(zout.id, states, None, name) if states else None

    def foreach(self, e, name):
        """A For Each Geometry Element zone: its input node takes the geometry, the selection
        and the input items, its body runs once per element, and the items its return gives
        make the output node's main and generation items."""
        zin = ir.Node(f"n{len(self.nodes)}", ir.FOREACH_INPUT, line=e.line, col=e.col)
        zout = ir.Node(f"n{len(self.nodes) + 1}", ir.FOREACH_OUTPUT, line=e.line, col=e.col)
        zin.pair = zout.id
        zout.items = []
        self.nodes += [zin, zout]
        geometry = self.zone_value(e.geometry)
        selection, given, values, items = None, set(), [], []
        for a in e.args:
            k = key(a.name)
            if k in given:
                self.error(a, f"« {a.name} » donné deux fois")
                continue
            given.add(k)
            if k == "domain":
                if isinstance(a.value, ast.Ref) and a.value.name in FOREACH_DOMAINS:
                    zout.props["domain"] = a.value.name
                else:
                    self.error(a, f"domain attend une valeur parmi {', '.join(FOREACH_DOMAINS)}")
                continue
            if k == "selection":
                selection = (self.eval(a.value), a)
                continue
            if k in ("index", "element"):
                self.error(a, f"« {k} » est {'le numéro' if k == 'index' else 'la géométrie'} de l'élément : "
                              "choisir un autre nom d'item")
                continue
            v = self.zone_value(a)
            if v is None:
                continue
            if isinstance(v, Sym):
                self.error(a, f"nom inconnu « {v.name} »")
                continue
            t = value_type(v)
            if t not in FOREACH_INPUT_ITEMS:
                self.error(a, f"un item d'entrée de foreach ne peut pas être de type {t}")
                continue
            items.append((a.name, t))
            values.append((a, v))
        zin.items = items
        sockets = [Socket(n, n, t) for n, t in items]
        zin_inputs = [Socket("Geometry", "Geometry", "Geometry"), Socket("Selection", "Selection", "Bool")] + sockets
        zin_outputs = [Socket("Index", "Index", "Int"), Socket("Element", "Element", "Geometry")] + sockets
        zin.n_inputs, zin.n_outputs = len(zin_inputs), len(zin_outputs)
        if isinstance(geometry, Sym):
            self.error(e.geometry, f"nom inconnu « {geometry.name} »")
        elif isinstance(geometry, Empty) and geometry.type != "Geometry":
            self.error(e.geometry, f"foreach.geometry attend Geometry, reçoit {geometry.type}")
        elif geometry is not None and not isinstance(geometry, Empty):
            self.connect(zin, zin_inputs[0], geometry, e.geometry, "foreach")
        if selection is not None and selection[0] is not None:
            self.connect(zin, zin_inputs[1], *selection, "foreach")
        for (a, v), sock in zip(values, sockets):
            if not isinstance(v, Empty):
                self.connect(zin, sock, v, a, "foreach")

        zone = Zone("foreach", zout, [], None)
        zone.outputs = [Socket("Geometry", ir.FOREACH_GEOMETRY, "Geometry")]
        names = {key(s.name): s for s in sockets}
        names.update(index=zin_outputs[0], element=zin_outputs[1])
        self.body(e, name, zone, zin, zin_outputs, names)
        zout.n_outputs = len(zone.outputs)
        return Out(zout.id, zone.outputs, None, name)

    def body(self, e, name, zone, zin, zin_outputs, names):
        """Check a zone's body, which sees the outer names and `names`, outputs of the zone's input."""
        saved = self.env, self.returned, self.zone
        self.env = dict(self.env)
        for k, sock in names.items():
            self.env[k] = Out(zin.id, zin_outputs, sock, k)
        self.returned = None
        self.zone = zone
        frame = self.frame_now
        self.statements(e.body, None, frame)
        if not self.returned:
            self.error(e, f"return manquant dans {'la' if zone.word == 'closure' else 'le'} {zone.word} de « {name} »")
        zin.frame = zone.out.frame = frame
        self.env, self.returned, self.zone = saved
        self.frame_now = frame

    def zone_value(self, a):
        """The value of an item, an Arg (or an expression): a type alone is an item with no value,
        `cache: Bundle`; `nom: Type = valeur` gives the item that type, `nom: Type = _` none."""
        if isinstance(a, ast.Arg) and a.type is not None:
            t = a.type.type
            if t not in TYPES:
                self.error(a.type, f"type « {t} » inconnu ; types : {', '.join(TYPES)}")
                return None
            if is_no_value(a.value):
                return Empty(t)
            v = self.eval(a.value)
            return Typed(v, t) if v is not None else None
        v = self.eval(a.value if isinstance(a, ast.Arg) else a)
        if isinstance(v, Sym) and v.name in TYPES:
            return Empty(v.name)
        return v

    def zone_return(self, stmt):
        if self.zone.word == "foreach":
            self.foreach_return(stmt)
            return
        zone, word = self.zone, self.zone.word
        states = zone.states
        if word == "closure":
            what, whats, twice = "une sortie de la closure", "sorties", "sortie « {} » rendue deux fois"
        else:
            what, whats, twice = f"un état du {word}", "états", "état « {} » rendu deux fois"
        if isinstance(stmt.value, ast.Record):
            for f in stmt.value.fields:
                if zone.skip is not None and key(f.name) == "skip":
                    if "skip" in zone.given:
                        self.error(f, "skip rendu deux fois")
                        continue
                    zone.given.add("skip")
                    value = self.eval(f.value)
                    if value is not None:
                        self.connect(zone.out, zone.skip, value, f, word)
                    continue
                sock = next((s for s in states if key(f.name) == key(s.name)), None)
                if sock is None:
                    self.error(f, f"« {f.name} » n'est pas {what} ; {whats} : "
                                  f"{', '.join(s.name for s in states) or 'aucune'}")
                    continue
                if sock.name in zone.given:
                    self.error(f, twice.format(f.name))
                    continue
                zone.given.add(sock.name)
                self.state(sock, self.zone_value(f), f)
            return
        if len(states) != 1:
            many = (f"ce {word} a plusieurs états" if word != "closure" else
                    "cette closure a plusieurs sorties" if states else "cette closure n'a pas de sortie")
            self.error(stmt, f"{many} : return ({', '.join(s.name + ': …' for s in states)})")
            return
        zone.given.add(states[0].name)
        self.state(states[0], self.zone_value(stmt.value), stmt.value)

    def state(self, sock, value, at):
        """The next value of a state: linked, set, or left empty by its type alone."""
        if isinstance(value, Empty):
            if value.type != sock.type:
                self.error(at, f"{self.zone.word}.{sock.key} attend {sock.type}, reçoit {value.type}")
        elif value is not None:
            self.connect(self.zone.out, sock, value, at, self.zone.word)

    def foreach_return(self, stmt):
        """The items of a For Each output: main items, then each Geometry with its attributes."""
        zone = self.zone
        if not isinstance(stmt.value, ast.Record):
            self.error(stmt, "un foreach rend ses items par nom : return (valeur: v, mesh: g, …)")
            return
        main, generation, seen = [], [], set()
        for f in stmt.value.fields:
            if key(f.name) in seen:
                self.error(f, f"item « {f.name} » rendu deux fois")
                continue
            seen.add(key(f.name))
            v = self.zone_value(f)
            if v is None:
                continue
            if isinstance(v, Sym):
                self.error(f, f"nom inconnu « {v.name} »")
                continue
            t = value_type(v)
            if t == "Geometry" or generation:
                if t not in FOREACH_ITEMS and t != "Geometry":
                    self.error(f, f"un attribut généré par foreach ne peut pas être de type {t}")
                    continue
                generation.append((f, v, t))
            elif t not in FOREACH_ITEMS:
                self.error(f, f"un item de foreach ne peut pas être de type {t}")
                continue
            else:
                main.append((f, v, t))
        zone.out.items = [(f.name, t) for f, _v, t in main + generation]
        zone.out.main = len(main)
        zone.out.n_inputs = len(zone.out.items)
        sockets = [Socket(n, n, t) for n, t in zone.out.items]
        if any(s.key == "geometry" for s in sockets):
            # Then only the zone's name alone gives it
            zone.outputs = [Socket(ir.FOREACH_GEOMETRY, ir.FOREACH_GEOMETRY, "Geometry")]
        zone.outputs += sockets
        for (f, v, _t), sock in zip(main + generation, sockets):
            if not isinstance(v, Empty):
                self.connect(zone.out, sock, v, f, "foreach")

    def untyped(self, fields):
        """The fields of a return: a type before `=` belongs to an item, not to an output."""
        for f in fields:
            if f.type is not None:
                self.error(f, f"« {f.name} » : un type ne s'écrit pas dans un return")
            else:
                yield f

    # Closure zones

    def closure(self, e, name):
        """A Closure zone: its input node gives the closure's inputs to its body, its output
        node takes what the body returns and gives the closure. The body captures the outer names."""
        cin = ir.Node(f"n{len(self.nodes)}", CLOSURE_INPUT, line=e.line, col=e.col)
        cout = ir.Node(f"n{len(self.nodes) + 1}", CLOSURE_OUTPUT, line=e.line, col=e.col)
        cin.pair = cout.id
        self.nodes += [cin, cout]
        options = {}
        items = self.declared(e.params, "in", options, "closure")
        outs = self.declared(e.outputs, "out", options, "closure")
        for n in (cin, cout):
            n.items, n.out_items, n.item_options = items, outs, options
        inputs = item_sockets(items)
        results = item_sockets(outs)
        cin.n_outputs = len(inputs)
        cout.n_inputs, cout.n_outputs = len(results), 1

        # The body sees the outer names and the inputs; its own names stay inside
        zone = Zone("closure", cout, results, None)
        self.body(e, name, zone, cin, inputs, {key(s.name): s for s in inputs})
        self.signatures[cout.id] = (items, outs, options)
        return Out(cout.id, [Socket("Closure", "Closure", "Closure")], None, name)

    def declared(self, params, side, options, what):
        """(name, type) of items declared as `name: Type(structure_type: …)`; their options go in `options`."""
        items = []
        for p in params:
            if p.type not in ITEM_TYPES:
                self.error(p, f"type « {p.type} » inconnu ; types : {', '.join(ITEM_TYPES)}")
                continue
            if p.default is not None or p.range is not None:
                self.error(p, f"un item de {what} n'a ni valeur par défaut ni bornes")
                continue
            if key(p.name) in {key(n) for n, _t in items}:
                self.error(p, f"item « {p.name} » déclaré deux fois")
                continue
            items.append((p.name, p.type))
            found = self.item_options(p, p)
            if found:
                options[p.name if side == "in" else ("out", p.name)] = found
        return items

    # Bundles and closure calls

    def signature_call(self, c, spec, piped, target=None):
        """Combine Bundle, Separate Bundle and Evaluate Closure: nodes whose items the text gives a type each.

        `target` is the closure of `f(x: …)`, a call on a name; else it is the first positional value."""
        node = ir.Node("", spec.bl_idname, line=c.line, col=c.col)
        positional = [(piped, c)] if piped is not None else []
        named = []
        for a in c.args:
            if a.name is not None and a.type is None and a.name in spec.props:
                v = self.eval(a.value)
                if isinstance(v, (Lit, Sym)):
                    self.prop(node, spec.props[a.name], v, a)
                    continue
            if a.name is None:
                positional.append((None if is_no_value(a.value) else self.eval(a.value), a.value))
            else:
                named.append((a, self.zone_value(a)))
        fixed = SIGNATURE_NODES[spec.bl_idname]["inputs"][0]
        if target is not None:
            if positional:
                self.error(positional[0][1], f"une closure prend ses entrées par nom : {c.name}(x: …)")
                return None
            positional = [(target, c)]
        if len(positional) > fixed:
            if spec.bl_idname == SEPARATE_BUNDLE:
                self.error(positional[fixed][1], "SeparateBundle prend le bundle seul : "
                                                 "SeparateBundle(b) -> (nom: Type, …)")
            else:
                self.error(positional[fixed][1], f"{c.name} : les items se donnent par nom, {c.name}(…, nom: valeur)")
            return None

        options = {}
        if spec.bl_idname == COMBINE_BUNDLE:
            if c.outputs is not None:
                self.error(c, "CombineBundle n'a qu'une sortie, le bundle : pas de « -> »")
                return None
            items, values = self.given_items(c, named, options)
        elif spec.bl_idname == SEPARATE_BUNDLE:
            if named:
                self.error(named[0][0], "SeparateBundle déclare ses items après « -> » : "
                                        "SeparateBundle(b) -> (nom: Type, …)")
                return None
            if c.outputs is None:
                self.error(c, "SeparateBundle déclare ses items : SeparateBundle(b) -> (nom: Type, …)")
                return None
            items, values = [], []
        elif c.outputs is not None:
            items, values = self.given_items(c, named, options)
        else:
            # Evaluate Closure without `->`: the items of the closure it is given, defined in this graph
            closure = positional[0][0] if positional else None
            sig = self.signatures.get(closure.node) if isinstance(closure, Out) else None
            if sig is None:
                self.error(c, f"{c.name} : la signature de la closure n'est pas connue ici ; écrire ses items : "
                              f"{c.name}(x: Float = …) -> (r: Float)")
                return None
            items, outs, sig_options = sig
            options = dict(sig_options)
            node.out_items = outs
            values = []
            for a, v in named:
                if isinstance(v, (Empty, Typed)):
                    self.error(a, f"« {a.name} » : avec un type, écrire aussi les sorties : {c.name}(…) -> (…)")
                    return None
                if a.options:
                    self.error(a, f"« {a.name} » : avec des options, écrire aussi les sorties : {c.name}(…) -> (…)")
                    return None
                name = next((n for n, _t in items if key(n) == key(a.name)), None)
                if name is None:
                    self.error(a, f"la closure n'a pas d'entrée « {a.name} » ; entrées : "
                                  f"{', '.join(n for n, _t in items) or 'aucune'}")
                elif v is not None and not (isinstance(v, Sym) and v.name == NO_VALUE):
                    values.append((name, v, a))
        if items is None:
            return None
        if c.outputs is not None:
            node.out_items = self.declared(c.outputs, "out", options, c.name)
        if spec.bl_idname != SEPARATE_BUNDLE:
            node.items = items
        node.item_options = options

        sides = SIGNATURE_NODES[spec.bl_idname]
        fixed_inputs, fixed_outputs = self.schema.sockets(self.g.kind, spec, node.props)
        inputs = fixed_inputs[:sides["inputs"][0]] + item_sockets(node.items or [])
        outputs = fixed_outputs[:sides["outputs"][0]] + item_sockets(node.out_items or [])
        node.n_inputs, node.n_outputs = len(inputs), len(outputs)
        # Numbered once its arguments have made their own nodes
        node.id = f"n{len(self.nodes)}"
        self.nodes.append(node)
        for (v, a), sock in zip(positional, inputs):
            if v is not None:
                self.connect(node, sock, v, a, c.name)
        names = [n for n, _t in node.items or []]
        for name, v, a in values:
            self.connect(node, inputs[fixed + names.index(name)], v, a, c.name)
        return Out(node.id, outputs, None, c.name)

    def given_items(self, c, named, options):
        """(items, values) from `name: value`, `name: Type = value` and `name: Type` arguments;
        (None, None) on error."""
        items, values = [], []
        ok = True
        for a, v in named:
            if key(a.name) in {key(n) for n, _t in items}:
                self.error(a, f"{c.name} : « {a.name} » donné deux fois")
                ok = False
                continue
            if isinstance(v, Sym):
                if v.name == NO_VALUE:
                    self.error(a, f"« {a.name} » n'a pas de valeur : écrire son type, {a.name}: Float")
                else:
                    self.error(a.value, f"nom inconnu « {v.name} »")
                ok = False
                continue
            if v is None:
                ok = False
                continue
            t = value_type(v)
            if t not in ITEM_TYPES:
                self.error(a, f"{c.name} : pas d'item de type {t}")
                ok = False
                continue
            items.append((a.name, t))
            found = self.item_options(c, a)
            if found:
                options[a.name] = found
            if not isinstance(v, Empty):
                values.append((a.name, v, a))
        return (items, values) if ok else (None, None)

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
        if isinstance(e, ast.BinOp) and e.op == "+":
            return self.plus(e)
        if isinstance(e, ast.BinOp):
            return self.formula(e, e.op, [(self.eval(e.left), e.left), (self.eval(e.right), e.right)])
        if isinstance(e, ast.Not):
            return self.formula(e, "not", [(self.eval(e.value), e.value)])
        if isinstance(e, ast.Neg):
            v = self.eval(e.value)
            if isinstance(v, Lit) and v.type in ("Int", "Float"):
                return Lit(-v.value, v.type)
            if isinstance(v, Lit) and isinstance(v.value, tuple):
                return Lit(tuple(-x for x in v.value), v.type)
            # -x is x times -1: Math Multiply, or Vector Math Scale
            return self.formula(e, "neg", [(v, e.value), (Lit(-1.0, "Float"), e)])
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
        if e.socket in sugar.COMPONENTS and target.socket is not None and target.socket.type == "Vector" \
                and (target.chosen is not None or find_socket(target.outputs, e.socket) is None):
            return self.component(e, target)
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

    def component(self, e, target):
        """`v.x`: one Separate XYZ per vector, shared by its components."""
        src = target.socket
        spec = self.schema.node(self.g.kind, "SeparateXYZ")
        if spec is None:
            self.error(e, f"pas de SeparateXYZ dans un arbre {self.g.kind}")
            return None
        inputs, outputs = self.schema.sockets(self.g.kind, spec, {})
        memo = (target.node, src.identifier)
        if memo not in self.separated:
            node = ir.Node(f"n{len(self.nodes)}", spec.bl_idname, n_inputs=len(inputs),
                           n_outputs=len(outputs), line=e.line, col=e.col)
            self.nodes.append(node)
            self.connect(node, inputs[0], target, e, "SeparateXYZ")
            self.separated[memo] = node.id
        sock = find_socket(outputs, e.socket)
        return Out(self.separated[memo], outputs, sock, f"{target.label}.{e.socket}")

    def plus(self, e):
        """`a + b + c`: one Join Geometry for geometries, else Math or Vector Math, pair by pair.

        Joining is the same whatever the parentheses, so `a + (b + c)` is one
        Join too: the canonical graph has no Join feeding a Join of its own.
        """
        steps = []
        while isinstance(e, ast.BinOp) and e.op == "+":
            steps.append(e)
            e = e.left
        steps.reverse()
        v = self.eval(e)
        if value_type(v) == "Geometry":
            return self.join(steps[0], [(v, e)] + [(self.eval(t), t) for s in steps for t in plus_terms(s.right)])
        for s in steps:
            right = self.eval(s.right)
            if value_type(right) == "Geometry" and v is not None:
                self.error(s.left, f"« + » joint des Geometry, pas {value_type(v)}")
                return None
            v = self.formula(s, "+", [(v, s.left), (right, s.right)])
        return v

    def join(self, at, terms):
        for v, a in terms:
            if v is None:
                return None
            if isinstance(v, Sym):
                self.error(a, f"nom inconnu « {v.name} »")
                return None
            if value_type(v) != "Geometry":
                self.error(a, f"« + » joint des Geometry, pas {value_type(v)}")
                return None
        spec = self.schema.node(self.g.kind, "JoinGeometry")
        if spec is None:
            self.error(at, f"pas de JoinGeometry dans un arbre {self.g.kind}")
            return None
        inputs, outputs = self.schema.sockets(self.g.kind, spec, {})
        node = ir.Node(f"n{len(self.nodes)}", spec.bl_idname, n_inputs=len(inputs), n_outputs=len(outputs),
                       line=at.line, col=at.col)
        self.nodes.append(node)
        for v, a in terms:
            self.connect(node, inputs[0], v, a, "+")
        return Out(node.id, outputs, None, "+")

    def is_function(self, name):
        return (name in sugar.FUNCS and name not in self.graphs
                and self.schema.node(self.g.kind, name) is None)

    def formula(self, at, op, operands):
        """A Math, Vector Math or Compare node for an operator or a function, from evaluated operands."""
        for v, a in operands:
            if v is None:
                return None
            if isinstance(v, Sym):
                self.error(a, f"nom inconnu « {v.name} »")
                return None
        try:
            name, props, order = sugar.choose(op, [value_type(v) for v, _a in operands])
        except ValueError as err:
            self.error(at, str(err))
            return None
        spec = self.schema.node(self.g.kind, name)
        if spec is None:
            self.error(at, f"pas de {name} dans un arbre {self.g.kind}")
            return None
        inputs, outputs = self.schema.sockets(self.g.kind, spec, props)
        n_inputs = len(inputs)
        if name in sugar.OPERANDS:
            inputs = inputs[:sugar.OPERANDS[name]]
        if len(inputs) != len(operands):
            self.error(at, f"{op} attend {len(inputs)} argument(s), en reçoit {len(operands)}")
            return None
        node = ir.Node(f"n{len(self.nodes)}", spec.bl_idname, props=dict(props), n_inputs=n_inputs,
                       n_outputs=len(outputs), line=at.line, col=at.col)
        self.nodes.append(node)
        for sock, i in zip(inputs, order):
            v, a = operands[i]
            self.connect(node, sock, v, a, op)
        return Out(node.id, outputs, None, op)

    def call(self, c, piped=None):
        spec = None if c.name in self.graphs or self.is_function(c.name) else self.schema.node(self.g.kind, c.name)
        if spec is not None and spec.bl_idname in (COMBINE_BUNDLE, SEPARATE_BUNDLE, EVALUATE_CLOSURE):
            return self.signature_call(c, spec, piped)
        if spec is None and c.name not in self.graphs and not self.is_function(c.name) \
                and self.existing_group(c) is None and isinstance(self.env.get(c.name), Out) \
                and value_type(self.env[c.name]) == "Closure":
            # A call on a name that holds a closure, when nothing else has that name: Evaluate Closure
            evaluate = self.schema.node(self.g.kind, "EvaluateClosure")
            if evaluate is not None:
                return self.signature_call(c, evaluate, piped, target=self.env[c.name])
        if c.outputs is not None:
            self.error(c, f"« -> » déclare les items de SeparateBundle ou EvaluateClosure, pas de {c.name}")
            return None
        items = self.takes_items(c.name)
        for a in c.args:
            if a.type is not None and not items:
                self.error(a, f"« {a.name}: {a.type.type} = … » donne le type d'un item : d'un nœud à items, "
                              "d'une zone ou d'EvaluateClosure")
                return None
        if self.is_function(c.name):
            operands = [(piped, c)] if piped is not None else []
            for a in c.args:
                if a.name is not None:
                    self.error(a, f"{c.name} ne prend pas d'argument nommé")
                    return None
                operands.append((self.eval(a.value), a.value))
            return self.formula(c, c.name, operands)

        positional = [(piped, c)] if piped is not None else []
        named = []
        failed = False
        for a in c.args:
            if a.alias and not items:
                self.error(a, f"« {a.name} as {a.alias} » : seuls les items d'un nœud à items prennent une clé")
            if a.options and not items:
                self.error(a, f"« {a.name}(…) » : seuls les items d'un nœud à items prennent des options")
            # An item may be given its type, or be its type alone
            v = self.zone_value(a) if items and a.name is not None else self.eval(a.value)
            failed |= v is None
            if a.name is None:
                positional.append((v, a.value))
            else:
                named.append((a.name, v, a))

        node = ir.Node(f"n{len(self.nodes)}", "", line=c.line, col=c.col)
        spec = None if c.name in self.graphs else self.schema.node(self.g.kind, c.name)
        group = self.existing_group(c) if c.name not in self.graphs and spec is None else None
        if c.name in self.graphs:
            inputs, outputs = self.group_signature(c, node)
            if inputs is None:
                return None
        elif group is not None:
            if isinstance(group, list):
                self.error(c, f"« {c.name} » désigne plusieurs groupes du fichier : "
                              f"{', '.join(g.name for g in group)}")
                return None
            node.bl_idname = GROUP_NODES[self.g.kind]
            node.group = group.name
            inputs = [Socket(n, k, t) for n, k, t in group.keys("INPUT")]
            outputs = [Socket(n, k, t) for n, k, t in group.keys("OUTPUT")]
        else:
            if spec is None:
                if self.unsure:
                    return None
                close = difflib.get_close_matches(c.name, self.schema.node_names(self.g.kind), 3)
                hint = f" ; voulez-vous dire {', '.join(close)} ?" if close else ""
                self.error(c, f"nœud « {c.name} » inconnu dans un arbre {self.g.kind}{hint}")
                return None
            node.bl_idname = spec.bl_idname
            rest = []
            for name, v, a in named:
                if name in spec.props and isinstance(v, (Lit, Sym)) and not a.alias:
                    self.prop(node, spec.props[name], v, a)
                else:
                    rest.append((name, v, a))
            named = rest
            if spec.bl_idname in ITEM_NODES:
                inputs, outputs = self.item_sockets(c, spec, node, positional, named)
                if inputs is None:
                    return None
            else:
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

    def takes_items(self, name):
        spec = None if name in self.graphs else self.schema.node(self.g.kind, name)
        return spec is not None and spec.bl_idname in ITEM_NODES

    def item_sockets(self, c, spec, node, positional, named):
        """(inputs, outputs) of a node whose items the call makes, which it records in node.items."""
        shape = ITEM_NODES[spec.bl_idname]
        fixed = self.schema.sockets(self.g.kind, spec, node.props)[0][:shape.inputs]
        if shape.named:
            if len(positional) > shape.inputs:
                self.error(positional[shape.inputs][1], f"{c.name} : les valeurs se donnent par nom, "
                                                        f"{c.name}(…, nom: valeur)")
                return None, None
            # An item under a key of its own may be named like a fixed input
            given = [(n, v, a) for n, v, a in named if a.alias or find_socket(fixed, n) is None]
            named[:] = [(n, v, a) for n, v, a in named if not a.alias and find_socket(fixed, n) is not None]
        else:
            given = [(str(k), v, a) for k, (v, a) in enumerate(positional[shape.inputs:])]
            del positional[shape.inputs:]
        for name, _v, a in named:
            if a.options:
                self.error(a, f"{c.name} : « {name} » est une entrée du nœud, pas un item ; elle ne prend pas d'options")
        items, values, options, keys = [], [], {}, []
        for name, v, a in given:
            alias = getattr(a, "alias", None)
            if key(name) in {key(n) for n, _t in items}:
                self.error(a, f"{c.name} : « {name} » donné deux fois")
                continue
            if alias and (find_socket(fixed, alias) is not None or alias in spec.props or alias in keys):
                self.error(a, f"{c.name} : la clé « {alias} » est déjà une entrée, un réglage ou un item du nœud")
                continue
            if not alias and shape.named and (key(name) in keys or name in keys):
                self.error(a, f"{c.name} : « {name} » est déjà la clé d'un item")
                continue
            if getattr(a, "options", None):
                options[name] = self.item_options(c, a)
            if isinstance(v, Sym) and v.name == NO_VALUE and not shape.typed:
                # An empty item: no link, its default value (an empty geometry…)
                items.append((name, None))
                keys.append(alias)
                continue
            if isinstance(v, Sym):
                self.error(a, f"nom inconnu « {v.name} »")
                continue
            if v is None:
                continue
            t = value_type(v)
            allowed = shape.types or tuple(ITEM_TYPES)
            if shape.typed and t not in allowed:
                self.error(a, f"{c.name} : pas d'item {t} ; types : {', '.join(allowed)}")
                return None, None
            items.append((name, t))
            keys.append(alias)
            if not isinstance(v, Empty):
                # Its type alone is an item with no link, holding the default value of its type
                values.append((alias or name, v, a))
        if not shape.typed:
            # The items share the node's data_type: written, or the type of the first one
            chosen = node.props.get("data_type")
            typed = [t for _n, t in items if t is not None]
            t = DATA_TYPES.get(chosen) if chosen else typed[0] if typed else "Float"
            if t not in ITEM_TYPES:
                self.error(c, f"{c.name} : pas d'items de type {chosen or t}")
                return None, None
            node.props["data_type"] = ITEM_TYPES[t]
            items = [(name, t) for name, _t in items]
        node.items = items
        node.item_options = {n: o for n, o in options.items() if o}
        inputs, outputs = self.schema.sockets(self.g.kind, spec, node.props)
        # An item with a key of its own goes by it in text, and by its number to the builder
        names = [(k or name, f"#{i}" if k else name) for i, ((name, _t), k) in enumerate(zip(items, keys))]
        sockets = [Socket(n, ident, t) for (n, ident), (_name, t) in zip(names, items)]
        # Each value to its own item, by name: an empty one in between is skipped
        named += values
        added = {"value": sockets, "flag": [Socket(n, ident, "Bool") for n, ident in names]}.get(shape.out, [])
        return inputs[:shape.inputs] + sockets, outputs[:shape.outputs] + added

    def existing_group(self, c):
        """A node group of the file with that key, when the text does not define one."""
        groups = getattr(self.schema, "groups", None)
        return groups(self.g.kind).get(c.name) if groups else None

    def group_signature(self, c, node):
        callee = self.graphs[c.name]
        if callee.kind != self.g.kind:
            self.error(c, f"« {c.name} » est un graph {callee.kind}, pas {self.g.kind}")
            return None, None
        self.calls.add(c.name)
        node.bl_idname = GROUP_NODES[self.g.kind]
        node.group = callee.name
        return ([Socket(p.name, p.key, p.type) for p in callee.params],
                [Socket(o.name, o.key, o.type) for o in callee.outputs])

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
        if isinstance(v, Typed):
            v = v.value
        if isinstance(v, Empty):
            self.error(at, f"{label} : un type seul ({v.type}) ne va qu'à un item")
            return
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
        # A gizmo's value holds a number when nothing is linked to it; a join, nothing
        if sock.multi_input and sock.type in NO_DEFAULT:
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
              or (sock.type in DATABLOCKS and v.type == "String")
              or (sock.type not in STRICT and v.type not in STRICT))
        if not ok:
            self.error(at, f"{where} attend {sock.type}, reçoit {v.type}")
            return
        if sock.type == "Int" and v.type == "Float":
            # Blender would not round it: say so rather than fail at build
            self.error(at, f"{where} attend un entier : {int(v.value)} plutôt que {v.value}")
            return
        node.values[sock.identifier] = v.value


# Interface settings the text writes in their own way, not as options
WRITTEN_ELSEWHERE = {
    "name": "avant les deux-points", "socket_type": "après les deux-points : x: Float",
    "bl_socket_idname": "avec le type et subtype", "default_value": "après = : x: Float = 1.0",
    "min_value": "avec in : x: Float in 0.0..1.0", "max_value": "avec in : x: Float in 0.0..1.0",
    "default_input": "après = : p: Vector = Position()", "dimensions": "par la taille du défaut : (0.5, 0.5)",
}

# Text type -> the socket type of a zone item, for each kind of item Blender takes
REPEAT_ITEMS = {t: v for t, v in ITEM_TYPES.items() if t != "Shader"}
SIMULATION_ITEMS = {t: ITEM_TYPES[t] for t in FIELD_TYPES + ("String", "Geometry", "Bundle")}
FOREACH_INPUT_ITEMS = {t: ITEM_TYPES[t] for t in FIELD_TYPES + ("Menu",)}
FOREACH_ITEMS = {t: ITEM_TYPES[t] for t in FIELD_TYPES}  # main items, and generated attributes
FOREACH_DOMAINS = ("POINT", "EDGE", "FACE", "CORNER", "CURVE", "INSTANCE", "LAYER")

# Names a zone's body gives itself, which no state may take
STATE_NAMES = {
    "repeat": {"iteration": "« iteration » est le numéro du tour : choisir un autre nom d'état"},
    "simulate": {"delta_time": "« delta_time » est le temps écoulé depuis le pas précédent : "
                               "choisir un autre nom d'état",
                 "skip": "« skip » se rend par return (…, skip: …) : choisir un autre nom d'état"},
}
DATA_TYPES = {v: t for t, v in ITEM_TYPES.items()}


def twice_hint(p):
    """How to keep two sockets of the same name: give one a key of its own."""
    return f' ; pour garder les deux, nommer l\'autre avec as : "{p.name}" as {snake(p.name)}_2: {p.type}'


def item_sockets(items):
    """Sockets of declared items, numbered by position: `#0`, `#1`… The builder finds them so."""
    return [Socket(name, f"#{i}", t) for i, (name, t) in enumerate(items)]


def is_no_value(e):
    return isinstance(e, ast.Ref) and e.name == NO_VALUE


def plus_terms(e):
    """The terms of `a + (b + c)`, parentheses aside."""
    if isinstance(e, ast.BinOp) and e.op == "+":
        return plus_terms(e.left) + plus_terms(e.right)
    return [e]


def value_type(v):
    if isinstance(v, Out):
        return v.socket.type if v.socket else None
    if isinstance(v, (Lit, Empty, Typed)):
        return v.type
    return None


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
