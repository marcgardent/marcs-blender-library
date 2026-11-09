"""Export tests, run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_export.py
"""

import glob
import os
import sys
import traceback
from collections import Counter
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

from bnodes.host import build_source, export_tree  # noqa: E402
from bnodes.lang import sugar  # noqa: E402

FIXTURES = ROOT / "tests" / "bnodes" / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text()


def test_wave_comes_back_identical():
    src = fixture("wave.bn")
    (tree,) = build_source(src, "wave.bn")
    assert len(tree.nodes) == 9 and len(tree.links) == 9
    text, warnings = export_tree(tree)
    assert text == src, text
    assert warnings == []


def test_frames_come_back_identical():
    src = fixture("frames.bn")
    (tree,) = build_source(src, "frames.bn")
    frames = {f.label or f.name: f for f in tree.nodes if f.bl_idname == "NodeFrame"}
    assert sorted(frames) == ["Check the scale", "Detail", "Frame", "Frame.001", "Noise", "Output"], sorted(frames)
    assert frames["Detail"].parent == frames["Noise"]
    assert frames["Noise"].use_custom_color and tuple(round(c, 3) for c in frames["Noise"].color) == (1.0, 0.647, 0.0)
    assert not frames["Output"].use_custom_color
    assert tree.nodes["p"].parent == frames["Noise"] and tree.nodes["d"].parent == frames["Detail"]
    assert tree.nodes["Group Output"].parent == frames["Output"]
    text, warnings = export_tree(tree)
    assert text == src, text
    assert warnings == []


def test_a_node_in_another_frame_than_its_user_gets_a_name():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    frame = tree.nodes.new("NodeFrame")
    frame.label = "Wave"
    sine = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "SINE")
    sine.parent = frame
    text, warnings = export_tree(tree)
    # The Add before it stays out of the frame, so it gets a name too
    assert '  math = p.x + t\n  "Wave" {\n    math_2 = sin(math)\n  }\n  h = math_2 * 0.2\n' in text, text
    assert warnings == []
    build_source(text, "wave.bn")
    assert tree.nodes["math_2"].parent.label == "Wave" and tree.nodes["math"].parent is None


def test_a_frame_split_by_its_links_is_reported():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    frame = tree.nodes.new("NodeFrame")
    frame.label = "Ends"
    for name in ("p", "Group Output"):
        tree.nodes[name].parent = frame
    tree.nodes["h"].parent = None
    text, warnings = export_tree(tree)
    assert text.count('"Ends" {') == 2, text
    assert any("coupé en deux" in w for w in warnings), warnings


def test_products_come_back_as_signs():
    src = ("geometry graph lean(geometry: Geometry, up: Vector) -> Geometry {\n"
           "  p = Position()\n"
           "  side = p × up\n"
           "  return SetPosition(geometry, offset: side * (p ⋅ up))\n"
           "}\n")
    (tree,) = build_source(src.replace("p ⋅ up", "dot(p, up)").replace("p × up", "p cross up"), "lean.bn")
    text, warnings = export_tree(tree)
    assert text == src, text
    assert warnings == []


def test_formulas_come_back_identical():
    src = fixture("formulas.bn")
    (tree,) = build_source(src, "formulas.bn")
    text, _ = export_tree(tree)
    assert text == src, text


def test_comparisons_come_back_identical():
    src = fixture("compare.bn")
    (tree,) = build_source(src, "compare.bn")
    kinds = sorted((n.data_type, n.operation) for n in tree.nodes if n.bl_idname == "FunctionNodeCompare")
    assert ("INT", "EQUAL") in kinds and ("STRING", "EQUAL") in kinds and ("VECTOR", "EQUAL") in kinds
    logic = sorted(n.operation for n in tree.nodes if n.bl_idname == "FunctionNodeBooleanMath")
    assert logic == ["AND", "NOT", "OR", "XOR"], logic
    text, warnings = export_tree(tree)
    assert text == src, text
    assert warnings == []


def test_compare_calls_read_back_as_symbols():
    src = fixture("compare.bn").replace("p.z > t", "Compare(p.z, t, operation: GREATER_THAN)")
    (tree,) = build_source(src, "compare.bn")
    text, _ = export_tree(tree)
    assert "  high = p.z > t\n" in text, text


