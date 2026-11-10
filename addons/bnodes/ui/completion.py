"""Suggestions under the cursor of a .bn text.

The operator is modal: it keeps the popup open while the word is typed,
refreshes it on a timer, and takes ↑ ↓ Tab Enter Esc. Every other key goes
through to the Text Editor. A watcher opens it after `(`, `.` or `:`.
"""

import blf
import bpy

from ..host import BlenderSchema, modules
from ..lang.complete import OPENERS, complete, product_sign
from . import actions, draw, prefs

ROWS = 10
WATCH = 0.1


class Popup:
    """What the draw callback shows; the operator itself may be gone when it runs."""
    text = None  # Text being completed, or None when closed
    line = 0     # 1-based
    start = 0    # 1-based column of the word being replaced
    items = ()
    selected = 0
    seen = None  # (line, column, body) at the last refresh


def cursor_state(text):
    return text.current_line_index, text.current_character, text.current_line.body


def refresh(text):
    """Suggestions at the cursor of the text; False, and closed, when there are none."""
    line, col = text.current_line_index + 1, text.current_character + 1
    with BlenderSchema() as schema:
        Popup.start, items = complete(text.as_string(), line, col, schema, modules.load)
    Popup.line, Popup.items = line, items
    Popup.selected = min(Popup.selected, len(items) - 1) if items else 0
    Popup.text = text if items else None
    Popup.seen = cursor_state(text)
    return bool(items)


def accept(context):
    """Write the selected item in place of the word; True when suggestions follow it."""
    item = Popup.items[Popup.selected]
    text = Popup.text
    row = Popup.line - 1
    text.select_set(row, Popup.start - 1, row, text.current_character)
    bpy.ops.text.insert(text=item.insert)
    # A call or a prop has more to say right after: its inputs, its values
    if item.insert.endswith("(") or item.kind == "prop":
        Popup.selected = 0
        return refresh(text)
    close()
    return False


def close():
    Popup.text, Popup.items, Popup.selected, Popup.seen = None, (), 0, None


