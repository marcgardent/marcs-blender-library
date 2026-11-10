"""Syntax tree of a .bn file. Every node keeps its source position (line, col)."""

from dataclasses import dataclass, field

from .schema import key


@dataclass
class Number:
    value: float
    is_int: bool
    line: int
    col: int


@dataclass
class String:
    value: str
    line: int
    col: int


@dataclass
class Bool:
    value: bool
    line: int
    col: int


@dataclass
class Tuple:
    items: list
    line: int
    col: int


@dataclass
class Ref:
    """A bare name: a parameter, a local, or an enum value such as POWER."""
    name: str
    line: int
    col: int


@dataclass
class Arg:
    name: str | None  # None for a positional argument
    value: object
    line: int
    col: int
    # `Lisse(description: "…"): a`: an item's other settings, by their Blender name
    options: list = field(default_factory=list)  # of Arg, all named
    # `hauteur: Float = h`: an item given its type, a Param (its options are merged into `options`)
    type: object = None
    # `Selection as capturé: m`: the key of an item named like an input or a setting of its node
    alias: str | None = None


@dataclass
class Call:
    name: str
    args: list
    line: int
    col: int
    # `SeparateBundle(b) -> (hauteur: Float)`: the output items it declares, Params
    outputs: list | None = None
    single_output: bool = False  # `-> Float` rather than `-> (name: Float)`


@dataclass
class Member:
    """`target.socket`: picks an output of a node."""
    target: object
    socket: str
    line: int
    col: int


@dataclass
class Pipe:
    """`left |> call` means `call` with `left` as its first positional argument."""
    left: object
    call: object  # a Call, or a Member of a Call
    line: int
    col: int


@dataclass
class BinOp:
    op: str
    left: object
    right: object
    line: int
    col: int


@dataclass
class Neg:
    value: object
    line: int
    col: int


@dataclass
class Not:
    value: object
    line: int
    col: int


@dataclass
class Look:
    """`@ "Label" #color hide mute` after a statement: how the node it makes is shown in the editor."""
    flags: list  # of words: hide, mute
    line: int
    col: int
    label: str | None = None
    color: object = None  # the color's text with its `#`, or None; an (r, g, b) when read from a tree


@dataclass
class Assign:
    name: str
    value: object
    line: int
    col: int
    look: Look | None = None


@dataclass
class Record:
    """`return (mesh: a, area: b)` for a graph with several outputs."""
    fields: list  # of Arg, all named
    line: int
    col: int


@dataclass
class Return:
    value: object
    line: int
    col: int
    look: Look | None = None  # of the group output, or of the output node of the zone it ends


@dataclass
class Frame:
    """`"Title" #color { … }`: a Blender frame around the nodes its statements make. Not a scope."""
    label: str | None
    color: object  # the color's text with its `#`, or None; an (r, g, b) when read from a tree
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace
    # `"Title" .. { … }`: more of the last frame of that title in the same block, not a new one
    continued: bool = False


@dataclass
class Repeat:
    """`repeat(count, state: start, …) { … return (state: next, …) }`: a Repeat zone.

    Written only as the value of an assignment. In the body the states are names,
    and `iteration` is the number of the current turn, from 0.
    """
    count: object
    states: list  # of Arg, all named
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace


@dataclass
class Closure:
    """`closure(x: Float, …) -> Float { … return … }`: a Closure zone.

    Written only as the value of an assignment. In the body the inputs are names,
    and the names outside are seen too: their values are captured.
    """
    params: list   # of Param
    outputs: list  # of Param
    single_output: bool
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace


@dataclass
class Simulate:
    """`simulate(state: start, …) { … return (state: next, …, skip: c) }`: a Simulation zone.

    Written only as the value of an assignment. In the body the states are names,
    and `delta_time` is the time since the last step.
    """
    states: list  # of Arg, all named
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace


@dataclass
class Foreach:
    """`foreach(geometry, domain: FACE, item: field, …) { … return (main: v, …, mesh: g, attribute: a, …) }`:
    a For Each Geometry Element zone.

    Written only as the value of an assignment. The named arguments are the domain, the
    selection and the input items; in the body `index`, `element` and the input items are
    names. The returned fields before the first Geometry are main items, the rest
    generation items: each Geometry and the attributes after it.
    """
    geometry: object
    args: list  # of Arg, all named
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace


# Zones are blocks written as the value of an assignment
ZONES = (Repeat, Simulate, Foreach, Closure)


@dataclass
class Param:
    """`name: Type = default in lo..hi`; the default and the range are optional."""
    name: str
    type: str
    line: int
    col: int
    default: object = None  # a literal, or a call such as Position() for an implicit input
    range: tuple | None = None  # (lo, hi) literals, None for an open side
    # `x: Float(subtype: FACTOR, description: "…")`: other interface settings, by their Blender name
    options: list = field(default_factory=list)  # of Arg, all named
    # `"Seed" as guide_seed: Int`: the name the text gives it, when two sockets share a name
    alias: str | None = None

    @property
    def key(self):
        """How the body and the callers name it."""
        return self.alias or key(self.name)


@dataclass
class Panel:
    """`"Title"(default_closed: true) { a: Float, … }` in a parameter or output list: an interface panel.

    Its items are Params, then nested Panels. A panel holding inputs and outputs is
    written in both lists, its settings in the first.
    """
    name: str
    items: list
    line: int
    col: int
    options: list = field(default_factory=list)  # of Arg, all named: description, default_closed
    end: int = 0  # line of the closing brace


def flatten(items):
    """The Params of a parameter list, panels opened, in order."""
    out = []
    for i in items:
        out += flatten(i.items) if isinstance(i, Panel) else [i]
    return out


@dataclass
class Graph:
    kind: str
    name: str
    params: list   # every input, panels opened: see `inputs` for the list as written
    outputs: list
    single_output: bool  # `-> Geometry` rather than `-> (name: Geometry)`
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace
    description: str | None = None  # a string first in the body: the group's tooltip
    description_line: int = 0
    # `geometry(is_tool: true) graph …`: the tree's own settings, by their Blender name
    settings: list = field(default_factory=list)  # of Arg, all named
    # The lists as written, with their Panels; None when they have none
    param_tree: list | None = None
    output_tree: list | None = None

    def tree(self, side):
        """The inputs ("INPUT") or outputs as written: Params and Panels."""
        if side == "INPUT":
            return self.param_tree if self.param_tree is not None else self.params
        return self.output_tree if self.output_tree is not None else self.outputs


@dataclass
class Use:
    """`use maths (fbm, bosse) from "//lib/maths.bn"`: the list and the source are optional.

    With no source, the module is the text `maths.bn` of the same .blend.
    """
    name: str
    names: list | None  # graph keys; None imports every graph of the module
    source: str | None
    line: int
    col: int


@dataclass
class File:
    graphs: list = field(default_factory=list)
    uses: list = field(default_factory=list)
