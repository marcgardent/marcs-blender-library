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

RESERVED = {"graph", "return", "true", "false", "and", "or", "xor", "not", "dot", "cross", "repeat"}


def can_link(src, dst):
    return src == dst or (src not in STRICT and dst not in STRICT)


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
