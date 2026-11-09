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
from bnodes.ui import actions  # noqa: E402

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
    items = [k for k in kc.keymaps["Text"].keymap_items if k.idname == "bnodes.text_to_tree"]
    assert [(k.type, k.ctrl) for k in items] == [("RET", True)]


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
