"""Bundles and closures: CombineBundle, SeparateBundle, closure zones and their evaluation."""

import pytest

from lang import BnError, compile_source, ir, parse
from lang.format import format_source
from lang.printer import to_source
from lang.schema import CLOSURE_INPUT, CLOSURE_OUTPUT


def compile_all(source, schema):
    return compile_source(source, schema, "t.bn")


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def graph(body, outputs="Float"):
    return f"geometry graph g(geometry: Geometry, t: Float, b: Bundle, c: Closure) -> {outputs} {{\n{body}\n}}\n"


def nodes(g, bl_idname):
    return [n for n in g.nodes if n.bl_idname == bl_idname]


def test_fixture_prints_back_unchanged(fixture_text):
    src = fixture_text("bundles.bn")
    assert to_source(parse(src)) == src
    assert format_source(src) == src


def test_the_fixture_checks(fixture_text, schema):
    ressort, appliquer, cumul = compile_all(fixture_text("bundles.bn"), schema)
    assert len(nodes(appliquer, "NodeSeparateBundle")) == 2
    (h,) = nodes(appliquer, "NodeEvaluateClosure")
    assert h.props == {"define_signature": True}
    assert h.item_options == {("in", "Point Count"): {"structure_type": "SINGLE"}}
    (rout,) = nodes(cumul, ir.REPEAT_OUTPUT)
    assert rout.items == [("total", "Float"), ("dernier", "Bundle")]


def test_a_closure_is_a_zone_that_captures_outer_names(schema):
    (g,) = compile_all(graph("  f = closure(x: Float, \"Point Count\": Int(structure_type: SINGLE)) -> (r: Float) {\n"
                             "    return x * t + point_count\n  }\n  return f(x: 1.0)"), schema)
    (cin,), (cout,) = nodes(g, CLOSURE_INPUT), nodes(g, CLOSURE_OUTPUT)
    assert cin.pair == cout.id and cout.name == "f"
    assert cin.items == cout.items == [("x", "Float"), ("Point Count", "Int")]
    assert cout.out_items == [("r", "Float")]
    assert cout.item_options == {("in", "Point Count"): {"structure_type": "SINGLE"}}
    multiply = next(n for n in g.nodes if n.props.get("operation") == "MULTIPLY")
    assert ("Value", ir.Link(cin.id, "#0")) in multiply.links
    assert ("Value_001", ir.Link(ir.GROUP_INPUT, "t")) in multiply.links
    assert [ident for ident, _l in cout.links] == ["#0"]


def test_an_evaluation_takes_the_items_of_the_closure_it_is_given(schema):
    (g,) = compile_all(graph("  f = closure(x: Float, v: Vector) -> Float {\n    return x\n  }\n"
                             "  return f(v: Position())"), schema)
    (e,) = nodes(g, "NodeEvaluateClosure")
    assert e.items == [("x", "Float"), ("v", "Vector")] and e.out_items == [("Float", "Float")]
    assert [ident for ident, _l in e.links] == ["Closure", "#1"]


def test_an_evaluation_declares_its_items_when_the_closure_comes_from_elsewhere(schema):
    src = graph("  e = EvaluateClosure(c, x: t, g: Geometry = _, r: Rotation = (0.0, 0.0, 1.0)) -> (r: Float, s: Vector)\n"
                "  return e.s.z")
    (g,) = compile_all(src, schema)
    (e,) = nodes(g, "NodeEvaluateClosure")
    assert e.items == [("x", "Float"), ("g", "Geometry"), ("r", "Rotation")]
    assert e.out_items == [("r", "Float"), ("s", "Vector")]
    assert e.values == {"#2": (0.0, 0.0, 1.0)}
    assert [ident for ident, _l in e.links] == ["Closure", "#0"]


def test_a_closure_name_called_is_an_evaluation(schema):
    (g,) = compile_all(graph("  return c(x: t) -> Float"), schema)
    (e,) = nodes(g, "NodeEvaluateClosure")
    assert e.links[0] == ("Closure", ir.Link(ir.GROUP_INPUT, "c"))


