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
    "  return geometry\n"
    "    |> SubdivideMesh(level: 2)\n"
    "    |> SetShadeSmooth(domain: FACE)\n"
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
        "  return geometry\n"
        "    |> SetShadeSmooth()\n"
        "}\n")


def test_long_signature_breaks_per_parameter():
    params = ", ".join(f"input_number_{i}: Float" for i in range(6))
    text = to_source(parse(f"geometry graph g({params}) -> Float {{\n  return input_number_0\n}}"))
    assert text.startswith("geometry graph g(\n    input_number_0: Float,\n")
    assert to_source(parse(text)) == text