def test_joins_read_back_as_one_plus():
    head = "geometry graph j(a: Geometry, b: Geometry, c: Geometry) -> (x: Geometry, y: Geometry, z: Geometry) {\n"
    src = head + "  return (x: JoinGeometry(a + b, c), y: JoinGeometry(a), z: a + (b + c))\n}\n"
    (tree,) = build_source(src, "j.bn")
    assert sum(n.bl_idname == "GeometryNodeJoinGeometry" for n in tree.nodes) == 4  # x is a join of a join
    text, _ = export_tree(tree)
    canonical = head + "  return (x: a + b + c, y: JoinGeometry(a), z: a + b + c)\n}\n"
    assert text == canonical, text
    (tree,) = build_source(text, "j.bn")
    assert sum(n.bl_idname == "GeometryNodeJoinGeometry" for n in tree.nodes) == 3
    shared = head + "  ab = a + b\n  return (x: ab + c, y: ab, z: c)\n}\n"
    (tree,) = build_source(shared, "j.bn")
    assert export_tree(tree)[0] == shared  # a join used twice stays its own node


def test_math_calls_read_back_as_formulas():
    (tree,) = build_source(fixture("wave_v0.bn"), "wave_v0.bn")
    text, _ = export_tree(tree)
    assert "  s = p.x + t\n  h = sin(s) * 0.2\n" in text, text


def test_groups_pipes_and_quoted_names_come_back_identical():
    bpy.data.materials.new("Rust")
    src = fixture("round_trip.bn")
    trees = build_source(src, "round_trip.bn")
    assert [t.name for t in trees] == ["Smooth Mesh", "scatter"]
    text, warnings = export_tree(trees[-1])
    assert text == src, text
    assert warnings == []


def test_rebuilding_a_group_keeps_its_callers_and_settings():
    src = fixture("round_trip.bn")
    smooth, scatter = build_source(src, "round_trip.bn")
    # A tree outside the text calls the group, a modifier sets an input
    caller = bpy.data.node_groups.new("caller", "GeometryNodeTree")
    group = caller.nodes.new("GeometryNodeGroup")
    group.node_tree = smooth
    value = caller.nodes.new("FunctionNodeInputInt")
    caller.links.new(value.outputs[0], group.inputs["Level"])
    bpy.ops.mesh.primitive_cube_add()
    mod = bpy.context.object.modifiers.new("scatter", "NODES")
    mod.node_group = scatter
    count = next(i.identifier for i in scatter.interface.items_tree if i.name == "Point Count")
    getattr(mod.properties.inputs, count).value = 7

    build_source(src.replace("SetShadeSmooth()", "SetShadeSmooth(domain: EDGE)"), "round_trip.bn")
    assert group.node_tree == smooth and group.inputs["Level"].is_linked
    assert mod.node_group == scatter and getattr(mod.properties.inputs, count).value == 7
    assert any(n.bl_idname == "GeometryNodeSetShadeSmooth" and n.domain == "EDGE" for n in smooth.nodes)


def test_bundled_assets_export_and_come_back_stable():
    root = bpy.utils.system_resource("DATAFILES", path="assets/nodes")
    ours = {g.name for g in bpy.data.node_groups}
    for path in sorted(glob.glob(os.path.join(root, "*.blend"))):
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.node_groups = list(src.node_groups)
    names = [g.name for g in bpy.data.node_groups
             if g.bl_idname == "GeometryNodeTree" and g.library is None and g.name not in ours]
    stats = Counter()
    for name in names:
        tree = bpy.data.node_groups[name]
        before = node_kinds(tree)
        text, warnings = export_tree(tree)
        stats["exported"] += 1
        stats["compare as symbol"] += sum(text.count(f" {op} ") for op in sugar.COMPARE)
        stats["compare as call"] += text.count("Compare(")
        stats["logic as symbol"] += sum(text.count(f" {op} ") for op in ("and", "or")) + text.count("not ")
        stats["logic as call"] += text.count("BooleanMath(")
        stats["join as call"] += text.count("JoinGeometry(")
        if any("pas encore pris en charge" in w for w in warnings):
            stats["not yet"] += 1
            continue
        build_source(text, name)
        rebuilt = bpy.data.node_groups[name]
        again, _ = export_tree(rebuilt)
        assert again == text, name
        assert node_kinds(rebuilt) == before, name
        stats["stable"] += 1
    print("   bundled trees:", dict(stats))
    assert stats["exported"] == len(names) and stats["stable"] >= 50


def node_kinds(tree):
    """Node types that reach the output, reroutes, frames and dead nodes aside."""
    out = next((n for n in tree.nodes if n.bl_idname == "NodeGroupOutput" and n.is_active_output), None)
    seen, stack = set(), [out] if out else []
    while stack:
        n = stack.pop()
        if n.name in seen:
            continue
        seen.add(n.name)
        for s in n.inputs:
            for link in s.links:
                if not link.is_muted:
                    stack.append(link.from_node)
    nodes = [tree.nodes[n] for n in seen]
    return Counter(n.bl_idname for n in nodes
                   if n.bl_idname not in ("NodeReroute", "NodeGroupInput", "NodeGroupOutput"))


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
