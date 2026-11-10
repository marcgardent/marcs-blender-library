"""What the checker needs to know about nodes, and how it asks for it.

host/schema.py answers from Blender itself; tests answer with a small fake.
"""

import re
from dataclasses import dataclass, field
from typing import Protocol

# Text type name -> interface socket type, for graph parameters and outputs
TYPES = {
    "Float": "NodeSocketFloat",
    "Int": "NodeSocketInt",
    "Bool": "NodeSocketBool",
    "Vector": "NodeSocketVector",
    "Color": "NodeSocketColor",
    "Rotation": "NodeSocketRotation",
    "Matrix": "NodeSocketMatrix",
    "String": "NodeSocketString",
    "Menu": "NodeSocketMenu",
    "Geometry": "NodeSocketGeometry",
    "Shader": "NodeSocketShader",
    "Object": "NodeSocketObject",
    "Collection": "NodeSocketCollection",
    "Material": "NodeSocketMaterial",
    "Image": "NodeSocketImage",
    "Texture": "NodeSocketTexture",
    "Bundle": "NodeSocketBundle",
    "Closure": "NodeSocketClosure",
}

# These only link to their own type. Between the others (numbers, vectors,
# colors, rotations) Blender converts, and has the last word on the details.
STRICT = {"Geometry", "Shader", "String", "Menu", "Matrix", "Object", "Collection",
          "Material", "Image", "Texture", "Bundle", "Closure"}

# Written in text as the datablock's name: material: "Rust"
DATABLOCKS = {"Object", "Collection", "Material", "Image", "Texture"}

TREE_KINDS = ("geometry", "shader", "compositor")

# Default of an unlinked group input taken from the context: `p: Vector = Position()`.
# Text call -> (interface default_input, the one type it suits)
IMPLICIT = {
    "Position": ("POSITION", "Vector"),
    "Normal": ("NORMAL", "Vector"),
    "Index": ("INDEX", "Int"),
    "ID": ("ID_OR_INDEX", "Int"),
    "InstanceTransform": ("INSTANCE_TRANSFORM", "Matrix"),
    "SelfObject": ("SELF_OBJECT", "Object"),
}

# Types whose interface socket has a min and a max: `t: Float = 0.5 in 0.0..1.0`
RANGED = {"Float", "Int", "Vector"}

# Types with no default value in text: links only
NO_DEFAULT = {"Geometry", "Shader", "Bundle", "Closure", "Matrix"}

# Text type -> the socket type of an item (zone, Capture Attribute) or a node's data_type (switches)
ITEM_TYPES = {"Float": "FLOAT", "Int": "INT", "Bool": "BOOLEAN", "Vector": "VECTOR", "Color": "RGBA",
              "Rotation": "ROTATION", "Matrix": "MATRIX", "String": "STRING", "Menu": "MENU",
              "Geometry": "GEOMETRY", "Shader": "SHADER", "Object": "OBJECT", "Collection": "COLLECTION",
              "Material": "MATERIAL", "Image": "IMAGE", "Texture": "TEXTURE", "Bundle": "BUNDLE",
              "Closure": "CLOSURE"}

# What a Capture Attribute can hold: fields only
FIELD_TYPES = ("Float", "Int", "Bool", "Vector", "Color", "Rotation", "Matrix")


@dataclass(frozen=True)
class ItemNode:
    """A node whose sockets are a list of items, after a few fixed ones.

    The call makes the items: one per named value (`CaptureAttribute(g, hauteur: h)`,
    `MenuSwitch(mode, Lisse: a, Rugueux: b)`), or one per value after the fixed
    inputs (`IndexSwitch(i, a, b, c)`). An item's other settings are its options:
    `MenuSwitch(mode, Lisse(description: "…"): a)`.
    """
    collection: str  # the node's item collection, e.g. capture_items
    inputs: int      # fixed inputs before the items
    outputs: int     # fixed outputs before the items
    named: bool      # items given by name, else by position
    typed: bool      # each item has its own type, else the node's data_type is theirs
    # What each item adds to the outputs: "value" one of its type, "flag" a Bool (Menu Switch), or nothing
    out: str | None = None
    types: tuple = ()  # the text types an item may have, when not all of them
    type_prop: str = "socket_type"  # the item's property that holds its type: not an option
    # When the type is not given to new(): text type -> the value of type_prop
    kinds: dict | None = field(default=None, hash=False)
    # Options that only mean something on a field item: on the others Blender sets them itself
    field_only: tuple = ()


