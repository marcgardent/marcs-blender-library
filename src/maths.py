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

import bnodes  # noqa: E402
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
    "Couleurs": "85199657-c026-4a23-9b92-0a73c02aef8a",
    "Échantillonnage": "25d9369e-ae19-4a8e-bd0d-65df2d70d488",
    "Bruits": "a19651d8-4add-4a92-a14f-95d39a01df4c",
}

TAGS = {
    "Courbes": ("courbe", "easing", "falloff", "maths"),
    "Ondes": ("onde", "wave", "périodique", "maths"),
    "Vecteurs": ("vecteur", "vector", "maths"),
    "Angles": ("angle", "radians", "maths"),
    "Champs": ("sdf", "distance", "volume", "maths"),
    "Hasard": ("random", "hasard", "maths"),
    "Couleurs": ("couleur", "palette", "maths"),
    "Échantillonnage": ("points", "sampling", "répartition", "maths"),
    "Bruits": ("bruit", "noise", "fbm", "fractal", "maths"),
}

# Ce que trace la vignette de chaque groupe : (formule en x de 0 à 1, y en bas, y en haut)
CURVES = {
    "biais": ("biais(x, 0.25)", 0.0, 1.0),
    "gain": ("gain(x, 0.25)", 0.0, 1.0),
    "accélère": ("accélère(x, 3.0)", 0.0, 1.0),
    "freine": ("freine(x, 3.0)", 0.0, 1.0),
    "accélère freine": ("accélère_freine(x, 3.0)", 0.0, 1.0),
    "rebond": ("rebond(x)", 0.0, 1.0),
    "élastique": ("élastique(x)", -0.1, 1.4),
    "recul": ("recul(x)", -0.2, 1.0),
    "impulsion": ("impulsion(x, 6.0)", 0.0, 1.0),
    "bosse": ("bosse(x, 0.5, 0.3)", 0.0, 1.0),
    "parabole": ("parabole(x, 2.0)", 0.0, 1.0),
    "marches": ("marches(x * 4.0, 0.3)", 0.0, 4.0),
    "triangle": ("triangle(x * 2.0)", 0.0, 1.0),
    "créneau": ("créneau(x * 2.0, 0.3)", 0.0, 1.0),
    "sinus01": ("sinus01(x * 2.0)", 0.0, 1.0),
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
    "sdf cône": "sdf_cône(p, 1.0, 0.9, 0.2)",
    "sdf ellipsoïde": "sdf_ellipsoïde(p, (1.2, 0.7, 0.6))",
    "sdf octaèdre": "sdf_octaèdre(p, 1.2)",
    # Les SDF du plan XY : la coupe passe dans leur plan
    "sdf cercle": "sdf_cercle(CombineXYZ(p.x, p.z), 1.0)",
    "sdf rectangle": "sdf_rectangle(CombineXYZ(p.x, p.z), (1.0, 0.5))",
    "torsion": "sdf_boîte(torsion(p, 1.2), (0.9, 0.3, 1.2))",
    "courbure": "sdf_boîte(courbure(p, 0.8), (1.2, 0.3, 0.25))",
}
# Bruits, sur le même carré : (formule, valeur noire, valeur blanche)
NOISES = {
    "fbm": ("fbm(p * 2.0)", -0.6, 0.6),
    "fbm crêtes": ("fbm_crêtes(p * 2.0)", 0.2, 0.9),
}
# Tirages : (formule, nombre de points, ce que montre la vignette de chaque point (x, y, z))
SCATTERS = {
    "direction aléatoire": ("direction_aléatoire(i, 3)", 600, lambda x, y, z: (x, z)),
    "point dans disque": ("point_dans_disque(i, 3)", 600, lambda x, y, z: (x, y)),
    # Vue de dessus de l'hémisphère nord : la spirale
    "point fibonacci": ("point_fibonacci(i, 800)", 800, lambda x, y, z: (x, y) if z > 0 else None),
    "suite r2": ("suite_r2(i)", 400, lambda x, y, z: (x * 2.0 - 1.0, y * 2.0 - 1.0)),
}

ORANGE = (0.88, 0.44, 0.19)
BLEU = (0.27, 0.51, 0.71)


# ---------------------------------------------------------------------------
# Construction depuis le texte
# ---------------------------------------------------------------------------

def sections(source):
    """Nom de chaque graph -> (section, description) : le titre « // ---- … ---- »
    qui le précède et la chaîne en tête de son corps."""
    lines = source.splitlines()
    out = {}
    for g in parse(source).graphs:
        title = next(re.match(r"// ---- (\w+)", lines[j]) for j in range(g.line - 1, -1, -1)
                     if lines[j].startswith("// ----"))
        out[g.name] = (title.group(1), g.description or "")
    return out


def mark_assets(trees, info):
    for ng in trees:
        section, description = info[ng.name]
        ng.description = description
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
    (tree,) = build_source("use maths\n\n" + text, "sonde.bn")
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
    _, values = probe("courbes", "MeshLine(512)", {n: e for n, (e, _, _) in CURVES.items()})
    for name, (_, bottom, top) in CURVES.items():
        scale = top - bottom
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
                c.dot(lo + k / 511 * (hi - lo), lo + (v - bottom) / scale * (hi - lo), 3.0, ORANGE)
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


