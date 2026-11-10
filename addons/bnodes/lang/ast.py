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


@dataclass
class Call:
    name: str
    args: list
    line: int
    col: int


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
class Assign:
    name: str
    value: object
    line: int
    col: int


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


@dataclass
class Frame:
    """`"Title" #color { … }`: a Blender frame around the nodes its statements make. Not a scope."""
    label: str | None
    color: object  # the color's text with its `#`, or None; an (r, g, b) when read from a tree
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace


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
