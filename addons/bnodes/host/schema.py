"""The node schema, read from Blender rather than written by hand.

Every node type is created once in a hidden scratch tree to list its
properties. Sockets depend on properties (Math SINE has one input), so they
are read on demand with the properties set, and memoized.
"""

import bpy

from ..lang.schema import ITEM_NODES, ITEM_TYPES, TYPES, GroupSpec, NodeSpec, Prop, Socket, interface_keys, key

TREE_TYPES = {
    "geometry": "GeometryNodeTree",
    "shader": "ShaderNodeTree",
    "compositor": "CompositorNodeTree",
}

# Stripped from bl_idname to make the text name, earlier prefixes win a clash
PREFIXES = ("GeometryNode", "FunctionNode", "ShaderNode", "CompositorNode", "TextureNode", "Node")

# Handled by the builder, purely visual, or paired zones that v0 does not write
SKIP = {
    "NodeGroupInput", "NodeGroupOutput", "NodeReroute", "NodeFrame", "NodeImplicitConversion",
    "NodeUndefined", "NodeCustomGroup", "GeometryNodeGroup", "ShaderNodeGroup", "CompositorNodeGroup",
}
ZONES = ("SimulationInput", "SimulationOutput", "RepeatInput", "RepeatOutput",
         "ForeachGeometryElementInput", "ForeachGeometryElementOutput", "ClosureInput", "ClosureOutput")

SOCKET_TYPES = {
    "VALUE": "Float", "INT": "Int", "BOOLEAN": "Bool", "VECTOR": "Vector", "RGBA": "Color",
    "ROTATION": "Rotation", "MATRIX": "Matrix", "STRING": "String", "MENU": "Menu",
    "GEOMETRY": "Geometry", "SHADER": "Shader", "OBJECT": "Object", "COLLECTION": "Collection",
    "MATERIAL": "Material", "IMAGE": "Image", "TEXTURE": "Texture", "BUNDLE": "Bundle",
    "CLOSURE": "Closure",
}

PROP_KINDS = {"ENUM", "BOOLEAN", "INT", "FLOAT", "STRING"}

# Where the item list of a node stands in its panel: the editor's, not the tree's
UI_PROPS = {"active_index", "active_input_index", "active_output_index"}

# Per Blender version: {kind: {text name: NodeSpec}}, and the socket memo
_specs = {}
_sockets = {}


def text_name(bl_idname):
    for prefix in PREFIXES:
        if bl_idname.startswith(prefix) and len(bl_idname) > len(prefix):
            return bl_idname[len(prefix):]
    return bl_idname


def socket_info(sock):
    return Socket(sock.name, sock.identifier, SOCKET_TYPES.get(sock.type, sock.type.title()),
                  sock.is_multi_input)


def available(sockets):
    return [socket_info(s) for s in sockets if not s.is_unavailable and s.type != "CUSTOM"]


