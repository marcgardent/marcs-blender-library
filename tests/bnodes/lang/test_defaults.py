"""Defaults, bounds and implicit fields of a graph's inputs: `t: Float = 0.5 in 0.0..1.0`."""

import pytest

from lang import BnError, compile_source, parse
from lang.format import format_source
from lang.printer import to_source


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [str(d) for d in err.value.diagnostics]


def graph(params):
    return f"geometry graph g(geometry: Geometry, {params}) -> Geometry {{\n  return geometry\n}}\n"


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("defaults.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_defaults_bounds_and_implicit_fields_reach_the_graph(schema, fixture_text):
    g = compile_one(fixture_text("defaults.bn"), schema)
    assert g.defaults == {
        "force": {"value": 0.25, "min": 0.001, "max": 0.999},
        "pas": {"value": 3, "min": 1, "max": 10},
        "actif": {"value": True},
        "direction": {"value": (0.0, 0.0, 1.0)},
        "teinte": {"value": (0.8, 0.3, 0.1)},
        "p": {"implicit": "POSITION"},
        "id": {"implicit": "ID_OR_INDEX"},
        "nom": {"value": "déport"},
        "matière": {"value": "Rust"},
        "jeu": {"min": -1.0, "max": 1.0},
    }


def test_an_int_default_on_a_float_is_a_float(schema):
    assert compile_one(graph("t: Float = 2"), schema).defaults == {"t": {"value": 2.0}}


def test_negative_vector_default(schema):
    assert compile_one(graph("v: Vector = -(1.0, 2.0, 3.0)"), schema).defaults == {"v": {"value": (-1.0, -2.0, -3.0)}}


def test_a_name_called_in_is_still_a_parameter():
    g = parse("geometry graph g(in: Float) -> Float {\n  return in\n}\n").graphs[0]
    assert [p.name for p in g.params] == ["in"]


@pytest.mark.parametrize("params, message", [
    ("t: Float = true", "t.bn:1:49  valeur par défaut de type Bool pour une entrée Float"),
    ("n: Int = 1.5", "t.bn:1:47  valeur par défaut de type Float pour une entrée Int"),
    ("t: Float = Position()", "t.bn:1:49  Position() ne sert de valeur par défaut qu'à une entrée Vector"),
    ("m: Matrix = (1.0, 0.0, 0.0)", "t.bn:1:50  une entrée Matrix n'a pas de valeur par défaut"),
    ("b: Bool in 0..1", "t.bn:1:49  une entrée Bool n'a pas de bornes ; bornes pour : Float, Int, Vector"),
    ("t: Float in 1.0..0.0", "t.bn:1:50  bornes de « t » : le min dépasse le max"),
    ("n: Int in 0.0..1", "t.bn:1:48  borne de « n » : un nombre entier"),
    ("t: Float = t", "t.bn:1:49  valeur par défaut de « t » : un nombre, un tuple, true/false, un texte"
                     " ou Position(), Normal(), Index(), ID(), InstanceTransform(), SelfObject()"),
])
def test_wrong_defaults_are_reported(schema, params, message):
    assert errors(graph(params), schema) == [message]


def test_an_output_has_no_default(schema):
    msgs = errors("geometry graph g(t: Float) -> (r: Float = 1.0) {\n  return (r: t)\n}\n", schema)
    assert msgs == ["t.bn:1:32  la sortie « r » n'a ni valeur par défaut ni bornes"]


def test_a_range_may_be_open_on_one_side(schema):
    src = graph("r: Float = 1.0 in 0.0.., d: Float in ..-0.5")
    assert to_source(parse(src)) == src
    assert compile_one(src, schema).defaults == {"r": {"value": 1.0, "min": 0.0}, "d": {"max": -0.5}}


def test_a_vector_default_of_two_numbers_is_a_2d_vector(schema):
    assert compile_one(graph("uv: Vector = (0.5, 0.5)"), schema).defaults == {"uv": {"value": (0.5, 0.5)}}