BAKE_TYPES = ("Float", "Int", "Bool", "Vector", "Color", "Rotation", "Matrix", "String", "Geometry", "Bundle")
LIST_TYPES = ("Float", "Int", "Bool", "Vector", "Color", "Rotation", "Matrix", "String", "Menu")

ITEM_NODES = {
    "GeometryNodeCaptureAttribute": ItemNode("capture_items", 2, 2, named=True, typed=True, out="value",
                                             types=FIELD_TYPES, type_prop="data_type"),
    "GeometryNodeIndexSwitch": ItemNode("index_switch_items", 1, 1, named=False, typed=False),
    "GeometryNodeMenuSwitch": ItemNode("enum_items", 1, 1, named=True, typed=False, out="flag"),
    "FunctionNodeFormatString": ItemNode("format_items", 1, 1, named=True, typed=True,
                                         types=("Float", "Int", "String")),
    "GeometryNodeBake": ItemNode("bake_items", 0, 0, named=True, typed=True, out="value", types=BAKE_TYPES,
                                 field_only=("attribute_domain", "is_attribute")),
    "GeometryNodeFieldToList": ItemNode("list_items", 1, 0, named=True, typed=True, out="value", types=LIST_TYPES),
    "GeometryNodeFieldToGrid": ItemNode("grid_items", 1, 0, named=True, typed=True, out="value",
                                        types=("Float", "Int", "Bool", "Vector"), type_prop="data_type"),
    "GeometryNodeRasterizePoints": ItemNode("rasterize_items", 6, 0, named=True, typed=True, out="value",
                                            types=("Float", "Vector"), type_prop="type",
                                            kinds={"Float": "SCALAR", "Vector": "VECTOR"}),
    "GeometryNodeCombineList": ItemNode("combine_list_items", 0, 1, named=False, typed=False),
    # What it shows, by name: `Viewer(mesh: g, hauteur: h)`, a statement nothing reads
    "GeometryNodeViewer": ItemNode("viewer_items", 0, 0, named=True, typed=True),
}

# An item left without a link or a value: `MenuSwitch(mode, Lisse: a, Vide: _)`
NO_VALUE = "_"

COMBINE_BUNDLE = "NodeCombineBundle"
SEPARATE_BUNDLE = "NodeSeparateBundle"
EVALUATE_CLOSURE = "NodeEvaluateClosure"
CLOSURE_INPUT = "NodeClosureInput"
CLOSURE_OUTPUT = "NodeClosureOutput"

# Nodes whose items the text declares with a type each, and where they stand:
# side -> (fixed sockets before the items, the item list of ir.Node there or None).
# `items` are the inputs of a closure, `out_items` its outputs, and so on.
SIGNATURE_NODES = {
    COMBINE_BUNDLE: {"inputs": (0, "items"), "outputs": (1, None)},
    SEPARATE_BUNDLE: {"inputs": (1, None), "outputs": (0, "out_items")},
    EVALUATE_CLOSURE: {"inputs": (1, "items"), "outputs": (0, "out_items")},
    CLOSURE_INPUT: {"inputs": (0, None), "outputs": (0, "items")},
    CLOSURE_OUTPUT: {"inputs": (0, "out_items"), "outputs": (1, None)},
}

# Their item collections, shaped as ITEM_NODES for the host's item helpers:
# (bl_idname, the ir.Node list, "items" or "out_items") -> ItemNode. A Closure Input has none: its output holds them.
SIGNATURE_ITEMS = {
    (COMBINE_BUNDLE, "items"): ItemNode("bundle_items", 0, 1, named=True, typed=True),
    (SEPARATE_BUNDLE, "out_items"): ItemNode("bundle_items", 1, 0, named=True, typed=True, out="value"),
    (EVALUATE_CLOSURE, "items"): ItemNode("input_items", 1, 0, named=True, typed=True),
    (EVALUATE_CLOSURE, "out_items"): ItemNode("output_items", 1, 0, named=True, typed=True, out="value"),
    (CLOSURE_OUTPUT, "items"): ItemNode("input_items", 0, 1, named=True, typed=True),
    (CLOSURE_OUTPUT, "out_items"): ItemNode("output_items", 0, 1, named=True, typed=True),
}


def signature_items(bl_idname):
    """[(ir.Node list, ItemNode)] of a node the text declares, inputs first."""
    return [(attr, shape) for (idname, attr), shape in SIGNATURE_ITEMS.items() if idname == bl_idname]


