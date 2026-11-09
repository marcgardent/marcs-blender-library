import pytest

from lang import parse
from lang.printer import to_source

# Canonical texts: printing what was parsed gives them back unchanged
CANONICAL = [
    "geometry graph wave(geometry: Geometry, t: Float) -> Geometry {\n"
    "  p = Position()\n"
    "  s = Math(SeparateXYZ(p).x, t, operation: ADD)\n"
    "  h = Math(Math(s, operation: SINE), 0.2, operation: MULTIPLY)\n"
    "  return SetPosition(geometry, offset: CombineXYZ(z: h))\n"
    "}\n",
    "geometry graph g(geometry: Geometry) -> Geometry {\n"
    "  return geometry |> SubdivideMesh(level: 2)\n"
    "    |> SetShadeSmooth(domain: FACE)\n"
    "    |> SetMaterial(material: \"Rust\")\n"
    "}\n",
    'geometry graph "Smooth by Angle"(mesh: Geometry, "Fur Density": Float) -> (Mesh: Geometry, n: Int) {\n'
    "  return (Mesh: mesh, n: 3)\n"
    "}\n"
    "\n"
    "geometry graph main(geometry: Geometry) -> Geometry {\n"
    "  x = smooth_by_angle(geometry, fur_density: -0.5).Mesh\n"
    '  return SetMaterial(x, material: "Rust", "Base Color": (1.0, 0.5, 0.0, 1.0), enabled: true)\n'
    "}\n",
    "geometry graph g(geometry: Geometry) -> Geometry {\n"
    "  return ()\n"
    "}\n",
    "geometry graph g(geometry: Geometry, t: Float) -> Geometry {\n"
    "  top = t + 1.0 >= t * 2.0\n"
    "  same = (t < 0.0) == (t > 1.0)\n"
    "  inside = t > 0.0 and not (t > 1.0 or t == 0.5) and (not same) == top\n"
    "  either = (t > 0.0 or same) and (top xor same)\n"
    "  flip = (top or same) xor inside\n"
    "  odd = top xor same xor inside\n"
    '  return SetPosition(geometry, selection: top != (t == 0.5), offset: (0.0, 0.0, -t))\n'
    "}\n",
    "geometry graph g(n: Vector, u: Vector) -> Float {\n"
    "  side = n × u\n"
    "  return (n ⋅ side) * 2.0 + (n × u) ⋅ (u + n) - n ⋅ u\n"
    "}\n",
    "shader graph rust(uv: Vector) -> Shader {\n"
    "  n = NoiseTexture(uv, scale: 8)\n"
    "  return PrincipledBSDF(\n"
    "    base_color: ColorRamp(n.fac),\n"
    "    roughness: n.fac * 0.5 + 0.4,\n"
    "    metallic: (n.fac - 0.1) * 2.0,\n"
    "    subsurface_weight: 0.25)\n"
    "}\n",
]


@pytest.mark.parametrize("source", CANONICAL)
def test_canonical_text_prints_back_unchanged(source):
    assert to_source(parse(source)) == source


def test_layout_is_normalized():
    messy = "geometry graph g(geometry:Geometry)->Geometry{return geometry|>SetShadeSmooth()}"
    assert to_source(parse(messy)) == (
        "geometry graph g(geometry: Geometry) -> Geometry {\n"
        "  return geometry |> SetShadeSmooth()\n"
        "}\n")


def test_long_signature_breaks_per_parameter():
    params = ", ".join(f"input_number_{i}: Float" for i in range(6))
    text = to_source(parse(f"geometry graph g({params}) -> Float {{\n  return input_number_0\n}}"))
    assert text.startswith("geometry graph g(\n    input_number_0: Float,\n")
    assert to_source(parse(text)) == text


def test_words_print_as_signs():
    text = to_source(parse("geometry graph g(n: Vector, u: Vector) -> Float {\n  return n dot (u cross n)\n}"))
    assert "  return n ⋅ (u × n)\n" in text


def test_xor_beside_or_takes_parentheses():
    # Same strength as `or`, read from the left: the parentheses say so
    text = to_source(parse("geometry graph g(a: Bool, b: Bool) -> Bool {\n  return a or b xor a\n}"))
    assert "  return (a or b) xor a\n" in text, text
