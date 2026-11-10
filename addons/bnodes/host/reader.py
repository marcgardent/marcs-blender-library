"""Node group -> AST, the other way round from builder.py.

A node becomes a named statement when several links use it, when its
name was given by hand, or when it sits in another frame than its user;
otherwise it is written inline where it is used. Frames become blocks
around their statements, reroutes are followed. What text cannot hold
yet is reported as warnings, never as a failed export.
"""

import re
from collections import Counter

import bpy

from ..lang import ast, sugar
from ..lang.printer import to_source
from ..lang.ir import REPEAT_INPUT, REPEAT_OUTPUT
from ..lang.schema import IMPLICIT, ITEM_NODES, ITEM_TYPES, NO_VALUE, RESERVED, TYPES, key, snake
from .modules import module_of
from .schema import (PANEL_OPTIONS, SOCKET_TYPES, TREE_FLAGS, TREE_TYPES, BlenderSchema, fresh_item, fresh_options,
                     option_names, root_panel, same_option, snapshot, socket_keys, text_name)

KINDS = {v: k for k, v in TREE_TYPES.items()}
IMPLICIT_CALLS = {mode: name for name, (mode, _type) in IMPLICIT.items()}
INTERFACE_TYPES = {v: k for k, v in TYPES.items()}
GROUP_NODES = {"GeometryNodeGroup", "ShaderNodeGroup", "CompositorNodeGroup"}
SKIP = {"NodeFrame", "NodeReroute"}

# Read, but written wrong: a gizmo's links point at the value it moves, not at what feeds it
NOT_YET = {"GeometryNodeGizmoLinear", "GeometryNodeGizmoDial", "GeometryNodeGizmoTransform"}

FIRST_OPTIONS = {"is_panel_toggle": 0, "subtype": 1, "description": 2}

# Kept for statements even when they hold their default
ALWAYS = {"operation"}

JOIN = "GeometryNodeJoinGeometry"
FORMULA_NODES = {"ShaderNodeMath": "Math", "ShaderNodeVectorMath": "VectorMath", "FunctionNodeCompare": "Compare",
                 "FunctionNodeBooleanMath": "BooleanMath"}
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
    # A group another module built is written as a use of that module, not copied
    home = module_of(tree)
    uses = {}

    def visit(t, seen):
        if t in graphs or t in seen:
            return
        reader = GraphReader(t, schema, warnings)
        # The builder makes a modifier of a graph that no other one of the text calls
        reader.called = t is not tree
        graph = reader.read()
        # Only the groups that reach the output are exported with it
        for callee in sorted(reader.callees, key=lambda c: c.name):
            module = module_of(callee)
            if module is not None and module != home:
                uses.setdefault(module, set()).add(key(callee.name))
            else:
                visit(callee, seen | {t})
        graphs[t] = graph
        order.append(graph)

    visit(tree, frozenset())
    return ast.File(order, [ast.Use(name, sorted(names), source, 0, 0)
                            for (name, source), names in uses.items()]), warnings


