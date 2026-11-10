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
from bnodes.host.schema import (INTERFACE_FIELDS, fresh_options, item_option_names, option_names,  # noqa: E402
                                same_option, snapshot)
from bnodes.lang.schema import ITEM_NODES  # noqa: E402
from bnodes.lang import BnError, parse, sugar  # noqa: E402
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


def test_simulation_and_foreach_zones_come_back_identical():
    src = fixture("zones.bn")
    trees = build_source(src, "zones.bn")
    for tree in trees:
        pairs = [n for n in tree.nodes if hasattr(n, "pair_with_output")]
        assert pairs and all(n.paired_output is not None for n in pairs), tree.name
        assert all(link.is_valid for link in tree.links), tree.name
    text = "\n".join(export_tree(t)[0] for t in trees)
    assert text == src, text
    assert all(export_tree(t)[1] == [] for t in trees)
    chute, semis, _compte = trees
    sim = next(n for n in chute.nodes if n.bl_idname == "GeometryNodeSimulationOutput")
    assert [(i.name, i.socket_type) for i in sim.state_items] == [
        ("points", "GEOMETRY"), ("vitesse", "FLOAT"), ("cache", "BUNDLE")]
    out = next(n for n in semis.nodes if n.bl_idname == "GeometryNodeForeachGeometryElementOutput")
    assert out.domain == "FACE"
    assert [(i.name, i.socket_type) for i in out.input_items] == [("centre", "VECTOR")]
    assert [i.name for i in out.main_items] == ["double"]
    assert [(i.name, i.socket_type) for i in out.generation_items] == [("points", "GEOMETRY"), ("rang", "INT")]


def test_unlinked_and_mistyped_zone_items_are_written_or_reported():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    tree.nodes.clear()
    zin = tree.nodes.new("GeometryNodeSimulationInput")
    zout = tree.nodes.new("GeometryNodeSimulationOutput")
    zin.pair_with_output(zout)
    zout.state_items.new("ROTATION", "r")
    zout.state_items[1].attribute_domain = "FACE"
    gout = tree.nodes.new("NodeGroupOutput")
    tree.links.new(zout.outputs[0], gout.inputs[0])
    text, warnings = export_tree(tree)
    # The geometry starts empty and is written by its type; the rotation's value would read as a vector
    assert "simulate(Geometry: Geometry, r: (0.0, 0.0, 0.0))" in text, text
    assert any("« r » est un Rotation qui reçoit un Vector" in w for w in warnings), warnings
    assert any("domaine FACE de l'état « r »" in w for w in warnings), warnings


ZONES_CALLER = """geometry graph essai_semis(geometry: Geometry) -> Geometry {
  e = semis(MeshGrid(2.0, 2.0, 3, 3))
  return e.points |> PointsToVertices() |> StoreNamedAttribute(name: "rang", value: e.rang)
}

geometry graph essai_double(geometry: Geometry) -> Geometry {
  e = semis(MeshGrid(2.0, 2.0, 3, 3))
  return e.geometry |> StoreNamedAttribute(domain: FACE, name: "d", value: e.double)
}

geometry graph essai_chute(geometry: Geometry) -> Geometry {
  c = chute(MeshGrid(1.0, 1.0, 2, 2), gravité: -10.0)
  return c.geometry |> StoreNamedAttribute(name: "v", value: c.vitesse)
    |> StoreNamedAttribute(name: "n", value: compte(1.0))
}
"""


def evaluated(tree):
    obj = bpy.data.objects.new(tree.name, bpy.data.meshes.new(tree.name))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new(tree.name, "NODES").node_group = tree
    return obj


