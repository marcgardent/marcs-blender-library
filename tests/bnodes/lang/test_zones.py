"""Simulation and For Each zones: `s = simulate(state: start, …) { … }`, `e = foreach(geometry, …) { … }`."""

import pytest

from lang import BnError, compile_source, ir, parse
from lang.format import format_source
from lang.printer import to_source


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [str(d) for d in err.value.diagnostics]


def graph(body, outputs="Geometry"):
    return f"geometry graph g(geometry: Geometry, t: Float) -> {outputs} {{\n{body}\n}}\n"


def zone(g, bl_idname):
    zin = next(n for n in g.nodes if n.bl_idname == bl_idname)
    return zin, g.node(zin.pair)


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("zones.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_simulate_and_foreach_stay_names_without_a_block():
    # Contextual keywords: a call of that name, or a name, is what it was
    tree = parse(graph("  simulate = foreach(geometry, 1.0)\n  return simulate"))
    assert type(tree.graphs[0].body[0].value).__name__ == "Call"


def test_states_and_skip_of_a_simulation(schema):
    g = compile_one(graph("  s = simulate(mesh: geometry, v: 0.0) {\n"
                          "    return (mesh: mesh |> SetPosition(offset: CombineXYZ(z: v * delta_time)), "
                          "skip: t > 1.0)\n  }\n  return s.mesh"), schema)
    zin, zout = zone(g, ir.SIMULATION_INPUT)
    assert zout.bl_idname == ir.SIMULATION_OUTPUT
    assert zin.items == zout.items == [("mesh", "Geometry"), ("v", "Float")]
    assert zin.values == {"v": 0.0} and zin.links == [("mesh", ir.Link(ir.GROUP_INPUT, "geometry"))]
    # v is not returned: it goes on unchanged
    assert ("v", ir.Link(zin.id, "v")) in zout.links
    assert "Skip" in [i for i, _l in zout.links]
    times = [n for n in g.nodes if n.bl_idname == "ShaderNodeMath" and ("Value_001", ir.Link(zin.id, "Delta Time")) in n.links]
    assert times


def test_a_type_alone_is_an_item_with_no_value(schema):
    g = compile_one(graph("  s = simulate(mesh: Geometry, cache: Bundle) {\n    return ()\n  }\n  return s.mesh"),
                    schema)
    zin, zout = zone(g, ir.SIMULATION_INPUT)
    assert zout.items == [("mesh", "Geometry"), ("cache", "Bundle")]
    assert zin.links == [] and zin.values == {}


def test_foreach_items_main_then_generated(schema):
    g = compile_one(graph("  e = foreach(geometry, domain: FACE, selection: false, h: Position().z) {\n"
                          "    return (aire: h * 2.0, rang: index, mesh: element, couleur: h)\n  }\n"
                          "  return e.mesh", "Geometry"), schema)
    zin, zout = zone(g, ir.FOREACH_INPUT)
    assert zout.props == {"domain": "FACE"}
    assert zin.items == [("h", "Float")]
    assert zin.values == {"Selection": False} and ("Geometry", ir.Link(ir.GROUP_INPUT, "geometry")) in zin.links
    assert zout.items == [("aire", "Float"), ("rang", "Int"), ("mesh", "Geometry"), ("couleur", "Float")]
    assert zout.main == 2
    assert ("mesh", ir.Link(zin.id, "Element")) in zout.links and ("rang", ir.Link(zin.id, "Index")) in zout.links
    assert g.node(ir.GROUP_OUTPUT).links == [("Geometry", ir.Link(zout.id, "mesh"))]


def test_the_zone_alone_is_the_geometry_it_went_through(schema):
    g = compile_one(graph("  e = foreach(geometry) {\n    return (geometry: element)\n  }\n  return e"), schema)
    _zin, zout = zone(g, ir.FOREACH_INPUT)
    assert g.node(ir.GROUP_OUTPUT).links == [("Geometry", ir.Link(zout.id, ir.FOREACH_GEOMETRY))]
    g = compile_one(graph("  e = foreach(geometry) {\n    return (geometry: element)\n  }\n  return e.geometry"), schema)
    assert g.node(ir.GROUP_OUTPUT).links == [("Geometry", ir.Link(zout.id, "geometry"))]


@pytest.mark.parametrize("body, message", [
    ("  s = simulate(v: 0.0) {\n    x = v\n  }\n  return geometry",
     "t.bn:2:7  return manquant dans le simulate de « s »"),
    ("  s = simulate(delta_time: 0.0) {\n    return ()\n  }\n  return geometry",
     "t.bn:2:16  « delta_time » est le temps écoulé depuis le pas précédent : choisir un autre nom d'état"),
    ("  s = simulate(v: 0.0, u: 1.0) {\n    return v\n  }\n  return geometry",
     "t.bn:3:5  ce simulate a plusieurs états : return (v: …, u: …)"),
    ("  s = simulate(v: 0.0) {\n    return (w: v)\n  }\n  return geometry",
     "t.bn:3:13  « w » n'est pas un état du simulate ; états : v"),
    ("  s = simulate(m: Shader) {\n    return ()\n  }\n  return geometry",
     "t.bn:2:16  un état de simulate ne peut pas être de type Shader"),
    ("  e = foreach(geometry, domain: FACES) {\n    return ()\n  }\n  return e",
     "t.bn:2:25  domain attend une valeur parmi POINT, EDGE, FACE, CORNER, CURVE, INSTANCE, LAYER"),
    ("  e = foreach(geometry, index: 1.0) {\n    return ()\n  }\n  return e",
     "t.bn:2:25  « index » est le numéro de l'élément : choisir un autre nom d'item"),
    ("  e = foreach(geometry) {\n    return element\n  }\n  return e",
     "t.bn:3:5  un foreach rend ses items par nom : return (valeur: v, mesh: g, …)"),
    ("  e = foreach(geometry) {\n    return (nom: \"a\")\n  }\n  return e",
     "t.bn:3:13  un item de foreach ne peut pas être de type String"),
    ("  e = foreach(geometry) {\n    d = index\n    return ()\n  }\n  return d",
     "t.bn:6:10  nom inconnu « d »"),
])
def test_wrong_zones_are_reported(schema, body, message):
    assert errors(graph(body), schema) == [message]


@pytest.mark.parametrize("body, message", [
    ("  s = simulate(geometry) {\n    return ()\n  }\n  return s",
     "t.bn:2:7  simulate attend des états nommés : simulate(état: départ, …)"),
    ("  e = foreach(domain: FACE) {\n    return ()\n  }\n  return e",
     "t.bn:2:7  foreach attend d'abord la géométrie, puis des valeurs nommées : "
     "foreach(geometry, domain: FACE, valeur: champ, …)"),
])
def test_wrong_zone_syntax_is_reported(body, message):
    with pytest.raises(BnError) as err:
        parse(graph(body), "t.bn")
    assert [str(d) for d in err.value.diagnostics] == [message]