class BlenderSchema:
    """Use as a context manager: the scratch trees are removed on exit."""

    def __init__(self):
        self.version = bpy.app.version
        self.scratch = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for tree in self.scratch.values():
            bpy.data.node_groups.remove(tree)
        self.scratch.clear()

    def tree(self, kind):
        if kind not in self.scratch:
            self.scratch[kind] = bpy.data.node_groups.new(f".bnodes_scratch_{kind}", TREE_TYPES[kind])
        return self.scratch[kind]

    def specs(self, kind):
        key = (self.version, kind)
        if key not in _specs:
            _specs[key] = self.read_specs(kind)
        return _specs[key]

    def read_specs(self, kind):
        tree = self.tree(kind)
        base = {p.identifier for p in bpy.types.Node.bl_rna.properties}
        found = {}
        for idname in sorted(dir(bpy.types)):
            cls = getattr(bpy.types, idname)
            if (idname in SKIP or idname.endswith(ZONES) or not isinstance(cls, type)
                    or not issubclass(cls, bpy.types.Node) or cls is bpy.types.Node):
                continue
            try:
                node = tree.nodes.new(idname)
            except RuntimeError:
                continue  # not available in this tree kind
            props = {}
            for p in node.bl_rna.properties:
                if p.identifier in base or p.type not in PROP_KINDS or p.is_readonly or p.identifier in UI_PROPS:
                    continue
                if getattr(p, "is_array", False) or getattr(p, "array_length", 0):
                    continue  # a color or a vector property: not in the text yet
                if p.type == "ENUM" and p.is_enum_flag:
                    continue
                items = tuple(i.identifier for i in p.enum_items) if p.type == "ENUM" else ()
                props[p.identifier] = Prop(p.identifier, p.type, items)
            tree.nodes.remove(node)
            found[idname] = props

        specs = {}
        taken = {}
        rank = {p: i for i, p in enumerate(PREFIXES)}

        def prefix_rank(idname):
            return next((rank[p] for p in PREFIXES if idname.startswith(p)), len(PREFIXES))

        for idname in sorted(found, key=prefix_rank):
            name = text_name(idname)
            # GeometryNodeInputPosition reads as Position, when that name is free
            short = name[len("Input"):] if name.startswith("Input") and len(name) > 5 else None
            if short and short not in taken and text_name_free(short, found):
                name = short
            if name in taken:
                name = idname
            spec = NodeSpec(name, idname, found[idname])
            taken[name] = spec
            specs[name] = spec
            specs[idname] = spec  # the full bl_idname always works too
            if name != text_name(idname) and text_name(idname) not in specs:
                specs[text_name(idname)] = spec
        return specs

    # Schema protocol

    def node(self, kind, name):
        return self.specs(kind).get(name) if kind in TREE_TYPES else None

    def node_names(self, kind):
        return sorted({s.name for s in self.specs(kind).values()}) if kind in TREE_TYPES else []

    def sockets(self, kind, spec, props):
        inputs, outputs, _values, _props = self.fresh(kind, spec, props)
        return list(inputs), list(outputs)

    def groups(self, kind):
        """{key: GroupSpec} of the file's node groups of that kind, hidden ones (.name) aside."""
        types = {v: k for k, v in TYPES.items()}
        found = {}
        for tree in bpy.data.node_groups if kind in TREE_TYPES else ():
            if tree.bl_idname != TREE_TYPES[kind] or tree.name.startswith("."):
                continue
            items = [i for i in tree.interface.items_tree if i.item_type == "SOCKET"]
            sig = [tuple((i.name, types.get(i.socket_type, i.socket_type.removeprefix("NodeSocket")))
                         for i in items if i.in_out == io) for io in ("INPUT", "OUTPUT")]
            keys = [tuple(socket_keys(tree, io).values()) for io in ("INPUT", "OUTPUT")]
            spec = GroupSpec(tree.name, *sig, *keys)
            k = key(tree.name)
            if k in found:
                spec = (found[k] if isinstance(found[k], list) else [found[k]]) + [spec]
            found[k] = spec
        return found

    def defaults(self, kind, spec, props):
        """What a new node holds once `props` are set: ({input identifier: value}, {prop: value})."""
        _inputs, _outputs, values, prop_values = self.fresh(kind, spec, props)
        return values, prop_values

    def fresh(self, kind, spec, props):
        key = (self.version, kind, spec.bl_idname, tuple(sorted(props.items())))
        if key not in _sockets:
            tree = self.tree(kind)
            node = tree.nodes.new(spec.bl_idname)
            try:
                for name, value in props.items():
                    try:
                        setattr(node, name, value)
                    except (TypeError, ValueError, AttributeError):
                        pass  # the builder reports it, with Blender's own message
                values = {s.identifier: snapshot(s) for s in node.inputs}
                prop_values = {p: getattr(node, p) for p in spec.props}
                _sockets[key] = (available(node.inputs), available(node.outputs), values, prop_values)
            finally:
                tree.nodes.remove(node)
        return _sockets[key]


def root_panel(tree):
    """The panel around the whole interface, None when it is empty. Blender 5.2 has no
    interface.root_panel, but every item at the top has it as parent."""
    iface = tree.interface
    if hasattr(iface, "root_panel"):
        return iface.root_panel
    return next((i.parent for i in iface.items_tree if i.parent.parent is None), None)


# On a built group: {socket identifier: {"name", "key"}} for the sockets the text named with `as`
ALIASES = "bnodes_aliases"


def socket_keys(tree, io):
    """{identifier: text key} of one side of a group's interface, in order: see interface_keys.

    The keys the text gave with `as` stay, as long as the socket keeps its name."""
    types = {v: k for k, v in TYPES.items()}
    items = [i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == io]
    stored = tree.get(ALIASES, {})
    given = [stored[i.identifier]["key"] if i.identifier in stored and stored[i.identifier]["name"] == i.name
             else None for i in items]
    keys = interface_keys([(i.name, i.parent.name if i.parent.parent is not None else None,
                            types.get(i.socket_type, i.socket_type.removeprefix("NodeSocket"))) for i in items], given)
    return {i.identifier: k for i, k in zip(items, keys)}


# Settings of a tree as a new one has them: the text writes those that differ, in this order.
# is_modifier is the builder's to decide, unless the text says otherwise
TREE_FLAGS = {"is_modifier": False, "is_tool": False, "is_mode_object": False, "is_mode_edit": False,
              "is_mode_sculpt": False, "is_mode_paint": False, "is_type_mesh": False, "is_type_curve": False,
              "is_type_pointcloud": False, "is_type_grease_pencil": False, "use_wait_for_click": False,
              "show_modifier_manage_panel": True}

# A panel's settings, as a new one has them; its name is written before its brace
PANEL_OPTIONS = {"description": "", "default_closed": False}


# What a new interface input of each socket type holds: the text writes only what differs
INTERFACE_FIELDS = ("default_value", "min_value", "max_value", "default_input")
_fresh_items = {}