def test_simulation_and_foreach_zones_compute():
    trees = {t.name: t for t in build_source(fixture("zones.bn") + "\n" + ZONES_CALLER, "essai.bn")}
    scene = bpy.context.scene
    scene.frame_set(scene.frame_start)
    semis_obj, double_obj = evaluated(trees["essai_semis"]), evaluated(trees["essai_double"])
    depsgraph = bpy.context.evaluated_depsgraph_get()
    # 4 faces, the first 3 selected: one point at the centre of each, with the face's index
    mesh = semis_obj.evaluated_get(depsgraph).data
    assert len(mesh.vertices) == 3
    assert [d.value for d in mesh.attributes["rang"].data] == [0, 1, 2]
    assert all(abs(v.co.z) < 1e-6 and abs(v.co.x) == abs(v.co.y) == 0.5 for v in mesh.vertices)
    mesh = double_obj.evaluated_get(depsgraph).data
    assert [round(d.value, 3) for d in mesh.attributes["d"].data] == [0.0, 2.0, 4.0, 0.0]

    obj = evaluated(trees["essai_chute"])
    seen = []
    for frame in range(scene.frame_start, scene.frame_start + 4):
        scene.frame_set(frame)
        mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        seen.append((mesh.attributes["n"].data[0].value, mesh.attributes["v"].data[0].value, mesh.vertices[0].co.z))
    counts, speeds, heights = zip(*seen)
    # One step a frame, the first at the start frame with no time gone by: the speed
    # grows by g × dt, and the points fall by the new speed × dt
    assert counts == (1.0, 2.0, 3.0, 4.0), seen
    assert speeds[0] == heights[0] == 0.0, seen
    dt = 1 / scene.render.fps
    for k in range(1, 4):
        assert abs(speeds[k] - speeds[k - 1] + 10.0 * dt) < 1e-5, seen
        assert abs(heights[k] - heights[k - 1] - speeds[k] * dt) < 1e-5, seen


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


def test_panels_and_looks_are_reported():
    (tree,) = build_source(fixture("wave.bn"), "wave.bn")
    tree.interface.new_panel("Réglages")
    node = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeMath")
    node.label, node.hide = "Hauteur", True
    _text, warnings = export_tree(tree)
    assert any("panneaux de l'interface (Réglages)" in w for w in warnings), warnings
    assert any("présentation non exportée : libellé (1), replié (1)" in w for w in warnings), warnings


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


def test_more_item_nodes_come_back_identical():
    src = fixture("items_more.bn")
    trees = build_source(src, "items_more.bn")
    text = "\n".join(export_tree(t)[0] for t in trees)
    assert text == src, text
    assert all(export_tree(t)[1] == [] for t in trees)
    by_name = {t.name: t for t in trees}
    bake = by_name["cuisson"].nodes["b"]
    assert [(i.name, i.socket_type) for i in bake.bake_items] == [("Geometry", "GEOMETRY"), ("h", "FLOAT")]
    assert (bake.bake_items[1].attribute_domain, bake.bake_items[1].is_attribute) == ("FACE", True)
    menu = by_name["modes"].nodes["m"]
    assert [(i.name, i.description) for i in menu.enum_items] == [
        ("Lisse", "Garde la géométrie telle quelle"), ("Rugueux", "")]
    # An option taken out of the text goes back to a new item's
    (modes,) = build_source(src.split("\n\n")[-1].replace('(description: "Garde la géométrie telle quelle")', ""),
                            "items_more.bn")
    assert modes.nodes["m"].enum_items[0].description == ""


GRIDS = """geometry graph grilles(points: Geometry, t: Float) -> (densité: Float, champ: Float, n: Int) {
  r = RasterizePoints(points, densité: 1.0, vitesse: Normal().normal)
  f = FieldToGrid(r.densité, a: t * 2.0, b: Index())
  return (densité: r.densité, champ: f.a, n: ListLength(CombineList(1.0, t, 3.0)))
}
"""


