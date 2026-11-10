"""Interface settings written as options, `x: Float(subtype: FACTOR)`, and the graph's description."""

import pytest

from lang import BnError, compile_source, parse
from lang.format import format_source
from lang.printer import to_source


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("interface.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_options_and_description_reach_the_graph(schema, fixture_text):
    (g,) = compile_source(fixture_text("interface.bn"), schema)
    assert g.description == "Garde une part des points, à une taille donnée"
    assert g.options == {
        ("INPUT", "t"): {"subtype": "FACTOR", "description": "La part à garder"},
        ("INPUT", "taille"): {"subtype": "DISTANCE", "structure_type": "SINGLE"},
        ("INPUT", "graine"): {"hide_in_modifier": True},
        ("OUTPUT", "Hauteur"): {"description": "La hauteur de chaque point"},
    }
    assert g.defaults["t"] == {"value": 0.5, "min": 0.0, "max": 1.0}


def test_the_description_is_first_in_the_body():
    src = 'geometry graph g() -> Float {\n  x = 1.0\n  "Trop tard"\n  return x\n}\n'
    with pytest.raises(BnError, match="première ligne"):
        parse(src)


def test_a_titled_frame_is_not_a_description():
    g = parse('geometry graph g() -> Float {\n  "Calcul" {\n    x = 1.0\n  }\n  return x\n}\n').graphs[0]
    assert g.description is None and len(g.body) == 2


def test_settings_with_a_syntax_of_their_own_are_not_options(schema):
    src = "geometry graph g(x: Float(default_value: 1.0, min_value: 0.0)) -> Float {\n  return x\n}\n"
    assert errors(src, schema) == ["default_value s'écrit après = : x: Float = 1.0",
                                   "min_value s'écrit avec in : x: Float in 0.0..1.0"]


def test_an_option_takes_a_plain_value(schema):
    src = "geometry graph g(x: Float(description: Position())) -> Float {\n  return x\n}\n"
    assert errors(src, schema)[0].startswith("option « description » : un nombre")


def test_long_outputs_take_one_line_each():
    out = ", ".join(f'sortie_{i}: Float(description: "La sortie numéro {i}")' for i in range(3))
    src = parse(f"geometry graph g(x: Float) -> ({out}) {{\n  return ()\n}}\n")
    assert to_source(src) == (
        "geometry graph g(\n    x: Float\n) -> (\n"
        + ",\n".join(f'    sortie_{i}: Float(description: "La sortie numéro {i}")' for i in range(3))
        + "\n) {\n  return ()\n}\n")
