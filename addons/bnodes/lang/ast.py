"""Syntax tree of a .bn file. Every node keeps its source position (line, col)."""

from dataclasses import dataclass, field


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
    look: Look | None = None  # of the group output, or of a repeat's output


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


@dataclass
class Graph:
    kind: str
    name: str
    params: list
    outputs: list
    single_output: bool  # `-> Geometry` rather than `-> (name: Geometry)`
    body: list
    line: int
    col: int
    end: int = 0  # line of the closing brace
    description: str | None = None  # a string first in the body: the group's tooltip
    description_line: int = 0


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