def option_key(attr, name):
    """The key of an item's options in ir.Node.item_options: its name, ("out", name) for an output item."""
    return name if attr == "items" else ("out", name)

RESERVED = {"graph", "return", "true", "false", "and", "or", "xor", "not", "dot", "cross", "repeat"}


# Links Blender converts although one side is strict
CONVERSIONS = {("Rotation", "Matrix")}


def can_link(src, dst):
    return src == dst or (src not in STRICT and dst not in STRICT) or (src, dst) in CONVERSIONS


def snake(name):
    """Socket name as written in text: `Base Color` -> `base_color`."""
    s = re.sub(r"\W+", "_", name.lower()).strip("_")
    if not s or s[0].isdigit():
        s = "_" + s
    return s + "_" if s in RESERVED else s


def key(name):
    """How a parameter or graph is named in code: itself when it can be, else snake_case.

    A name that is not its own key is written quoted where it is declared:
    `"Fur Density": Float`, then used as `fur_density`.
    """
    return name if name.isidentifier() and name not in RESERVED else snake(name)


def interface_keys(sockets, given=()):
    """The text key of each socket of one side of an interface, from [(name, panel, type)] in order.

    Each one's key, but a name that repeats (two « Seed », in two panels or in one) keeps it
    for its first socket only; the next ones are told apart by their panel, then by their
    type, then by a number: `guide_map_seed`, `seed_vector`, `seed_2`. The reader writes
    these as `"Seed" as guide_map_seed: Int`; `panel` is the innermost panel's name, or None.
    `given` holds, per socket, the key a text gave it with `as`, or None: kept when it is free.
    """
    given = list(given) + [None] * (len(sockets) - len(given))
    out = [None] * len(sockets)
    taken = set()
    for i, k in enumerate(given):
        if k is not None and k not in taken:
            out[i] = k
            taken.add(k)
    # An alias of the rule never takes the key a socket has by its own name
    natural = taken | {key(name) for name, _panel, _type in sockets}
    first = {}
    for i, (name, panel, type) in enumerate(sockets):
        k = key(name)
        if out[i] is not None:
            continue
        if k not in taken:
            first.setdefault(k, panel)
            out[i] = k
            taken.add(k)
            continue
        tries = ([f"{snake(panel)}_{snake(name)}"] if panel is not None and panel != first.get(k) else []) + \
            [f"{snake(name)}_{snake(type)}"]
        pick = next((t for t in tries if t not in natural), None)
        n = 2
        while pick is None:
            pick = f"{snake(name)}_{n}" if f"{snake(name)}_{n}" not in natural else None
            n += 1
        natural.add(pick)
        taken.add(pick)
        out[i] = pick
    return out


@dataclass(frozen=True)
class Socket:
    name: str        # UI name, e.g. "Base Color"
    identifier: str  # stable internal name, e.g. "Value_001"
    type: str        # a key of TYPES, or another Blender type name
    multi_input: bool = False

    @property
    def key(self):
        return snake(self.name)


@dataclass(frozen=True)
class Prop:
    name: str
    kind: str  # ENUM, BOOLEAN, INT, FLOAT or STRING
    items: tuple = ()  # enum values; empty when Blender computes them at runtime


@dataclass(frozen=True)
class NodeSpec:
    name: str       # text name, e.g. SetPosition
    bl_idname: str  # e.g. GeometryNodeSetPosition
    props: dict = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class GroupSpec:
    """A node group already in the file, called by its key like a graph of the text."""
    name: str
    inputs: tuple   # (name, type) of its interface
    outputs: tuple
    # The text key of each input and output, when one differs from key(name): see interface_keys
    input_keys: tuple = ()
    output_keys: tuple = ()

    def keys(self, side):
        """(name, key, type) of its inputs ("INPUT") or outputs."""
        sockets, keys = (self.inputs, self.input_keys) if side == "INPUT" else (self.outputs, self.output_keys)
        return [(n, keys[i] if keys else key(n), t) for i, (n, t) in enumerate(sockets)]


class Schema(Protocol):
    def node(self, kind, name):
        """NodeSpec for a text name in a tree kind, or None."""

    def node_names(self, kind):
        """Every text name of the tree kind, for suggestions."""

    def sockets(self, kind, spec, props):
        """(inputs, outputs) available once `props` are set: lists of Socket."""

    def groups(self, kind):
        """{key: GroupSpec, or a list of them when the key repeats} for the groups of the file.

        Optional: a schema without it has no group to offer."""
