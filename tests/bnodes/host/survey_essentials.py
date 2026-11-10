"""Inventaire des node groups livrés avec Blender, relus par Nodes as Text :

    blender --background --factory-startup --python tests/bnodes/host/survey_essentials.py

Pour chaque groupe de datafiles/assets/nodes : asset ou non, nombre de nœuds, et les
avertissements de Tree → Text. Sert à docs/analyse-groupes-blender.md.
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

from bnodes.host import export_tree  # noqa: E402

SKIP = {"NodeFrame", "NodeReroute", "NodeGroupInput", "NodeGroupOutput"}


def cause(warning):
    m = re.search(r": (\w+) \(«", warning)
    if m:
        return m.group(1)
    if "coupé en deux" in warning:
        return "frame coupé"
    if "sans effet" in warning:
        return "nœuds sans effet"
    return warning


def main():
    folder = Path(bpy.utils.system_resource("DATAFILES", path="assets/nodes"))
    causes = defaultdict(set)
    nodes = Counter()
    for path in sorted(folder.glob("*.blend")):
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.node_groups = list(src.node_groups)
        groups = [g for g in dst.node_groups if g is not None]
        clean = 0
        print(f"\n{path.name}")
        for g in groups:
            kinds = Counter(n.bl_idname for n in g.nodes if n.bl_idname not in SKIP)
            nodes.update(kinds)
            _, warnings = export_tree(g)
            clean += not warnings
            for w in warnings:
                causes[cause(w)].add(g.name)
            mark = "A" if g.asset_data else "-"
            print(f"  {mark} {'ok  ' if not warnings else 'avert'} {sum(kinds.values()):4} {g.name}")
        print(f"  {len(groups)} groupes, {sum(1 for g in groups if g.asset_data)} assets, {clean} relus sans avertissement")

    print("\nCauses d'avertissement (groupes touchés)")
    for c, names in sorted(causes.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(names):3} {c}")
    print("\nNœuds les plus employés")
    for k, v in nodes.most_common(10):
        print(f"  {v:4} {k}")


main()
