"""Construit l'asset « Maths » de Marc's Blender Library.

Une boîte à outils de fonctions mathématiques pour Geometry Nodes, écrite en texte
dans src/maths.bn et construite par l'extension Nodes as Text (addons/bnodes) :
courbes de réglage, ondes, vecteurs, angles, champs de distance signée et hasard.

    blender -b --factory-startup --python src/maths.py

Écrit assets/geometry_nodes/maths.blend, previews/maths.png et les images de
docs/maths.md. Chaque courbe, onde, SDF ou tirage reçoit une vignette tracée à
partir des valeurs que Blender calcule avec le groupe lui-même.
"""
import math
import os
import re
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "addons"))

from bnodes.host import build_source  # noqa: E402
from bnodes.lang import parse  # noqa: E402

SRC = os.path.join(ROOT, "src", "maths.bn")
DEMO = os.path.join(ROOT, "src", "maths_demo.bn")
BLEND_PATH = os.path.join(ROOT, "assets", "geometry_nodes", "maths.blend")
PREVIEW_PATH = os.path.join(ROOT, "previews", "maths.png")
IMAGES = os.path.join(ROOT, "docs", "images")

# « Geometry Nodes/Maths/… » dans blender_assets.cats.txt, par section de maths.bn.
CATALOGS = {
    "Courbes": "a6b2424f-9ae9-43da-a399-ec3210a866c5",
    "Ondes": "f3de963a-6f99-4f8d-bd4f-a49adb7c5e79",
    "Vecteurs": "391bddc9-8b92-4969-ba9e-ce961a8c3f5f",
    "Angles": "92950255-dbd3-4b12-9454-b78123f90546",
    "Champs": "35939de3-539a-476b-9ebc-25c8d8a7df10",
    "Hasard": "d7443a2b-2977-41a1-9689-e55f78125685",
}

TAGS = {
    "Courbes": ("courbe", "easing", "falloff", "maths"),
    "Ondes": ("onde", "wave", "périodique", "maths"),
    "Vecteurs": ("vecteur", "vector", "maths"),
    "Angles": ("angle", "radians", "maths"),
    "Champs": ("sdf", "distance", "volume", "maths"),
    "Hasard": ("random", "hasard", "maths"),
}

# Valeurs par défaut des entrées (le texte ne les écrit pas encore) : valeur, ou
# (valeur, min, max). Une entrée p prend la position, une entrée id l'index.
DEFAULTS = {
    "biais": {"force": (0.25, 0.001, 0.999)},
    "gain": {"contraste": (0.25, 0.001, 0.999)},
    "accélère": {"puissance": (2.0, 0.0, None)},
    "freine": {"puissance": (2.0, 0.0, None)},
    "accélère freine": {"puissance": (2.0, 0.0, None)},
    "impulsion": {"raideur": 4.0},
    "bosse": {"centre": 0.5, "demi largeur": (0.25, 0.0001, None)},
    "parabole": {"finesse": (1.0, 0.0, None)},
    "marches": {"montée": (0.25, 0.0001, 1.0)},
    "créneau": {"cycle": (0.5, 0.0, 1.0)},
    "sur le plan": {"normale": (0.0, 0.0, 1.0)},
    "angle signé": {"axe": (0.0, 0.0, 1.0)},
    "proche sur segment": {"b": (0.0, 0.0, 1.0)},
    "sdf sphère": {"rayon": 1.0},
    "sdf boîte": {"demi taille": (1.0, 1.0, 1.0)},
    "sdf tore": {"grand rayon": 1.0, "petit rayon": 0.25},
    "sdf cylindre": {"rayon": 1.0, "demi hauteur": 1.0},
    "sdf capsule": {"b": (0.0, 0.0, 1.0), "rayon": 0.25},
    "soustraction douce": {"douceur": (0.1, 0.0, None)},
    "coque": {"épaisseur": (0.1, 0.0, None)},
    "répétition": {"cellule": (1.0, 1.0, 1.0)},
}
IMPLICIT = {"p": "POSITION", "id": "ID_OR_INDEX"}

