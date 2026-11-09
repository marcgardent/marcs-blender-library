"""Add-on tests without a UI, run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_ui.py
"""

import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402
from bnodes.lang import BnError  # noqa: E402
from bnodes.lang.lexer import tokenize  # noqa: E402
from bnodes.ui import actions, completion, highlight  # noqa: E402

WAVE = (ROOT / "tests" / "bnodes" / "fixtures" / "wave.bn").read_text()

bnodes.register()


def new_text(name, body):
    text = bpy.data.texts.new(name)
    text.from_string(body)
    return text


def test_text_to_tree_links_and_numbers_nodes():
    text = new_text("wave.bn", WAVE)
    (tree,) = actions.text_to_tree(text)
    assert tree.bnodes_text == text
    assert actions.linked_trees(text) == [tree]
    assert [n.name for n in actions.nodes_on_line(tree, 2)] == ["p"]
    line3 = {n.bl_idname for n in actions.nodes_on_line(tree, 3)}
    assert line3 == {"ShaderNodeSeparateXYZ", "ShaderNodeMath"}, line3
    assert actions.node_line(tree.nodes["Group Output"]) == 4


def test_error_moves_the_cursor_and_is_kept_for_the_panel():
    text = new_text("broken.bn", WAVE.replace("CombineXYZ(z: h)", "CombineXYZ(w: h)"))
    try:
        actions.text_to_tree(text)
    except BnError:
        pass
    else:
        raise AssertionError("no error")
    (d,) = actions.DIAGNOSTICS["broken.bn"]
    assert (d.line, d.col) == (4, 51) and "« w »" in d.message, d
    assert (text.current_line_index, text.current_character) == (3, 50)
    assert "broken" not in bpy.data.node_groups


def test_tree_to_text_writes_the_linked_text():
    text = bpy.data.texts["wave.bn"]
    text.from_string("// edited by hand\n" + WAVE)
    tree = bpy.data.node_groups["wave"]
    written, warnings = actions.tree_to_text(tree)
    assert written == text and warnings == []
    assert text.as_string() == WAVE


def test_tree_to_text_creates_a_text():
    (tree,) = actions.text_to_tree(new_text("other.bn", WAVE.replace("wave", "ripple")))
    tree.bnodes_text = None
    text, _ = actions.tree_to_text(tree)
    assert text.name == "ripple.bn" and tree.bnodes_text == text


def test_shortcut_is_bound_to_text_editor():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return  # no add-on keyconfig in this Blender session
    items = {k.idname: k for k in kc.keymaps["Text"].keymap_items if k.idname.startswith("bnodes.")}
    build, suggest = items["bnodes.text_to_tree"], items["bnodes.complete"]
    assert (build.type, build.ctrl) == ("RET", True)
    assert (suggest.type, suggest.alt, suggest.ctrl, suggest.shift) == ("SPACE", True, False, False)


def test_suggestions_come_from_blender():
    text = new_text("draft.bn", "geometry graph d(geometry: Geometry) -> Geometry {\n  x = Math(operation: ")
    text.cursor_set(1, character=len(text.lines[1].body))
    assert completion.refresh(text)
    labels = [i.label for i in completion.Popup.items]
    assert "SINE" in labels and "ADD" in labels, labels[:5]
    text.from_string("geometry graph d(geometry: Geometry) -> Geometry {\n  return SetPosition(")
    text.cursor_set(1, character=len(text.lines[1].body))
    assert completion.refresh(text)
    labels = [i.label for i in completion.Popup.items]
    assert labels[:4] == ["geometry", "selection", "position", "offset"], labels[:6]
    completion.close()
    assert ".bnodes_scratch_geometry" not in bpy.data.node_groups


def test_highlight_classes():
    line = '  return SetPosition(geometry, offset: CombineXYZ(z: sin(h) * 0.2)) // up'
    got = [(t.text, c) for t, c in highlight.classify(tokenize(line, strict=False)[:-1])]
    assert got == [("return", "keyword"), ("SetPosition", "node"), ("CombineXYZ", "node"),
                   ("sin", "function"), ("0.2", "literal"), ("// up", "comment")], got
    head = 'geometry graph wave(geometry: Geometry, t: Float) -> Geometry {'
    got = [(t.text, c) for t, c in highlight.classify(tokenize(head, strict=False)[:-1])]
    assert got == [("geometry", "keyword"), ("graph", "keyword"), ("wave", "node"), ("Geometry", "Geometry"),
                   ("Float", "Float"), ("Geometry", "Geometry")], got


def test_unregister_and_register_again():
    bnodes.unregister()
    assert not hasattr(bpy.types.NodeTree, "bnodes_text")
    bnodes.register()
    assert bpy.data.node_groups["wave"].bnodes_text == bpy.data.texts["wave.bn"]


def main():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


main()
