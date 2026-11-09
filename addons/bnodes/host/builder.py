"""ir.Graph -> node group.

The whole file is first built into scratch trees, so an error leaves the
file as it was. Then each graph is rebuilt in place, in the group of the
same name: interface sockets that did not change keep their identifier,
so modifier settings and the links of other trees calling the group stay.
"""

import bpy

from .. import lang
from ..lang import ir
from ..lang.errors import BnError, Diagnostic
from ..lang.layout import layout
from ..lang.schema import TYPES
from .schema import TREE_TYPES, BlenderSchema

DATABLOCKS = {"OBJECT": "objects", "COLLECTION": "collections", "MATERIAL": "materials",
              "IMAGE": "images", "TEXTURE": "textures"}

# Source line of each node, for the text and node editors to follow each other
LINE = "bnodes_line"

# Set rather than left to Blender, which translates new names when asked to
FIXED_NAMES = {ir.GROUP_INPUT: "Group Input", ir.GROUP_OUTPUT: "Group Output"}


def build_source(source, filename="<text>"):
    """Compile a .bn source and build its graphs. Returns the node groups, raises BnError."""
    with BlenderSchema() as schema:
        graphs = lang.compile_source(source, schema, filename)
    builder = Builder(filename, graphs)
    for g in graphs:
        if g.kind != "geometry":
            builder.fail(g, f"les arbres {g.kind} arrivent en v3")

    scratch = {}
    try:
        for g in graphs:
            tree = bpy.data.node_groups.new(f".bnodes_check_{g.name}", TREE_TYPES[g.kind])
            scratch[g.name] = tree
            builder.build(g, tree, scratch)
    finally:
        for tree in scratch.values():
            bpy.data.node_groups.remove(tree)

    built = {}
    for g in graphs:
        built[g.name] = builder.build(g, target(g), built)
    return list(built.values())


def target(g):
    """The group to rebuild: the existing one of that name, else a new one."""
    tree = bpy.data.node_groups.get(g.name)
    if tree is not None and tree.bl_idname == TREE_TYPES[g.kind] and tree.library is None:
        return tree
    return bpy.data.node_groups.new(g.name, TREE_TYPES[g.kind])


class Builder:
    def __init__(self, filename, graphs):
        self.filename = filename
        self.graphs = {g.name: g for g in graphs}
        # Only the graphs nobody calls are offered as modifiers
        self.called = {n.group for g in graphs for n in g.nodes if n.group}

    def fail(self, node, message):
        raise BnError([Diagnostic(self.filename, node.line, node.col, message)])

    def build(self, g, tree, built):
        # Named nodes keep their place across rebuilds
        kept = {n.name: n.location_absolute.copy() for n in tree.nodes}
        tree.nodes.clear()
        sync_interface(tree, g)
        if (g.name not in self.called and g.inputs[:1] and g.outputs[:1]
                and g.inputs[0][1] == g.outputs[0][1] == "Geometry"):
            tree.is_modifier = True
        self.fill(tree, g, built, kept)
        return tree

    def fill(self, tree, g, built, kept):
        pos = layout(g)
        frames = {}
        for f in g.frames:
            frame = tree.nodes.new("NodeFrame")
            frames[f.id] = frame
            if f.label:
                frame.name = frame.label = f.label
            if f.color:
                frame.use_custom_color = True
                frame.color = f.color
            frame[LINE] = f.line
            if f.parent:
                frame.parent = frames[f.parent]
            # A frame around nodes shrinks to them; a note needs a place and a size of its own
            if f.id in pos:
                frame.location_absolute = kept.get(frame.name, pos[f.id])
                frame.width = max(frame.width, 12 * len(f.label or ""))

        nodes = {}
        for n in g.nodes:
            node = tree.nodes.new(n.bl_idname)
            nodes[n.id] = node
            name = n.name or FIXED_NAMES.get(n.id)
            if name:
                node.name = name
            node[LINE] = n.line
            if n.frame:
                node.parent = frames[n.frame]
            if n.group:
                node.node_tree = built[n.group]
            for prop, value in n.props.items():
                try:
                    setattr(node, prop, value)
                except (TypeError, ValueError, AttributeError) as e:
                    self.fail(n, f"{prop}: {e}")

        for n in g.nodes:
            node = nodes[n.id]
            name = n.name or FIXED_NAMES.get(n.id)
            node.location_absolute = kept[name] if name in kept else pos[n.id]

            for ident, value in n.values.items():
                sock = self.socket(g, n, node, ident, "inputs")
                try:
                    sock.default_value = self.coerce(n, sock, value)
                except (TypeError, ValueError) as e:
                    self.fail(n, f"{ident}: {e}")

        for n in g.nodes:
            for ident, link in n.links:
                src = self.socket(g, g.node(link.node), nodes[link.node], link.output, "outputs")
                dst = self.socket(g, n, nodes[n.id], ident, "inputs")
                made = tree.links.new(src, dst)
                if not made.is_valid:
                    self.fail(n, f"Blender refuse le lien {src.name} ({src.type}) → {dst.name} ({dst.type})")

    def socket(self, g, n, node, ident, side):
        """A Blender socket from its text identifier.

        Interface sockets (group input and output, group nodes) are named in
        text but numbered in Blender, so they are found by position.
        """
        sockets = getattr(node, side)
        names = None
        if n.id == ir.GROUP_INPUT:
            names = g.inputs
        elif n.id == ir.GROUP_OUTPUT:
            names = g.outputs
        elif n.group:
            callee = self.graphs[n.group]
            names = callee.inputs if side == "inputs" else callee.outputs
        if names is not None:
            return sockets[[name for name, _t in names].index(ident)]
        sock = next((s for s in sockets if s.identifier == ident), None)
        if sock is None:
            self.fail(n, f"socket « {ident} » introuvable dans Blender")
        return sock

    def coerce(self, n, sock, value):
        if sock.type in DATABLOCKS and isinstance(value, str):
            found = getattr(bpy.data, DATABLOCKS[sock.type]).get(value)
            if found is None:
                self.fail(n, f"{sock.type.title()} « {value} » introuvable dans le fichier")
            return found
        return coerce(sock, value)


def coerce(sock, value):
    """A text literal as the socket's default_value."""
    current = sock.default_value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and hasattr(current, "__len__") \
            and not isinstance(current, str):
        return [value] * len(current)
    if isinstance(value, tuple) and len(value) == 3 and hasattr(current, "__len__") and len(current) == 4:
        return (*value, 1.0)
    return value


def sync_interface(tree, g):
    """Make the interface match the signature, reusing the sockets that did not change."""
    iface = tree.interface
    sockets = [i for i in iface.items_tree if i.item_type == "SOCKET"]
    keep = []
    for io, names in (("OUTPUT", g.outputs), ("INPUT", g.inputs)):
        for name, type in names:
            found = next((i for i in sockets if i.name == name and i.in_out == io
                          and i.socket_type == TYPES[type] and i not in keep), None)
            keep.append(found or iface.new_socket(name, in_out=io, socket_type=TYPES[type]))
    for item in sockets:
        if item not in keep:
            iface.remove(item)
    # Panels are the user's layout: kept as they are, and then order is theirs too
    if not any(i.item_type == "PANEL" for i in iface.items_tree):
        for position, item in enumerate(keep):
            iface.move(item, position)