class GraphReader:
    def __init__(self, tree, schema, warnings):
        self.tree = tree
        self.schema = schema
        self.kind = KINDS.get(tree.bl_idname)
        self.warnings = warnings
        self.index = {n.name: i for i, n in enumerate(tree.nodes)}
        self.exprs = {}
        self.chain_heads = set()  # ids of calls whose first argument is a geometry name
        self.opened = set()  # frames written as blocks so far
        self.called = False  # another graph of the text calls it

    def warn(self, message):
        self.warnings.append(f"{self.tree.name} : {message}")

    def read(self):
        tree = self.tree
        if self.kind is None:
            raise ValueError(f"{tree.name} n'est pas un arbre de nœuds lisible")
        written = {}  # interface socket identifier -> its Param
        for io in ("INPUT", "OUTPUT"):
            for item in tree.interface.items_tree:
                if item.item_type == "SOCKET" and item.in_out == io:
                    p = self.param(item)
                    written[item.identifier] = self.defaults(p, item) if io == "INPUT" else p
            for ident, k in socket_keys(tree, io).items():
                if k != key(written[ident].name):
                    written[ident].alias = k
        param_tree, output_tree = self.interface(written)
        params, outputs = ast.flatten(param_tree), ast.flatten(output_tree)
        self.param_keys = [p.key for p in params]
        paneled = any(isinstance(i, ast.Panel) for i in output_tree)
        single = len(outputs) == 1 and outputs[0].name == outputs[0].type and not outputs[0].options and not paneled

        outs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
        out = next((n for n in outs if n.is_active_output), outs[0] if outs else None)

        self.incoming = self.resolve_links()
        # A Repeat output reaches its input even when no link joins them
        self.pairs = {n.paired_output.name: n for n in tree.nodes
                      if n.bl_idname == REPEAT_INPUT and n.paired_output is not None}
        reached = self.reach(out)
        self.zone_of = self.zones(reached)
        dead = [n for n in tree.nodes if n.bl_idname not in SKIP and n not in reached
                and n.bl_idname != "NodeGroupInput"]
        if dead:
            self.warn(f"{len(dead)} nœud(s) sans effet sur la sortie, non exportés")
        for n in reached:
            if n.mute:
                self.warn(f"« {n.name} » est désactivé (mute) ; le texte l'exporte actif")

        self.callees = {n.node_tree for n in reached if n.bl_idname in GROUP_NODES and n.node_tree is not None}
        uses, user = {}, {}
        for n in reached:
            for links in self.incoming.get(n.name, {}).values():
                for src, _sock in links:
                    uses[src.name] = uses.get(src.name, 0) + 1
                    user[src.name] = n
        # A Separate XYZ reads as v.x: it vanishes, and v is written once per component
        self.separates = {}
        for n in reached:
            vector = self.incoming.get(n.name, {}).get("Vector")
            if n.bl_idname == "ShaderNodeSeparateXYZ" and vector and not self.hand_named(n):
                self.separates[n.name] = vector[0]
                src = vector[0][0].name
                uses[src] = uses.get(src, 0) + uses.get(n.name, 0) - 1
        taken = set(self.param_keys)
        for rout, rin in self.pairs.items():
            if rout in self.zone_of or any(n.name == rout for n in reached):
                taken.update([key(s.name) for s in self.items(rin.outputs)[1:]] + ["iteration"])
        self.bound = {}
        for n in sorted(reached, key=lambda n: self.index[n.name]):
            if n.bl_idname in ("NodeGroupInput", "NodeGroupOutput", REPEAT_INPUT) or n.name in self.separates:
                continue
            if n.bl_idname == REPEAT_OUTPUT:
                # A zone is a block: always a statement of its own
                self.bound[n.name] = unique(self.binding_name(n), taken)
                continue
            # Written inline, a node would land in its user's frame
            used_by = user.get(n.name)
            while used_by is not None and used_by.name in self.separates:
                used_by = user.get(used_by.name)
            framed_apart = used_by is not None and frame_name(n) != frame_name(used_by)
            if uses.get(n.name, 0) > 1 or self.hand_named(n) or framed_apart:
                self.bound[n.name] = unique(self.binding_name(n), taken)

        body = []
        fields = []
        if out is not None:
            out_inputs = [s for s in out.inputs if s.type != "CUSTOM"]
            # A name two outputs share is no name: the second one goes by its key
            for sock, o in zip(out_inputs, outputs):
                links = self.incoming.get(out.name, {}).get(sock.identifier)
                if links:
                    fields.append((o.alias or o.name, self.use(*links[0])))
        for name in self.statement_order(None):
            node = self.tree.nodes[name]
            body.append((node, ast.Assign(self.bound[name], self.expr(node), 0, 0)))
        if single and fields:
            value = fields[0][1]
        else:
            value = ast.Record([ast.Arg(n, v, 0, 0) for n, v in fields], 0, 0)
        body.append((out, ast.Return(value, 0, 0)))
        graph = ast.Graph(self.kind, tree.name, params, outputs, single, self.framed(body), 0, 0)
        if any(isinstance(i, ast.Panel) for i in param_tree):
            graph.param_tree = param_tree
        if paneled:
            graph.output_tree = output_tree
        graph.settings = self.settings()
        if tree.description:
            graph.description = tree.description.replace('"', "'").replace("\n", " ")
        self.unwritten()
        return graph

    def settings(self):
        """`geometry(is_tool: true) graph …`: the tree's settings that differ from a new tree's.

        is_modifier only when the builder would decide otherwise: it makes a modifier of a
        graph nobody calls whose first input and output are geometries."""
        tree = self.tree
        sockets = [i for i in tree.interface.items_tree if i.item_type == "SOCKET"]
        geometry_first = all(next((i.socket_type for i in sockets if i.in_out == io), None) == "NodeSocketGeometry"
                             for io in ("INPUT", "OUTPUT"))
        fresh = dict(TREE_FLAGS, is_modifier=geometry_first and not self.called)
        return [ast.Arg(f, ast.Bool(getattr(tree, f), 0, 0), 0, 0) for f in TREE_FLAGS
                if hasattr(tree, f) and getattr(tree, f) != fresh[f]]

    def interface(self, written):
        """(inputs, outputs) as the header writes them: Params, and Panels around them.

        A panel goes in the inputs when it holds inputs, or holds nothing, or when a panel
        after it there does: the order of the panels is the inputs', then the outputs'.
        Its settings go where it is written first."""
        given = set()

        def holds(panel, io):
            return any(c.item_type == "SOCKET" and c.in_out == io or c.item_type == "PANEL" and holds(c, io)
                       for c in panel.interface_items)

        def items(panel, io):
            out = [written[c.identifier] for c in panel.interface_items
                   if c.item_type == "SOCKET" and c.in_out == io]
            subs = [c for c in panel.interface_items if c.item_type == "PANEL"]
            if io == "INPUT":
                wanted = [c for c in subs if holds(c, "INPUT") or not holds(c, "OUTPUT")]
                last = subs.index(wanted[-1]) if wanted else -1
                subs = subs[:last + 1]
            else:
                subs = [c for c in subs if holds(c, "OUTPUT")]
            for c in subs:
                out.append(ast.Panel(c.name.replace('"', "'"), items(c, io), 0, 0, self.panel_options(c, given)))
            return out

        root = root_panel(self.tree)
        if root is None:
            return [], []
        return items(root, "INPUT"), items(root, "OUTPUT")

    def panel_options(self, panel, given):
        if panel.identifier in given:
            return []
        given.add(panel.identifier)
        out = []
        for option, fresh in PANEL_OPTIONS.items():
            value = getattr(panel, option)
            if value != fresh:
                out.append(ast.Arg(option, option_literal(panel, option, value), 0, 0))
        return out

    def unwritten(self):
        """Say what the text leaves out: how the nodes look."""
        looks = Counter()
        for n in self.tree.nodes:
            if n.bl_idname in SKIP:
                continue
            looks["libellé"] += bool(n.label)
            looks["couleur"] += n.use_custom_color
            looks["replié"] += n.hide
        if +looks:
            self.warn("présentation non exportée : " + ", ".join(f"{k} ({v})" for k, v in looks.items() if v))

    def param(self, item):
        type = INTERFACE_TYPES.get(item.socket_type)
        if type is None:
            type = item.socket_type.removeprefix("NodeSocket")
            self.warn(f"type d'interface {item.socket_type} inconnu du texte")
        p = ast.Param(item.name, type, 0, 0)
        fresh = fresh_options(item.socket_type, item.in_out)
        # The subtype and the description first, as one reads them; then Blender's order
        for option in sorted(option_names(item), key=lambda o: FIRST_OPTIONS.get(o, len(FIRST_OPTIONS))):
            value = getattr(item, option)
            if option in fresh and not same_option(option, value, fresh[option]):
                p.options.append(ast.Arg(option, option_literal(item, option, value), 0, 0))
        return p

    def defaults(self, p, item):
        """The default, bounds and implicit field of an input, when they differ from a new socket's."""
        fresh = fresh_item(item.socket_type)
        if "default_input" in fresh and item.default_input != fresh["default_input"]:
            call = IMPLICIT_CALLS.get(item.default_input)
            if call is not None and IMPLICIT[call][1] == p.type:
                p.default = ast.Call(call, [], 0, 0)
            else:
                self.warn(f"entrée « {item.name} » : valeur implicite {item.default_input} non exportée")
        elif "default_value" in fresh and not same(snapshot(item), fresh["default_value"]):
            p.default = self.default_literal(item, p.type)
        if "min_value" in fresh:
            bounds = [None if bounded(v, f) else ast.Number(int(v), True, 0, 0) if p.type == "Int" else number(v)
                      for v, f in ((item.min_value, fresh["min_value"]), (item.max_value, fresh["max_value"]))]
            if bounds != [None, None]:
                p.range = tuple(bounds)
        return p

    def default_literal(self, item, type):
        value = snapshot(item)
        if type == "Float":
            return number(value)
        if type == "Int":
            return ast.Number(int(value), True, 0, 0)
        if type == "Bool":
            return ast.Bool(bool(value), 0, 0)
        if type in ("Vector", "Rotation", "Color") and isinstance(value, tuple):
            if type == "Color" and len(value) == 4 and same(value[3], 1.0):
                value = value[:3]
            return ast.Tuple([number(v) for v in value], 0, 0)
        if type == "Menu":
            return enum_literal(value)
        if isinstance(value, str):
            return ast.String(value.replace('"', "'").replace("\n", " "), 0, 0)
        self.warn(f"valeur par défaut de « {item.name} » ({type}) non exportée")
        return None

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
            if n.name in self.pairs:
                stack.append(self.pairs[n.name])
        return reached

    def zones(self, reached):
        """{node name: name of the Repeat output whose body holds it}, the innermost zone.

        A node is in a zone when it depends on the zone's input and the zone's output
        depends on it, as Blender decides.
        """
        depends = {}

        def on(n, rin):
            k = (n.name, rin.name)
            if k not in depends:
                depends[k] = False  # a cycle is no dependency
                depends[k] = any(src == rin or on(src, rin)
                                 for links in self.incoming.get(n.name, {}).values() for src, _s in links)
            return depends[k]

        members = {}
        names = {n.name for n in reached}
        for rout, rin in self.pairs.items():
            if rout not in names:
                continue
            inside, stack, seen = set(), [self.tree.nodes[rout]], set()
            while stack:
                n = stack.pop()
                for links in self.incoming.get(n.name, {}).values():
                    for src, _s in links:
                        if src.name in seen or src == rin:
                            continue
                        seen.add(src.name)
                        if on(src, rin):
                            inside.add(src.name)
                            stack.append(src)
            members[rout] = inside
        zone_of = {}
        for rout, inside in sorted(members.items(), key=lambda kv: len(kv[1])):
            for name in inside:
                zone_of.setdefault(name, rout)
        # The input sits where its output sits
        for rout, rin in self.pairs.items():
            if rout in zone_of:
                zone_of[rin.name] = zone_of[rout]
        return zone_of

    def items(self, sockets):
        return [s for s in sockets if s.type != "CUSTOM"]

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
        if node.bl_idname == REPEAT_INPUT:
            return ast.Ref("iteration" if sock.identifier == "Iteration" else key(sock.name), 0, 0)
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
        # Group sockets and items are named in text, not numbered: Item_1 means nothing there
        named = node.bl_idname in GROUP_NODES or node.bl_idname in ITEM_NODES
        return member(target, socket_name(sock, outputs, named, group_keys(node, "OUTPUT")))

    def expr(self, node):
        if node.name not in self.exprs:
            self.exprs[node.name] = self.repeat(node) if node.bl_idname == REPEAT_OUTPUT else self.call(node)
        return self.exprs[node.name]

    def repeat(self, rout):
        """`repeat(count, state: start, …) { … return (state: next, …) }` for a Repeat zone."""
        rin = self.pairs[rout.name]
        incoming = self.incoming.get(rin.name, {})
        sockets = self.items(rin.inputs)
        values = []
        for sock in sockets:
            links = incoming.get(sock.identifier)
            if links:
                values.append(self.use(*links[0]))
            else:
                # A geometry with nothing linked has no literal: written JoinGeometry(), it would
                # come back with one node more
                values.append(self.literal(rin, sock, {}))
        for sock, v in zip(sockets, values):
            if v is None:
                self.warn(f"repeat « {rout.name} » : « {sock.name} » ({sock.type}) part sans valeur, "
                          "pas encore pris en charge par le texte")
        values = [v if v is not None else ast.Ref("aucun", 0, 0) for v in values]
        count, starts = values[0], values[1:]
        states = [ast.Arg(s.name, v, 0, 0) for s, v in zip(sockets[1:], starts)]
        # In the body a state hides the group input of the same name
        hidden = {key(s.name) for s in sockets[1:]} & set(self.param_keys)
        inside = [n for n, z in self.zone_of.items() if z == rout.name] + [rout.name]
        gin = [s for n in inside for links in self.incoming.get(n, {}).values() for s in links
               if s[0].bl_idname == "NodeGroupInput"]
        for src, sock in gin:
            k = self.param_keys[self.items(src.outputs).index(sock)]
            if k in hidden:
                self.warn(f"repeat « {rout.name} » : son corps lit l'entrée « {k} », cachée par l'état du même nom ; "
                          "pas encore pris en charge par le texte")
                hidden.discard(k)

        statements = [(self.tree.nodes[n], ast.Assign(self.bound[n], self.expr(self.tree.nodes[n]), 0, 0))
                      for n in self.statement_order(rout.name)]
        fields = []
        outgoing = self.incoming.get(rout.name, {})
        for sock in self.items(rout.inputs):
            links = outgoing.get(sock.identifier)
            if links and links[0][0] == rin and links[0][1].name == sock.name:
                continue  # unchanged: the text leaves it out
            value = self.use(*links[0]) if links else self.literal(rout, sock, {})
            if value is not None:
                fields.append((sock.name, value))
        if len(sockets) == 2 and fields:
            ret = ast.Return(fields[0][1], 0, 0)
        else:
            ret = ast.Return(ast.Record([ast.Arg(n, v, 0, 0) for n, v in fields], 0, 0), 0, 0)
        body = self.framed(statements + [(rout, ret)], base=frame_path(rout), notes=False)
        return ast.Repeat(count, states, body, 0, 0)

    def call(self, node):
        group = node.bl_idname in GROUP_NODES
        spec = None if group else self.spec(node)
        if group:
            if node.node_tree is None:
                self.warn(f"« {node.name} » n'a pas d'arbre ; écrit comme un appel vide")
                return ast.Call("missing_group", [], 0, 0)
            name = key(node.node_tree.name)
        elif spec is None or node.bl_idname in NOT_YET:
            name = text_name(node.bl_idname)
            self.warn(f"{name} (« {node.name} ») n'est pas encore pris en charge par le texte")
        else:
            name = spec.name
            if has_items(node) and node.bl_idname not in ITEM_NODES:
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
        if spec is not None and spec.bl_idname == JOIN and not props:
            joined = self.join(node)
            if joined is not None:
                return joined
        if spec is not None and spec.bl_idname in FORMULA_NODES:
            formula = self.formula(node, spec, props)
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
        shape = ITEM_NODES.get(node.bl_idname)
        if shape is not None:
            self.item_types(node, shape, inputs[shape.inputs:], incoming, props)
            # By name, an item called like a fixed input would be read back as that input
            fixed = {snake(s.name) for s in inputs[:shape.inputs]} | {s.identifier for s in inputs[:shape.inputs]}
            clash = [s.name for s in inputs[shape.inputs:]
                     if shape.named and (snake(s.name) in fixed or s.name in fixed)]
            if clash:
                self.warn(f"{name} (« {node.name} ») : l'item « {clash[0]} » porte le nom d'une entrée du nœud, "
                          "pas encore pris en charge par le texte")
        positional = True
        geometry_first = False
        for i, sock in enumerate(inputs):
            item = shape is not None and i >= shape.inputs
            links = incoming.get(sock.identifier)
            if links:
                values = [self.use(*src) for src in links]
            else:
                # An item is made by its value: it is always written
                lit = self.literal(node, sock, {} if item else defaults)
                values = [lit] if lit is not None else []
            if not values and item and not shape.typed:
                values = [ast.Ref(NO_VALUE, 0, 0)]
            elif not values and item:
                self.warn(f"{name} (« {node.name} ») : l'item « {sock.name} » n'a ni lien ni valeur "
                          "que le texte sache écrire ; il est perdu")
            if not values:
                positional = False
                continue
            if item and shape.named:
                positional = False
            label = None if positional else sock.name if item else \
                socket_name(sock, inputs, group, group_keys(node, "INPUT"))
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

    def item_types(self, node, shape, items, incoming, props):
        """The text gives an item the type of its value: say when Blender's differs, and
        write a switch's data_type only when its first item does not tell it."""
        for sock in items:
            links = incoming.get(sock.identifier)
            given = SOCKET_TYPES.get(links[0][1].type) if links else literal_type(snapshot(sock), sock)
            wanted = SOCKET_TYPES.get(sock.type)
            if shape.typed and given is not None and given != wanted:
                self.warn(f"« {node.name} » : l'item « {sock.name} » est un {wanted} qui reçoit un {given} ; "
                          f"relu comme {given}")
        if node.bl_idname == "GeometryNodeMenuSwitch":
            lost = [i.name for i in node.enum_items if i.description]
            if lost:
                self.warn(f"« {node.name} » : description des items {', '.join(lost)} non exportée")
        if not shape.typed:
            # As the checker reads it: the type of the first item that has a value
            given = "Float"
            for sock in items:
                links = incoming.get(sock.identifier)
                t = SOCKET_TYPES.get(links[0][1].type) if links else literal_type(snapshot(sock), sock)
                if t is not None:
                    given = t
                    break
            if ITEM_TYPES.get(given) == node.data_type:
                props.pop("data_type", None)
            else:
                props["data_type"] = node.data_type

    def join(self, node):
        """`a + b + c` for a Join Geometry of two links or more.

        A Join written inline in another one (used nowhere else) melts into
        it: the same geometry in the same order, one node fewer.
        """
        links = self.incoming.get(node.name, {}).get(node.inputs[0].identifier, [])
        if len(links) < 2:
            return None
        terms = []
        for src in links:
            terms += plus_terms(self.use(*src))
        e = terms[0]
        for t in terms[1:]:
            e = ast.BinOp("+", e, t, 0, 0)
        return e

    def formula(self, node, spec, props):
        """`a * 2.0 + sin(t)`, `h > 0.5`, `a and not b` for a Math, Vector Math, Compare or Boolean Math node,
        when it reads back as that node. `props` are the node's non-default props."""
        name, operation = FORMULA_NODES[spec.bl_idname], node.operation
        inputs = [s for s in node.inputs if not s.is_unavailable]
        if name in sugar.OPERANDS:
            # The inputs a formula does not write must be left alone
            defaults, _props = self.schema.defaults(self.kind, spec, props)
            rest = inputs[sugar.OPERANDS[name]:]
            inputs = inputs[:sugar.OPERANDS[name]]
            for sock in rest:
                if self.incoming.get(node.name, {}).get(sock.identifier) \
                        or not same(snapshot(sock), defaults.get(sock.identifier)):
                    return None
        operands = []
        for sock in inputs:
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
            elif sock.type == "BOOLEAN":
                operands.append([(ast.Bool(bool(value), 0, 0), "Bool")])
            elif sock.type == "INT":
                operands.append([(ast.Number(int(value), True, 0, 0), "Int")])
            elif sock.type == "STRING":
                operands.append([(ast.String(value, 0, 0), "String")])
            elif sock.type == "RGBA":
                operands.append([(ast.Tuple([number(v) for v in value], 0, 0), "Color")])
            else:
                return None

        def means(op, types):
            try:
                node_name, chosen, order = sugar.choose(op, types)
            except ValueError:
                return False
            return (node_name == name and order == tuple(range(len(types))) and set(props) <= set(chosen)
                    and all(getattr(node, k) == v for k, v in chosen.items()))

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
                if op == "not":
                    return ast.Not(exprs[0], 0, 0)
                if op in sugar.BINOPS or op in sugar.PRODUCTS or op in sugar.COMPARE or op in sugar.LOGIC:
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

    def statement_order(self, zone):
        """Bound nodes of a zone's body (None: the graph's), each after the ones it uses,
        staying in the current frame when it can, else in tree order."""
        names = [n for n in self.bound if self.zone_of.get(n) == zone]
        level = {self.bound[n] for n in names}
        deps = {}
        for name in names:
            deps[name] = {r for r in refs(self.expr(self.tree.nodes[name])) if r in level}
        by_binding = {b: n for n, b in self.bound.items()}
        waiting = {n: {by_binding[d] for d in ds if by_binding[d] != n} for n, ds in deps.items()}
        ready = [n for n, ds in waiting.items() if not ds]
        order, path = [], []
        while ready:
            n = min(ready, key=lambda n: (-shared(path, frame_path(self.tree.nodes[n])), self.index[n]))
            ready.remove(n)
            order.append(n)
            path = frame_path(self.tree.nodes[n])
            for m, ds in waiting.items():
                if n in ds:
                    ds.discard(n)
                    if not ds:
                        ready.append(m)
        return order

    # Frames

    def framed(self, statements, base=(), notes=True):
        """[(node, statement)] in order -> the body, with frames as blocks around their statements.

        A repeat body is framed inside the frames `base` of its statement; notes go in the graph's body.
        """
        body = []
        stack = [(None, body)]
        # Shared with the repeat bodies, framed first: a frame opened there is no note
        opened = self.opened
        blocks = {}
        for node, stmt in statements:
            path = frame_path(node) if node is not None else []
            path = path[len(base):] if [f.name for f in path[:len(base)]] == [f.name for f in base] else []
            names = [f.name for f in path]
            while len(stack) > 1 and stack[-1][0].name not in names:
                stack.pop()
            for f in path[len(stack) - 1:]:
                if f.name in opened:
                    self.warn(f"le frame « {f.label or f.name} » est coupé en deux : ses nœuds dépendent "
                              "de nœuds d'un autre frame qui dépendent d'eux")
                opened.add(f.name)
                block = blocks[f.name] = self.frame(f)
                stack[-1][1].append(block)
                stack.append((f, block.body))
            stack[-1][1].append(stmt)

        if not notes:
            return body
        # Frames around no exported node are notes, written where their parent is
        frames = sorted((n for n in self.tree.nodes if n.bl_idname == "NodeFrame"), key=lambda n: self.index[n.name])

        def note(f):
            block = blocks[f.name] = self.frame(f)
            block.body = [note(c) for c in frames if frame_name(c) == f.name and c.name not in opened]
            return block

        for f in frames:
            if f.name in blocks or f.name in opened:
                continue
            parent = frame_name(f)
            # A note in a frame of a repeat body is not written
            if parent is None or parent in blocks:
                where = body if parent is None else blocks[parent].body
                # Before the return, which nothing may follow
                at = len(where) - 1 if where and holds_return(where[-1]) else len(where)
                where.insert(at, note(f))
        return body

    def frame(self, f):
        label = f.label.replace('"', "'") or None
        color = tuple(f.color) if f.use_custom_color else None
        return ast.Frame(label, color, [], 0, 0)


