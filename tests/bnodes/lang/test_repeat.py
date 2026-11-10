"""Repeat zones: `r = repeat(count, state: start, …) { … return (state: next, …) }`."""

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


def graph(body):
    return f"geometry graph g(geometry: Geometry, t: Float) -> Float {{\n{body}\n}}\n"


def zone(g):
    rin = next(n for n in g.nodes if n.bl_idname == ir.REPEAT_INPUT)
    return rin, g.node(rin.pair)


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("repeat.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_a_long_repeat_head_takes_one_state_per_line():
    src = graph("  r = repeat(\n    10,\n    somme_des_valeurs_trouvées: 0.0,\n    amplitude_de_départ: 0.5,\n"
                "    fréquence_de_départ: 1.0) {\n    return ()\n  }\n  return r.somme_des_valeurs_trouvées")
    assert to_source(parse(src)) == src


def test_states_become_items_of_both_nodes(schema):
    g = compile_one(graph("  r = repeat(4, somme: 0.0, f: 1.0) {\n    return (somme: somme + t * f, f: f * 2.0)\n"
                          "  }\n  return r.somme"), schema)
    rin, rout = zone(g)
    assert rin.items == rout.items == [("somme", "Float"), ("f", "Float")]
    assert rin.values == {"Iterations": 4, "somme": 0.0, "f": 1.0}
    assert rout.name == "r" and [i for i, _l in rout.links] == ["somme", "f"]
    out = g.node(ir.GROUP_OUTPUT)
    assert out.links == [("Float", ir.Link(rout.id, "somme"))]


def test_a_state_left_out_goes_on_unchanged(schema):
    g = compile_one(graph("  r = repeat(4, somme: 0.0, pas: t) {\n    return (somme: somme + pas)\n  }\n"
                          "  return r.somme"), schema)
    rin, rout = zone(g)
    assert ("pas", ir.Link(rin.id, "pas")) in rout.links
    assert rin.links == [("pas", ir.Link(ir.GROUP_INPUT, "t"))]


def test_iteration_is_the_turn_number(schema):
    g = compile_one(graph("  r = repeat(3, somme: 0.0) {\n    return somme + iteration\n  }\n  return r"), schema)
    rin, _rout = zone(g)
    add = next(n for n in g.nodes if n.bl_idname == "ShaderNodeMath")
    assert ("Value_001", ir.Link(rin.id, "Iteration")) in add.links


def test_names_of_the_body_stay_inside(schema):
    msgs = errors(graph("  r = repeat(3, s: 0.0) {\n    d = s * 2.0\n    return d\n  }\n  return d"), schema)
    assert msgs == ["t.bn:6:10  nom inconnu « d »"]


@pytest.mark.parametrize("body, message", [
    ("  r = repeat(3, s: 0.0) {\n    x = s\n  }\n  return r", "t.bn:2:7  return manquant dans le repeat de « r »"),
    ("  r = repeat(3, s: 0.0, u: 1.0) {\n    return s\n  }\n  return r.s",
     "t.bn:3:5  ce repeat a plusieurs états : return (s: …, u: …)"),
    ("  r = repeat(3, s: 0.0) {\n    return (v: s)\n  }\n  return r", "t.bn:3:13  « v » n'est pas un état du repeat ; états : s"),
    ("  r = repeat(3, s: 0.0, s: 1.0) {\n    return ()\n  }\n  return r", "t.bn:2:25  état « s » déclaré deux fois"),
    ("  r = repeat(3, iteration: 0.0) {\n    return ()\n  }\n  return r",
     "t.bn:2:17  « iteration » est le numéro du tour : choisir un autre nom d'état"),
])
def test_wrong_zones_are_reported(schema, body, message):
    assert errors(graph(body), schema) == [message]


@pytest.mark.parametrize("body, message", [
    ("  return repeat(3, s: 0.0) {\n    return s\n  }",
     "t.bn:2:10  repeat s'écrit seul, en valeur d'un nom : r = repeat(10, état: départ) { … }"),
    ("  r = repeat(s: 0.0) {\n    return s\n  }\n  return r",
     "t.bn:2:7  repeat attend d'abord le nombre de tours : repeat(10, état: départ, …)"),
    ("  r = repeat(3) {\n    return 1.0\n  }\n  return r", "t.bn:2:7  repeat attend au moins un état : repeat(10, état: départ)"),
])
def test_wrong_repeat_syntax_is_reported(body, message):
    with pytest.raises(BnError) as err:
        parse(graph(body), "t.bn")
    assert [str(d) for d in err.value.diagnostics] == [message]
