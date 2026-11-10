"""The node schema, read from Blender rather than written by hand.

Every node type is created once in a hidden scratch tree to list its
properties. Sockets depend on properties (Math SINE has one input), so they
are read on demand with the properties set, and memoized.
"""

import bpy

from ..lang.schema import TYPES, GroupSpec, NodeSpec, Prop, Socket, key

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
                if p.identifier in base or p.type not in PROP_KINDS or p.is_readonly:
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
            spec = GroupSpec(tree.name, *sig)
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
