"""Check the suggestions popup and the highlighting in a real Blender window, then quit.

    blender --factory-startup --python tests/bnodes/gui/check_completion.py -- shots_dir

Key presses do not reach Blender in every session, so typing is done by
writing into the text, and accepting an item calls what Tab or Enter call.
Prints PASS/FAIL lines, saves screenshots, exits 1 on a failure.
"""

import os
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402
from bnodes.ui import completion  # noqa: E402
from bnodes.ui.completion import Popup  # noqa: E402

SHOTS = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None
WAVE = (ROOT / "tests" / "bnodes" / "fixtures" / "wave.bn").read_text()
DRAFT = "\n".join(WAVE.split("\n")[:3]) + "\n  return SetPosition"
failures = []
area = {}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def override():
    a = area["text"]
    return bpy.context.temp_override(window=bpy.context.window, area=a,
                                     region=next(r for r in a.regions if r.type == "WINDOW"),
                                     space_data=a.spaces.active)


def shot(name):
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        with bpy.context.temp_override(window=bpy.context.window):
            bpy.ops.screen.screenshot(filepath=str(SHOTS / f"{name}.png"))
        print("SHOT", SHOTS / f"{name}.png")


def labels():
    return [i.label for i in Popup.items]


def running():
    return any(op.bl_idname == "BNODES_OT_complete" for op in bpy.context.window.modal_operators)


def last_line():
    return bpy.data.texts["wave.bn"].current_line.body


def close_splash():
    bpy.ops.wm.read_homefile()
    return 0.5


def setup():
    bnodes.register()
    win = bpy.context.window
    a = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    a.type = "TEXT_EDITOR"
    text = bpy.data.texts.new("wave.bn")
    text.from_string(DRAFT)
    space = a.spaces.active
    space.text = text
    space.show_line_numbers = True
    text.cursor_set(3, character=len(text.lines[3].body))
    area["text"] = a
    return 0.5


def type_paren():
    bpy.data.texts["wave.bn"].write("(")
    return 0.6


def check_auto_open():
    check("typing ( opens the suggestions", Popup.text is not None and running())
    check("inputs of SetPosition first", labels()[:4] == ["geometry", "selection", "position", "offset"],
          labels()[:6])
    return 0.3


def shoot_inputs():
    shot("inputs")
    return 0.2


def accept_offset():
    Popup.selected = labels().index("offset")
    with override():
        more = completion.accept(bpy.context)
    check("accepting writes the named argument", last_line() == "  return SetPosition(offset: ", last_line())
    check("an input closes the suggestions", not more and Popup.text is None)
    return 0.4


def type_word():
    check("the operator ends with its popup", not running())
    bpy.data.texts["wave.bn"].write("Comb")
    with override():
        bpy.ops.bnodes.complete("INVOKE_DEFAULT")
    check("the shortcut's operator opens on a word", Popup.text is not None and labels()[0].startswith("Comb"),
          labels()[:5])
    bpy.data.texts["wave.bn"].write("ineX")
    return 0.5


def check_refilter():
    check("typing narrows the list", labels() == ["CombineXYZ"], labels()[:5])
    with override():
        more = completion.accept(bpy.context)
    check("accepting a node opens its inputs", more and labels()[:3] == ["x", "y", "z"], labels()[:5])
    check("the node is written", last_line().endswith("offset: CombineXYZ("), last_line())
    return 0.4


def shoot_node_inputs():
    shot("node_inputs")
    completion.close()
    return 0.4


def type_dot():
    check("closing ends the operator", not running())
    # Typed through the editor with undo steps, as keys would; the watcher sees one character at a time
    text = bpy.data.texts["wave.bn"]
    text.from_string(WAVE)
    text.cursor_set(2, character=len(text.lines[2].body))
    with override():
        bpy.ops.text.insert("EXEC_DEFAULT", True, text="\n  k = p dot")
    return 0.4


def type_space():
    with override():
        bpy.ops.text.insert("EXEC_DEFAULT", True, text=" ")
    return 0.4


def check_dot():
    check("dot becomes ⋅ once typed", last_line() == "  k = p ⋅ ", last_line())
    with bpy.context.temp_override(window=bpy.context.window, area=area["text"],
                                   region=next(r for r in area["text"].regions if r.type == "WINDOW")):
        bpy.ops.ed.undo()
    check("undo brings dot back", bpy.data.texts["wave.bn"].lines[3].body == "  k = p dot ",
          bpy.data.texts["wave.bn"].lines[3].body)
    return 0.4


def full_text():
    text = bpy.data.texts["wave.bn"]
    text.from_string(WAVE + "\n// a comment\n")
    text.cursor_set(0)
    area["text"].spaces.active.top = 0
    return 0.5


def shoot_highlight():
    shot("highlight")
    space = area["text"].spaces.active
    space.font_size = 20
    space.show_word_wrap = False
    return 0.5


def shoot_zoomed():
    shot("highlight_zoomed")
    return finish()


def finish():
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.stdout.flush()
    os._exit(1 if failures else 0)


STEPS = [close_splash, setup, type_paren, check_auto_open, shoot_inputs, accept_offset, type_word,
         check_refilter, shoot_node_inputs, type_dot, type_space, check_dot, full_text, shoot_highlight,
         shoot_zoomed]


def run():
    step = STEPS.pop(0)
    try:
        delay = step()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check(step.__name__, False, repr(e))
        return finish()
    return delay if STEPS else None


bpy.app.timers.register(run, first_interval=1.0, persistent=True)
