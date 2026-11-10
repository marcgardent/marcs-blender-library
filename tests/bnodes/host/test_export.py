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
from bnodes.host.schema import INTERFACE_FIELDS, fresh_options, option_names, same_option, snapshot  # noqa: E402
from bnodes.lang import parse, sugar  # noqa: E402
from bnodes.lang.format import format_source  # noqa: E402
from bnodes.lang.printer import to_source  # noqa: E402

FIXTURES = ROOT / "tests" / "bnodes" / "fixtures"
DOCS = ROOT / "docs"


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


def test_a_frame_split_by_its_links_goes_on_in_a_second_block():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    frame = tree.nodes.new("NodeFrame")
    frame.label = "Ends"
    for name in ("p", "Group Output"):
        tree.nodes[name].parent = frame
    tree.nodes["h"].parent = None
    text, warnings = export_tree(tree)
    assert text.count('"Ends" {') == 1 and text.count('"Ends" .. {') == 1, text
    assert warnings == [], warnings
    (tree,) = build_source(text, "wave.bn")
    assert [f.label for f in tree.nodes if f.bl_idname == "NodeFrame"] == ["Ends"]
    assert tree.nodes["p"].parent == tree.nodes["Group Output"].parent == tree.nodes["Ends"]
    assert export_tree(tree) == (text, [])


def test_two_frames_of_one_title_stay_two():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    for names in (("p",), ("Group Output",)):
        frame = tree.nodes.new("NodeFrame")
        frame.label = "Bout"
        for name in names:
            tree.nodes[name].parent = frame
    text, warnings = export_tree(tree)
    assert text.count('"Bout" {') == 2 and ".." not in text and warnings == [], (text, warnings)


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


def test_doc_examples_build_and_read_back():
    page = (DOCS / "nodes-as-text.md").read_text()
    examples = sorted((DOCS / "exemples").glob("*.bn"))
    assert len(examples) == 3
    for path in examples:
        src = path.read_text()
        assert format_source(src) == src, f"{path.name} is not formatted"
        assert f"```\n{src}```" in page, f"{path.name} differs from its copy in the page"
        trees = build_source(src, path.name)
        text, warnings = export_tree(trees[-1])
        # Comments and blank lines are not in a tree: the program itself comes back
        assert text == to_source(parse(src)), text
        assert warnings == [], warnings


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


