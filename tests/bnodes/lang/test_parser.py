import pytest

from lang import BnError, ast, parse
from lang.lexer import tokenize

# Snippets from the spec: they must all parse, formulas included
SPEC_SNIPPETS = [
    "geometry graph g(v: Vector, geometry: Geometry) -> Geometry {\n"
    "  a = SetPosition(geometry, offset: v)\n  return Math(a, b, operation: POWER)\n}",
    "geometry graph g(v: Vector) -> Float {\n  return SeparateXYZ(v).z\n}",
    "geometry graph g() -> Float {\n  p = Position()\n  return sin(p.x) + cos(p.y) * p.z\n}",
    "geometry graph g(geometry: Geometry) -> Geometry {\n"
    "  return geometry\n    |> SubdivideMesh(level: 2)\n    |> SetShadeSmooth()\n}",
    "geometry graph wave(\n    geometry: Geometry, t: Float\n) -> Geometry {\n  return geometry\n}",
    "geometry graph grid() -> Geometry {\n  return MeshGrid(size_x: 2, size_y: 2)\n    |> SetShadeSmooth()\n}",
    "shader graph rust(uv: Vector) -> Shader {\n  n = NoiseTexture(uv, scale: 8)\n"
    "  return PrincipledBSDF(\n    base_color: ColorRamp(n.fac),\n    roughness: n.fac * 0.5 + 0.4)\n}",
    "compositor graph look(image: Color) -> Color {\n  return image\n"
    "    |> Glare(glare_type: FOG_GLOW)\n    |> ColorBalance(lift: 0.95)\n}",
]


@pytest.mark.parametrize("source", SPEC_SNIPPETS)
def test_spec_snippets_parse(source):
    assert len(parse(source).graphs) == 1


def test_wave(fixture_text):
    g = parse(fixture_text("wave_v0.bn")).graphs[0]
    assert (g.kind, g.name, g.single_output) == ("geometry", "wave", True)
    assert [(p.name, p.type) for p in g.params] == [("geometry", "Geometry"), ("t", "Float")]
    assert [type(s).__name__ for s in g.body] == ["Assign", "Assign", "Assign", "Return"]


def test_positions_are_one_based():
    toks = tokenize("a = 1\n  // note\n  b |> F()")
    assert [(t.text, t.line, t.col) for t in toks[:3]] == [("a", 1, 1), ("=", 1, 3), ("1", 1, 5)]
    assert [(t.text, t.line, t.col) for t in toks[3:5]] == [("b", 3, 3), ("|>", 3, 5)]


def test_precedence():
    ret = parse("geometry graph g() -> Float {\n  return a + b * c |> F()\n}").graphs[0].body[0]
    pipe = ret.value
    assert isinstance(pipe, ast.Pipe)
    add = pipe.left
    assert add.op == "+" and add.right.op == "*"


def test_negative_number_folds():
    ret = parse("geometry graph g() -> Float {\n  return -0.5\n}").graphs[0].body[0]
    assert isinstance(ret.value, ast.Number) and ret.value.value == -0.5


def test_tuple_and_quoted_socket():
    body = parse('shader graph g(n: Vector) -> Shader {\n'
                 '  x = F((0, 0, 1), "Base Color": n)\n  return x."BSDF"\n}').graphs[0].body
    call = body[0].value
    assert isinstance(call.args[0].value, ast.Tuple)
    assert call.args[1].name == "Base Color"
    assert body[1].value.socket == "BSDF"


def test_record_return():
    g = parse("geometry graph g(a: Geometry) -> (mesh: Geometry, n: Int) {\n"
              "  return (mesh: a, n: 3)\n}").graphs[0]
    assert not g.single_output
    assert [f.name for f in g.body[0].value.fields] == ["mesh", "n"]


@pytest.mark.parametrize("source, line, col, text", [
    ("geometry graph g() -> Float {\n  return F(a: 1, 2)\n}", 2, 18, "positionnel après"),
    ("geometry graph g() -> Float {\n  return 1\n", 3, 1, "« } » attendu"),
    ("geometry graph g() -> Float {\n  F()\n}", 2, 3, "instruction attendue"),
    ("geometry graph g() -> Float {\n  return x |> 3\n}", 2, 12, "après |>"),
    ('geometry graph g() -> Float {\n  return "abc\n}', 2, 10, "chaîne non fermée"),
])
def test_syntax_errors(source, line, col, text):
    with pytest.raises(BnError) as err:
        parse(source, "t.bn")
    d = err.value.diagnostics[0]
    assert (d.line, d.col) == (line, col)
    assert text in d.message
