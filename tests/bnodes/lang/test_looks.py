"""Statements nothing reads, and `@ …` after a statement: how its node is shown."""

import pytest

from lang import BnError, compile_source, parse
from lang.format import format_source
from lang.printer import to_source

LOOKS = """geometry graph g(geometry: Geometry, t: Float) -> Geometry {
  p = Position() @ mute
  vue = SetPosition(geometry, offset: p) @ "Vue" #e07030 hide
  "Bloc" {
    c = CombineXYZ(z: t) @ #teal
  }
  h = geometry |> SetPosition(offset: p)
    |> SubdivideMesh(2) @ mute
  return h @ mute
}
"""


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def test_a_look_prints_back_unchanged():
    assert to_source(parse(LOOKS)) == LOOKS
    assert format_source(LOOKS) == LOOKS


def test_a_look_goes_on_the_node_its_statement_makes(schema):
    g = compile_one(LOOKS, schema)
    by_name = {n.name: n for n in g.nodes if n.name}
    assert by_name["p"].look == {"mute": True}
    # On a pipe, the node of the last stage, which the name binds
    assert by_name["h"].bl_idname == "GeometryNodeSubdivideMesh" and by_name["h"].look == {"mute": True}
    assert by_name["vue"].look == {"label": "Vue", "use_custom_color": True,
                                   "color": (224 / 255, 112 / 255, 48 / 255), "hide": True}
    assert by_name["c"].look == {"use_custom_color": True, "color": (0.0, 128 / 255, 128 / 255)}
    assert g.node("group_output").look == {"mute": True}


def test_a_statement_nothing_reads_is_built(schema):
    g = compile_one(LOOKS, schema)
    vue = next(n for n in g.nodes if n.name == "vue")
    assert vue.bl_idname == "GeometryNodeSetPosition" and vue.id not in {src for src, _dst in g.edges()}


def test_a_look_needs_a_node_of_its_own(schema):
    src = "geometry graph g(geometry: Geometry) -> Geometry {\n  a = geometry @ mute\n  return a\n}\n"
    with pytest.raises(BnError, match="« a » ne fait pas de nœud à lui"):
        compile_source(src, schema, "t.bn")


def test_the_next_line_is_the_next_statement():
    src = ("geometry graph g(geometry: Geometry) -> Geometry {\n  a = Position() @ mute\n  hide = a\n"
           "  b = Position() @ \"B\"\n  #red {\n    c = b\n  }\n  return geometry\n}\n")
    (stmt, alias, b, frame, _ret) = parse(src).graphs[0].body
    assert stmt.look.flags == ["mute"] and alias.name == "hide"
    assert (b.look.label, b.look.color) == ("B", None) and frame.color == "#red"


def test_an_unknown_look_color_is_an_error(schema):
    src = "geometry graph g(geometry: Geometry) -> Geometry {\n  a = Position() @ #nope\n  return geometry\n}\n"
    with pytest.raises(BnError, match="couleur « #nope » inconnue"):
        compile_source(src, schema, "t.bn")


def test_an_empty_look_is_an_error():
    with pytest.raises(BnError, match="après @, sur sa ligne"):
        parse("geometry graph g(geometry: Geometry) -> Geometry {\n  a = Position() @\n  return geometry\n}\n")
    with pytest.raises(BnError, match="donné deux fois"):
        parse("geometry graph g(geometry: Geometry) -> Geometry {\n  a = Position() @ mute mute\n  return geometry\n}\n")