def frame_name(node):
    parent = node.parent
    return parent.name if parent is not None and parent.bl_idname == "NodeFrame" else None


def frame_path(node):
    """The frames around a node, outermost first."""
    path = []
    parent = node.parent
    while parent is not None and parent.bl_idname == "NodeFrame":
        path.insert(0, parent)
        parent = parent.parent
    return path


def shared(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[n].name == b[n].name:
        n += 1
    return n


def holds_return(s):
    return isinstance(s, ast.Return) or isinstance(s, ast.Frame) and any(holds_return(i) for i in s.body)


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


def option_literal(item, option, value):
    if isinstance(value, bool):
        return ast.Bool(value, 0, 0)
    if isinstance(value, (int, float)):
        return number(value) if isinstance(value, float) else ast.Number(value, True, 0, 0)
    if item.bl_rna.properties[option].type == "ENUM":
        return enum_literal(value)
    return ast.String(value.replace('"', "'").replace("\n", " "), 0, 0)


def literal_type(value, sock):
    """The text type of the literal written for an unlinked socket, as the checker reads it back."""
    if value is None or sock.type in ("GEOMETRY", "MATRIX", "SHADER", "BUNDLE", "CLOSURE"):
        return None
    if isinstance(value, bool):
        return "Bool"
    if isinstance(value, int) and sock.type == "INT":
        return "Int"
    if isinstance(value, (int, float)):
        return "Float"
    if isinstance(value, tuple):
        return "Color" if len(value) == 4 else "Vector"
    return SOCKET_TYPES.get(sock.type)


def has_items(node):
    """Nodes whose sockets are a user-edited list: Capture Attribute, Menu Switch, Bake…"""
    return any(p.type == "COLLECTION" and p.identifier.endswith("items") for p in node.bl_rna.properties)


def unique(name, taken):
    base, i = name, 2
    while name in taken:
        name, i = f"{base}_{i}", i + 1
    taken.add(name)
    return name


def socket_name(sock, sockets, group, keys=None):
    """How text names this socket: its key when unique, else what tells it apart:
    for a group's socket, the key its graph gives it (see interface_keys)."""
    snakes = [snake(s.name) for s in sockets]
    if snakes.count(snake(sock.name)) == 1:
        return snake(sock.name)
    if keys and sock.identifier in keys:
        return keys[sock.identifier]
    return sock.name if group else sock.identifier


def group_keys(node, io):
    """{socket identifier: text key} of a group node's inputs or outputs; None for another node."""
    if node.bl_idname not in GROUP_NODES or node.node_tree is None:
        return None
    return socket_keys(node.node_tree, io)


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-6
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if hasattr(a, "__len__") and not isinstance(a, str) and hasattr(b, "__len__"):
        return same(tuple(a), tuple(b))
    return a == b


def bounded(value, fresh):
    """No bound written: the new socket's, or one so far out it means none (old files hold ±3.40282e38)."""
    return same(value, fresh) or abs(value) >= 1e30


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


def plus_terms(e):
    """Terms of a Join read inline: its operands are geometries, so every + is a join."""
    if isinstance(e, ast.BinOp) and e.op == "+":
        return plus_terms(e.left) + plus_terms(e.right)
    return [e]


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
    elif isinstance(e, (ast.Neg, ast.Not)):
        yield from refs(e.value)
    elif isinstance(e, ast.Repeat):
        yield from refs(e.count)
        for a in e.states:
            yield from refs(a.value)
        for s in e.body:
            yield from statement_refs(s)


def statement_refs(s):
    if isinstance(s, ast.Frame):
        for inner in s.body:
            yield from statement_refs(inner)
    elif isinstance(s, ast.Return) and isinstance(s.value, ast.Record):
        for f in s.value.fields:
            yield from refs(f.value)
    else:
        yield from refs(s.value)
