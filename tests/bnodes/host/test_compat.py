"""The compatibility promise of the LTS 1, run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_compat.py

Every text of tests/bnodes/compat/1.0 must build, in every 1.x, the trees it built in
1.0: same nodes, settings, values, links and interface. Each text's trees are kept as
JSON beside it. After a change that is meant to alter them (a fix, never a new syntax),
write them again, and say why in the commit:

    blender --background --factory-startup --python tests/bnodes/host/test_compat.py -- --update
"""

import json
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

from bnodes.host import build_source, export_tree  # noqa: E402
from bnodes.host.schema import snapshot  # noqa: E402
from bnodes.lang import parse  # noqa: E402
from bnodes.lang.printer import to_source  # noqa: E402

CORPUS = ROOT / "tests" / "bnodes" / "compat" / "1.0"
# The texts of the 1.0 corpus beside its own: the fixtures, the doc examples and Maths
OTHERS = sorted((ROOT / "tests" / "bnodes" / "fixtures").glob("*.bn")) + \
    sorted((ROOT / "docs" / "exemples").glob("*.bn")) + [ROOT / "src" / "maths.bn"]
UPDATE = "--update" in sys.argv

# The editor's, or Blender's bookkeeping: not what a text means
SKIP_PROPS = {"name", "label", "location", "location_absolute", "width", "height", "dimensions", "select",
              "show_options", "show_preview", "show_texture", "hide", "color", "use_custom_color", "parent",
              "active_index", "bl_idname", "bl_label", "bl_description", "bl_icon", "bl_static_type",
              "bl_width_default", "bl_width_min", "bl_width_max", "bl_height_default", "bl_height_min",
              "bl_height_max", "type", "internal_links", "rna_type", "warning_propagation", "is_active_output"}


def plain(value):
    if isinstance(value, float):
        return round(value, 5)
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    return value


def node_dump(node):
    props = {}
    for p in node.bl_rna.properties:
        if p.identifier in SKIP_PROPS or p.is_readonly or p.type not in ("BOOLEAN", "ENUM", "INT", "FLOAT", "STRING"):
            continue
        if getattr(p, "is_array", False) or p.type == "ENUM" and p.is_enum_flag:
            continue
        props[p.identifier] = plain(getattr(node, p.identifier))
    if node.bl_idname == "NodeFrame":
        props["label"] = node.label
    items = [i.name for i in getattr(node, "capture_items", getattr(node, "repeat_items", getattr(node, "enum_items", ())))]
    sockets = [s for s in node.inputs if s.type != "CUSTOM"]
    dump = {
        "type": node.bl_idname,
        "props": props,
        "items": items,
        "group": node.node_tree.name if getattr(node, "node_tree", None) else None,
        "frame": node.parent.label if node.parent else None,
        "values": [plain(snapshot(s)) if not s.is_linked and hasattr(s, "default_value") else None for s in sockets],
    }
    # Every other item collection, each item with its settings: only where there is one, so that
    # the trees kept before it (whose items are the names above) are dumped as they were
    lists = {p.identifier: [item_dump(i) for i in getattr(node, p.identifier)] for p in node.bl_rna.properties
             if p.type == "COLLECTION" and p.identifier.endswith("items") and p.identifier not in DUMPED_ITEMS
             and len(getattr(node, p.identifier))}
    if lists:
        dump["item_lists"] = lists
    return dump


# The item collections dumped by name alone under "items", as in 1.0, and those of the Index Switch,
# numbered items whose type is the node's data_type: what 1.0 kept of them, the trees keep
DUMPED_ITEMS = {"capture_items", "repeat_items", "enum_items", "index_switch_items"}


def item_dump(item):
    """An item's name, type and settings, as plain data."""
    return {p.identifier: plain(getattr(item, p.identifier)) for p in item.bl_rna.properties
            if not p.is_readonly and p.type in ("BOOLEAN", "ENUM", "INT", "FLOAT", "STRING")
            and not getattr(p, "is_array", False) and not (p.type == "ENUM" and p.is_enum_flag)}


def tree_dump(tree):
    """A tree as plain data, nodes in an order that does not depend on their names."""
    nodes = sorted(tree.nodes, key=lambda n: (n.bl_idname, n.get("bnodes_line", 0), n.name))
    index = {n.name: i for i, n in enumerate(nodes)}
    links = sorted([index[l.from_node.name], list(l.from_node.outputs).index(l.from_socket),
                    index[l.to_node.name], list(l.to_node.inputs).index(l.to_socket)] for l in tree.links)
    interface = []
    for i in tree.interface.items_tree:
        if i.item_type != "SOCKET":
            continue
        fields = {f: plain(snapshot(i) if f == "default_value" else getattr(i, f))
                  for f in ("default_value", "min_value", "max_value", "default_input", "subtype", "description",
                            "structure_type", "hide_in_modifier") if hasattr(i, f)}
        interface.append([i.in_out, i.name, i.socket_type, fields])
    return {"name": tree.name, "description": tree.description, "is_modifier": tree.is_modifier,
            "interface": interface, "nodes": [node_dump(n) for n in nodes], "links": links}


def build(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for name, color in (("Rust", (0.5, 0.2, 0.1, 1.0)), ("Courbe", (1.0, 0.5, 0.1, 1.0)),
                        ("Cadre", (0.2, 0.2, 0.2, 1.0)), ("Forme", (0.7, 0.7, 0.7, 1.0)),
                        ("Montagne", (0.3, 0.3, 0.2, 1.0))):
        bpy.data.materials.new(name).diffuse_color = color
    for module in CORPUS.glob("*.bn"):
        bpy.data.texts.new(module.name).from_string(module.read_text())
    trees = build_source(path.read_text(), path.name)
    return trees


def check(path):
    trees = build(path)
    got = [tree_dump(t) for t in trees]
    golden = path.with_suffix(".json") if path.parent == CORPUS else CORPUS / "autres" / (path.stem + ".json")
    if UPDATE or not golden.exists():
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(json.dumps(got, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        print(f"   écrit {golden.relative_to(ROOT)}")
        return
    want = json.loads(golden.read_text())
    assert len(got) == len(want), f"{path.name} : {len(got)} arbres au lieu de {len(want)}"
    for g, w in zip(got, want):
        assert g == w, f"{path.name} : « {w['name']} » ne se construit plus à l'identique"


def test_the_corpus_builds_as_in_1_0():
    for path in sorted(CORPUS.glob("*.bn")):
        check(path)


def test_the_other_texts_build_as_in_1_0():
    for path in OTHERS:
        check(path)


def test_the_corpus_reads_back_as_written():
    trees = build(CORPUS / "tout.bn")
    text = "\n".join(export_tree(t)[0] for t in trees)
    assert text == to_source(parse((CORPUS / "tout.bn").read_text())), text


def main():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


main()