# Ce que trace la vignette de chaque groupe : (formule en x de 0 à 1, échelle de y)
CURVES = {
    "biais": ("biais(x, 0.25)", 1.0),
    "gain": ("gain(x, 0.25)", 1.0),
    "accélère": ("accélère(x, 3.0)", 1.0),
    "freine": ("freine(x, 3.0)", 1.0),
    "accélère freine": ("accélère_freine(x, 3.0)", 1.0),
    "impulsion": ("impulsion(x, 6.0)", 1.0),
    "bosse": ("bosse(x, 0.5, 0.3)", 1.0),
    "parabole": ("parabole(x, 2.0)", 1.0),
    "marches": ("marches(x * 4.0, 0.3)", 4.0),
    "triangle": ("triangle(x * 2.0)", 1.0),
    "créneau": ("créneau(x * 2.0, 0.3)", 1.0),
    "sinus01": ("sinus01(x * 2.0)", 1.0),
}
# Coupe y = 0 des SDF, sur [-1.4, 1.4]²
FIELDS = {
    "sdf sphère": "sdf_sphère(p, 1.0)",
    "sdf boîte": "sdf_boîte(p, (0.9, 0.6, 0.6))",
    "sdf tore": "sdf_tore(p, 0.8, 0.3)",
    "sdf cylindre": "sdf_cylindre(p, 0.7, 0.9)",
    "sdf capsule": "sdf_capsule(p, (-0.7, 0.0, -0.5), (0.7, 0.0, 0.5), 0.35)",
    "soustraction douce": "soustraction_douce(sdf_boîte(p, (0.8, 0.8, 0.8)), sdf_sphère(p - (0.5, 0.0, 0.5), 0.8), 0.2)",
    "coque": "coque(sdf_sphère(p, 0.9), 0.2)",
    "répétition": "sdf_sphère(répétition(p, 0.7), 0.25)",
}
SCATTERS = {
    "direction aléatoire": "direction_aléatoire(i, 3)",
    "point dans disque": "point_dans_disque(i, 3)",
}

ORANGE = (0.88, 0.44, 0.19)
BLEU = (0.27, 0.51, 0.71)


# ---------------------------------------------------------------------------
# Construction depuis le texte
# ---------------------------------------------------------------------------

def sections(source):
    """Nom de chaque graph -> (section, description) : le titre « // ---- … ---- »
    qui le précède et les commentaires collés au-dessus de lui."""
    lines = source.splitlines()
    out = {}
    for g in parse(source).graphs:
        k = g.line - 2
        comment = []
        while k >= 0 and lines[k].startswith("//"):
            comment.insert(0, lines[k][2:].strip())
            k -= 1
        title = next(re.match(r"// ---- (\w+)", lines[j]) for j in range(g.line - 1, -1, -1)
                     if lines[j].startswith("// ----"))
        out[g.name] = (title.group(1), " ".join(comment))
    return out


def set_defaults(ng, values):
    for item in ng.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT":
            continue
        if item.name in IMPLICIT:
            item.default_input = IMPLICIT[item.name]
            item.hide_value = True
        v = values.get(item.name)
        if v is None:
            continue
        if isinstance(v, tuple) and len(v) == 3 and item.socket_type != "NodeSocketVector":
            v, lo, hi = v
            if lo is not None:
                item.min_value = lo
            if hi is not None:
                item.max_value = hi
        item.default_value = v


def mark_assets(trees, info):
    for ng in trees:
        section, description = info[ng.name]
        ng.description = description
        set_defaults(ng, DEFAULTS.get(ng.name, {}))
        ng.asset_mark()
        data = ng.asset_data
        data.catalog_id = CATALOGS[section]
        data.author = "Marc Gardent"
        data.description = description
        for tag in TAGS[section]:
            data.tags.new(tag, skip_if_exists=True)


# ---------------------------------------------------------------------------
# Valeurs calculées par Blender
# ---------------------------------------------------------------------------

def probe(name, mesh, stores, vector=False):
    """Évalue des formules sur les points de `mesh` (du texte) : {nom: valeurs}."""
    data = "FLOAT_VECTOR" if vector else "FLOAT"
    chain = "\n    |> ".join(f'StoreNamedAttribute(name: "a{k}", value: {e}, data_type: {data})'
                              for k, e in enumerate(stores.values()))
    text = (f"geometry graph sonde_{name}() -> Geometry {{\n  i = Index()\n  x = i / 511.0\n"
            f"  p = CombineXYZ(Position().x, 0.0, Position().y)\n  return {mesh}\n    |> {chain}\n}}\n")
    (tree,) = [t for t in build_source(text_all() + text, "sonde.bn") if t.name == f"sonde_{name}"]
    obj = bpy.data.objects.new("sonde", bpy.data.meshes.new("sonde"))
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new("sonde", "NODES").node_group = tree
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    co = [tuple(v.co) for v in ev.vertices]
    out = {}
    for k, key in enumerate(stores):
        attr = ev.attributes[f"a{k}"].data
        out[key] = [tuple(d.vector) for d in attr] if vector else [d.value for d in attr]
    bpy.data.objects.remove(obj)
    bpy.data.node_groups.remove(tree)
    return co, out


