import pytest

from lang import BnError, compile_source, ir
from lang.layout import layout


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [str(d) for d in err.value.diagnostics]


def graph(body, sig="geometry graph g(geometry: Geometry, t: Float) -> Geometry"):
    return f"{sig} {{\n{body}\n}}"


def test_wave_is_nine_nodes_and_nine_links(schema, fixture_text):
    g = compile_one(fixture_text("wave_v0.bn"), schema)
    assert len(g.nodes) == 9
    assert len(g.edges()) == 9
    by_name = {n.name: n for n in g.nodes if n.name}
    assert by_name["p"].bl_idname == "GeometryNodeInputPosition"
    assert by_name["s"].props == {"operation": "ADD"}
    assert by_name["h"].values == {"Value_001": 0.2}
    out = g.node(ir.GROUP_OUTPUT)
    assert [ident for ident, _link in out.links] == ["Geometry"]


def test_unary_math_has_one_input(schema):
    msgs = errors(graph("  x = Math(t, t, operation: SINE)\n  return geometry"), schema)
    assert msgs == ["t.bn:2:15  Math prend 1 entrée(s) : value"]


def test_unknown_input_lists_inputs(schema):
    msgs = errors(graph("  v = CombineXYZ(w: t)\n  return geometry"), schema)
    assert msgs == ["t.bn:2:18  CombineXYZ n'a pas d'entrée « w » ; entrées : x, y, z"]


def test_unknown_enum_value_suggests(schema):
    msgs = errors(graph("  x = Math(t, operation: SINUS)\n  return geometry"), schema)
    assert msgs[0].startswith("t.bn:2:15  operation: SINUS inconnu ; voulez-vous dire SINE ? ; valeurs : ADD,")


def test_type_mismatch(schema):
    msgs = errors(graph("  return SetPosition(geometry, offset: geometry)"), schema)
    assert msgs == ["t.bn:2:32  SetPosition.offset attend Vector, reçoit Geometry (geometry)"]


def test_unknown_node_suggests(schema):
    msgs = errors(graph("  return SetPositon(geometry)"), schema)
    assert "voulez-vous dire SetPosition" in msgs[0]


def test_all_errors_reported_at_once(schema):
    msgs = errors(graph("  a = Nope()\n  b = CombineXYZ(w: t)\n  return 3"), schema)
    assert len(msgs) == 3


def test_duplicate_sockets_by_identifier(schema):
    msgs = errors(graph("  x = Math(value: t)\n  return geometry"), schema)
    assert "ambigu" in msgs[0] and "Value_001" in msgs[0]
    g = compile_one(graph("  x = Math(Value_001: t)\n  return geometry"), schema)
    assert g.nodes[2].links[0][0] == "Value_001"


def test_pipe_inserts_first_argument(schema):
    g = compile_one(graph("  return geometry\n    |> SubdivideMesh(level: 2)\n    |> SetShadeSmooth(domain: FACE)"),
                    schema)
    sub, smooth = g.nodes[2], g.nodes[3]
    assert sub.links == [("Mesh", ir.Link(ir.GROUP_INPUT, "geometry"))]
    assert sub.values == {"Level": 2}
    assert smooth.props == {"domain": "FACE"}
    assert smooth.links == [("Geometry", ir.Link(sub.id, "Mesh"))]


def test_multi_input_takes_all_positionals(schema):
    g = compile_one(graph("  a = SetPosition(geometry)\n  return JoinGeometry(geometry, a, geometry)"), schema)
    join = g.nodes[3]
    assert [ident for ident, _ in join.links] == ["Geometry"] * 3


def test_shared_name_is_one_node(schema):
    g = compile_one(graph("  p = Position()\n  v = CombineXYZ(SeparateXYZ(p).x, SeparateXYZ(p).y)\n"
                          "  return SetPosition(geometry, offset: v, position: p)"), schema)
    assert sum(n.bl_idname == "GeometryNodeInputPosition" for n in g.nodes) == 1