def noise_previews():
    co, values = probe("bruits", f"MeshGrid(2.8, 2.8, {SIZE}, {SIZE})", {n: e for n, (e, _, _) in NOISES.items()})
    for name, (_, black, white) in NOISES.items():
        c = Canvas()
        for (x, y, _), v in zip(co, values[name]):
            g = min(1.0, max(0.0, (v - black) / (white - black)))
            px = round((x + 1.4) / 2.8 * (SIZE - 1))
            py = round((y + 1.4) / 2.8 * (SIZE - 1))
            c.blend(px, py, (g, g * 0.95, g * 0.88), 1.0)
        c.save(bpy.data.node_groups[name])


def scatter_previews():
    for name, (formula, count, view) in SCATTERS.items():
        _, values = probe("tirage", f"MeshLine({count})", {name: formula}, vector=True)
        c = Canvas()
        half = (SIZE - 56) / 2
        c.frame(28, SIZE - 28)
        for point in values[name]:
            seen = view(*point)
            if seen is not None:
                c.dot(SIZE / 2 + seen[0] * half, SIZE / 2 + seen[1] * half, 2.0, BLEU)
        c.save(bpy.data.node_groups[name])


def palette_preview():
    """La palette par défaut, de t = 0 à gauche à t = 1 à droite."""
    _, values = probe("palette", "MeshLine(512)", {"palette": "palette(x)"}, vector=True)
    c = Canvas()
    for px in range(28, SIZE - 28):
        col = values["palette"][round((px - 28) / (SIZE - 57) * 511)]
        for py in range(28, SIZE - 28):
            c.blend(px, py, col, 1.0)
    c.save(bpy.data.node_groups["palette"])


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
    bruits = bpy.data.collections.new("Démo Bruits")
    for coll in (courbes, sdf, bruits):
        scene.collection.children.link(coll)

    demo_object("Démo Courbes", "démo courbes", courbes)
    names = [["biais", "gain", "accélère", "freine"],
             ["accélère freine", "impulsion", "bosse", "parabole"],
             ["rebond", "élastique", "recul", "marches"],
             ["triangle", "créneau", "sinus01"]]
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
    # Les montagnes à l'écart des formes, pour qui ouvre le fichier
    montagnes = demo_object("Démo Bruits", "démo bruits", bruits)
    montagnes.location = (4.0, 14.0, 0.0)
    cam_courbes = camera((2.6, -2.05, 10.0), (0, 0, 0), ortho=6.6)
    cam_sdf = camera((4.2, -17.5, 13.5), (math.radians(45), 0, 0), lens=46)
    cam_bruits = camera((4.0, 3.0, 7.5), (math.radians(55), 0, 0), lens=30)
    return (cam_courbes, courbes), (cam_sdf, sdf), (cam_bruits, bruits)


def set_material_group():
    text = 'geometry graph "matériau forme"(g: Geometry) -> Geometry {\n  return SetMaterial(g, material: "Forme")\n}\n'
    (tree,) = build_source(text, "matériau.bn")
    return tree


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Enregistrée, l'extension relie chaque groupe à son texte : il le suit quand on l'ajoute ailleurs
    bnodes.register()
    source = text_all()
    with open(DEMO) as f:
        demo = f.read()
    info = sections(source)
    # Le texte voyage avec le fichier : Ctrl+Entrée le reconstruit avec l'extension.
    # La démo et les sondes y prennent les fonctions par « use maths ».
    for name, text in (("maths.bn", source), ("maths_demo.bn", demo)):
        bpy.data.texts.new(name).write(text)
    # Les démos nomment ces matériaux
    material("Courbe", (*ORANGE, 1.0))
    material("Cadre", (0.25, 0.25, 0.27, 1.0))
    material("Forme", (0.75, 0.72, 0.68, 1.0), roughness=0.35)
    material("Montagne", (0.32, 0.29, 0.25, 1.0), roughness=0.8)
    build_source(demo, "maths_demo.bn")
    mark_assets([bpy.data.node_groups[name] for name in info], info)
    curve_previews()
    field_previews()
    scatter_previews()
    palette_preview()
    noise_previews()

    (cam_c, courbes), (cam_s, sdf), (cam_b, bruits) = build_demos()
    os.makedirs(IMAGES, exist_ok=True)
    render(cam_c, os.path.join(IMAGES, "maths-courbes.png"), (1100, 1150), courbes, "BLENDER_WORKBENCH")
    render(cam_s, os.path.join(IMAGES, "maths-sdf.png"), (1400, 1050), sdf)
    render(cam_s, PREVIEW_PATH, (700, 525), sdf)
    render(cam_b, os.path.join(IMAGES, "maths-bruits.png"), (1400, 700), bruits)
    for coll in bpy.data.collections:
        coll.hide_render = False

    os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Asset ecrit :", BLEND_PATH)


main()
