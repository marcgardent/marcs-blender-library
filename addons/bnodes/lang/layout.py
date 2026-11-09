"""Layered placement: links go left to right, one column per depth.

Each frame takes a band of rows of its own, below the nodes of its parent,
so that no two frames overlap.
"""

from . import ir

COLUMN = 200   # node width (140) plus the gap
HEADER = 40    # title bar and margins
ROW = 22       # one socket row
GAP = 30       # between nodes of a column
BAND = 90      # between two bands: room for a frame's margins and title
NOTE = 100     # height of an empty frame


def height(node):
    return HEADER + ROW * (node.n_inputs + node.n_outputs)


def layout(graph):
    """{node id: (x, y)}, Blender coordinates (y up), the top-left node at the origin.

    An empty frame, a note, gets a place too, under its id.
    """
    preds = {n.id: [] for n in graph.nodes}
    succs = {n.id: [] for n in graph.nodes}
    for src, dst in graph.edges():
        preds[dst].append(src)
        succs[src].append(dst)

    # Longest path from the sources
    depth = {}

    def depth_of(nid):
        if nid not in depth:
            depth[nid] = 1 + max((depth_of(p) for p in preds[nid]), default=-1)
        return depth[nid]

    for n in graph.nodes:
        depth_of(n.id)

    last = max(depth.values(), default=0)
    if preds[ir.GROUP_OUTPUT] or len(graph.nodes) > 2:
        last = max(last, 1)
    depth[ir.GROUP_OUTPUT] = last
    depth[ir.GROUP_INPUT] = 0

    # A source with no input (Position, a constant) sits just before its first user
    for n in graph.nodes:
        if n.id not in (ir.GROUP_INPUT, ir.GROUP_OUTPUT) and not preds[n.id] and succs[n.id]:
            depth[n.id] = max(0, min(depth[s] for s in succs[n.id]) - 1)

    members, children = {}, {}
    for n in graph.nodes:
        members.setdefault(n.frame, []).append(n)
    for f in graph.frames:
        children.setdefault(f.parent, []).append(f.id)

    def filled(frame):
        return members.get(frame) or any(filled(c) for c in children.get(frame, ()))

    pos = {}

    def band(frame, top):
        """Place a frame's own nodes from `top` down, then its frames below; the y under them all."""
        y = top
        columns = {}
        for n in members.get(frame, ()):
            columns.setdefault(depth[n.id], []).append(n)
        # Order each column by the mean rank of its predecessors in the band, to cut crossings
        rank = {}
        for d in sorted(columns):
            col = columns[d]
            order = {n.id: i for i, n in enumerate(col)}

            def key(n):
                ranks = [rank[p] for p in preds[n.id] if p in rank]
                return (sum(ranks) / len(ranks) if ranks else order[n.id], order[n.id])

            col.sort(key=key)
            bottom = top
            for i, n in enumerate(col):
                rank[n.id] = i
                pos[n.id] = (d * COLUMN, -bottom)
                bottom += height(n) + GAP
            y = max(y, bottom)
        for child in children.get(frame, ()):
            if y > top:
                y += BAND
            if filled(child):
                y = band(child, y)
            else:
                pos[child] = (0, -y)
                y += NOTE
        return y

    band(None, 0)
    return pos
