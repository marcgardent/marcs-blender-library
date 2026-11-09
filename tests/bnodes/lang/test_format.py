import pytest

from lang import BnError
from lang.format import format_source

MESSY = """// Two graphs

geometry graph "Smooth Mesh"(Mesh: Geometry, Level: Int) -> Geometry {
  // smooth the mesh
  return Mesh
    |> SubdivideMesh(Level)   // finer
    // then shade
    |> SetShadeSmooth()
}
// next one
geometry graph scatter(geometry: Geometry) -> Geometry {
  grid = MeshGrid(2.0,2.0, 3, 3) // a grid


  smooth = smooth_mesh(grid.mesh, 2)
  return geometry+smooth
  // end of body
} // done
"""

FORMATTED = """// Two graphs

geometry graph "Smooth Mesh"(Mesh: Geometry, Level: Int) -> Geometry {
  // smooth the mesh
  return Mesh |> SubdivideMesh(Level)  // finer
    // then shade
    |> SetShadeSmooth()
}

// next one
geometry graph scatter(geometry: Geometry) -> Geometry {
  grid = MeshGrid(2.0, 2.0, 3, 3)  // a grid

  smooth = smooth_mesh(grid.mesh, 2)
  return geometry + smooth
  // end of body
}  // done
"""


def test_format_keeps_comments_and_one_blank_line():
    assert format_source(MESSY) == FORMATTED


def test_format_is_stable():
    assert format_source(FORMATTED) == FORMATTED


def test_comment_inside_a_spread_call_stays_on_its_argument():
    long = ", ".join(f"input_{i}: {i}.0" for i in range(12))
    text = format_source(f"geometry graph g() -> Geometry {{\n  return F(a: 1.0,  // first\n {long})\n}}")
    assert "    a: 1.0,  // first\n" in text
    assert format_source(text) == text


def test_format_refuses_broken_text():
    with pytest.raises(BnError):
        format_source("geometry graph g() -> Geometry {\n  return\n")
