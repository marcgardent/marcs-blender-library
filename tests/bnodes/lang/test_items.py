"""Nodes whose sockets are items: Capture Attribute, Index Switch, Menu Switch."""

import pytest

from lang import BnError, compile_source, parse
from lang.format import format_source
from lang.printer import to_source


def node(source, schema, bl_idname):
    g = compile_source(source, schema, "t.bn")[-1]
    return g, next(n for n in g.nodes if n.bl_idname == bl_idname)


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def graph(body, outputs="Float"):
    return f"geometry graph g(geometry: Geometry, mode: Menu, i: Int, t: Float) -> {outputs} {{\n{body}\n}}\n"


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("items.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_each_named_value_is_a_capture_item(schema):
    src = graph('  c = CaptureAttribute(geometry, hauteur: t, "Rest Position": Position(), domain: FACE)\n'
                "  return c.hauteur + c.rest_position.z")
    g, c = node(src, schema, "GeometryNodeCaptureAttribute")
    assert c.items == [("hauteur", "Float"), ("Rest Position", "Vector")]
    assert c.props == {"domain": "FACE"}
    assert [ident for ident, _l in c.links] == ["Geometry", "hauteur", "Rest Position"]
    assert c.n_inputs == c.n_outputs == 4


def test_a_capture_takes_its_values_by_name(schema):
    src = graph("  return CaptureAttribute(geometry, true, t).geometry", "Geometry")
    assert errors(src, schema) == ["CaptureAttribute : les valeurs se donnent par nom, CaptureAttribute(…, nom: valeur)"]


def test_a_capture_holds_fields_only(schema):
    src = graph("  return CaptureAttribute(geometry, g: geometry).geometry", "Geometry")
    assert errors(src, schema)[0].startswith("CaptureAttribute ne capture pas un Geometry")


def test_an_index_switch_takes_the_type_of_its_first_item(schema):
    g, s = node(graph("  return IndexSwitch(i, 1, 2, 3)", "Int"), schema, "GeometryNodeIndexSwitch")
    assert s.props == {"data_type": "INT"}
    assert s.items == [("0", "Int"), ("1", "Int"), ("2", "Int")]
    assert s.values == {"0": 1, "1": 2, "2": 3} and [i for i, _l in s.links] == ["Index"]


def test_a_written_data_type_wins(schema):
    _g, s = node(graph("  return IndexSwitch(i, 1, 2, data_type: FLOAT)"), schema, "GeometryNodeIndexSwitch")
    assert s.props == {"data_type": "FLOAT"} and s.items == [("0", "Float"), ("1", "Float")]


def test_an_empty_item_keeps_its_place(schema):
    src = graph("  return IndexSwitch(i, _, geometry, _)", "Geometry")
    _g, s = node(src, schema, "GeometryNodeIndexSwitch")
    assert s.props == {"data_type": "GEOMETRY"} and [n for n, _t in s.items] == ["0", "1", "2"]
    assert [i for i, _l in s.links] == ["Index", "1"]


def test_menu_items_are_named_and_flag_their_choice(schema):
    src = graph("  m = MenuSwitch(mode, Lisse: geometry, \"Très rugueux\": _)\n  return m.très_rugueux", "Bool")
    _g, m = node(src, schema, "GeometryNodeMenuSwitch")
    assert m.items == [("Lisse", "Geometry"), ("Très rugueux", "Geometry")]
    assert "data_type" in m.props and m.props["data_type"] == "GEOMETRY"
    assert m.n_outputs == 3


def test_a_menu_value_picks_an_item(schema):
    _g, m = node(graph("  return MenuSwitch(Lisse, Lisse: 1.0, Rugueux: 2.0).output"), schema, "GeometryNodeMenuSwitch")
    assert m.values == {"Menu": "Lisse", "Lisse": 1.0, "Rugueux": 2.0} and m.props == {"data_type": "FLOAT"}


def test_an_item_given_twice_fails(schema):
    src = graph("  return MenuSwitch(mode, a: 1.0, a: 2.0).output")
    assert errors(src, schema) == ["MenuSwitch : « a » donné deux fois"]
