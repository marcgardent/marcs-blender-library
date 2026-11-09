import pytest

from lang import BnError, compile_source, parse
from lang.colors import rgb, spell
from lang.format import format_source
from lang.printer import to_source

ROCKS = """geometry graph rocks(geometry: Geometry, t: Float) -> Geometry {
  "Noise" #orange {
    p = Position()
    "Detail" {
      d = p.z * 0.1
    }
  }
  #e73 {
    k = d + t
  }
  {
    m = k * 2.0
  }
  "Check the scale" #tomato {}
  "Output" {
    return geometry |> SetPosition(offset: CombineXYZ(z: m))
  }
}
"""


def compile_one(source, schema):
    return compile_source(source, schema, "t.bn")[-1]


def errors(source, schema):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn")
    return [d.message for d in err.value.diagnostics]


def test_frames_print_back_unchanged():
    assert to_source(parse(ROCKS)) == ROCKS


def test_title_and_color_are_optional():
    (g,) = parse(ROCKS).graphs
    heads = [(s.label, s.color) for s in g.body]
    assert heads == [("Noise", "#orange"), (None, "#e73"), (None, None), ("Check the scale", "#tomato"),
                     ("Output", None)]


def test_frames_hold_the_nodes_of_their_statements(schema):
    g = compile_one(ROCKS, schema)
    frames = {f.id: f for f in g.frames}
    assert [(f.label, f.color and spell(f.color), f.parent and frames[f.parent].label) for f in g.frames] == [
        ("Noise", "orange", None), ("Detail", None, "Noise"), (None, "ee7733", None), (None, None, None),
        ("Check the scale", "tomato", None), ("Output", None, None)]

    def label(name):
        n = next(n for n in g.nodes if n.name == name)
        return frames[n.frame].label if n.frame else None

    assert label("p") == "Noise" and label("d") == "Detail"
    output = g.node("group_output")
    assert frames[output.frame].label == "Output"
    assert g.node("group_input").frame is None
    combine = next(n for n in g.nodes if n.bl_idname == "ShaderNodeCombineXYZ")
    assert frames[combine.frame].label == "Output"


def test_names_cross_frames(schema):
    # A frame is not a scope: `d` is used after its frame closed
    compile_one(ROCKS, schema)


def test_unknown_color(schema):
    src = ROCKS.replace("#tomato", "#nope")
    assert errors(src, schema) == ["couleur « #nope » inconnue : #rrggbb, #rgb ou un nom CSS (#orange, #teal…)"]


def test_a_note_may_follow_return(schema):
    body = ROCKS.replace('  "Check the scale" #tomato {}\n', "")
    compile_one(body.replace("  }\n}\n", '  }\n  "Done" {}\n}\n'), schema)
    late = body.replace("  }\n}\n", '  }\n  "Late" {\n    x = 1.0\n  }\n}\n')
    assert errors(late, schema) == ["instruction après return"]


def test_a_title_needs_quotes():
    with pytest.raises(BnError) as err:
        parse("geometry graph g() -> Geometry {\n  Noise {\n  }\n}")
    assert "frame" in err.value.diagnostics[0].message


@pytest.mark.parametrize("text, expected", [("orange", (1.0, 165 / 255, 0.0)), ("ORANGE", (1.0, 165 / 255, 0.0)),
                                            ("fff", (1.0, 1.0, 1.0)), ("e07030", (224 / 255, 112 / 255, 48 / 255)),
                                            ("nope", None), ("ffff", None)])
def test_colors(text, expected):
    assert rgb(text) == expected


def test_format_indents_frames():
    messy = 'geometry graph g(geometry: Geometry) -> Geometry {\n"A" #teal { x = 1.0 }\n  return geometry\n}\n'
    assert format_source(messy) == ('geometry graph g(geometry: Geometry) -> Geometry {\n  "A" #teal {\n'
                                    '    x = 1.0\n  }\n  return geometry\n}\n')
