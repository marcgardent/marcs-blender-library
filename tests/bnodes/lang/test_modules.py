"""Modules: `use maths (fbm) from "//lib/maths.bn"`, and the groups already in the file."""

import pytest

from lang import BnError, compile_source, parse
from lang.format import format_source
from lang.printer import to_source
from lang.schema import GroupSpec

MATHS = """\
geometry graph double(x: Float) -> Float {
  return x * 2.0
}

geometry graph quadruple(x: Float) -> Float {
  return double(double(x))
}

geometry graph moitié(x: Float) -> Float {
  return x / 2.0
}
"""

MAIN = """\
use maths

geometry graph g(geometry: Geometry) -> Geometry {
  return SetPosition(geometry, offset: CombineXYZ(z: quadruple(1.0)))
}
"""


def loader(modules):
    """A load(name, source) over {(name, source): text}, recording what it was asked."""
    asked = []

    def load(name, source):
        asked.append((name, source))
        if (name, source) not in modules:
            raise LookupError(f"pas de texte « {name}.bn »")
        return modules[(name, source)], source or f"{name}.bn"
    load.asked = asked
    return load


def errors(source, schema, load=None):
    with pytest.raises(BnError) as err:
        compile_source(source, schema, "t.bn", load)
    return [d.message for d in err.value.diagnostics]


def test_uses_print_back_sorted_at_the_head():
    src = ('use b from "//lib/b.bn"\nuse a (f, g)\n\n'
           "geometry graph g() -> Float {\n  return 1.0\n}\n")
    assert to_source(parse(src)) == ('use a (f, g)\nuse b from "//lib/b.bn"\n\n'
                                     "geometry graph g() -> Float {\n  return 1.0\n}\n")


def test_format_sorts_the_uses_and_keeps_their_comments():
    src = ("// Les fonctions\nuse maths\nuse bruits  // le fbm\n"
           "geometry graph g() -> Float {\n  return 1.0\n}\n")
    assert format_source(src) == ("// Les fonctions\nuse bruits  // le fbm\nuse maths\n\n"
                                  "geometry graph g() -> Float {\n  return 1.0\n}\n")


def test_a_long_list_takes_one_name_per_line():
    names = [f"fonction_numéro_{i}" for i in range(6)]
    src = "use maths (\n" + "".join(f"  {n},\n" for n in names) + ')\n\ngeometry graph g() -> Float {\n  return 1.0\n}\n'
    assert to_source(parse(src)) == src


def test_use_is_a_name_like_any_other_outside_the_head(schema):
    src = "geometry graph g(use: Float) -> Float {\n  from = use * 2.0\n  return from\n}\n"
    assert to_source(parse(src)) == src
    compile_source(src, schema)


def test_a_use_after_a_graph_fails():
    with pytest.raises(BnError, match="en tête du fichier"):
        parse("geometry graph g() -> Float {\n  return 1.0\n}\nuse maths\n")


def test_the_module_comes_first_marked_with_its_name(schema):
    load = loader({("maths", None): MATHS})
    graphs = compile_source(MAIN, schema, "t.bn", load)
    assert [(g.name, g.module) for g in graphs] == [
        ("double", ("maths", None)), ("quadruple", ("maths", None)), ("moitié", ("maths", None)), ("g", None)]
    assert load.asked == [("maths", None)]


def test_a_list_brings_those_graphs_and_what_they_call(schema):
    src = MAIN.replace("use maths", "use maths (quadruple)")
    graphs = compile_source(src, schema, "t.bn", loader({("maths", None): MATHS}))
    assert [g.name for g in graphs] == ["double", "quadruple", "g"]


def test_a_graph_left_out_of_the_list_is_unknown(schema):
    src = MAIN.replace("use maths", "use maths (moitié)")
    assert any("quadruple" in m and "inconnu" in m for m in errors(src, schema, loader({("maths", None): MATHS})))


def test_the_source_reaches_the_loader(schema):
    src = MAIN.replace("use maths", 'use maths from "//lib/maths.bn"')
    load = loader({("maths", "//lib/maths.bn"): MATHS})
    graphs = compile_source(src, schema, "t.bn", load)
    assert graphs[0].module == ("maths", "//lib/maths.bn")


