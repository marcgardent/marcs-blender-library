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
class Param:
    name: str
    type: str
    line: int
    col: int


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


@dataclass
class File:
    graphs: list = field(default_factory=list)