def fresh_item(socket_type):
    """{field: value} of a new group input of `socket_type`, fields it has only."""
    if socket_type not in _fresh_items:
        tree = bpy.data.node_groups.new(".bnodes_fresh", "GeometryNodeTree")
        try:
            item = tree.interface.new_socket("x", in_out="INPUT", socket_type=socket_type)
            _fresh_items[socket_type] = {f: snapshot(item) if f == "default_value" else getattr(item, f)
                                         for f in INTERFACE_FIELDS if hasattr(item, f)}
        finally:
            bpy.data.node_groups.remove(tree)
    return _fresh_items[socket_type]


# Interface settings the text writes otherwise than as options, or that are the editor's
NOT_OPTIONS = {"name", "socket_type", "bl_socket_idname", "default_value", "min_value", "max_value",
               "default_input", "dimensions", "select"}
_fresh_options = {}


def option_names(item):
    """The settings of an interface socket that the text writes as options, in Blender's order."""
    return [p.identifier for p in item.bl_rna.properties
            if not p.is_readonly and p.identifier not in NOT_OPTIONS
            and p.type in ("BOOLEAN", "ENUM", "STRING", "INT", "FLOAT")
            and not getattr(p, "is_array", False) and not (p.type == "ENUM" and p.is_enum_flag)]


def fresh_options(socket_type, in_out):
    """{option: value} of a new interface socket: what the text leaves out."""
    if (socket_type, in_out) not in _fresh_options:
        tree = bpy.data.node_groups.new(".bnodes_fresh", "GeometryNodeTree")
        try:
            item = tree.interface.new_socket("x", in_out=in_out, socket_type=socket_type)
            _fresh_options[(socket_type, in_out)] = {o: getattr(item, o) for o in option_names(item)}
        finally:
            bpy.data.node_groups.remove(tree)
    return _fresh_options[(socket_type, in_out)]


def new_item(node, shape, name, type):
    """Add one item to a node of ITEM_NODES, as `new()` of its collection wants it."""
    items = getattr(node, shape.collection)
    if not shape.named:
        return items.new()
    if not shape.typed:
        return items.new(name)
    if shape.kinds is not None:
        item = items.new(name)
        setattr(item, shape.type_prop, shape.kinds[type])
        return item
    return items.new(ITEM_TYPES[type], name)


def item_option_names(item, shape):
    """The settings of an item that the text writes as its options, in Blender's order."""
    return [p.identifier for p in item.bl_rna.properties
            if not p.is_readonly and p.identifier not in ("name", shape.type_prop)
            and p.type in ("BOOLEAN", "ENUM", "STRING", "INT", "FLOAT")
            and not getattr(p, "is_array", False) and not (p.type == "ENUM" and p.is_enum_flag)]


_fresh_item_options = {}


def fresh_item_options(bl_idname, items, shape=None):
    """[{option: value}] of the (name, type) items made in that order on a new node, as the
    builder makes them: what the text leaves out. Blender sets some from the items before
    (a Bake's Geometry item becomes an attribute holder once a field follows it)."""
    shape = shape or ITEM_NODES[bl_idname]
    key = (bl_idname, shape.collection, tuple(items))
    if key not in _fresh_item_options:
        tree = bpy.data.node_groups.new(".bnodes_fresh", "GeometryNodeTree")
        try:
            node = tree.nodes.new(bl_idname)
            getattr(node, shape.collection).clear()
            for name, type in items:
                new_item(node, shape, name, type)
            _fresh_item_options[key] = [{o: getattr(i, o) for o in item_option_names(i, shape)}
                                        for i in getattr(node, shape.collection)]
        finally:
            bpy.data.node_groups.remove(tree)
    return _fresh_item_options[key]
_fresh_values = {}


def fresh_item_value(bl_idname, collection, socket_type):
    """The value the input socket of a new item holds: a closure's output, an evaluation's input."""
    k = (bl_idname, collection, socket_type)
    if k not in _fresh_values:
        tree = bpy.data.node_groups.new(".bnodes_fresh", "GeometryNodeTree")
        try:
            node = tree.nodes.new(bl_idname)
            items = getattr(node, collection)
            items.clear()
            items.new(socket_type, "x")
            _fresh_values[k] = snapshot([s for s in node.inputs if s.type != "CUSTOM"][-1])
        finally:
            bpy.data.node_groups.remove(tree)
    return _fresh_values[k]


def same_option(name, a, b):
    # Sockets made before Blender 4 say NONE where new ones say DEFAULT
    plain = {"NONE", "DEFAULT"}
    return a == b or name == "subtype" and a in plain and b in plain


def snapshot(sock):
    """A socket's default_value as plain Python: tuples for vectors, names for datablocks."""
    value = getattr(sock, "default_value", None)
    if isinstance(value, bpy.types.ID):
        return value.name
    if hasattr(value, "__len__") and not isinstance(value, str):
        return tuple(value)
    return value


def text_name_free(short, found):
    """No other node already strips to `short`."""
    return all(text_name(i) != short for i in found)
