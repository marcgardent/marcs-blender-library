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
from ..lang.schema import ITEM_NODES, ITEM_TYPES, TYPES
from ..lang.typecheck import REPEAT_ITEMS
from . import modules
from .schema import TREE_TYPES, BlenderSchema, fresh_item, fresh_options, same_option

DATABLOCKS = {"OBJECT": "objects", "COLLECTION": "collections", "MATERIAL": "materials",
              "IMAGE": "images", "TEXTURE": "textures"}

# Source line of each node, for the text and node editors to follow each other
LINE = "bnodes_line"

# Set rather than left to Blender, which translates new names when asked to
FIXED_NAMES = {ir.GROUP_INPUT: "Group Input", ir.GROUP_OUTPUT: "Group Output"}


def build_source(source, filename="<text>"):
    """Compile a .bn source and build its graphs, and those its `use` lines bring.

    Returns the node groups of the source's own graphs, raises BnError.
    """
    with BlenderSchema() as schema:
        graphs = lang.compile_source(source, schema, filename, modules.load)
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
        tree = built[g.name] = builder.build(g, target(g), built)
        mark(tree, g.module)
    return [built[g.name] for g in graphs if g.module is None]


def mark(tree, module):
    """Say which module a group comes from, so that Tree → Text writes its use back."""
    if module is None:
        tree.pop(modules.MODULE, None)
        tree.pop(modules.SOURCE, None)
        return
    name, source = module
    tree[modules.MODULE] = name
    tree[modules.SOURCE] = source or ""
    if hasattr(tree, "bnodes_text"):
        # A text module goes along with the group when it is appended elsewhere
        tree.bnodes_text = bpy.data.texts.get(name + ".bn") if source is None else None


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
        tree.description = g.description or ""
        # The subtype first: it makes the socket again, with its own defaults
        self.options(tree, g)
        # After the links: a menu input only has its items once it feeds a menu
        self.defaults(tree, g)
        return tree

    def options(self, tree, g):
        """Each socket's other settings as written (subtype, description…), else a new socket's."""
        for io, names in (("INPUT", g.inputs), ("OUTPUT", g.outputs)):
            for name, _type in names:
                item = interface_item(tree, io, name)
                fresh = fresh_options(item.socket_type, io)
                wanted = g.options.get((io, name), {})
                unknown = [o for o in wanted if o not in fresh]
                if unknown:
                    self.fail(g, f"« {name} » : option {unknown[0]} inconnue ; options : {', '.join(fresh)}")
                for option in sorted(fresh, key=lambda o: o != "subtype"):
                    value = wanted.get(option, fresh[option])
                    if same_option(option, getattr(item, option), value):
                        continue
                    try:
                        setattr(item, option, value)
                    except (TypeError, ValueError) as e:
                        self.fail(g, f"option {option} de « {name} » : {e}")
                    item = interface_item(tree, io, name)

    def defaults(self, tree, g):
        """Each input's default, bounds and implicit field as written, else a new socket's."""
        items = [i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
        for name, _type in g.inputs:
            item = next(i for i in items if i.name == name)
            spec = g.defaults.get(name, {})
            fresh = fresh_item(item.socket_type)
            if "min_value" in fresh:
                item.min_value = spec.get("min", fresh["min_value"])
                item.max_value = spec.get("max", fresh["max_value"])
            if "default_input" in fresh:
                item.default_input = spec.get("implicit", fresh["default_input"])
            if "default_value" not in fresh:
                continue
            value = spec.get("value", fresh["default_value"])
            if item.socket_type.removeprefix("NodeSocket").upper() in DATABLOCKS and isinstance(value, str):
                found = getattr(bpy.data, DATABLOCKS[item.socket_type.removeprefix("NodeSocket").upper()]).get(value)
                if found is None:
                    self.fail(g, f"« {name} » : {_type} « {value} » introuvable dans le fichier")
                value = found
            elif item.socket_type == "NodeSocketVector" and hasattr(item, "dimensions"):
                if item.dimensions != len(value):
                    # The item changes type (Vector2D…): its default holds the new size once fetched again
                    item.dimensions = len(value)
                    item = next(i for i in tree.interface.items_tree
                                if i.item_type == "SOCKET" and i.in_out == "INPUT" and i.name == name)
            elif isinstance(value, tuple) and len(value) == 3 and len(item.default_value) == 4:
                value = (*value, 1.0)
            try:
                item.default_value = value
            except (TypeError, ValueError) as e:
                self.fail(g, f"valeur par défaut de « {name} » : {e}")

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
                # A group of the file the text does not define is used as it is
                node.node_tree = built[n.group] if n.group in self.graphs else bpy.data.node_groups[n.group]
            for prop, value in n.props.items():
                try:
                    setattr(node, prop, value)
                except (TypeError, ValueError, AttributeError) as e:
                    self.fail(n, f"{prop}: {e}")

        # Zones: pair each input with its output, then give the output its items (the input follows)
        for n in g.nodes:
            if n.pair:
                nodes[n.id].pair_with_output(nodes[n.pair])
        for n in g.nodes:
            if n.items is not None and n.bl_idname == ir.REPEAT_OUTPUT:
                items = nodes[n.id].repeat_items
                items.clear()
                for name, type in n.items:
                    items.new(REPEAT_ITEMS[type], name)
            elif n.items is not None and n.bl_idname in ITEM_NODES:
                self.items(nodes[n.id], n)

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

    def items(self, node, n):
        """The items of a Capture Attribute or a switch, in the order of the text."""
        items = getattr(node, ITEM_NODES[n.bl_idname].collection)
        items.clear()
        for name, type in n.items:
            if n.bl_idname == "GeometryNodeCaptureAttribute":
                items.new(ITEM_TYPES[type], name)
            elif n.bl_idname == "GeometryNodeMenuSwitch":
                items.new(name)
            else:
                items.new()

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
        elif n.group in self.graphs:
            callee = self.graphs[n.group]
            names = callee.inputs if side == "inputs" else callee.outputs
        elif n.group:
            io = "INPUT" if side == "inputs" else "OUTPUT"
            names = [(i.name, None) for i in node.node_tree.interface.items_tree
                     if i.item_type == "SOCKET" and i.in_out == io]
        elif n.items is not None and n.bl_idname in ITEM_NODES:
            # The fixed sockets by identifier, then the items by position
            shape = ITEM_NODES[n.bl_idname]
            sockets = [s for s in sockets if s.type != "CUSTOM"]
            fixed = shape.inputs if side == "inputs" else shape.outputs
            found = next((s for s in sockets[:fixed] if s.identifier == ident), None)
            if found is not None:
                return found
            return sockets[fixed + [name for name, _t in n.items].index(ident)]
        elif n.items is not None:
            # Zone items are numbered by Blender too; the input node has the count first
            names = n.items
            if n.bl_idname == ir.REPEAT_INPUT:
                names = [("Iterations" if side == "inputs" else "Iteration", "Int")] + names
            sockets = [s for s in sockets if s.type != "CUSTOM"]
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


def interface_item(tree, io, name):
    return next(i for i in tree.interface.items_tree
                if i.item_type == "SOCKET" and i.in_out == io and i.name == name)


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
