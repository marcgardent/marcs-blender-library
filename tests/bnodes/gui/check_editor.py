"""Check the text and node editors in a real Blender window, then quit.

    blender --factory-startup --python tests/bnodes/gui/check_editor.py -- shot.png

Splits the 3D view into a Text Editor on wave.bn and a Node Editor, builds
the tree from the text editor, checks the selection sync both ways, saves a
screenshot. Prints PASS/FAIL lines and exits 1 on a failure.
"""

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402

SHOT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else None
WAVE = (ROOT / "tests" / "bnodes" / "fixtures" / "wave.bn").read_text()
failures = []
areas = {}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def window_region(area):
    return next(r for r in area.regions if r.type == "WINDOW")


def close_splash():
    # Loading the start file again drops the splash screen; the timer is persistent
    bpy.ops.wm.read_homefile()
    return 0.5


def setup():
    bnodes.register()
    win = bpy.context.window
    view = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(window=win, area=view, region=window_region(view)):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.45)
    left, right = sorted((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.x)
    left.type = "TEXT_EDITOR"
    right.type = "NODE_EDITOR"
    right.ui_type = "GeometryNodeTree"
    text = bpy.data.texts.new("wave.bn")
    text.from_string(WAVE)
    space = left.spaces.active
    space.text = text
    space.show_region_ui = True
    space.show_line_numbers = True
    right.spaces.active.show_region_ui = True
    for area, tab in ((left, "Nodes"), (right, "Text")):
        try:
            next(r for r in area.regions if r.type == "UI").active_panel_category = tab
        except AttributeError:
            pass  # read-only until the sidebar has been drawn once
    areas.update(text=left, nodes=right)
    return 0.5


def build():
    # Simulated key presses do not reach Blender in every session (they did not
    # here), so the shortcut is checked in the keymap and the operator is run
    # from the real Text Editor
    km = bpy.context.window_manager.keyconfigs.user.keymaps["Text"]
    bound = [k for k in km.keymap_items if k.idname == "bnodes.text_to_tree"]
    check("Ctrl+Enter is bound in the text editor",
          [(k.type, k.ctrl, k.active) for k in bound] == [("RET", True, True)])
    area = areas["text"]
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=window_region(area),
                                   space_data=area.spaces.active):
        bpy.ops.bnodes.text_to_tree()
    return 0.8


def show_tree():
    tree = bpy.data.node_groups.get("wave")
    check("Text → Tree builds the tree", tree is not None and len(tree.nodes) == 9)
    if tree is None:
        return finish()
    check("tree is linked to its text", tree.bnodes_text == bpy.data.texts["wave.bn"])
    space = areas["nodes"].spaces.active
    space.pin = True
    space.node_tree = tree
    return 0.5


def frame_tree():
    # Once the tree is drawn, so that its nodes have a size
    with bpy.context.temp_override(window=bpy.context.window, area=areas["nodes"],
                                   region=window_region(areas["nodes"])):
        bpy.ops.node.view_all()
    return 0.5


def click_node():
    tree = bpy.data.node_groups["wave"]
    tree.nodes.active = tree.nodes["h"]
    return 0.8


def check_cursor_then_move():
    text = bpy.data.texts["wave.bn"]
    check("active node puts the cursor on its line", text.current_line_index == 2,
          f"line {text.current_line_index + 1}")
    text.cursor_set(1)
    return 0.8


def check_selection():
    tree = bpy.data.node_groups["wave"]
    active = tree.nodes.active
    check("cursor line selects its nodes", active is not None and active.name == "p" and active.select,
          active.name if active else "none")
    check("other nodes are deselected", not tree.nodes["h"].select)
    return 0.5


def text_override():
    area = areas["text"]
    return bpy.context.temp_override(window=bpy.context.window, area=area, region=window_region(area),
                                     space_data=area.spaces.active)


def format_text():
    # Typed through the editor, so that undo has the messy line to come back to. Python calls
    # push undo steps only when asked to, as a click on the button does
    text = bpy.data.texts["wave.bn"]
    with text_override():
        text.select_set(1, 0, 1, len(text.lines[1].body))
        bpy.ops.text.insert("EXEC_DEFAULT", True, text="  p=Position()  // here")
        bpy.ops.bnodes.format("EXEC_DEFAULT", True)
    check("Format rewrites the text and keeps its comment",
          text.as_string() == WAVE.replace("p = Position()", "p = Position()  // here"), text.lines[1].body)
    return 0.5


def undo_format():
    area = areas["text"]
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=window_region(area)):
        bpy.ops.ed.undo()
    text = bpy.data.texts["wave.bn"]  # undo may load the data again
    check("undo brings the text back", text.lines[1].body == "  p=Position()  // here", text.lines[1].body)
    with bpy.context.temp_override(window=bpy.context.window, area=area, region=window_region(area)):
        bpy.ops.ed.redo()
    return 0.5


def shoot():
    for area, tab in ((areas["text"], "Nodes"), (areas["nodes"], "Text")):
        try:
            next(r for r in area.regions if r.type == "UI").active_panel_category = tab
        except AttributeError as e:
            print("NOTE", e)
    return 0.5


def save_shot():
    if SHOT:
        with bpy.context.temp_override(window=bpy.context.window):
            bpy.ops.screen.screenshot(filepath=SHOT)
        print("SHOT", SHOT)
    return finish()


def finish():
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.stdout.flush()
    os._exit(1 if failures else 0)


STEPS = [close_splash, setup, build, show_tree, frame_tree, click_node, check_cursor_then_move, check_selection, format_text, undo_format,
         shoot, save_shot]


def run():
    step = STEPS.pop(0)
    try:
        delay = step()
    except Exception as e:
        check(step.__name__, False, repr(e))
        return finish()
    return delay if STEPS else None


bpy.app.timers.register(run, first_interval=1.0, persistent=True)