def text_all():
    with open(SRC) as f:
        return f.read() + "\n"


# ---------------------------------------------------------------------------
# Vignettes tracées en Python, pixel par pixel
# ---------------------------------------------------------------------------

SIZE = 256


class Canvas:
    def __init__(self):
        self.px = [0.0] * (SIZE * SIZE * 4)

    def blend(self, x, y, color, alpha):
        if 0 <= x < SIZE and 0 <= y < SIZE and alpha > 0:
            i = (y * SIZE + x) * 4
            a = self.px[i + 3]
            out = alpha + a * (1 - alpha)
            for c in range(3):
                self.px[i + c] = (color[c] * alpha + self.px[i + c] * a * (1 - alpha)) / out
            self.px[i + 3] = out

    def dot(self, cx, cy, r, color):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                d = math.hypot(x - cx, y - cy)
                self.blend(x, y, color, min(1.0, max(0.0, r + 0.5 - d)))

    def frame(self, lo, hi, color=(0.5, 0.5, 0.5)):
        for t in range(lo, hi + 1):
            for x, y in ((t, lo), (t, hi), (lo, t), (hi, t)):
                self.blend(x, y, color, 0.6)

    def save(self, ng=None, path=None):
        if ng is not None:
            preview = ng.preview_ensure()
            preview.image_size = (SIZE, SIZE)
            preview.image_pixels_float = self.px
        if path:
            img = bpy.data.images.new("vignette", SIZE, SIZE, alpha=True)
            img.pixels = self.px
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            bpy.data.images.remove(img)


def curve_previews():
    _, values = probe("courbes", "MeshLine(512)", {n: e for n, (e, _) in CURVES.items()})
    for name, (_, scale) in CURVES.items():
        c = Canvas()
        lo, hi = 28, SIZE - 28
        c.frame(lo, hi)
        ys = values[name]
        for k, y in enumerate(ys):
            # Un saut (créneau, marches) est relié par des points intermédiaires
            prev = ys[k - 1] if k else y
            steps = max(1, int(abs(y - prev) / scale * (hi - lo) / 2))
            for s in range(steps):
                v = prev + (y - prev) * (s + 1) / steps
                c.dot(lo + k / 511 * (hi - lo), lo + v / scale * (hi - lo), 3.0, ORANGE)
        c.save(bpy.data.node_groups[name])


def field_color(d):
    """La palette d'Inigo Quilez : orange dehors, bleu dedans, des bandes tous les 0.1."""
    base = (0.9, 0.6, 0.3) if d > 0 else (0.4, 0.7, 0.9)
    k = (1.0 - math.exp(-4.0 * abs(d))) * (0.8 + 0.2 * math.cos(math.pi * 20.0 * d))
    col = [b * k for b in base]
    edge = max(0.0, 1.0 - abs(d) / 0.015)
    return [c + (1.0 - c) * edge for c in col]


def field_previews():
    co, values = probe("champs", f"MeshGrid(2.8, 2.8, {SIZE}, {SIZE})", FIELDS)
    for name in FIELDS:
        c = Canvas()
        for (x, y, _), d in zip(co, values[name]):
            px = round((x + 1.4) / 2.8 * (SIZE - 1))
            py = round((y + 1.4) / 2.8 * (SIZE - 1))
            c.blend(px, py, field_color(d), 1.0)
        c.save(bpy.data.node_groups[name])


def scatter_previews():
    _, values = probe("hasard", "MeshLine(600)", SCATTERS, vector=True)
    for name in SCATTERS:
        c = Canvas()
        half = (SIZE - 56) / 2
        c.frame(28, SIZE - 28)
        for x, y, z in values[name]:
            # Les directions vues de côté : x et z
            v = z if name == "direction aléatoire" else y
            c.dot(SIZE / 2 + x * half, SIZE / 2 + v * half, 2.0, BLEU)
        c.save(bpy.data.node_groups[name])


