"""Nodes whose sockets are items: Capture Attribute, the switches, Format String, Bake, Field to List…"""

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
    assert errors(src, schema)[0].startswith("CaptureAttribute : pas d'item Geometry")


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


def test_more_items_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("items_more.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_format_string_items_are_named_inputs(schema):
    src = graph('  return FormatString("{n} : {x}", n: i, x: t)', "String")
    _g, f = node(src, schema, "FunctionNodeFormatString")
    assert f.items == [("n", "Int"), ("x", "Float")]
    assert f.values == {"Format": "{n} : {x}"} and [i for i, _l in f.links] == ["n", "x"]
    assert f.n_inputs == 3 and f.n_outputs == 1


def test_format_string_takes_numbers_and_strings_only(schema):
    src = graph('  return FormatString("{b}", b: true)', "String")
    assert errors(src, schema) == ["FormatString : pas d'item Bool ; types : Float, Int, String"]


def test_bake_items_give_their_outputs(schema):
    src = graph("  b = Bake(Geometry: geometry, h: t)\n  return b.h")
    _g, b = node(src, schema, "GeometryNodeBake")
    assert b.items == [("Geometry", "Geometry"), ("h", "Float")]
    assert b.n_inputs == b.n_outputs == 2


def test_field_to_list_keeps_its_count_input(schema):
    _g, f = node(graph('  return FieldToList(i, a: t, Nom: "*").a'), schema, "GeometryNodeFieldToList")
    assert f.items == [("a", "Float"), ("Nom", "String")]
    assert f.values == {"Nom": "*"} and [i for i, _l in f.links] == ["Count", "a"]


def test_an_item_takes_options(schema):
    src = graph('  b = Bake(Geometry: geometry, h(attribute_domain: FACE, is_attribute: true): t)\n'
                '  m = MenuSwitch(mode, Lisse(description: "Sans relief"): 1.0, Rugueux: 2.0)\n'
                "  return b.h + m.output")
    g = compile_source(src, schema, "t.bn")[-1]
    b, m = (next(n for n in g.nodes if n.bl_idname == k) for k in ("GeometryNodeBake", "GeometryNodeMenuSwitch"))
    assert b.item_options == {"h": {"attribute_domain": "FACE", "is_attribute": True}}
    assert m.item_options == {"Lisse": {"description": "Sans relief"}}
    assert m.items == [("Lisse", "Float"), ("Rugueux", "Float")]


def test_item_options_print_back():
    src = 'geometry graph g(mode: Menu) -> Float {\n  return MenuSwitch(mode, "Très lisse"(description: "d"): 1.0).output\n}\n'
    f = parse(src)
    arg = f.graphs[0].body[0].value.target.args[1]
    assert (arg.name, [(o.name, o.value.value) for o in arg.options]) == ("Très lisse", [("description", "d")])
    assert to_source(f) == src


def test_a_call_given_as_a_value_is_not_an_item():
    f = parse("geometry graph g(x: Float) -> Float {\n  return Math(Math(x, 1.0), b: 2.0)\n}\n")
    inner = f.graphs[0].body[0].value.args[0]
    assert inner.name is None and inner.value.name == "Math"


def test_options_only_go_on_items(schema):
    assert errors(graph("  return Math(Value(x: 1): 2.0)"), schema) == [
        "« Value(…) » : seuls les items d'un nœud à items prennent des options"]
    assert errors(graph("  return FieldToList(Count(x: 1): 3, a: t).a"), schema) == [
        "FieldToList : « Count » est une entrée du nœud, pas un item ; elle ne prend pas d'options"]
    assert errors(graph("  return Bake(h(socket_type: INT): t).h"), schema) == [
        "Bake : le nom et le type d'un item s'écrivent « nom: valeur »"]


def test_a_repeat_state_takes_no_options():
    with pytest.raises(BnError) as err:
        parse("geometry graph g(x: Float) -> Float {\n  r = repeat(3, s(a: 1): x) {\n    return s\n  }\n  return r\n}\n")
    assert err.value.diagnostics[0].message == "un état de repeat ne prend pas d'options"


def test_an_item_named_like_an_input_goes_by_a_key_of_its_own(schema):
    src = graph("  c = CaptureAttribute(geometry, t > 0.0, Selection as capturé: t < 1.0, domain as domaine: t)\n"
                "  return SetPosition(c.geometry, c.capturé, offset: CombineXYZ(z: c.domaine)).geometry", "Geometry")
    assert to_source(parse(src)) == src
    g, c = node(src, schema, "GeometryNodeCaptureAttribute")
    assert c.items == [("Selection", "Bool"), ("domain", "Float")] and c.props == {}
    assert [ident for ident, _l in c.links] == ["Geometry", "Selection", "#0", "#1"]
    user = next(n for n in g.nodes if n.bl_idname == "GeometryNodeSetPosition")
    assert ("Selection", "#0") in [(i, link.output) for i, link in user.links]


def test_an_item_key_with_options_prints_back():
    src = graph('  return MenuSwitch(mode, Menu as menu_2(description: "Le premier"): 1.0, B: 2.0).output')
    assert to_source(parse(src)) == src


def test_a_key_must_be_free_and_only_names_an_item(schema):
    taken = graph("  return CaptureAttribute(geometry, a as selection: t).geometry", "Geometry")
    assert errors(taken, schema) == ["CaptureAttribute : la clé « selection » est déjà une entrée, un réglage ou un item du nœud"]
    plain = graph("  return SetPosition(geometry, offset as o: (0.0, 0.0, 1.0)).geometry", "Geometry")
    assert errors(plain, schema)[0].startswith("« offset as o » : seuls les items")
    with pytest.raises(BnError, match="ne nomme que l'item"):
        parse(graph("  r = repeat(3, a as b: 0.0) {\n    return a\n  }\n  return r"))
