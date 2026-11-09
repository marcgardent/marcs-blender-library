"""Mixed view: a .bn text and its tree side by side follow each other.

Clicking a node puts the text cursor on its line; moving the cursor to a
line selects the nodes of that line. Selection changes made by operators
do not always reach msgbus, so a timer compares with the last state.
"""

import bpy

from . import actions

PERIOD = 0.25

# (text name, tree name) -> (active node name, cursor line) last seen
_seen = {}


def pairs(window):
    """(text area, node area) shown together, where the tree was built from the text."""
    areas = window.screen.areas if window.screen else ()
    texts = [a for a in areas if a.type == "TEXT_EDITOR" and actions.is_bn(a.spaces.active.text)]
    nodes = [a for a in areas if a.type == "NODE_EDITOR" and a.spaces.active.edit_tree is not None]
    for ta in texts:
        for na in nodes:
            if na.spaces.active.edit_tree.bnodes_text == ta.spaces.active.text:
                yield ta, na


def follow(ta, na):
    space = ta.spaces.active
    text, tree = space.text, na.spaces.active.edit_tree
    key = (text.name, tree.name)
    active = tree.nodes.active
    state = (active.name if active else None, text.current_line_index + 1)
    last = _seen.get(key)
    _seen[key] = state
    if last is None or state == last:
        return

    if state[0] != last[0] and active is not None:
        line = actions.node_line(active)
        if line:
            text.cursor_set(line - 1)
            if not space.top <= line - 1 < space.top + space.visible_lines:
                space.top = max(0, line - 1 - space.visible_lines // 2)
            ta.tag_redraw()
            _seen[key] = (state[0], line)
    elif state[1] != last[1]:
        found = actions.nodes_on_line(tree, state[1])
        if found:
            for n in tree.nodes:
                n.select = n in found
            tree.nodes.active = found[0]
            na.tag_redraw()
            _seen[key] = (found[0].name, state[1])


def tick():
    wm = bpy.context.window_manager
    if wm is None or not wm.bnodes_sync:
        return PERIOD
    for window in wm.windows:
        for ta, na in pairs(window):
            follow(ta, na)
    return PERIOD


def register():
    bpy.app.timers.register(tick, first_interval=PERIOD, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    _seen.clear()
