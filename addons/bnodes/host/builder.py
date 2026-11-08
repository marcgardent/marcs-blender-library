"""ir.Graph -> node group.

Each graph is built into a fresh tree. Only when the whole file built does
the new tree take the place of the old one (users remapped, name kept), so
a failed build leaves the file as it was.
"""

import bpy

from .. import lang
from ..lang import ir
from ..lang.errors import BnError, Diagnostic
from ..lang.layout import layout
from ..lang.schema import TYPES
from .schema import TREE_TYPES, BlenderSchema

# Set rather than left to Blender, which translates new names when asked to
FIXED_NAMES = {ir.GROUP_INPUT: "Group Input", ir.GROUP_OUTPUT: "Group Output"}


def build_source(source, filename="<text>"):
    """Compile a .bn source and build its graphs. Returns the node groups, raises BnError."""
    with BlenderSchema() as schema:
        graphs = lang.compile_source(source, schema, filename)
    builder = Builder(filename)
    built = {}
    try:
        for g in graphs:
            built[g.name] = builder.build(g, built)
    except BnError:
        for tree in built.values():
            bpy.data.node_groups.remove(tree)
        raise
    return [swap_in(tree, name) for name, tree in built.items()]


def swap_in(tree, name):
    """Give `tree` the name and the users of the existing group called `name`."""
    old = bpy.data.node_groups.get(name)
    if old is not None and old is not tree:
        old.user_remap(tree)
        bpy.data.node_groups.remove(old)
    tree.name = name
    return tree


class Builder:
    def __init__(self, filename):
        self.filename = filename

    def fail(self, node, message):
        raise BnError([Diagnostic(self.filename, node.line, node.col, message)])

    def build(self, g, built):
        if g.kind != "geometry":
            self.fail(g, f"les arbres {g.kind} arrivent en v3")

        # Named nodes keep their place across rebuilds
        old = bpy.data.node_groups.get(g.name)
        kept = {}
        if old is not None and old.bl_idname == TREE_TYPES[g.kind]:
            kept = {n.name: n.location.copy() for n in old.nodes}

        tree = bpy.data.node_groups.new(g.name, TREE_TYPES[g.kind])
        try:
            self.fill(tree, g, built, kept)
        except BnError:
            bpy.data.node_groups.remove(tree)
            raise
        return tree

    def fill(self, tree, g, built, kept):
        for name, type in g.inputs:
            tree.interface.new_socket(name, in_out="INPUT", socket_type=TYPES[type])
        for name, type in g.outputs:
            tree.interface.new_socket(name, in_out="OUTPUT", socket_type=TYPES[type])
        if g.kind == "geometry" and g.inputs[:1] and g.inputs[0][1] == g.outputs[0][1] == "Geometry":
            tree.is_modifier = True

        param = {name: i for i, (name, _t) in enumerate(g.inputs)}
        result = {name: i for i, (name, _t) in enumerate(g.outputs)}
        nodes = {}
        for n in g.nodes:
            node = tree.nodes.new(n.bl_idname)
            nodes[n.id] = node
            name = n.name or FIXED_NAMES.get(n.id)
            if name:
                node.name = name
            if n.group:
                node.node_tree = built[n.group]
            for prop, value in n.props.items():
                try:
                    setattr(node, prop, value)
                except (TypeError, ValueError, AttributeError) as e:
                    self.fail(n, f"{prop}: {e}")

        pos = layout(g)
        for n in g.nodes:
            node = nodes[n.id]
            name = n.name or FIXED_NAMES.get(n.id)
            node.location = kept[name] if name in kept else pos[n.id]

            for ident, value in n.values.items():
                sock = self.input(n, node, ident, result)
                try:
                    sock.default_value = coerce(sock, value)
                except (TypeError, ValueError) as e:
                    self.fail(n, f"{ident}: {e}")

        for n in g.nodes:
            for ident, link in n.links:
                src_node = nodes[link.node]
                if link.node == ir.GROUP_INPUT:
                    src = src_node.outputs[param[link.output]]
                else:
                    src = next(s for s in src_node.outputs if s.identifier == link.output)
                dst = self.input(n, nodes[n.id], ident, result)
                made = tree.links.new(src, dst)
                if not made.is_valid:
                    self.fail(n, f"Blender refuse le lien {src.name} ({src.type}) → {dst.name} ({dst.type})")

    def input(self, n, node, ident, result):
        if n.id == ir.GROUP_OUTPUT:
            return node.inputs[result[ident]]
        sock = next((s for s in node.inputs if s.identifier == ident), None)
        if sock is None:
            self.fail(n, f"entrée « {ident} » introuvable dans Blender")
        return sock


def coerce(sock, value):
    """A text literal as the socket's default_value."""
    current = sock.default_value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and hasattr(current, "__len__") \
            and not isinstance(current, str):
        return [value] * len(current)
    if isinstance(value, tuple) and len(value) == 3 and hasattr(current, "__len__") and len(current) == 4:
        return (*value, 1.0)
    return value
