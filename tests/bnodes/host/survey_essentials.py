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
    if "porte le nom d'une entrée ou d'un réglage" in warning:
        return "item au nom d'une entrée du nœud"
    if "de l'item" in warning and "non exporté" in warning:
        return "option d'un item donné par position"
    if "(dans deux panneaux ?)" in warning:
        return "nom répété dans l'interface"
    if "désactivé (mute)" in warning:
        return "nœud désactivé"
    if "présentation non exportée" in warning:
        return "présentation (libellés, couleurs, nœuds repliés)"
    if "panneaux de l'interface" in warning:
        return "panneaux de l'interface"
    if "réglages de l'arbre" in warning:
        return "réglages de l'arbre (outil, modifier)"
    if "part sans valeur" in warning:
        return "état de zone sans valeur"
    if "qui reçoit un" in warning and "relu comme" in warning:
        return "item relu d'un autre type"
    if re.search(r"domaine \w+ de l", warning):
        return "domaine d'un item de zone"
    if "valeur de menu de" in warning:
        return "item de zone : valeur de menu"
    if "cachée par l'état" in warning or "un nom de la zone" in warning or "deux items du même nom" in warning:
        return "nom d'item de zone"
    if "ne suit aucune géométrie" in warning:
        return "attribut généré sans géométrie"
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
