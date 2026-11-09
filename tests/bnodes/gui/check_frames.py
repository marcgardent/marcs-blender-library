"""Check the frames of frames.bn in a real Blender window, then quit.

    blender --factory-startup --python tests/bnodes/gui/check_frames.py -- shot.png

Builds the tree beside its text, lets Blender draw it so that frames get
their size, checks that no two sibling frames overlap, saves a screenshot.
Prints PASS/FAIL lines and exits 1 on a failure.
"""

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402
from bnodes.ui import actions  # noqa: E402

SHOT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else None
SOURCE = (ROOT / "tests" / "bnodes" / "fixtures" / "frames.bn").read_text()
failures = []
areas = {}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def window_region(area):
    return next(r for r in area.regions if r.type == "WINDOW")


def close_splash():
    bpy.ops.wm.read_homefile()
    return 0.5


def setup():
    bnodes.register()
    win = bpy.context.window
    view = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(window=win, area=view, region=window_region(view)):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.4)
    left, right = sorted((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.x)
    left.type = "TEXT_EDITOR"
    right.type = "NODE_EDITOR"
    right.ui_type = "GeometryNodeTree"
    text = bpy.data.texts.new("frames.bn")
    text.from_string(SOURCE)
    left.spaces.active.text = text
    left.spaces.active.show_line_numbers = True
    (tree,) = actions.text_to_tree(text)
    text.cursor_set(0)
    left.spaces.active.top = 0
    space = right.spaces.active
    space.pin = True
    space.node_tree = tree
    areas.update(text=left, nodes=right)
    return 0.8


def frame_tree():
    with bpy.context.temp_override(window=bpy.context.window, area=areas["nodes"],
                                   region=window_region(areas["nodes"])):
        bpy.ops.node.view_all()
    return 0.8


def box(node, scale):
    """(x0, y0, x1, y1) in view units: dimensions are in pixels, scaled with the interface."""
    x, y = node.location_absolute
    w, h = node.dimensions
    return x, y - h / scale, x + w / scale, y


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def check_frames():
    tree = bpy.data.node_groups["rocks"]
    frames = [n for n in tree.nodes if n.bl_idname == "NodeFrame"]
    check("six frames are built", len(frames) == 6, len(frames))
    sized = all(n.dimensions[0] > 0 for n in frames)
    check("frames are drawn with a size", sized)
    position = tree.nodes["p"]
    scale = position.dimensions[0] / position.width
    clashes = [(a.name, b.name) for i, a in enumerate(frames) for b in frames[i + 1:]
               if a.parent == b.parent and overlap(box(a, scale), box(b, scale))]
    check("sibling frames do not overlap", not clashes, clashes)
    nodes = [n for n in tree.nodes if n.bl_idname != "NodeFrame"]
    outside = [(n.name, f.name) for n in nodes for f in frames
               if overlap(box(n, scale), box(f, scale)) and not is_inside(n, f)]
    check("nodes overlap only their own frames", not outside, outside)
    return 0.3


def is_inside(node, frame):
    parent = node.parent
    while parent is not None:
        if parent == frame:
            return True
        parent = parent.parent
    return False


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


STEPS = [close_splash, setup, frame_tree, check_frames, save_shot]


def run():
    step = STEPS.pop(0)
    try:
        delay = step()
    except Exception as e:
        check(step.__name__, False, repr(e))
        return finish()
    return delay if STEPS else None


bpy.app.timers.register(run, first_interval=1.0, persistent=True)
