import pytest

from lang import BnError, compile_source, ir
from lang.sugar import choose


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def graph(body, sig="geometry graph g(geometry: Geometry, t: Float, v: Vector, w: Vector) -> Geometry"):
    return f"{sig} {{\n{body}\n  return geometry\n}}"


def ops(g):
    """(node, operation) of every Math and Vector Math node, in creation order."""
    return [(n.bl_idname.removeprefix("ShaderNode"), n.props.get("operation")) for n in g.nodes
            if n.bl_idname in ("ShaderNodeMath", "ShaderNodeVectorMath")]


def node(g, name):
    return next(n for n in g.nodes if n.name == name)


def test_spec_wave_is_four_nodes(schema):
    g = compile_one("geometry graph wave(geometry: Geometry, t: Float) -> Geometry {\n"
                    "  p = Position()\n  h = sin(p.x + t) * 0.2\n"
                    "  return SetPosition(geometry, offset: CombineXYZ(z: h))\n}", schema)
    assert len(g.nodes) == 9 and len(g.edges()) == 9
    assert ops(g) == [("Math", "ADD"), ("Math", "SINE"), ("Math", "MULTIPLY")]
    h = node(g, "h")
    assert h.values == {"Value_001": 0.2}
    sep = next(n for n in g.nodes if n.bl_idname == "ShaderNodeSeparateXYZ")
    add = next(n for n in g.nodes if n.props.get("operation") == "ADD")
    assert add.links == [("Value", ir.Link(sep.id, "X")), ("Value_001", ir.Link(ir.GROUP_INPUT, "t"))]


def test_precedence_and_parentheses(schema):
    g = compile_one(graph("  a = t + t * 2.0\n  b = (t + t) * 2.0\n  c = t - t - t"), schema)
    assert ops(g) == [("Math", "MULTIPLY"), ("Math", "ADD"), ("Math", "ADD"), ("Math", "MULTIPLY"),
                      ("Math", "SUBTRACT"), ("Math", "SUBTRACT")]
    a = node(g, "a")
    assert a.links[1][0] == "Value_001"  # t * 2.0 is the right operand of +


def test_components_share_one_separate(schema):
    g = compile_one(graph("  p = Position()\n  a = p.x + p.y\n  b = v.z"), schema)
    seps = [n for n in g.nodes if n.bl_idname == "ShaderNodeSeparateXYZ"]
    assert len(seps) == 2  # one for p, one for v


def test_vector_math(schema):
    g = compile_one(graph("  a = v * 2.0\n  b = 2.0 * v\n  c = v + w\n  d = length(v)\n  e = -v\n  f = -t\n"
                          "  k = v + 1.0\n  m = min(v, w)"), schema)
    assert ops(g) == [("VectorMath", "SCALE"), ("VectorMath", "SCALE"), ("VectorMath", "ADD"),
                      ("VectorMath", "LENGTH"), ("VectorMath", "SCALE"), ("Math", "MULTIPLY"),
                      ("VectorMath", "ADD"), ("VectorMath", "MINIMUM")]
    b = node(g, "b")
    assert b.links == [("Vector", ir.Link(ir.GROUP_INPUT, "v"))] and b.values == {"Scale": 2.0}
    assert node(g, "e").values == {"Scale": -1.0}
    assert node(g, "k").values == {"Vector_001": 1.0}


def test_length_gives_a_float(schema):
    g = compile_one(graph("  c = CombineXYZ(length(v))"), schema)
    length = next(n for n in g.nodes if n.props.get("operation") == "LENGTH")
    assert node(g, "c").links == [("X", ir.Link(length.id, "Value"))]


def test_negative_literals_fold(schema):
    g = compile_one(graph("  a = t * -(2.0)\n  b = v + -(1.0, 2.0, 3.0)"), schema)
    assert node(g, "a").values == {"Value_001": -2.0}
    assert node(g, "b").values == {"Vector_001": (-1.0, -2.0, -3.0)}


@pytest.mark.parametrize("body, message", [
    ("  a = geometry + 1.0", "« + » ne s'applique pas à Geometry"),
    ("  a = length(t)", "length attend des vecteurs"),
    ("  a = atan2(t)", "atan2 attend 2 argument(s), en reçoit 1"),
    ("  a = sin(t, base: 2.0)", "sin ne prend pas d'argument nommé"),
    ("  a = sin(nope)", "nom inconnu « nope »"),
    ("  a = t.x", "« t » est déjà une sortie (Float) ; « .x » n'existe pas"),
])
def test_formula_errors(schema, body, message):
    assert errors(graph(body), schema) == [message]


def test_choose_is_shared_with_export():
    assert choose("*", ["Float", "Vector"]) == ("VectorMath", {"operation": "SCALE"}, (1, 0))
    assert choose("*", ["Vector", "Vector"]) == ("VectorMath", {"operation": "MULTIPLY"}, (0, 1))
    assert choose("sin", ["Int"]) == ("Math", {"operation": "SINE"}, (0,))
    with pytest.raises(ValueError):
        choose("atan2", ["Vector", "Vector"])


def compares(g):
    return [(n.props["data_type"], n.props["operation"]) for n in g.nodes if n.bl_idname == "FunctionNodeCompare"]


def test_comparisons_make_compare_nodes(schema):
    g = compile_one(graph("  a = t > 0.5\n  b = v == w\n  c = 1 <= 2\n  d = \"x\" != \"y\"\n"
                          "  e = t + 1.0 < t * 2.0\n  f = (1.0, 0.0, 0.0, 1.0) == (1.0, 0.0, 0.0, 1.0)"), schema)
    assert compares(g) == [("FLOAT", "GREATER_THAN"), ("VECTOR", "EQUAL"), ("INT", "LESS_EQUAL"),
                           ("STRING", "NOT_EQUAL"), ("FLOAT", "LESS_THAN"), ("RGBA", "EQUAL")]
    a = node(g, "a")
    assert a.links == [("A", ir.Link(ir.GROUP_INPUT, "t"))] and a.values == {"B": 0.5}
    assert "Epsilon" not in node(g, "b").values  # == keeps Blender's epsilon
    e = node(g, "e")
    assert [s for s, _l in e.links] == ["A", "B"]


def test_a_comparison_is_a_bool(schema):
    g = compile_one(graph("  x = SetPosition(geometry, selection: t > 0.0)"), schema)
    cmp = next(n for n in g.nodes if n.bl_idname == "FunctionNodeCompare")
    assert ("Selection", ir.Link(cmp.id, "Result")) in node(g, "x").links


@pytest.mark.parametrize("body, message", [
    ('  a = "x" < "y"', "« < » : une String ne se compare qu'à une String, par == ou !="),
    ('  a = "x" == t', "« == » : une String ne se compare qu'à une String, par == ou !="),
    ("  a = geometry == geometry", "« == » ne s'applique pas à Geometry"),
])
def test_comparison_errors(schema, body, message):
    assert errors(graph(body), schema) == [message]


def logic(g):
    return [n.props["operation"] for n in g.nodes if n.bl_idname == "FunctionNodeBooleanMath"]


def test_and_or_not_make_boolean_math(schema):
    g = compile_one(graph("  a = t > 0.0 and t < 1.0 or not t > 2.0\n  b = xor(true, t > 0.0)"), schema)
    assert logic(g) == ["AND", "NOT", "OR", "XOR"]
    a = node(g, "a")
    assert [s for s, _l in a.links] == ["Boolean", "Boolean_001"]
    assert node(g, "b").values == {"Boolean": True}


def test_logic_errors(schema):
    assert errors(graph("  a = v and true"), schema) == ["« and » attend des Bool, pas Vector"]
