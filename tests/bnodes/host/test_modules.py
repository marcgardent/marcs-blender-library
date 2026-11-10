"""Modules and the groups of the file, run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_modules.py
"""

import sys
import tempfile
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402
from bnodes.host import build_source, export_tree  # noqa: E402
from bnodes.host.modules import module_of  # noqa: E402
from bnodes.lang import BnError  # noqa: E402

bnodes.register()

MATHS = """\
geometry graph double(x: Float) -> Float {
  return x * 2.0
}

geometry graph quadruple(x: Float) -> Float {
  return double(double(x))
}

geometry graph moitié(x: Float) -> Float {
  return x / 2.0
}
"""

BODY = """\
geometry graph monte(geometry: Geometry) -> Geometry {
  return SetPosition(geometry, offset: CombineXYZ(z: quadruple(0.25)))
}
"""


def reset():
    # The add-on stays registered: its classes and properties live on past the reset
    bpy.ops.wm.read_factory_settings(use_empty=True)


def maths_text():
    text = bpy.data.texts.new("maths.bn")
    text.from_string(MATHS)
    return text


def errors(source):
    try:
        build_source(source, "t.bn")
    except BnError as e:
        return [d.message for d in e.diagnostics]
    raise AssertionError("no error")


def test_use_builds_the_module_from_its_text():
    reset()
    text = maths_text()
    (tree,) = build_source("use maths\n\n" + BODY, "t.bn")
    assert tree.name == "monte" and module_of(tree) is None
    for name in ("double", "quadruple", "moitié"):
        group = bpy.data.node_groups[name]
        assert module_of(group) == ("maths", None), name
        assert group.bnodes_text == text, name
    (call,) = [n for n in tree.nodes if n.bl_idname == "GeometryNodeGroup"]
    assert call.node_tree == bpy.data.node_groups["quadruple"]


def test_a_list_builds_only_what_it_needs():
    reset()
    maths_text()
    build_source("use maths (quadruple)\n\n" + BODY, "t.bn")
    assert "double" in bpy.data.node_groups and "moitié" not in bpy.data.node_groups


def test_export_writes_the_use_instead_of_the_module():
    reset()
    maths_text()
    (tree,) = build_source("use maths\n\n" + BODY, "t.bn")
    source, warnings = export_tree(tree)
    assert not warnings, warnings
    assert source == "use maths (quadruple)\n\n" + BODY, source
    (again,) = build_source(source, "t.bn")
    assert again == tree


def test_export_of_a_module_graph_keeps_its_own_module_inline():
    reset()
    maths_text()
    build_source("use maths\n\n" + BODY, "t.bn")
    source, _warnings = export_tree(bpy.data.node_groups["quadruple"])
    assert "use" not in source and "graph double" in source and "graph quadruple" in source, source


def test_building_the_module_itself_clears_the_mark():
    reset()
    maths_text()
    build_source("use maths\n\n" + BODY, "t.bn")
    build_source(MATHS, "maths.bn")
    assert module_of(bpy.data.node_groups["double"]) is None


def test_a_file_module_is_relative_to_the_blend():
    reset()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "lib").mkdir()
        (Path(tmp) / "lib" / "maths.bn").write_text(MATHS)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(tmp) / "scène.blend"))
        src = 'use maths from "//lib/maths.bn"\n\n' + BODY
        (tree,) = build_source(src, "t.bn")
        assert module_of(bpy.data.node_groups["double"]) == ("maths", "//lib/maths.bn")
        assert bpy.data.node_groups["double"].bnodes_text is None
        source, _warnings = export_tree(tree)
        assert source == src.replace("use maths from", "use maths (quadruple) from"), source


def test_unsaved_file_and_dot_paths_explain_themselves():
    reset()
    (message,) = errors('use maths from "//lib/maths.bn"\n\n' + BODY)
    assert "enregistrer le fichier d'abord" in message, message
    (message,) = errors('use maths from "./lib/maths.bn"\n\n' + BODY)
    assert "« //lib/maths.bn »" in message, message
    (message,) = errors("use maths\n\n" + BODY)
    assert message.startswith("module « maths » : pas de texte « maths.bn »"), message


def test_a_group_of_the_file_is_called_as_it_is():
    reset()
    (helper,) = build_source("geometry graph \"Lift Up\"(z: Float, gain: Float) -> Vector {\n"
                             "  return CombineXYZ(z: z * gain)\n}\n", "helper.bn")
    helper.nodes.new("NodeFrame").name = "mine"
    src = "geometry graph g(geometry: Geometry) -> Geometry {\n" \
          "  return SetPosition(geometry, offset: lift_up(0.5, gain: 3.0))\n}\n"
    (tree,) = build_source(src, "t.bn")
    (call,) = [n for n in tree.nodes if n.bl_idname == "GeometryNodeGroup"]
    assert call.node_tree == helper and "mine" in helper.nodes
    assert call.inputs["z"].default_value == 0.5 and call.inputs["gain"].default_value == 3.0


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