def test_menu_socket_takes_enum_value(schema):
    g = compile_one(graph('  i = FindInString("abc", "b", mode: LAST)\n  return geometry'), schema)
    assert g.nodes[2].values == {"String": "abc", "Search": "b", "Mode": "LAST"}


def test_unknown_name_is_reported(schema):
    msgs = errors(graph("  return SetPosition(geometrie)"), schema)
    assert msgs == ["t.bn:2:22  nom inconnu « geometrie »"]


def test_formulas_wait_for_v2(schema):
    msgs = errors(graph("  h = t * 2\n  return geometry"), schema)
    assert "v2" in msgs[0]


def test_group_call_and_order(schema):
    src = ("geometry graph main(geometry: Geometry) -> Geometry {\n  return smooth(geometry)\n}\n"
           "geometry graph smooth(mesh: Geometry) -> Geometry {\n  return SetShadeSmooth(mesh)\n}\n")
    graphs = compile_source(src, schema)
    assert [g.name for g in graphs] == ["smooth", "main"]
    call = graphs[1].nodes[2]
    assert (call.bl_idname, call.group) == ("GeometryNodeGroup", "smooth")


def test_recursion_is_an_error(schema):
    src = "geometry graph a(g: Geometry) -> Geometry {\n  return a(g)\n}"
    assert "récursif" in errors(src, schema)[0]


def test_record_return(schema):
    g = compile_one("geometry graph g(a: Geometry) -> (mesh: Geometry, n: Int) {\n"
                    "  return (mesh: a, n: 3)\n}", schema)
    out = g.node(ir.GROUP_OUTPUT)
    assert out.links == [("mesh", ir.Link(ir.GROUP_INPUT, "a"))]
    assert out.values == {"n": 3}


def test_pixel_is_blade_only(schema):
    assert "Blade" in errors("pixel graph p(i: Color) -> Color {\n  return i\n}", schema)[0]


def test_layout_goes_left_to_right(schema, fixture_text):
    g = compile_one(fixture_text("wave_v0.bn"), schema)
    pos = layout(g)
    for src, dst in g.edges():
        assert pos[src][0] < pos[dst][0]
    assert pos[ir.GROUP_OUTPUT][0] == max(x for x, _y in pos.values())
    assert layout(g) == pos


def test_quoted_names_are_used_by_their_key(schema):
    src = ('geometry graph "Smooth by Angle"(Mesh: Geometry, "Fur Density": Float) -> Geometry {\n'
           "  return SetPosition(Mesh, offset: CombineXYZ(z: fur_density))\n}\n"
           "geometry graph main(geometry: Geometry) -> Geometry {\n"
           "  return smooth_by_angle(geometry, fur_density: 0.5)\n}\n")
    callee, main = compile_source(src, schema)
    assert callee.inputs == [("Mesh", "Geometry"), ("Fur Density", "Float")]
    call = main.nodes[2]
    assert call.group == "Smooth by Angle"
    assert call.values == {"Fur Density": 0.5}


def test_outputs_may_stay_unlinked(schema):
    g = compile_one("geometry graph g(a: Geometry) -> (mesh: Geometry, n: Int) {\n  return (n: 3)\n}", schema)
    assert g.node(ir.GROUP_OUTPUT).values == {"n": 3}
    g = compile_one("geometry graph g(a: Geometry) -> () {\n  return ()\n}", schema)
    assert g.outputs == []


def test_datablock_by_name(schema):
    from fake_schema import NODES, S
    from lang.schema import NodeSpec
    NODES["SetMaterial"] = (NodeSpec("SetMaterial", "GeometryNodeSetMaterial"),
                            [S("Geometry", "Geometry"), S("Selection", "Bool"), S("Material", "Material")],
                            [S("Geometry", "Geometry")])
    try:
        g = compile_one(graph('  return SetMaterial(geometry, material: "Rust")'), schema)
        assert g.nodes[2].values == {"Material": "Rust"}
        assert "attend Material" in errors(graph("  return SetMaterial(geometry, material: 3)"), schema)[0]
    finally:
        del NODES["SetMaterial"]