def test_defaults_bounds_and_implicit_fields_come_back_identical():
    if "Rust" not in bpy.data.materials:
        bpy.data.materials.new("Rust")
    src = fixture("defaults.bn")
    (tree,) = build_source(src, "defaults.bn")
    items = {i.name: i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    assert abs(items["force"].default_value - 0.25) < 1e-6 and abs(items["force"].max_value - 0.999) < 1e-6
    assert close(tuple(items["teinte"].default_value), (0.8, 0.3, 0.1, 1.0))
    assert items["p"].default_input == "POSITION" and items["id"].default_input == "ID_OR_INDEX"
    assert items["matière"].default_value == bpy.data.materials["Rust"]
    text, warnings = export_tree(tree)
    assert text == src, text
    assert warnings == []


def test_a_default_removed_from_the_text_is_reset():
    if "Rust" not in bpy.data.materials:
        bpy.data.materials.new("Rust")
    src = fixture("defaults.bn")
    build_source(src, "defaults.bn")
    (tree,) = build_source(src.replace(" = 0.25 in 0.001..0.999", "").replace(" = Position()", ""), "defaults.bn")
    items = {i.name: i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"}
    assert items["force"].default_value == 0.0 and items["force"].max_value > 1e30
    assert items["p"].default_input == "VALUE"


def test_repeat_zones_come_back_identical():
    src = fixture("repeat.bn")
    trees = build_source(src, "repeat.bn")
    for tree in trees:
        pairs = [n for n in tree.nodes if n.bl_idname == "GeometryNodeRepeatInput"]
        assert pairs and all(n.paired_output is not None for n in pairs), tree.name
        assert all(link.is_valid for link in tree.links), tree.name
    text = "\n".join(export_tree(t)[0] for t in trees)
    assert text == src, text
    assert all(export_tree(t)[1] == [] for t in trees)


CALLER = """geometry graph essai(geometry: Geometry) -> Geometry {
  p = pousses(MeshGrid(1.0, 1.0, 3, 3), 4)
  return p.geometry |> StoreNamedAttribute(name: "h", value: p.hauteur)
    |> StoreNamedAttribute(name: "t", value: table(5))
}
"""


def test_repeat_zones_compute():
    tree = build_source(fixture("repeat.bn") + "\n" + CALLER, "essai.bn")[-1]
    obj = bpy.data.objects.new("essai", bpy.data.meshes.new("essai"))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new("essai", "NODES").node_group = tree
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    # 4 turns of 0.5; 5 rows of 0 + 1 + 2 + 3 + 4
    assert abs(mesh.attributes["h"].data[0].value - 2.0) < 1e-6
    assert abs(mesh.attributes["t"].data[0].value - 50.0) < 1e-6
    # Each turn extrudes the top faces once more
    assert max(v.co.z for v in mesh.vertices) > 1.5 and len(mesh.vertices) > 9


def test_rebuilding_a_repeat_keeps_one_zone():
    src = fixture("repeat.bn")
    build_source(src, "repeat.bn")
    pousses, _table = build_source(src.replace("pas: 0.5", "pas: 0.25"), "repeat.bn")
    assert [n.bl_idname for n in pousses.nodes].count("GeometryNodeRepeatInput") == 1
    rin = next(n for n in pousses.nodes if n.bl_idname == "GeometryNodeRepeatInput")
    assert abs(rin.inputs["pas"].default_value - 0.25) < 1e-6


def test_item_nodes_come_back_identical():
    src = fixture("items.bn")
    trees = build_source(src, "items.bn")
    text = "\n".join(export_tree(t)[0] for t in trees)
    assert text == src, text
    assert all(export_tree(t)[1] == [] for t in trees)
    relief = trees[0]
    capture = next(n for n in relief.nodes if n.bl_idname == "GeometryNodeCaptureAttribute")
    assert [(i.name, i.data_type) for i in capture.capture_items] == [("hauteur", "FLOAT"), ("Rest Position", "FLOAT_VECTOR")]
    switch = next(n for n in relief.nodes if n.bl_idname == "GeometryNodeMenuSwitch")
    assert [i.name for i in switch.enum_items] == ["Lisse", "Rugueux"]


def test_interface_options_come_back_identical():
    src = fixture("interface.bn")
    (tree,) = build_source(src, "interface.bn")
    t = next(i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.name == "t")
    assert (t.subtype, t.description, t.default_value) == ("FACTOR", "La part à garder", 0.5)
    assert tree.description == "Garde une part des points, à une taille donnée"
    text, warnings = export_tree(tree)
    assert (text, warnings) == (src, []), (text, warnings)
    # An option taken out of the text goes back to a new socket's
    (tree,) = build_source(src.replace("subtype: FACTOR, ", "").replace('  "Garde une part des points, à une taille donnée"\n', ""), "interface.bn")
    t = next(i for i in tree.interface.items_tree if i.item_type == "SOCKET" and i.name == "t")
    assert t.subtype in ("NONE", "DEFAULT") and t.description == "La part à garder" and tree.description == ""


def test_gizmos_come_back_identical():
    src = fixture("gizmos.bn")
    (tree,) = build_source(src, "gizmos.bn")
    arrow = tree.nodes["flèche"]
    # The gizmo's value is linked to the input it moves, as in the editor
    assert [(l.from_node.bl_idname, l.from_socket.name) for l in arrow.inputs["Value"].links] == \
        [("NodeGroupInput", "hauteur")]
    assert tree.nodes["repère"].inputs["Value"].links[0].from_node.bl_idname == "FunctionNodeCombineTransform"
    alone = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeGizmoLinear" and n.name != "flèche")
    assert not alone.inputs["Value"].is_linked and alone.inputs["Value"].default_value == 2.0
    text, warnings = export_tree(tree)
    assert (text, warnings) == (src, []), (text, warnings)


def test_inputs_after_a_multi_input_are_named():
    src = ("geometry graph g(a: Geometry, b: Geometry) -> Geometry {\n"
           "  return MeshBoolean(a, b, a, self_intersection: true, operation: DIFFERENCE, solver: EXACT).mesh\n}\n")
    (tree,) = build_source(src, "g.bn")
    boolean = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeMeshBoolean")
    assert len(boolean.inputs["Mesh 2"].links) == 2 and boolean.inputs["Self Intersection"].default_value
    text, warnings = export_tree(tree)
    assert (text, warnings) == (src, []), (text, warnings)


def test_nodes_nothing_reads_come_back_identical():
    src = fixture("dead.bn")
    (tree,) = build_source(src, "dead.bn")
    assert not tree.nodes["alerte"].outputs[0].is_linked and tree.nodes["repère"].parent.label == "Poignée"
    assert tree.nodes["plus"].mute and not tree.nodes["repère"].mute
    text, warnings = export_tree(tree)
    assert (text, warnings) == (src, []), (text, warnings)


def test_a_node_left_aside_by_hand_is_written():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    extra = tree.nodes.new("ShaderNodeMath")
    tree.links.new(tree.nodes["p"].outputs[0], extra.inputs[0])
    extra.inputs[1].default_value = 3.0
    tree.nodes["h"].mute = True
    text, warnings = export_tree(tree)
    assert "  math = Math(p, 3.0, operation: ADD)\n" in text, text
    assert " @ mute\n" in text and warnings == [], (text, warnings)
    (tree,) = build_source(text, "wave.bn")
    assert tree.nodes["h"].mute and export_tree(tree) == (text, [])


def test_looks_come_back_identical():
    src = fixture("looks.bn")
    (tree,) = build_source(src, "looks.bn")
    h = tree.nodes["h"]
    assert h.label == "Hauteur" and h.use_custom_color and tuple(round(c, 3) for c in h.color) == (0.878, 0.439, 0.188)
    assert tree.nodes["p"].hide and tree.nodes["décalage"].mute and tree.nodes["Group Output"].label == "Fin"
    text, warnings = export_tree(tree)
    assert (text, warnings) == (src, []), (text, warnings)


def test_a_node_with_a_look_gets_a_name():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    sine = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "SINE")
    sine.label, sine.hide = "Onde", True
    text, warnings = export_tree(tree)
    assert '  math = sin(p.x + t) @ "Onde" hide\n  h = math * 0.2\n' in text and warnings == [], (text, warnings)


def test_a_repeat_shows_its_look_on_its_return():
    trees = build_source(fixture("repeat.bn"), "repeat.bn")
    rout = next(n for n in trees[0].nodes if n.bl_idname == "GeometryNodeRepeatOutput")
    rout.hide = True
    text, warnings = export_tree(trees[0])
    assert " @ hide\n" in text and warnings == [], (text, warnings)
    (tree, *_rest) = build_source(text, "repeat.bn")
    assert next(n for n in tree.nodes if n.bl_idname == "GeometryNodeRepeatOutput").hide
    assert export_tree(tree) == (text, [])


def test_panels_and_unwritten_looks_are_reported():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    tree.interface.new_panel("Réglages")
    # The text has no Group Input node of its own to show otherwise
    group_input = tree.nodes["Group Input"]
    group_input.use_custom_color, group_input.hide = True, True
    _text, warnings = export_tree(tree)
    assert any("panneaux de l'interface (Réglages)" in w for w in warnings), warnings
    assert any("présentation des Group Input non exportée : couleur (1), replié (1)" in w for w in warnings), warnings


ITEMS_CALLER = """geometry graph essai_items(geometry: Geometry) -> Geometry {
  r = relief(MeshGrid(2.0, 2.0, 3, 3) |> SetPosition(offset: CombineXYZ(z: 0.5)), Lisse, 1)
  return r.geometry |> StoreNamedAttribute(name: "v", value: r.v)
    |> StoreNamedAttribute(name: "lisse", value: r.lisse)
    |> StoreNamedAttribute(name: "cubes", value: AttributeDomainSize(géométries(geometry, 1)).point_count)
}
"""


def test_item_nodes_compute():
    tree = build_source(fixture("items.bn") + "\n" + ITEMS_CALLER, "essai.bn")[-1]
    obj = bpy.data.objects.new("essai", bpy.data.meshes.new("essai"))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new("essai", "NODES").node_group = tree
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    # Index 1 picks the captured height; Lisse leaves the grid where it was
    assert all(abs(d.value - 0.5) < 1e-6 for d in mesh.attributes["v"].data)
    assert all(d.value for d in mesh.attributes["lisse"].data)
    assert all(abs(v.co.z - 0.5) < 1e-6 for v in mesh.vertices) and len(mesh.vertices) == 9
    assert mesh.attributes["cubes"].data[0].value == 8


def close(a, b):
    """Equal, floats to a relative 1e-5: bounds far out (±3.4e38) differ in their last digits."""
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return abs(a - b) <= 1e-5 * max(1.0, abs(a), abs(b))
    return a == b


def interface(tree):
    """What the text holds of each input: its default, bounds and implicit field."""
    out = []
    for i in tree.interface.items_tree:
        if i.item_type == "SOCKET" and i.in_out == "INPUT":
            out.append((i.name, *(snapshot(i) if f == "default_value" else getattr(i, f)
                                  for f in INTERFACE_FIELDS if hasattr(i, f))))
    return out


def options(tree):
    """The other settings of each socket, as the text writes them, and the group's tooltip."""
    out = [tree.description]
    for i in tree.interface.items_tree:
        if i.item_type == "SOCKET":
            fresh = fresh_options(i.socket_type, i.in_out)
            out.append((i.in_out, i.name, {o: getattr(i, o) for o in option_names(i)
                                           if o in fresh and not same_option(o, getattr(i, o), fresh[o])}))
    return out


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
        settings = interface(tree)
        written = options(tree)
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
        assert all(close(a, b) for a, b in zip(interface(rebuilt), settings)), name
        assert options(rebuilt) == [d.replace('"', "'").replace("\n", " ") if isinstance(d, str) else d
                                    for d in written], name
        stats["stable"] += 1
    print("   bundled trees:", dict(stats))
    assert stats["exported"] == len(names) and stats["stable"] >= 75


def node_kinds(tree):
    """Node types and how each is shown: every node, reroutes, frames and group inputs aside.

    Colors to the 8 bits of the `#rrggbb` the text writes them with."""
    return Counter((n.bl_idname, n.mute, n.hide, n.label.replace('"', "'"),
                    tuple(round(c * 255) for c in n.color) if n.use_custom_color else None)
                   for n in tree.nodes if n.bl_idname not in ("NodeReroute", "NodeFrame", "NodeGroupInput"))


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
