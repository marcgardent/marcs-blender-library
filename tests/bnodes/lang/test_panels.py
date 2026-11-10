"""Interface panels `"Titre" { … }`, two sockets of one name told apart with `as`, and the tree's settings."""

import pytest

from lang import BnError, compile_source, parse
from lang.complete import complete
from lang.format import format_source
from lang.printer import to_source
from lang.schema import GroupSpec, interface_keys


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def graph(params, outputs="Geometry", body="  return geometry\n"):
    return f"geometry graph g({params}) -> {outputs} {{\n{body}}}\n"


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("panels.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_panels_nest_and_hold_their_settings(schema, fixture_text):
    # The fixture, with nodes the fake schema has
    src = fixture_text("panels.bn").replace(
        "DistributePointsOnFaces(geometry, density: densité, seed: graine)",
        "SetPosition(geometry, offset: CombineXYZ(densité, graine))").replace(
        "RandomValue(max: aléa_échelle, seed: rotation_graine)", "aléa_échelle * rotation_graine").replace(
        "points.points", "points")
    semis, appel = compile_source(src, schema)
    assert [(p.id, p.name, p.parent, p.options) for p in semis.panels] == [
        ("p0", "Taille", None, {"description": "La taille de chaque copie"}),
        ("p1", "Aléa", "p0", {"default_closed": True}),
        ("p2", "Rotation", None, {}),
    ]
    assert semis.input_keys == ["geometry", "densité", "échelle", "Aléa", "aléa_échelle", "graine",
                                "rotation_graine", "angle"]
    assert [n for n, _t in semis.inputs].count("échelle") == 2
    assert semis.panel_of == {
        ("INPUT", "échelle"): "p0", ("INPUT", "Aléa"): "p1", ("INPUT", "aléa_échelle"): "p1",
        ("INPUT", "graine"): "p1", ("INPUT", "rotation_graine"): "p2", ("INPUT", "angle"): "p2",
        ("OUTPUT", "Angle"): "p2",
    }
    assert semis.settings == {"show_modifier_manage_panel": False}
    # Defaults and options go by key: the two « échelle » keep their own
    assert semis.defaults["échelle"] == {"value": 1.0}
    assert semis.defaults["aléa_échelle"] == {"value": 0.2, "min": 0.0, "max": 1.0}
    assert semis.options[("INPUT", "Aléa")] == {"is_panel_toggle": True}
    # The caller names the second « échelle » by its key; links to the group input too
    call = next(n for n in appel.nodes if n.group == "semis")
    assert call.values == {"densité": 5.0, "échelle": 2.0, "aléa_échelle": 0.5, "rotation_graine": 3}
    product = next(n for n in semis.nodes if n.bl_idname == "ShaderNodeMath")
    assert [link.output for _i, link in product.links] == ["aléa_échelle", "rotation_graine"]


def test_a_graph_without_panels_prints_as_before():
    src = graph("geometry: Geometry, t: Float")
    assert to_source(parse(src)) == src
    g = parse(src).graphs[0]
    assert g.param_tree is None and g.output_tree is None and g.settings == []


def test_a_panel_always_takes_one_line_per_item():
    g = parse(graph('geometry: Geometry, "P" { t: Float }, "Vide" {}'))
    assert to_source(g) == ('geometry graph g(\n    geometry: Geometry,\n    "P" {\n        t: Float\n    },\n'
                            '    "Vide" {}\n) -> Geometry {\n  return geometry\n}\n')
    assert [p.name for p in g.graphs[0].params] == ["geometry", "t"]


def test_outputs_take_panels_too(schema):
    src = graph("geometry: Geometry", '(geometry: Geometry, "Infos" { n: Int })', "  return (geometry: geometry, n: 3)\n")
    assert to_source(parse(src)) == (
        "geometry graph g(\n    geometry: Geometry\n) -> (\n    geometry: Geometry,\n    \"Infos\" {\n        n: Int\n"
        "    }\n) {\n  return (geometry: geometry, n: 3)\n}\n")
    (g,) = compile_source(src, schema)
    assert [p.name for p in g.panels] == ["Infos"] and g.panel_of == {("OUTPUT", "n"): "p0"}


def test_a_panel_in_both_lists_is_one_panel(schema):
    src = graph('geometry: Geometry, "P"(default_closed: true) { t: Float }',
                '(geometry: Geometry, "P" { n: Int })', "  return (geometry: geometry, n: 3)\n")
    (g,) = compile_source(src, schema)
    assert [(p.name, p.options) for p in g.panels] == [("P", {"default_closed": True})]
    assert g.panel_of == {("INPUT", "t"): "p0", ("OUTPUT", "n"): "p0"}
    twice = src.replace('(geometry: Geometry, "P" {', '(geometry: Geometry, "P"(description: "x") {')
    assert errors(twice, schema) == ["réglages du panneau « P » donnés deux fois : une seule fois, dans la première "
                                     "liste où il paraît"]


def test_sockets_come_before_the_panels_of_their_level(schema):
    assert errors(graph('geometry: Geometry, "P" { t: Float }, u: Float'), schema) == [
        "« u » vient après le panneau « P » : Blender range les sockets d'un niveau avant ses panneaux"]
    assert errors(graph('geometry: Geometry, "P" {}, "P" {}'), schema) == [
        "panneau « P » écrit deux fois dans la même liste"]


def test_a_toggle_is_the_first_bool_of_its_panel_and_takes_its_name(schema):
    ok = graph('geometry: Geometry, "Fin" { Fin: Bool(is_panel_toggle: true), t: Float }')
    assert compile_source(ok, schema)[0].options[("INPUT", "Fin")] == {"is_panel_toggle": True}
    assert errors(graph('geometry: Geometry, "Fin" { t: Float, Fin: Bool(is_panel_toggle: true) }'), schema) == [
        "is_panel_toggle : l'interrupteur vient en premier dans le panneau « Fin »"]
    assert errors(graph('geometry: Geometry, "Fin" { on: Bool(is_panel_toggle: true) }'), schema) == [
        "is_panel_toggle : l'interrupteur porte le nom de son panneau, « Fin » (Blender le renomme ainsi)"]
    assert errors(graph("geometry: Geometry, on: Bool(is_panel_toggle: true)"), schema) == [
        "is_panel_toggle : une entrée Bool, la première d'un panneau"]


def test_two_sockets_of_one_name_need_a_key_of_their_own(schema):
    assert errors(graph('geometry: Geometry, "A" { t: Float }, "B" { t: Float }'), schema) == [
        "paramètre « t » défini deux fois ; pour garder les deux, nommer l'autre avec as : \"t\" as t_2: Float"]
    src = graph('geometry: Geometry, "A" { t: Float }, "B" { t as b_t: Int }',
                body="  return SetPosition(geometry, offset: CombineXYZ(t, b_t))\n")
    (g,) = compile_source(src, schema)
    assert g.inputs[-2:] == [("t", "Float"), ("t", "Int")] and g.input_keys[-2:] == ["t", "b_t"]
    assert to_source(parse(src)) == format_source(src)
    assert '        t as b_t: Int\n' in to_source(parse(src))


def test_a_caller_tells_them_apart_by_key_or_position(schema):
    callee = graph('geometry: Geometry, "A" { t: Float }, "B" { t as b_t: Float }')
    named = callee + "geometry graph h(geometry: Geometry) -> Geometry {\n  return g(geometry, b_t: 2.0)\n}\n"
    _g, h = compile_source(named, schema)
    assert next(n for n in h.nodes if n.group == "g").values == {"b_t": 2.0}
    by_position = named.replace("b_t: 2.0", "1.0, 2.0")
    _g, h = compile_source(by_position, schema)
    assert next(n for n in h.nodes if n.group == "g").values == {"t": 1.0, "b_t": 2.0}
    # By key, `t` is the first one; by a Blender name both share, neither
    _g, h = compile_source(named.replace("b_t: 2.0", "t: 2.0"), schema)
    assert next(n for n in h.nodes if n.group == "g").values == {"t": 2.0}
    shared = named.replace('"A" { t: Float }, "B" { t as b_t: Float }',
                           '"A" { "Fur Density": Float }, "B" { "Fur Density" as b_fur: Float }')
    assert errors(shared.replace("b_t: 2.0", '"Fur Density": 2.0'), schema) == [
        "« Fur Density » est ambigu ; utilisez l'identifiant : fur_density, b_fur"]


def test_a_group_of_the_file_gives_its_keys(schema):
    schema.existing = {"tige": GroupSpec("tige", (("Seed", "Int"), ("Seed", "Int")), (("Geometry", "Geometry"),),
                                         ("Seed", "guide_seed"))}
    src = "geometry graph h() -> Geometry {\n  return tige(guide_seed: 4)\n}\n"
    (h,) = compile_source(src, schema)
    assert next(n for n in h.nodes if n.group == "tige").values == {"guide_seed": 4}


def test_keys_of_a_repeated_name():
    sockets = [("Seed", None, "Int"), ("Hair Tie", "Hair Tie", "Bool"), ("Hair Tie", "Hair Tie", "Geometry"),
               ("Hair Tie", "Hair Tie", "Object"), ("Seed", "Guide Map", "Int"), ("Object", "Force", "Object"),
               ("Object", "Force", "Object")]
    assert interface_keys(sockets) == ["Seed", "hair_tie", "hair_tie_geometry", "hair_tie_object",
                                       "guide_map_seed", "Object", "object_object"]
    # A key the text gave stays, and the others make room around it
    assert interface_keys([("t", "A", "Float"), ("t", "B", "Float")], [None, "b_t"]) == ["t", "b_t"]
    assert interface_keys([("t", "A", "Float"), ("t", "B", "Float")], ["a_t", None]) == ["a_t", "t"]


def test_tree_settings_go_on_the_tree_kind(schema):
    src = "geometry(is_tool: true, is_mode_edit: true) graph g(geometry: Geometry) -> Geometry {\n  return geometry\n}\n"
    assert to_source(parse(src)) == src
    (g,) = compile_source(src, schema)
    assert g.settings == {"is_tool": True, "is_mode_edit": True}
    assert errors(src.replace("is_mode_edit: true", "is_mode_edit: Position()"), schema) == [
        "réglage « is_mode_edit » : un nombre, true/false, un texte ou une valeur comme FACTOR"]


def test_completion_reads_headers_with_panels_settings_and_keys(schema):
    head = ('geometry(is_tool: true) graph g(\n    geometry: Geometry,\n    "A"(default_closed: true) {\n'
            '        t: Float\n    },\n    "B" {\n        t as b_t: Float\n    }\n) -> Geometry {\n')
    src = head + "  return g2(geometry, "
    other = ("geometry graph g2(geometry: Geometry, \"P\" { x: Float, x as p_x: Float }) -> Geometry {\n"
             "  return geometry\n}\n")
    src = other + src
    lines = src.split("\n")
    _start, items = complete(src, len(lines), len(lines[-1]) + 1, schema)
    got = [i.label for i in items]
    assert got[:3] == ["geometry", "x", "p_x"], got
    assert "b_t" in got and "t" in got  # the graph's own inputs, by key
