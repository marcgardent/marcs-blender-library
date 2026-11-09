import pytest

from lang.complete import complete, product_sign

from fake_schema import MATH_OPS

HEAD = "geometry graph f(geometry: Geometry, t: Float, v: Vector) -> Geometry {\n"


def at_end(source, schema):
    """Suggestions with the cursor at the end of the source."""
    lines = source.split("\n")
    return complete(source, len(lines), len(lines[-1]) + 1, schema)


def labels(source, schema):
    return [i.label for i in at_end(source, schema)[1]]


def test_inputs_of_the_call_come_first(schema):
    got = labels(HEAD + "  return SetPosition(", schema)
    assert got[:4] == ["geometry", "selection", "position", "offset"], got
    assert "t" in got and "Position" in got  # positional values follow


def test_input_inserts_a_named_argument(schema):
    start, items = at_end(HEAD + "  return SetPosition(geometry, off", schema)
    assert (items[0].label, items[0].insert) == ("offset", "offset: ")
    assert start == len("  return SetPosition(geometry, ") + 1


def test_given_arguments_are_not_suggested_again(schema):
    got = labels(HEAD + "  return SetPosition(geometry, offset: v, ", schema)
    assert "offset" not in got and "selection" in got


def test_enum_values_after_the_prop(schema):
    assert labels(HEAD + "  x = Math(operation: ", schema) == list(MATH_OPS)
    assert labels(HEAD + "  x = Math(operation: SI", schema)[0] == "SINE"


def test_repeated_inputs_are_named_by_identifier(schema):
    got = labels(HEAD + "  x = Math(1.0, ", schema)
    assert got[:2] == ["Value", "Value_001"], got


def test_props_change_the_inputs(schema):
    got = labels(HEAD + "  x = VectorMath(operation: SCALE, ", schema)
    assert got[:2] == ["vector", "scale"], got


def test_outputs_of_a_bound_node(schema):
    src = HEAD + "  grid = MeshGrid(2.0, 2.0, 3, 3)\n  return grid."
    assert labels(src, schema) == ["mesh", "uv_map"]


def test_vector_output_also_has_components(schema):
    src = HEAD + "  p = Position()\n  h = p."
    assert labels(src, schema) == ["position", "x", "y", "z"]
    assert labels(HEAD + "  h = v.", schema) == ["x", "y", "z"]


def test_outputs_after_a_call(schema):
    assert labels(HEAD + "  return MeshGrid(1.0, 1.0, 2, 2).m", schema)[0] == "mesh"


def test_names_in_the_body(schema):
    src = HEAD + "  p = Position()\n  "
    got = labels(src, schema)
    assert got[:4] == ["p", "geometry", "t", "v"], got
    assert "return" in got and "sin" in got and "SetPosition" in got
    start, items = at_end(src + "Set", schema)
    assert [i.insert for i in items] == ["SetPosition(", "SetShadeSmooth("]
    assert start == 3


def test_initials(schema):
    assert labels(HEAD + "  x = SP", schema)[0] == "SetPosition"


def test_pipe_takes_calls_only(schema):
    got = labels(HEAD + "  return geometry\n    |> ", schema)
    assert "geometry" not in got and "SetPosition" in got


def test_calls_to_graphs_of_the_file(schema, fixture_text):
    src = fixture_text("round_trip.bn")
    cut = src.index("smooth_mesh(") + len("smooth_mesh(")
    lines = src[:cut].split("\n")
    _, items = complete(src, len(lines), len(lines[-1]) + 1, schema)
    assert [i.label for i in items[:2]] == ["mesh", "level"]
    assert "smooth_mesh" not in [i.label for i in at_end(src[:src.index("|>")], schema)[1]]


def test_types_in_the_header(schema):
    assert labels("geometry graph f(a: Fl", schema) == ["Float"]
    assert "Geometry" in labels("geometry graph f(a: Float) -> ", schema)
    assert labels("geometry graph f(a", schema) == []


def test_top_level(schema):
    assert labels("geo", schema) == ["geometry"]
    assert labels("geometry ", schema) == ["graph"]
    assert labels(HEAD + "}\n", schema)[:1] == ["geometry"]


def test_nothing_in_strings_comments_or_after_a_value(schema):
    assert labels(HEAD + '  x = SetMaterial(geometry, material: "Ru', schema) == []
    assert labels(HEAD + "  // Set", schema) == []
    assert labels(HEAD + "  x = t ", schema) == []
    assert labels(HEAD + "  x = 1", schema) == []


def test_values_after_a_comparison(schema):
    assert labels(HEAD + "  x = t >= ", schema)[:3] == ["geometry", "t", "v"]


def test_colors_after_a_hash(schema):
    start, items = at_end(HEAD + '  "Noise" #tom', schema)
    assert items[0].label == "tomato" and items[0].insert == "tomato" and items[0].detail == "#ff6347"
    assert start == len('  "Noise" #') + 1


def test_names_from_a_frame_are_seen_after_it(schema):
    got = labels(HEAD + '  "Noise" #orange {\n    p = Position()\n  }\n  "Relief" {\n    ', schema)
    assert "p" in got and "return" in got


@pytest.mark.parametrize("typed, expected", [
    ("  a = n dot ", (8, 11, "⋅")), ("  a = (n + u) cross ", (14, 19, "×")), ('  a = "x" dot ', (10, 13, "⋅")),
    ("  a = dot ", None), ("  a = n dot", None), ("  // n dot ", None), ("  a = n.dotx ", None),
    ("  return dot ", None),
])
def test_product_words_swap_after_an_operand(typed, expected):
    assert product_sign(typed) == expected