def test_bundles_take_the_types_of_their_values(schema):
    src = graph("  p = CombineBundle(hauteur: t, forme: geometry, \"Pin Positions\": Rotation = _, nid: CombineBundle())\n"
                "  s = SeparateBundle(p) -> (hauteur: Float, nid: Bundle(structure_type: SINGLE))\n"
                "  return s.hauteur")
    (g,) = compile_all(src, schema)
    (outer, inner), (s,) = nodes(g, "NodeCombineBundle")[::-1], nodes(g, "NodeSeparateBundle")
    assert outer.items == [("hauteur", "Float"), ("forme", "Geometry"), ("Pin Positions", "Rotation"), ("nid", "Bundle")]
    assert inner.items == [] and [ident for ident, _l in outer.links] == ["#0", "#1", "#3"]
    assert s.items is None and s.out_items == [("hauteur", "Float"), ("nid", "Bundle")]
    assert s.item_options == {("out", "nid"): {"structure_type": "SINGLE"}}
    assert g.node(ir.GROUP_OUTPUT).links == [("Float", ir.Link(s.id, "#0"))]


def test_a_repeat_state_may_start_empty_when_typed(schema):
    (g,) = compile_all(graph("  r = repeat(3, w: Bundle = _, k: Float = 1) {\n    return (w: b)\n  }\n  return r.k"), schema)
    (rin,) = nodes(g, ir.REPEAT_INPUT)
    assert rin.items == [("w", "Bundle"), ("k", "Float")]
    assert rin.values == {"Iterations": 3, "k": 1} and rin.links == []


def test_closure_stays_a_name():
    src = ("geometry graph closure(x: Float) -> Float {\n  return x\n}\n\n"
           "geometry graph g(t: Float) -> Float {\n  closure_2 = closure(t)\n  return closure(x: closure_2)\n}\n")
    assert to_source(parse(src)) == src


def test_a_graph_wins_over_a_closure_of_the_same_name(schema):
    src = ("geometry graph f(x: Float) -> Float {\n  return x\n}\n\n"
           "geometry graph g(f: Closure) -> Float {\n  return f(x: 1.0)\n}\n")
    g = compile_all(src, schema)[-1]
    assert [n.group for n in g.nodes if n.group] == ["f"]


def test_picking_a_declared_output_takes_parentheses():
    src = graph("  return (SeparateBundle(b) -> (a: Float, c: Float)).c")
    assert to_source(parse(src)) == src


@pytest.mark.parametrize("body, message", [
    ("  return EvaluateClosure(c, x: t)",
     "EvaluateClosure : la signature de la closure n'est pas connue ici ; écrire ses items : "
     "EvaluateClosure(x: Float = …) -> (r: Float)"),
    ("  return SeparateBundle(b).x", "SeparateBundle déclare ses items : SeparateBundle(b) -> (nom: Type, …)"),
    ("  return SeparateBundle(b, x: Float)",
     "SeparateBundle déclare ses items après « -> » : SeparateBundle(b) -> (nom: Type, …)"),
    ("  return CombineBundle(g: _)", "« g » n'a pas de valeur : écrire son type, g: Float = _"),
    ("  return CombineBundle(t)", "CombineBundle : les items se donnent par nom, CombineBundle(…, nom: valeur)"),
    ("  return SetPosition(geometry, offset: Vector = Position())",
     "« offset: Vector = … » donne le type d'un item : de CombineBundle, d'EvaluateClosure ou d'un état de repeat"),
    ("  return Position() -> Vector", "« -> » déclare les items de SeparateBundle ou EvaluateClosure, pas de Position"),
    ("  f = closure(x: Float) -> (r: Float) {\n    return (s: x)\n  }\n  return f(x: t)",
     "« s » n'est pas une sortie de la closure ; sorties : r"),
    ("  f = closure(x: Float = 1.0) -> Float {\n    return x\n  }\n  return f()",
     "un item de closure n'a ni valeur par défaut ni bornes"),
    ("  f = closure(x: Float(subtype: FACTOR)) -> Float {\n    return x\n  }\n  return f()",
     "option « subtype » inconnue pour un item ; options : structure_type"),
    ("  f = closure() -> Float {\n    return 1.0\n  }\n  return f(y: 1.0)",
     "la closure n'a pas d'entrée « y » ; entrées : aucune"),
    ("  f = closure(x: Float) -> Float {\n    d = x\n  }\n  return f(x: t)", "return manquant dans la closure de « f »"),
])
def test_wrong_bundles_and_closures_are_reported(schema, body, message):
    assert errors(graph(body), schema)[0] == message


def test_names_of_a_closure_body_stay_inside(schema):
    msgs = errors(graph("  f = closure(x: Float) -> Float {\n    d = x * 2.0\n    return d\n  }\n  return d"), schema)
    assert msgs == ["nom inconnu « d »"]