class BNODES_OT_complete(bpy.types.Operator):
    """Suggest nodes, inputs, outputs and values at the cursor"""
    bl_idname = "bnodes.complete"
    bl_label = "Suggestions"

    auto: bpy.props.BoolProperty(options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and space.type == "TEXT_EDITOR" and actions.is_bn(space.text)

    def invoke(self, context, event):
        text = context.space_data.text
        if Popup.text is not None or text.current_line_index != text.select_end_line_index \
                or text.current_character != text.select_end_character:
            return {"CANCELLED"}
        if not refresh(text):
            return {"CANCELLED"}
        if not self.auto and len(Popup.items) == 1 and text.current_character + 1 > Popup.start:
            if not accept(context):
                return self.finish(context, {"FINISHED"})
        self.timer = context.window_manager.event_timer_add(WATCH, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def finish(self, context, result):
        close()
        if getattr(self, "timer", None):
            context.window_manager.event_timer_remove(self.timer)
            self.timer = None
        if context.area:
            context.area.tag_redraw()
        return result

    def modal(self, context, event):
        space = context.space_data
        text = Popup.text
        if text is None or space is None or getattr(space, "text", None) != text:
            return self.finish(context, {"CANCELLED", "PASS_THROUGH"})
        context.area.tag_redraw()
        t, press = event.type, event.value == "PRESS"
        plain = not (event.ctrl or event.alt or event.oskey)

        if press and plain and t in {"UP_ARROW", "DOWN_ARROW", "PAGE_UP", "PAGE_DOWN"}:
            step = {"UP_ARROW": -1, "DOWN_ARROW": 1, "PAGE_UP": -ROWS, "PAGE_DOWN": ROWS}[t]
            Popup.selected = max(0, min(len(Popup.items) - 1, Popup.selected + step))
            return {"RUNNING_MODAL"}
        if press and plain and t in {"TAB", "RET", "NUMPAD_ENTER"}:
            return {"RUNNING_MODAL"} if accept(context) else self.finish(context, {"FINISHED"})
        if press and t == "ESC":
            return self.finish(context, {"CANCELLED"})
        if press and t in {"LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE"} or t == "WINDOW_DEACTIVATE":
            return self.finish(context, {"CANCELLED", "PASS_THROUGH"})
        if press and event.unicode and not (event.unicode.isalnum() or event.unicode == "_"):
            # The word is over; the watcher reopens after ( . :
            return self.finish(context, {"CANCELLED", "PASS_THROUGH"})
        if t == "TIMER":
            state = cursor_state(text)
            if state != Popup.seen:
                if state[0] != Popup.line - 1 or state[1] + 1 < Popup.start or not refresh(text):
                    return self.finish(context, {"CANCELLED", "PASS_THROUGH"})
        return {"PASS_THROUGH"}


def draw_popup():
    space = bpy.context.space_data
    text = Popup.text
    try:
        if text is None or space.text != text:
            return
    except ReferenceError:
        return  # the text was freed with its file
    lh = draw.line_height(space)
    scale = bpy.context.preferences.system.ui_scale
    size = round(space.font_size * scale)
    pad = round(4 * scale)
    x, y = draw.char_box(space, Popup.line - 1, Popup.start - 1)
    region = bpy.context.region

    items = Popup.items
    first = max(0, min(Popup.selected - ROWS // 2, len(items) - ROWS))
    shown = items[first:first + ROWS]
    blf.size(0, size)
    label_w = max(blf.dimensions(0, i.label)[0] for i in shown)
    detail_w = max((blf.dimensions(0, i.detail)[0] for i in shown if i.detail), default=0)
    width = label_w + detail_w + pad * (6 if detail_w else 2)
    more = len(items) > ROWS  # a last row says where the selection is
    height = lh * (len(shown) + more) + pad * 2

    top = y - pad  # just under the line being typed
    if top - height < 0:
        top = y + lh + height  # no room below: above the line
    x = max(0, min(x - pad, region.width - width))
    theme = bpy.context.preferences.themes[0].text_editor
    back, sel = theme.space.back, theme.selected_text
    draw.rects([(x - 1, top - height - 1, x + width + 1, top + 1)], (*theme.space.text, 0.35))
    draw.rects([(x, top - height, x + width, top)], (*(c * 0.8 for c in back), 0.97))
    row = Popup.selected - first
    draw.rects([(x, top - pad - lh * (row + 1), x + width, top - pad - lh * row)], (*sel, 1.0))

    fg = theme.space.text
    for n, item in enumerate(shown):
        baseline = top - pad - lh * (n + 1) + (lh - size) // 2 + round(2 * scale)
        blf.color(0, *fg, 1.0)
        blf.position(0, x + pad, baseline, 0)
        blf.draw(0, item.label)
        if item.detail:
            blf.color(0, *fg, 0.55)
            blf.position(0, x + width - pad - blf.dimensions(0, item.detail)[0], baseline, 0)
            blf.draw(0, item.detail)
    if more:
        blf.color(0, *fg, 0.55)
        note = f"{Popup.selected + 1}/{len(items)}"
        baseline = top - pad - lh * (len(shown) + 1) + (lh - size) // 2 + round(2 * scale)
        blf.position(0, x + width - pad - blf.dimensions(0, note)[0], baseline, 0)
        blf.draw(0, note)


# The watcher: one (line, column, body length) per text name, from the last tick
_typed = {}


def watch():
    wm = bpy.context.window_manager
    if wm is None:
        return WATCH
    if Popup.text is not None:
        # A popup left over by an operator that did not end itself (file loaded, area closed)
        if not any(op.bl_idname == "BNODES_OT_complete" for w in wm.windows for op in w.modal_operators):
            close()
        return WATCH
    for window in wm.windows:
        for area in window.screen.areas if window.screen else ():
            if area.type != "TEXT_EDITOR":
                continue
            text = area.spaces.active.text
            if not actions.is_bn(text):
                continue
            body = text.current_line.body
            now = (text.current_line_index, text.current_character, len(body))
            last = _typed.get(text.name)
            _typed[text.name] = now
            typed_one = last and now[0] == last[0] and now[1] == last[1] + 1 and now[2] == last[2] + 1
            if not typed_one:
                continue
            region = next(r for r in area.regions if r.type == "WINDOW")
            swap = product_sign(body[:now[1]])
            if swap:
                swap_sign(text, window, area, region, *swap)
                return WATCH
            if prefs.get().auto_complete and body[now[1] - 1:now[1]] in OPENERS:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.bnodes.complete("INVOKE_DEFAULT", auto=True)
                return WATCH
    return WATCH


def swap_sign(text, window, area, region, start, end, sign):
    """`n dot ` becomes `n ⋅ ` as it is typed; one undo step brings the word back."""
    row = text.current_line_index
    with bpy.context.temp_override(window=window, area=area, region=region):
        text.select_set(row, start, row, end)
        bpy.ops.text.insert("EXEC_DEFAULT", True, text=sign)
        text.cursor_set(row, character=start + len(sign) + 1)
    _typed[text.name] = (row, text.current_character, len(text.current_line.body))


classes = (BNODES_OT_complete,)
_handler = None


def register():
    global _handler
    _handler = bpy.types.SpaceTextEditor.draw_handler_add(draw_popup, (), "WINDOW", "POST_PIXEL")
    bpy.app.timers.register(watch, first_interval=WATCH, persistent=True)


def unregister():
    global _handler
    if bpy.app.timers.is_registered(watch):
        bpy.app.timers.unregister(watch)
    if _handler is not None:
        bpy.types.SpaceTextEditor.draw_handler_remove(_handler, "WINDOW")
        _handler = None
    close()
    _typed.clear()