def test_grid_and_list_items_come_back_identical():
    if not all(hasattr(bpy.types, k) for k in ("GeometryNodeRasterizePoints", "GeometryNodeFieldToGrid",
                                               "GeometryNodeCombineList")):
        return  # not in this Blender
    (tree,) = build_source(GRIDS, "grilles.bn")
    assert export_tree(tree) == (GRIDS, [])
    r = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeRasterizePoints")
    assert [(i.name, i.type) for i in r.rasterize_items] == [("densité", "SCALAR"), ("vitesse", "VECTOR")]
    f = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeFieldToGrid")
    assert [(i.name, i.data_type) for i in f.grid_items] == [("a", "FLOAT"), ("b", "INT")]
    c = next(n for n in tree.nodes if n.bl_idname == "GeometryNodeCombineList")
    assert len(c.combine_list_items) == 3 and c.data_type == "FLOAT"


def test_item_settings_blender_would_change_fail():
    for src, message in (
            ('  return FormatString("{a b}", "a b": 1.0)', "Blender renomme l'item « a b » en « a_b »"),
            ("  return Bake(h(couleur: 1): t).h", "item « h » : option couleur inconnue"),
            ('  return Bake(h(attribute_domain: CIEL): t).h', "option attribute_domain de l'item « h »")):
        out = "String" if "Format" in src else "Float"
        try:
            build_source(f"geometry graph essai_options(t: Float) -> {out} {{\n{src}\n}}\n", "essai.bn")
        except BnError as e:
            assert e.diagnostics[0].message.startswith(message), e.diagnostics[0].message
        else:
            raise AssertionError(src)


ITEMS_MORE_CALLER = """geometry graph essai_items_plus(geometry: Geometry) -> Geometry {
  texte = FormatString("{n}-{x}", n: 12, x: "ab")
  return geometry |> StoreNamedAttribute(name: "taille", value: StringLength(texte))
    |> StoreNamedAttribute(name: "un", value: listes(3))
    |> StoreNamedAttribute(name: "cuit", value: cuisson(geometry, 0.25).h)
}
"""


def test_more_item_nodes_compute():
    tree = build_source(fixture("items_more.bn") + "\n" + ITEMS_MORE_CALLER, "essai.bn")[-1]
    obj = bpy.data.objects.new("essai_plus", bpy.data.meshes.new("essai_plus"))
    bpy.context.scene.collection.objects.link(obj)
    mod = obj.modifiers.new("essai", "NODES")
    mod.node_group = tree
    obj.data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    # "12-ab", item 1 of a list of indices, and a Bake with nothing baked lets its values through
    assert mesh.attributes["taille"].data[0].value == 5
    assert abs(mesh.attributes["un"].data[0].value - 1.0) < 1e-6
    assert abs(mesh.attributes["cuit"].data[0].value - 0.25) < 1e-6


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
        held = item_settings(tree)
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
        assert item_settings(rebuilt) == held, name
        assert all(close(a, b) for a, b in zip(interface(rebuilt), settings)), name
        assert options(rebuilt) == [d.replace('"', "'").replace("\n", " ") if isinstance(d, str) else d
                                    for d in written], name
        stats["stable"] += 1
    print("   bundled trees:", dict(stats))
    assert stats["exported"] == len(names) and stats["stable"] >= 75


def item_settings(tree):
    """Each item node that reaches the output, with its items and their settings."""
    out = Counter()
    for n in reached(tree):
        shape = ITEM_NODES.get(n.bl_idname)
        if shape is not None:
            items = tuple((getattr(i, "name", None), tuple((o, plain_text(getattr(i, o))) for o in item_option_names(i, shape)
                                         if o not in shape.field_only))
                          for i in getattr(n, shape.collection))
            out[(n.bl_idname, items)] += 1
    return out


def plain_text(v):
    return v.replace('"', "'").replace("\n", " ") if isinstance(v, str) else v


def node_kinds(tree):
    """Node types that reach the output, reroutes, frames and dead nodes aside."""
    return Counter(n.bl_idname for n in reached(tree)
                   if n.bl_idname not in ("NodeReroute", "NodeGroupInput", "NodeGroupOutput"))


def reached(tree):
    """The nodes that reach the active output."""
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
    return [tree.nodes[n] for n in seen]


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
