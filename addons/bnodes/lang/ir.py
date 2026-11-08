"""Resolved graph: what the builder materializes, with no name left to look up."""

from dataclasses import dataclass, field

GROUP_INPUT = "group_input"
GROUP_OUTPUT = "group_output"


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


@dataclass
class Graph:
    kind: str
    name: str
    inputs: list   # (name, type) of the group interface
    outputs: list  # (name, type)
    nodes: list
    line: int = 0
    col: int = 0

    def node(self, node_id):
        return next(n for n in self.nodes if n.id == node_id)

    def edges(self):
        """(source id, target id) for every link."""
        return [(link.node, n.id) for n in self.nodes for _ident, link in n.links]
