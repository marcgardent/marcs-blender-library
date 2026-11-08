"""Build tests, run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_build.py
"""

import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

from bnodes.host import BlenderSchema, build_source  # noqa: E402
from bnodes.lang import BnError  # noqa: E402

WAVE = (ROOT / "tests" / "bnodes" / "fixtures" / "wave_v0.bn").read_text()


def test_wave_builds_nine_nodes_and_nine_links():
    (tree,) = build_source(WAVE, "wave_v0.bn")
    assert tree.name == "wave" and tree.is_modifier
    assert len(tree.nodes) == 9, [n.bl_idname for n in tree.nodes]
    assert len(tree.links) == 9
    assert all(link.is_valid for link in tree.links)
    assert tree.nodes["p"].bl_idname == "GeometryNodeInputPosition"
    assert tree.nodes["h"].operation == "MULTIPLY"
    assert abs(tree.nodes["h"].inputs[1].default_value - 0.2) < 1e-6
    items = tree.interface.items_tree
    assert [(s.name, s.socket_type) for s in items if s.in_out == "INPUT"] == [
        ("geometry", "NodeSocketGeometry"), ("t", "NodeSocketFloat")]
    assert [(s.name, s.socket_type) for s in items if s.in_out == "OUTPUT"] == [
        ("Geometry", "NodeSocketGeometry")]


def test_rebuild_keeps_users_and_named_places():
    (tree,) = build_source(WAVE, "wave_v0.bn")
    bpy.ops.mesh.primitive_cube_add()
    mod = bpy.context.object.modifiers.new("wave", "NODES")
    mod.node_group = tree
    tree.nodes["p"].location = (-500, 300)

    (again,) = build_source(WAVE.replace("0.2", "0.5"), "wave_v0.bn")
    assert again.name == "wave"
    assert mod.node_group == again
    assert tuple(again.nodes["p"].location) == (-500, 300)
    assert abs(again.nodes["h"].inputs[1].default_value - 0.5) < 1e-6
    assert len([g for g in bpy.data.node_groups if g.name.startswith("wave")]) == 1


def test_failed_build_leaves_the_tree_alone():
    (tree,) = build_source(WAVE, "wave_v0.bn")
    before = len(bpy.data.node_groups)
    try:
        build_source(WAVE.replace("x, t", "w, t"), "wave_v0.bn")
    except BnError as e:
        assert "SeparateXYZ n'a pas de sortie « w » ; sorties : x, y, z" in str(e), str(e)
    else:
        raise AssertionError("no error")
    assert len(bpy.data.node_groups) == before
    assert bpy.data.node_groups["wave"] == tree


def test_schema_reads_blender():
    with BlenderSchema() as schema:
        math = schema.node("geometry", "Math")
        assert math.bl_idname == "ShaderNodeMath"
        assert "SINE" in math.props["operation"].items
        assert schema.node("geometry", "Position").bl_idname == "GeometryNodeInputPosition"
        assert schema.node("geometry", "GeometryNodeSetPosition").name == "SetPosition"
        inputs, _ = schema.sockets("geometry", math, {"operation": "SINE"})
        assert [s.identifier for s in inputs] == ["Value"]
        inputs, _ = schema.sockets("geometry", math, {"operation": "MULTIPLY_ADD"})
        assert [s.identifier for s in inputs] == ["Value", "Value_001", "Value_002"]
    assert not [g for g in bpy.data.node_groups if g.name.startswith(".bnodes_scratch")]


def test_names_do_not_depend_on_the_ui_language():
    prefs = bpy.context.preferences.view
    prefs.language = "fr_FR"
    prefs.use_translate_interface = prefs.use_translate_new_dataname = True
    try:
        (tree,) = build_source(WAVE, "wave_v0.bn")
        sep = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeSeparateXYZ")
        assert [s.name for s in sep.outputs] == ["X", "Y", "Z"]
        set_pos = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeSetPosition")
        assert [s.name for s in set_pos.inputs] == ["Geometry", "Selection", "Position", "Offset"]
        assert "Group Input" in tree.nodes
    finally:
        prefs.language = "en_US"


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