# ---------------------------------------------------------------------------
# Démos et images de la documentation
# ---------------------------------------------------------------------------

def material(name, color, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def label(text, location, size=0.16, collection=None):
    data = bpy.data.curves.new(text, "FONT")
    data.body = text
    data.size = size
    data.align_x = "CENTER"
    obj = bpy.data.objects.new(f"Étiquette {text}", data)
    obj.location = location
    obj.data.materials.append(bpy.data.materials["Cadre"])
    (collection or bpy.context.scene.collection).objects.link(obj)
    return obj


def demo_object(name, group, collection):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    collection.objects.link(obj)
    obj.modifiers.new(group, "NODES").node_group = bpy.data.node_groups[group]
    return obj


def camera(location, rotation, ortho=None, lens=50):
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = location
    cam.rotation_euler = rotation
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    cam.data.lens = lens
    return cam


def render(cam, path, size, visible, engine="BLENDER_EEVEE"):
    scene = bpy.context.scene
    for coll in bpy.data.collections:
        coll.hide_render = coll is not visible
    scene.camera = cam
    scene.render.engine = engine
    # Workbench, pour les courbes : des aplats aux couleurs des matériaux
    scene.display.shading.light = "FLAT"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def build_demos():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("Fond")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.3, 0.3, 1.0)
    world.color = (0.9, 0.9, 0.88)
    scene.world = world

    courbes = bpy.data.collections.new("Démo Courbes")
    sdf = bpy.data.collections.new("Démo SDF")
    for coll in (courbes, sdf):
        scene.collection.children.link(coll)

    demo_object("Démo Courbes", "démo courbes", courbes)
    names = [["biais", "gain", "accélère", "freine"],
             ["accélère freine", "impulsion", "bosse", "parabole"],
             ["marches", "triangle", "créneau", "sinus01"]]
    for r, row in enumerate(names):
        for col, name in enumerate(row):
            label(name, (col * 1.4 + 0.5, -r * 1.6 - 0.25, 0.0), collection=courbes)

    obj = demo_object("Démo SDF", "démo sdf", sdf)
    obj.data.materials.append(bpy.data.materials["Forme"])
    obj.modifiers.new("Matériau", "NODES").node_group = set_material_group()
    sun = bpy.data.objects.new("Soleil", bpy.data.lights.new("Soleil", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (0.7, 0.2, 0.9)
    scene.collection.objects.link(sun)
    cam_courbes = camera((2.65, -1.25, 10.0), (0, 0, 0), ortho=6.0)
    cam_sdf = camera((4.2, -13.0, 11.0), (math.radians(47), 0, 0), lens=40)
    return (cam_courbes, courbes), (cam_sdf, sdf)


def set_material_group():
    text = 'geometry graph "matériau forme"(g: Geometry) -> Geometry {\n  return SetMaterial(g, material: "Forme")\n}\n'
    (tree,) = build_source(text, "matériau.bn")
    return tree


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = text_all()
    with open(DEMO) as f:
        demo = f.read()
    info = sections(source)
    # Les démos nomment ces matériaux
    material("Courbe", (*ORANGE, 1.0))
    material("Cadre", (0.25, 0.25, 0.27, 1.0))
    material("Forme", (0.75, 0.72, 0.68, 1.0), roughness=0.35)
    trees = build_source(source, "maths.bn")
    build_source(source + demo, "maths_demo.bn")
    mark_assets(trees, info)
    curve_previews()
    field_previews()
    scatter_previews()

    (cam_c, courbes), (cam_s, sdf) = build_demos()
    os.makedirs(IMAGES, exist_ok=True)
    render(cam_c, os.path.join(IMAGES, "maths-courbes.png"), (1100, 900), courbes, "BLENDER_WORKBENCH")
    render(cam_s, os.path.join(IMAGES, "maths-sdf.png"), (1400, 800), sdf)
    render(cam_s, PREVIEW_PATH, (700, 400), sdf)
    for coll in bpy.data.collections:
        coll.hide_render = False

    # Le texte voyage avec le fichier : Ctrl+Entrée le reconstruit avec l'extension
    for name, text in (("maths.bn", source), ("maths_demo.bn", demo)):
        bpy.data.texts.new(name).write(text)

    os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Asset ecrit :", BLEND_PATH)


main()