def test_a_missing_module_points_at_its_use(schema):
    with pytest.raises(BnError) as err:
        compile_source(MAIN, schema, "t.bn", loader({}))
    (d,) = err.value.diagnostics
    assert (d.line, d.col) == (1, 1) and d.message == "module « maths » : pas de texte « maths.bn »"


def test_without_a_loader_use_fails(schema):
    assert errors(MAIN, schema) == ["use : aucun module à charger ici"]


def test_an_error_in_the_module_is_reported_at_the_use(schema):
    broken = MATHS.replace("x * 2.0", "y * 2.0")
    (message,) = errors(MAIN, schema, loader({("maths", None): broken}))
    assert message.startswith("module « maths » : maths.bn:2:10") and "y" in message


def test_a_name_both_defined_and_imported_fails(schema):
    src = MAIN + "\ngeometry graph double(x: Float) -> Float {\n  return x\n}\n"
    assert "« double » est défini ici et importé de maths" in errors(src, schema, loader({("maths", None): MATHS}))


def test_a_name_in_two_modules_fails(schema):
    src = "use maths\nuse autres\n\n" + MAIN.split("\n\n", 1)[1]
    load = loader({("maths", None): MATHS, ("autres", None): MATHS.split("\n\n")[0] + "\n"})
    assert any("« double » est dans maths et dans autres" in m for m in errors(src, schema, load))


def test_the_same_module_twice_fails(schema):
    src = "use maths\nuse maths (double)\n\n" + MAIN.split("\n\n", 1)[1]
    assert "un seul use par module" in errors(src, schema, loader({("maths", None): MATHS}))[0]


def test_modules_may_use_modules_each_loaded_once(schema):
    base = "geometry graph un() -> Float {\n  return 1.0\n}\n"
    mid = "use base\n\ngeometry graph deux() -> Float {\n  return un() + un()\n}\n"
    src = "use base\nuse mid\n\ngeometry graph g() -> Float {\n  return deux() + un()\n}\n"
    load = loader({("base", None): base, ("mid", None): mid})
    graphs = compile_source(src, schema, "t.bn", load)
    assert [(g.name, g.module and g.module[0]) for g in graphs] == [("un", "base"), ("deux", "mid"), ("g", None)]
    assert load.asked == [("base", None), ("mid", None)]


def test_a_cycle_of_modules_fails(schema):
    a = "use b\n\ngeometry graph fa() -> Float {\n  return 1.0\n}\n"
    b = "use a\n\ngeometry graph fb() -> Float {\n  return 1.0\n}\n"
    src = "use a\n\ngeometry graph g() -> Float {\n  return fa()\n}\n"
    (message,) = errors(src, schema, loader({("a", None): a, ("b", None): b}))
    assert "import circulaire : a → b → a" in message


def test_a_group_of_the_file_is_called_by_its_key(schema):
    schema.existing = {"smooth_by_angle": GroupSpec("Smooth by Angle", (("Mesh", "Geometry"), ("Angle", "Float")),
                                                    (("Mesh", "Geometry"),))}
    src = "geometry graph g(mesh: Geometry) -> Geometry {\n  return smooth_by_angle(mesh, angle: 0.5)\n}\n"
    (g,) = compile_source(src, schema)
    (node,) = [n for n in g.nodes if n.group]
    assert node.group == "Smooth by Angle" and node.bl_idname == "GeometryNodeGroup"
    assert node.values == {"Angle": 0.5}


def test_a_graph_of_the_text_wins_over_a_group_of_the_file(schema):
    schema.existing = {"double": GroupSpec("double", (("x", "Float"), ("y", "Float")), (("r", "Float"),))}
    graphs = compile_source(MATHS, schema)
    (node, _) = [n for n in graphs[1].nodes if n.group]
    assert graphs[1].name == "quadruple" and node.n_inputs == 1


def test_two_groups_with_one_key_are_ambiguous(schema):
    spec = (("x", "Float"),), (("r", "Float"),)
    schema.existing = {"ab": [GroupSpec("ab", *spec), GroupSpec("AB ", *spec)]}
    src = "geometry graph g() -> Float {\n  return ab(1.0)\n}\n"
    assert errors(src, schema) == ["« ab » désigne plusieurs groupes du fichier : ab, AB "]
