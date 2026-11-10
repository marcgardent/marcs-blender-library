"""Resolved graph: what the builder materializes, with no name left to look up."""

from dataclasses import dataclass, field

GROUP_INPUT = "group_input"
GROUP_OUTPUT = "group_output"

REPEAT_INPUT = "GeometryNodeRepeatInput"
REPEAT_OUTPUT = "GeometryNodeRepeatOutput"
SIMULATION_INPUT = "GeometryNodeSimulationInput"
SIMULATION_OUTPUT = "GeometryNodeSimulationOutput"
FOREACH_INPUT = "GeometryNodeForeachGeometryElementInput"
FOREACH_OUTPUT = "GeometryNodeForeachGeometryElementOutput"

CLOSURE_INPUT = "NodeClosureInput"
CLOSURE_OUTPUT = "NodeClosureOutput"

ZONE_INPUTS = (REPEAT_INPUT, SIMULATION_INPUT, FOREACH_INPUT, CLOSURE_INPUT)
ZONE_OUTPUTS = (REPEAT_OUTPUT, SIMULATION_OUTPUT, FOREACH_OUTPUT, CLOSURE_OUTPUT)

# A zone node's fixed sockets, before its items: (inputs, outputs), by their text identifier.
# The For Each output's own Geometry has one no item can take: the default item is a "Geometry" too.
FOREACH_GEOMETRY = "__geometry__"
ZONE_SOCKETS = {
    REPEAT_INPUT: (("Iterations",), ("Iteration",)),
    REPEAT_OUTPUT: ((), ()),
    SIMULATION_INPUT: ((), ("Delta Time",)),
    SIMULATION_OUTPUT: (("Skip",), ()),
    FOREACH_INPUT: (("Geometry", "Selection"), ("Index", "Element")),
    FOREACH_OUTPUT: ((), (FOREACH_GEOMETRY,)),
}


@dataclass(frozen=True)
class Link:
    node: str    # source node id
    output: str  # output identifier; a parameter name on the group input


@dataclass
class Node:
    id: str
    bl_idname: str
    name: str | None = None  # the text name bound to it, kept as the Blender node name
    props: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)  # input identifier -> literal
    links: list = field(default_factory=list)   # (input identifier, Link); a multi-input may repeat
    group: str | None = None  # called graph, for a group node
    n_inputs: int = 0
    n_outputs: int = 0
    line: int = 0
    col: int = 0
    frame: str | None = None  # id of the frame it sits in
    # (name, type) of a zone's items, on both nodes of the zone; a For Each input has its
    # input items, its output the main items then the generation ones
    items: list | None = None
    pair: str | None = None    # on a zone's input node: the id of its output node
    main: int = 0              # on a For Each output: how many of its items are main items
    out_items: list | None = None  # (name, type) of the output items: a closure's, a Separate Bundle's
    # item name -> {item property: value}, when written; ("out", name) for one of out_items
    item_options: dict = field(default_factory=dict)
    look: dict = field(default_factory=dict)  # Blender property -> value: label, color, hide, mute


@dataclass
class Frame:
    id: str
    label: str | None
    color: tuple | None  # (r, g, b) in 0..1; None keeps the theme's
    parent: str | None = None
    line: int = 0
    col: int = 0


@dataclass
class Panel:
    """An interface panel. Blender puts in each panel its outputs, then its inputs, then its panels."""
    id: str
    name: str
    parent: str | None = None  # id of the panel it sits in
    options: dict = field(default_factory=dict)  # {Blender property: value}: description, default_closed
    line: int = 0
    col: int = 0


@dataclass
class Graph:
    kind: str
    name: str
    inputs: list   # (name, type) of the group interface
    outputs: list  # (name, type)
    nodes: list
    line: int = 0
    col: int = 0
    frames: list = field(default_factory=list)  # parents before their children
    # input key -> {"value", "min", "max", "implicit"}, each only when written
    defaults: dict = field(default_factory=dict)
    module: tuple | None = None  # (name, source) of the module that brought it, for a `use`
    # ("INPUT" or "OUTPUT", socket key) -> {Blender property: value}: subtype, description…
    options: dict = field(default_factory=dict)
    description: str | None = None  # the group's tooltip
    # The text key of each input and output, in order: how links and calls name them.
    # Its name's key, or the `as` one when two sockets share a name
    input_keys: list = field(default_factory=list)
    output_keys: list = field(default_factory=list)
    panels: list = field(default_factory=list)  # parents before their children, siblings in order
    panel_of: dict = field(default_factory=dict)  # ("INPUT" or "OUTPUT", socket key) -> panel id
    settings: dict = field(default_factory=dict)  # the tree's own: {Blender property: value}

    def keys(self, side):
        return self.input_keys if side == "INPUT" else self.output_keys

    def node(self, node_id):
        return next(n for n in self.nodes if n.id == node_id)

    def edges(self):
        """(source id, target id) for every link."""
        return [(link.node, n.id) for n in self.nodes for _ident, link in n.links]
