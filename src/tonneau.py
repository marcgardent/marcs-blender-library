"""Construit les assets « Tonneau » de Marc's Blender Library.

Geometry Nodes pour faire un tonneau à partir de douelles (planches verticales) :
bombé au milieu, deux cerclages, deux fonds en planches. Les étapes sont des
groupes réutilisables seuls (centre du mesh, boîte normalisée [-1, 1], profil en
cloche, poussée radiale, choix d'axe…).

    blender -b --factory-startup --python src/tonneau.py

Écrit assets/geometry_nodes/tonneau.blend et previews/tonneau.png.
"""
import math
import os

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(ROOT, "assets", "geometry_nodes", "tonneau.blend")
PREVIEW_PATH = os.path.join(ROOT, "previews", "tonneau.png")

# « Geometry Nodes/Tonneau » et « Geometry Nodes/Outils » dans blender_assets.cats.txt.
CATALOG_TONNEAU = "0a669493-bbbc-40e6-9719-535bc39cb630"
CATALOG_OUTILS = "43e4e1b4-c635-46b6-8440-7ae3963a39b6"

GEO, VEC, FLT, INT = "NodeSocketGeometry", "NodeSocketVector", "NodeSocketFloat", "NodeSocketInt"
MENU, MAT = "NodeSocketMenu", "NodeSocketMaterial"

# Couleurs des frames, par rôle.
MESURE = (0.20, 0.32, 0.45)
PROFIL = (0.40, 0.30, 0.18)
DEFORM = (0.22, 0.38, 0.22)
AXE = (0.35, 0.22, 0.40)
METAL = (0.30, 0.30, 0.33)
BOIS = (0.45, 0.33, 0.22)


# ---------------------------------------------------------------------------
# Outils de construction
# ---------------------------------------------------------------------------

class Tree:
    """Petit assistant pour poser des nœuds, des frames et des liens."""

    def __init__(self, name, description, modifier=False):
        self.ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
        self.ng.description = description
        self.ng.is_modifier = modifier

    def socket(self, name, socket_type, tip, default=None, out=False, panel=None,
               lo=None, hi=None, subtype=None):
        s = self.ng.interface.new_socket(
            name, description=tip, in_out="OUTPUT" if out else "INPUT",
            socket_type=socket_type, parent=panel)
        if subtype: s.subtype = subtype
        if default is not None: s.default_value = default
        if lo is not None: s.min_value = lo
        if hi is not None: s.max_value = hi
        return s

    def panel(self, name):
        return self.ng.interface.new_panel(name)

    def frame(self, label, color):
        f = self.ng.nodes.new("NodeFrame")
        f.label = label
        f.use_custom_color = True
        f.color = color
        f.label_size = 16
        f.shrink = True
        return f

    def node(self, bl_idname, x, y, label=None, parent=None, **props):
        n = self.ng.nodes.new(bl_idname)
        if label: n.label = label
        for k, v in props.items(): setattr(n, k, v)
        if parent: n.parent = parent
        n.location_absolute = (x, y)
        return n

    def math(self, op, x, y, label, parent=None, b=None):
        n = self.node("ShaderNodeMath", x, y, label, parent, operation=op)
        if b is not None: n.inputs[1].default_value = b
        return n

    def vmath(self, op, x, y, label, parent=None):
        return self.node("ShaderNodeVectorMath", x, y, label, parent, operation=op)

    def group(self, name, x, y, parent=None):
        return self.node("GeometryNodeGroup", x, y, None, parent, node_tree=bpy.data.node_groups[name])

    def io(self, x_in, x_out, y=0):
        return self.node("NodeGroupInput", x_in, y), self.node("NodeGroupOutput", x_out, y)

    def link(self, a, b):
        self.ng.links.new(a, b)


# ---------------------------------------------------------------------------
# Outils réutilisables
# ---------------------------------------------------------------------------

def build_choix_axe():
    t = Tree("Choix Axe", "Transforme un choix X / Y / Z en vecteurs : direction de l'axe et masque des deux autres.")
    t.socket("Axe", MENU, "Axe choisi")
    t.socket("Direction", VEC, "Vecteur unitaire de l'axe : X = (1,0,0), Y = (0,1,0), Z = (0,0,1)", out=True)
    t.socket("Masque", VEC, "Les deux autres axes, 1 − direction : Z donne (1,1,0)", out=True)
    gi, go = t.io(-500, 400)
    f = t.frame("Axe → direction, masque = 1 − direction", AXE)
    sw = t.node("GeometryNodeMenuSwitch", -250, 0, "Direction", f, data_type="VECTOR")
    sw.enum_items.clear()
    for axe, vec in (("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))):
        sw.enum_items.new(axe)
        sw.inputs[axe].default_value = vec
    inv = t.vmath("SUBTRACT", 50, -120, "1 − direction", f)
    inv.inputs[0].default_value = (1, 1, 1)
    t.link(gi.outputs["Axe"], sw.inputs["Menu"])
    t.link(sw.outputs["Output"], go.inputs["Direction"])
    t.link(sw.outputs["Output"], inv.inputs[1])
    t.link(inv.outputs["Vector"], go.inputs["Masque"])


def build_centre_mesh():
    t = Tree("Centre Mesh", "Centre géométrique réel et dimensions d'une géométrie, indépendants du pivot de l'objet.")
    t.socket("Geometry", GEO, "Géométrie à mesurer")
    t.socket("Centre", VEC, "(Min + Max) / 2", out=True)
    t.socket("Taille", VEC, "Max − Min sur X, Y, Z", out=True)
    t.socket("Min", VEC, "Coin bas de la boîte englobante", out=True)
    t.socket("Max", VEC, "Coin haut de la boîte englobante", out=True)
    gi, go = t.io(-700, 400)
    bb = t.node("GeometryNodeBoundBox", -480, 0)
    f1 = t.frame("Centre = (Min + Max) / 2", MESURE)
    add = t.vmath("ADD", -220, 160, "Min + Max", f1)
    mid = t.vmath("SCALE", 0, 160, "× 0,5", f1)
    mid.inputs["Scale"].default_value = 0.5
    f2 = t.frame("Taille = Max − Min", MESURE)
    size = t.vmath("SUBTRACT", 0, -100, "Max − Min", f2)
    t.link(gi.outputs[0], bb.inputs["Geometry"])
    t.link(bb.outputs["Min"], add.inputs[0]); t.link(bb.outputs["Max"], add.inputs[1])
    t.link(add.outputs["Vector"], mid.inputs[0])
    t.link(bb.outputs["Max"], size.inputs[0]); t.link(bb.outputs["Min"], size.inputs[1])
    t.link(mid.outputs["Vector"], go.inputs["Centre"]); t.link(size.outputs["Vector"], go.inputs["Taille"])
    t.link(bb.outputs["Min"], go.inputs["Min"]); t.link(bb.outputs["Max"], go.inputs["Max"])


def build_box_normalisee():
    t = Tree("Box Normalisée", "Position de chaque point dans sa boîte englobante, ramenée entre −1 et +1 (0 au centre).")
    t.socket("Geometry", GEO, "Géométrie de référence pour la boîte")
    t.socket("Axe", MENU, "Axe lu dans la sortie Valeur")
    t.socket("Normalisée", VEC, "−1 … +1 sur chaque axe", out=True)
    t.socket("Valeur", FLT, "−1 … +1 sur l'axe choisi", out=True)
    gi, go = t.io(-900, 700)
    f1 = t.frame("Mesure", MESURE)
    cm = t.group("Centre Mesh", -650, 120, f1)
    f2 = t.frame("(P − C) / (Taille / 2)", PROFIL)
    pos = t.node("GeometryNodeInputPosition", -400, 260, None, f2)
    loc = t.vmath("SUBTRACT", -180, 220, "P − C", f2)
    half = t.vmath("SCALE", -180, 20, "Taille / 2", f2)
    half.inputs["Scale"].default_value = 0.5
    div = t.vmath("DIVIDE", 40, 140, "÷ demi-taille", f2)
    f3 = t.frame("Lecture sur l'axe choisi", AXE)
    ax = t.group("Choix Axe", 40, -340, f3)
    dot = t.vmath("DOT_PRODUCT", 300, -250, "· direction", f3)
    t.link(gi.outputs["Geometry"], cm.inputs["Geometry"])
    t.link(pos.outputs[0], loc.inputs[0]); t.link(cm.outputs["Centre"], loc.inputs[1])
    t.link(cm.outputs["Taille"], half.inputs[0])
    t.link(loc.outputs["Vector"], div.inputs[0]); t.link(half.outputs["Vector"], div.inputs[1])
    t.link(gi.outputs["Axe"], ax.inputs["Axe"])
    t.link(div.outputs["Vector"], dot.inputs[0]); t.link(ax.outputs["Direction"], dot.inputs[1])
    t.link(div.outputs["Vector"], go.inputs["Normalisée"]); t.link(dot.outputs["Value"], go.inputs["Valeur"])


def build_profil_cloche():
    t = Tree("Profil Cloche", "Cloche 1 − t² : 0 pour t = ±1 (les bouts), 1 pour t = 0 (le centre).")
    t.socket("t", FLT, "Valeur entre −1 et +1, par exemple la sortie Valeur de Box Normalisée")
    t.socket("Profil", FLT, "0 aux bouts, 1 au centre", out=True)
    gi, go = t.io(-500, 400)
    f = t.frame("1 − t²", PROFIL)
    sq = t.math("MULTIPLY", -220, 0, "t²", f)
    inv = t.math("SUBTRACT", 0, 0, "1 − t²", f)
    inv.inputs[0].default_value = 1.0
    t.link(gi.outputs[0], sq.inputs[0]); t.link(gi.outputs[0], sq.inputs[1])
    t.link(sq.outputs[0], inv.inputs[1]); t.link(inv.outputs[0], go.inputs[0])


def build_poussee_radiale():
    t = Tree("Poussée Radiale", "Écarte chaque point de l'axe passant par le centre, proportionnellement à sa distance à cet axe.")
    t.socket("Geometry", GEO, "Géométrie réalisée (pas des instances)")
    t.socket("Centre", VEC, "Point par lequel passe l'axe")
    t.socket("Facteur", FLT, "Champ : 0 = immobile, 1 = distance à l'axe doublée, négatif = rentre vers l'axe", 0.0)
    t.socket("Axe", MENU, "Axe autour duquel on pousse ; on ne bouge jamais le long de cet axe")
    t.socket("Geometry", GEO, "Géométrie déformée", out=True)
    gi, go = t.io(-900, 700)
    f1 = t.frame("Vecteur radial = (P − C) × masque", DEFORM)
    pos = t.node("GeometryNodeInputPosition", -650, -140, None, f1)
    rad = t.vmath("SUBTRACT", -430, -100, "P − C", f1)
    ax = t.group("Choix Axe", -430, -300, f1)
    mask = t.vmath("MULTIPLY", -180, -140, "× masque", f1)
    f2 = t.frame("Offset = radial × facteur", DEFORM)
    scl = t.vmath("SCALE", 150, -100, "× facteur", f2)
    setp = t.node("GeometryNodeSetPosition", 400, 60, None, f2)
    t.link(pos.outputs[0], rad.inputs[0]); t.link(gi.outputs["Centre"], rad.inputs[1])
    t.link(gi.outputs["Axe"], ax.inputs["Axe"])
    t.link(rad.outputs["Vector"], mask.inputs[0]); t.link(ax.outputs["Masque"], mask.inputs[1])
    t.link(mask.outputs["Vector"], scl.inputs[0]); t.link(gi.outputs["Facteur"], scl.inputs["Scale"])
    t.link(gi.outputs["Geometry"], setp.inputs["Geometry"]); t.link(scl.outputs["Vector"], setp.inputs["Offset"])
    t.link(setp.outputs["Geometry"], go.inputs[0])


def build_paire_miroir():
    t = Tree("Paire Miroir", "Deux copies d'une géométrie, à +Distance et −Distance le long de Z.")
    t.socket("Geometry", GEO, "Géométrie construite autour de l'origine")
    t.socket("Distance", FLT, "Décalage de chaque copie depuis l'origine", 1.0, subtype="DISTANCE")
    t.socket("Geometry", GEO, "Les deux copies réunies", out=True)
    gi, go = t.io(-700, 500)
    f = t.frame("Copie en +Z et en −Z", AXE)
    neg = t.math("MULTIPLY", -450, -200, "− Distance", f, b=-1.0)
    up = t.node("ShaderNodeCombineXYZ", -220, 60, "(0, 0, +d)", f)
    dn = t.node("ShaderNodeCombineXYZ", -220, -200, "(0, 0, −d)", f)
    t1 = t.node("GeometryNodeTransform", 0, 160, "Copie haute", f)
    t2 = t.node("GeometryNodeTransform", 0, -160, "Copie basse", f)
    join = t.node("GeometryNodeJoinGeometry", 280, 0)
    t.link(gi.outputs["Distance"], up.inputs["Z"]); t.link(gi.outputs["Distance"], neg.inputs[0])
    t.link(neg.outputs[0], dn.inputs["Z"])
    t.link(gi.outputs["Geometry"], t1.inputs["Geometry"]); t.link(gi.outputs["Geometry"], t2.inputs["Geometry"])
    t.link(up.outputs[0], t1.inputs["Translation"]); t.link(dn.outputs[0], t2.inputs["Translation"])
    t.link(t2.outputs[0], join.inputs[0]); t.link(t1.outputs[0], join.inputs[0])
    t.link(join.outputs[0], go.inputs[0])


def build_orienter_axe():
    t = Tree("Orienter Axe", "Fait pivoter une géométrie construite le long de Z vers l'axe choisi, puis la place sur un centre.")
    t.socket("Geometry", GEO, "Géométrie construite le long de Z, autour de l'origine")
    t.socket("Axe", MENU, "Axe de destination")
    t.socket("Centre", VEC, "Où placer l'origine de la géométrie")
    t.socket("Geometry", GEO, "Géométrie orientée et placée", out=True)
    gi, go = t.io(-600, 400)
    f = t.frame("Z → axe choisi, puis translation au centre", AXE)
    # Passe par Choix Axe : une entrée menu ne peut alimenter qu'une seule définition X/Y/Z.
    ax = t.group("Choix Axe", -350, -120, f)
    al = t.node("FunctionNodeAlignRotationToVector", -120, -120, "Z → direction", f, axis="Z")
    tr = t.node("GeometryNodeTransform", 100, 0, None, f)
    t.link(gi.outputs["Axe"], ax.inputs["Axe"]); t.link(ax.outputs["Direction"], al.inputs["Vector"])
    t.link(gi.outputs["Geometry"], tr.inputs["Geometry"])
    t.link(al.outputs["Rotation"], tr.inputs["Rotation"]); t.link(gi.outputs["Centre"], tr.inputs["Translation"])
    t.link(tr.outputs[0], go.inputs[0])


# ---------------------------------------------------------------------------
# Pièces du tonneau
# ---------------------------------------------------------------------------

def build_cerclage():
    t = Tree("Cerclage", "Anneau plat (section rectangulaire) le long de Z, centré sur l'origine.")
    t.socket("Rayon", FLT, "Rayon intérieur de l'anneau", 1.0, lo=0.0, subtype="DISTANCE")
    t.socket("Largeur", FLT, "Hauteur de la bande le long de Z", 0.12, lo=0.0, subtype="DISTANCE")
    t.socket("Épaisseur", FLT, "Épaisseur radiale du métal", 0.025, lo=0.0, subtype="DISTANCE")
    t.socket("Résolution", INT, "Nombre de segments autour", 64, lo=3)
    t.socket("Mesh", GEO, "Anneau", out=True)
    gi, go = t.io(-800, 500)
    f1 = t.frame("Cercle au milieu de l'épaisseur", METAL)
    half = t.math("MULTIPLY", -550, 120, "Épaisseur / 2", f1, b=0.5)
    rmid = t.math("ADD", -330, 120, "Rayon + ép/2", f1)
    circ = t.node("GeometryNodeCurvePrimitiveCircle", -100, 160, None, f1, mode="RADIUS")
    f2 = t.frame("Section : rectangle épaisseur × largeur", METAL)
    prof = t.node("GeometryNodeCurvePrimitiveQuadrilateral", -100, -160, None, f2, mode="RECTANGLE")
    c2m = t.node("GeometryNodeCurveToMesh", 250, 0)
    c2m.inputs["Fill Caps"].default_value = True
    t.link(gi.outputs["Épaisseur"], half.inputs[0])
    t.link(gi.outputs["Rayon"], rmid.inputs[0]); t.link(half.outputs[0], rmid.inputs[1])
    t.link(rmid.outputs[0], circ.inputs["Radius"]); t.link(gi.outputs["Résolution"], circ.inputs["Resolution"])
    t.link(gi.outputs["Épaisseur"], prof.inputs["Width"]); t.link(gi.outputs["Largeur"], prof.inputs["Height"])
    t.link(circ.outputs["Curve"], c2m.inputs["Curve"]); t.link(prof.outputs["Curve"], c2m.inputs["Profile Curve"])
    t.link(c2m.outputs["Mesh"], go.inputs[0])


def build_fond_planches():
    t = Tree("Fond Planches", "Disque fait de planches parallèles, découpées en cercle, dans le plan XY et centré sur l'origine.")
    t.socket("Rayon", FLT, "Rayon du disque", 1.0, lo=0.0, subtype="DISTANCE")
    t.socket("Planches", INT, "Nombre de planches", 6, lo=1)
    t.socket("Épaisseur", FLT, "Épaisseur des planches le long de Z", 0.05, lo=0.0, subtype="DISTANCE")
    t.socket("Jeu", FLT, "Espace entre deux planches", 0.01, lo=0.0, subtype="DISTANCE")
    t.socket("Mesh", GEO, "Fond", out=True)
    gi, go = t.io(-1100, 1350)

    f1 = t.frame("Une planche par point : x = −R + w × (i + 0,5), w = 2R / N", BOIS)
    diam = t.math("MULTIPLY", -850, 200, "2R", f1, b=2.0)
    w = t.math("DIVIDE", -650, 200, "w = 2R / N", f1)
    idx = t.node("GeometryNodeInputIndex", -850, 0, None, f1)
    i5 = t.math("ADD", -650, 0, "i + 0,5", f1, b=0.5)
    xw = t.math("MULTIPLY", -450, 100, "w × (i + 0,5)", f1)
    xi = t.math("SUBTRACT", -250, 100, "− R", f1)
    pxyz = t.node("ShaderNodeCombineXYZ", -50, 100, "(x, 0, 0)", f1)
    pts = t.node("GeometryNodePoints", 150, 200, None, f1)

    f2 = t.frame("Planche = pavé (w − jeu) × 1 × épaisseur", BOIS)
    pw = t.math("SUBTRACT", -450, -250, "w − jeu", f2)
    size = t.node("ShaderNodeCombineXYZ", -250, -250, "Taille planche", f2)
    size.inputs["Y"].default_value = 1.0
    cube = t.node("GeometryNodeMeshCube", -50, -250, None, f2)
    cube.inputs["Vertices X"].default_value = 8
    inst = t.node("GeometryNodeInstanceOnPoints", 150, -50, None, f2)
    real = t.node("GeometryNodeRealizeInstances", 350, -50, None, f2)

    # Chaque sommet garde son x et prend y = ±√(R² − x²) : les bouts suivent le cercle.
    f3 = t.frame("Découpe en cercle : y = ±√(R² − x²)", BOIS)
    pos = t.node("GeometryNodeInputPosition", 150, -450, None, f3)
    sep = t.node("ShaderNodeSeparateXYZ", 350, -450, None, f3)
    r2 = t.math("MULTIPLY", 150, -650, "R²", f3)
    x2 = t.math("MULTIPLY", 550, -600, "x²", f3)
    d = t.math("SUBTRACT", 350, -700, "R² − x²", f3)
    d0 = t.math("MAXIMUM", 550, -800, "max(…, 0)", f3, b=0.0)
    sq = t.math("SQRT", 750, -800, "√", f3)
    sg = t.math("SIGN", 750, -450, "signe(y)", f3)
    yy = t.math("MULTIPLY", 950, -600, "± √", f3)
    npos = t.node("ShaderNodeCombineXYZ", 1150, -450, "(x, y, z)", f3)
    setp = t.node("GeometryNodeSetPosition", 600, -50)

    L = t.link
    L(gi.outputs["Rayon"], diam.inputs[0]); L(diam.outputs[0], w.inputs[0]); L(gi.outputs["Planches"], w.inputs[1])
    L(idx.outputs[0], i5.inputs[0]); L(w.outputs[0], xw.inputs[0]); L(i5.outputs[0], xw.inputs[1])
    L(xw.outputs[0], xi.inputs[0]); L(gi.outputs["Rayon"], xi.inputs[1]); L(xi.outputs[0], pxyz.inputs["X"])
    L(gi.outputs["Planches"], pts.inputs["Count"]); L(pxyz.outputs[0], pts.inputs["Position"])
    L(w.outputs[0], pw.inputs[0]); L(gi.outputs["Jeu"], pw.inputs[1])
    L(pw.outputs[0], size.inputs["X"]); L(gi.outputs["Épaisseur"], size.inputs["Z"])
    L(size.outputs[0], cube.inputs["Size"])
    L(pts.outputs[0], inst.inputs["Points"]); L(cube.outputs["Mesh"], inst.inputs["Instance"])
    L(inst.outputs[0], real.inputs[0])
    L(pos.outputs[0], sep.inputs[0])
    L(gi.outputs["Rayon"], r2.inputs[0]); L(gi.outputs["Rayon"], r2.inputs[1])
    L(sep.outputs["X"], x2.inputs[0]); L(sep.outputs["X"], x2.inputs[1])
    L(r2.outputs[0], d.inputs[0]); L(x2.outputs[0], d.inputs[1])
    L(d.outputs[0], d0.inputs[0]); L(d0.outputs[0], sq.inputs[0])
    L(sep.outputs["Y"], sg.inputs[0]); L(sg.outputs[0], yy.inputs[0]); L(sq.outputs[0], yy.inputs[1])
    L(sep.outputs["X"], npos.inputs["X"]); L(yy.outputs[0], npos.inputs["Y"]); L(sep.outputs["Z"], npos.inputs["Z"])
    L(real.outputs[0], setp.inputs["Geometry"]); L(npos.outputs[0], setp.inputs["Position"])
    L(setp.outputs[0], go.inputs[0])


# ---------------------------------------------------------------------------
# Modifiers
# ---------------------------------------------------------------------------

def build_tonneau():
    t = Tree("Tonneau", "Bombe une géométrie en tonneau autour d'un axe : nul aux bouts, maximal au milieu, "
                        "depuis le centre réel.", modifier=True)
    t.socket("Geometry", GEO, "Géométrie réalisée (mettre Realize Instances avant si ce sont des instances)")
    t.socket("Bombé", FLT, "Gonflement au milieu : 0,35 = rayon × 1,35. Négatif = diabolo", 0.35, lo=-2.0, hi=2.0)
    t.socket("Axe", MENU, "Axe du tonneau (Z = debout)")
    t.socket("Geometry", GEO, "Géométrie bombée", out=True)
    gi, go = t.io(-900, 900)
    f1 = t.frame("1. Mesure", MESURE)
    cm = t.group("Centre Mesh", -650, -200, f1)
    f2 = t.frame("2. Profil le long de l'axe", PROFIL)
    box = t.group("Box Normalisée", -650, 220, f2)
    cl = t.group("Profil Cloche", -380, 220, f2)
    mul = t.math("MULTIPLY", -150, 220, "× Bombé", f2)
    f3 = t.frame("3. Déformation", DEFORM)
    push = t.group("Poussée Radiale", 400, 0, f3)
    L = t.link
    L(gi.outputs["Geometry"], box.inputs["Geometry"]); L(gi.outputs["Axe"], box.inputs["Axe"])
    L(box.outputs["Valeur"], cl.inputs[0])
    L(cl.outputs[0], mul.inputs[0]); L(gi.outputs["Bombé"], mul.inputs[1])
    L(gi.outputs["Geometry"], cm.inputs["Geometry"])
    L(gi.outputs["Geometry"], push.inputs["Geometry"])
    L(cm.outputs["Centre"], push.inputs["Centre"])
    L(mul.outputs[0], push.inputs["Facteur"])
    L(gi.outputs["Axe"], push.inputs["Axe"])
    L(push.outputs[0], go.inputs[0])


def build_tonneau_ferme():
    t = Tree("Tonneau Fermé", "Tonneau complet à partir des douelles : bombé, deux cerclages et deux fonds en planches. "
                              "Attribut « partie » : 0 douelles, 1 cerclages, 2 fonds.", modifier=True)
    t.socket("Geometry", GEO, "Douelles réalisées (mettre Realize Instances avant si ce sont des instances)")
    t.socket("Axe", MENU, "Axe du tonneau (Z = debout)")
    t.socket("Bombé", FLT, "Gonflement au milieu : 0,35 = rayon × 1,35", 0.35, lo=-2.0, hi=2.0)
    pc = t.panel("Cerclages")
    t.socket("Position", FLT, "0 = au bout du tonneau, 1 = au milieu", 0.15, panel=pc, lo=0.0, hi=1.0, subtype="FACTOR")
    t.socket("Largeur", FLT, "Hauteur de la bande", 0.12, panel=pc, lo=0.0, subtype="DISTANCE")
    t.socket("Épaisseur", FLT, "Épaisseur du métal", 0.025, panel=pc, lo=0.0, subtype="DISTANCE")
    t.socket("Matériau Cerclages", MAT, "Matériau des cerclages", panel=pc)
    pf = t.panel("Fonds")
    t.socket("Retrait", FLT, "Distance entre le bout des douelles et le fond", 0.1, panel=pf, lo=0.0, subtype="DISTANCE")
    t.socket("Paroi", FLT, "Épaisseur des douelles : le fond s'arrête à leur face intérieure", 0.1, panel=pf,
             lo=0.0, subtype="DISTANCE")
    t.socket("Épaisseur Fond", FLT, "Épaisseur des planches du fond", 0.05, panel=pf, lo=0.0, subtype="DISTANCE")
    t.socket("Planches", INT, "Nombre de planches par fond", 6, panel=pf, lo=1)
    t.socket("Jeu", FLT, "Espace entre deux planches", 0.01, panel=pf, lo=0.0, subtype="DISTANCE")
    t.socket("Matériau Fonds", MAT, "Matériau des fonds", panel=pf)
    t.socket("Geometry", GEO, "Tonneau complet", out=True)
    gi, go = t.io(-1500, 1900)
    D = gi.outputs["Geometry"]

    # R = distance max des douelles à l'axe : la boîte englobante sous-estime
    # le rayon des coins, qui traverseraient alors les cerclages.
    f1 = t.frame("1. Mesure des douelles : centre, hauteur H, rayon R = distance max à l'axe", MESURE)
    cm = t.group("Centre Mesh", -1250, 350, f1)
    ax = t.group("Choix Axe", -1250, 50, f1)
    pos = t.node("GeometryNodeInputPosition", -1000, 520, None, f1)
    pc_ = t.vmath("SUBTRACT", -800, 480, "P − C", f1)
    pm = t.vmath("MULTIPLY", -600, 480, "× masque", f1)
    ln = t.vmath("LENGTH", -400, 480, "distance à l'axe", f1)
    rr = t.node("GeometryNodeAttributeStatistic", -200, 400, "R = max", f1)
    hh = t.vmath("DOT_PRODUCT", -1000, 80, "Taille · direction", f1)
    h2 = t.math("MULTIPLY", -800, 80, "H / 2", f1, b=0.5)
    R = rr.outputs["Max"]

    f2 = t.frame("2. Cerclages à ±(H/2) × (1 − position)", METAL)
    c1 = t.math("SUBTRACT", -600, -250, "1 − position", f2)
    c1.inputs[0].default_value = 1.0
    cz = t.math("MULTIPLY", -400, -250, "× H/2", f2)
    cer = t.group("Cerclage", -400, -450, f2)
    cpair = t.group("Paire Miroir", -150, -300, f2)
    cmat = t.node("GeometryNodeSetMaterial", 80, -300, None, f2)
    cid = t.node("GeometryNodeStoreNamedAttribute", 300, -300, "partie = 1", f2, data_type="INT")

    f3 = t.frame("3. Fonds à ±(H/2 − retrait), rayon R − paroi", BOIS)
    fr = t.math("SUBTRACT", -600, -750, "R − paroi", f3)
    fz = t.math("SUBTRACT", -600, -950, "H/2 − retrait", f3)
    fond = t.group("Fond Planches", -400, -750, f3)
    fpair = t.group("Paire Miroir", -150, -850, f3)
    fmat = t.node("GeometryNodeSetMaterial", 80, -850, None, f3)
    fid = t.node("GeometryNodeStoreNamedAttribute", 300, -850, "partie = 2", f3, data_type="INT")

    f4 = t.frame("4. Assemblage sur l'axe et le centre des douelles", AXE)
    jparts = t.node("GeometryNodeJoinGeometry", 550, -500, "Cerclages + fonds", f4)
    orient = t.group("Orienter Axe", 750, -500, f4)
    did = t.node("GeometryNodeStoreNamedAttribute", 750, 150, "partie = 0", f4, data_type="INT")
    jall = t.node("GeometryNodeJoinGeometry", 1000, 0, "Tout", f4)

    # Le bombé s'applique à tout l'ensemble, avec la boîte des douelles comme référence :
    # cerclages et fonds suivent la courbe des douelles.
    f5 = t.frame("5. Bombé de l'ensemble (référence : boîte des douelles)", DEFORM)
    box = t.group("Box Normalisée", 1000, 450, f5)
    cl = t.group("Profil Cloche", 1250, 450, f5)
    mb = t.math("MULTIPLY", 1450, 450, "× Bombé", f5)
    push = t.group("Poussée Radiale", 1650, 100, f5)

    for store, value in ((did, 0), (cid, 1), (fid, 2)):
        store.inputs["Name"].default_value = "partie"
        store.inputs["Value"].default_value = value

    L = t.link
    L(D, cm.inputs["Geometry"]); L(gi.outputs["Axe"], ax.inputs["Axe"])
    L(pos.outputs[0], pc_.inputs[0]); L(cm.outputs["Centre"], pc_.inputs[1])
    L(pc_.outputs["Vector"], pm.inputs[0]); L(ax.outputs["Masque"], pm.inputs[1])
    L(pm.outputs["Vector"], ln.inputs[0])
    L(D, rr.inputs["Geometry"]); L(ln.outputs["Value"], rr.inputs["Attribute"])
    L(cm.outputs["Taille"], hh.inputs[0]); L(ax.outputs["Direction"], hh.inputs[1]); L(hh.outputs["Value"], h2.inputs[0])
    # cerclages
    L(gi.outputs["Position"], c1.inputs[1]); L(c1.outputs[0], cz.inputs[0]); L(h2.outputs[0], cz.inputs[1])
    L(R, cer.inputs["Rayon"]); L(gi.outputs["Largeur"], cer.inputs["Largeur"])
    L(gi.outputs["Épaisseur"], cer.inputs["Épaisseur"])
    L(cer.outputs[0], cpair.inputs["Geometry"]); L(cz.outputs[0], cpair.inputs["Distance"])
    L(cpair.outputs[0], cmat.inputs["Geometry"]); L(gi.outputs["Matériau Cerclages"], cmat.inputs["Material"])
    L(cmat.outputs[0], cid.inputs["Geometry"])
    # fonds
    L(R, fr.inputs[0]); L(gi.outputs["Paroi"], fr.inputs[1])
    L(h2.outputs[0], fz.inputs[0]); L(gi.outputs["Retrait"], fz.inputs[1])
    L(fr.outputs[0], fond.inputs["Rayon"]); L(gi.outputs["Planches"], fond.inputs["Planches"])
    L(gi.outputs["Épaisseur Fond"], fond.inputs["Épaisseur"]); L(gi.outputs["Jeu"], fond.inputs["Jeu"])
    L(fond.outputs[0], fpair.inputs["Geometry"]); L(fz.outputs[0], fpair.inputs["Distance"])
    L(fpair.outputs[0], fmat.inputs["Geometry"]); L(gi.outputs["Matériau Fonds"], fmat.inputs["Material"])
    L(fmat.outputs[0], fid.inputs["Geometry"])
    # assemblage
    L(fid.outputs[0], jparts.inputs[0]); L(cid.outputs[0], jparts.inputs[0])
    L(jparts.outputs[0], orient.inputs["Geometry"]); L(gi.outputs["Axe"], orient.inputs["Axe"])
    L(cm.outputs["Centre"], orient.inputs["Centre"])
    L(D, did.inputs["Geometry"])
    L(orient.outputs[0], jall.inputs[0]); L(did.outputs[0], jall.inputs[0])
    # bombé
    L(D, box.inputs["Geometry"]); L(gi.outputs["Axe"], box.inputs["Axe"])
    L(box.outputs["Valeur"], cl.inputs[0]); L(cl.outputs[0], mb.inputs[0]); L(gi.outputs["Bombé"], mb.inputs[1])
    L(jall.outputs[0], push.inputs["Geometry"]); L(cm.outputs["Centre"], push.inputs["Centre"])
    L(mb.outputs[0], push.inputs["Facteur"]); L(gi.outputs["Axe"], push.inputs["Axe"])
    L(push.outputs[0], go.inputs[0])


def set_menu_defaults():
    """Axe Z par défaut. Les entrées menu ne connaissent X/Y/Z qu'une fois l'arbre mis à jour."""
    for ng in bpy.data.node_groups:
        ng.interface_update(bpy.context)
    for ng in bpy.data.node_groups:
        for item in ng.interface.items_tree:
            if getattr(item, "socket_type", "") == MENU and item.in_out == "INPUT":
                item.default_value = "Z"


ASSETS = {
    "Tonneau Fermé": (CATALOG_TONNEAU, ("tonneau", "barrel", "douelles", "cerclage", "fût")),
    "Tonneau": (CATALOG_TONNEAU, ("tonneau", "barrel", "bombé", "bulge")),
    "Cerclage": (CATALOG_TONNEAU, ("cerclage", "hoop", "anneau", "ring")),
    "Fond Planches": (CATALOG_TONNEAU, ("fond", "planches", "planks", "disque")),
    "Centre Mesh": (CATALOG_OUTILS, ("centre", "bounding box", "mesure")),
    "Box Normalisée": (CATALOG_OUTILS, ("bounding box", "normaliser", "-1 1")),
    "Profil Cloche": (CATALOG_OUTILS, ("profil", "parabole", "falloff")),
    "Poussée Radiale": (CATALOG_OUTILS, ("radial", "gonfler", "inflate")),
    "Choix Axe": (CATALOG_OUTILS, ("axe", "axis", "menu")),
    "Orienter Axe": (CATALOG_OUTILS, ("axe", "axis", "rotation")),
    "Paire Miroir": (CATALOG_OUTILS, ("miroir", "mirror", "copie")),
}


def mark_assets():
    for name, (catalog, tags) in ASSETS.items():
        ng = bpy.data.node_groups[name]
        ng.asset_mark()
        data = ng.asset_data
        data.catalog_id = catalog
        data.author = "Marc Gardent"
        data.description = ng.description
        for tag in tags:
            data.tags.new(tag, skip_if_exists=True)


# ---------------------------------------------------------------------------
# Scène de démo, contrôle et aperçus
# ---------------------------------------------------------------------------

def modifier_input(mod, name):
    item = mod.node_group.interface.items_tree[name]
    return getattr(mod.properties.inputs, item.identifier)


def material(name, color, metallic=0.0, roughness=0.6):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def build_douelles(bois):
    """Générateur de démo (pas un asset) : 12 douelles 0,5 × 0,1 × 3 sur un cercle de rayon 1."""
    t = Tree("Demo Douelles", "Douelles de démonstration pour Tonneau Fermé.", modifier=True)
    t.socket("Geometry", GEO, "Ignorée")
    t.socket("Geometry", GEO, "Douelles réalisées", out=True)
    gi, go = t.io(-900, 700)
    circ = t.node("GeometryNodeCurvePrimitiveCircle", -650, 150)
    circ.inputs["Resolution"].default_value = 12
    cube = t.node("GeometryNodeMeshCube", -650, -100)
    cube.inputs["Size"].default_value = (0.5, 0.1, 3.0)
    cube.inputs["Vertices Z"].default_value = 20
    tan = t.node("GeometryNodeInputTangent", -650, -350)
    al = t.node("FunctionNodeAlignRotationToVector", -430, -300, axis="X")
    iop = t.node("GeometryNodeInstanceOnPoints", -200, 0)
    real = t.node("GeometryNodeRealizeInstances", 20, 0)
    setm = t.node("GeometryNodeSetMaterial", 250, 0)
    setm.inputs["Material"].default_value = bois
    t.link(tan.outputs[0], al.inputs["Vector"]); t.link(al.outputs[0], iop.inputs["Rotation"])
    t.link(circ.outputs[0], iop.inputs["Points"]); t.link(cube.outputs["Mesh"], iop.inputs["Instance"])
    t.link(iop.outputs[0], real.inputs[0]); t.link(real.outputs[0], setm.inputs[0])
    t.link(setm.outputs[0], go.inputs[0])
    return t.ng


def build_demo():
    bois = material("Demo Douelles", (0.45, 0.26, 0.12, 1.0))
    fond = material("Demo Fond", (0.62, 0.42, 0.22, 1.0))
    metal = material("Demo Cerclages", (0.18, 0.18, 0.2, 1.0), metallic=1.0, roughness=0.35)
    mesh = bpy.data.meshes.new("Demo Tonneau")
    demo = bpy.data.objects.new("Demo Tonneau", mesh)
    bpy.context.scene.collection.objects.link(demo)
    demo.modifiers.new("Douelles", "NODES").node_group = build_douelles(bois)
    mod = demo.modifiers.new("Tonneau Fermé", "NODES")
    mod.node_group = bpy.data.node_groups["Tonneau Fermé"]
    modifier_input(mod, "Matériau Cerclages").value = metal
    modifier_input(mod, "Matériau Fonds").value = fond

    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (5.2, -5.2, 3.6)
    cam.rotation_euler = (math.radians(65), 0, math.radians(45))
    cam.data.lens = 65
    bpy.context.scene.camera = cam
    sun = bpy.data.objects.new("Soleil", bpy.data.lights.new("Soleil", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (0.8, 0.3, 0.6)
    bpy.context.scene.collection.objects.link(sun)
    return demo


def check(demo, bombe=0.35, paroi=0.1):
    """Contrôle : cerclages posés sur les coins des douelles, fonds dans leur paroi.

    Chaque rayon est ramené à sa valeur d'avant le bombé (÷ 1 + bombé × (1 − t²)),
    pour comparer des pièces qui ne sont pas à la même hauteur.
    """
    ev = demo.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    part = me.attributes["partie"].data
    h2 = max(abs(v.co.z) for v in me.vertices)
    rayons = {0: [], 1: [], 2: []}
    for i, v in enumerate(me.vertices):
        t = v.co.z / h2
        rayons[part[i].value].append(math.hypot(v.co.x, v.co.y) / (1 + bombe * (1 - t * t)))
    ev.to_mesh_clear()

    r_douelles = max(rayons[0])
    print("Contrôle (rayons avant bombé) :")
    print(f"  douelles   rayon des coins     {r_douelles:.3f}")
    print(f"  cerclages  rayon intérieur     {min(rayons[1]):.3f}  (attendu ≥ {r_douelles:.3f})")
    print(f"  fonds      rayon               {max(rayons[2]):.3f}  (attendu ≤ {r_douelles - paroi:.3f})")


def render_preview(ng, path=None):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = path or os.path.join(bpy.app.tempdir, "preview.png")
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(scene.render.filepath)
    preview = ng.preview_ensure()
    preview.image_size = img.size
    preview.image_pixels_float = list(img.pixels)
    bpy.data.images.remove(img)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build_choix_axe()
    build_centre_mesh()
    build_box_normalisee()
    build_profil_cloche()
    build_poussee_radiale()
    build_paire_miroir()
    build_orienter_axe()
    build_cerclage()
    build_fond_planches()
    build_tonneau()
    build_tonneau_ferme()
    set_menu_defaults()
    mark_assets()

    demo = build_demo()
    check(demo)
    # Vignette de Tonneau : un objet à part avec les mêmes douelles, bombées seulement.
    # (Changer le groupe d'un modifier recopie les valeurs par position d'entrée.)
    bombe = bpy.data.objects.new("Demo Bombé", bpy.data.meshes.new("Demo Bombé"))
    bpy.context.scene.collection.objects.link(bombe)
    bombe.modifiers.new("Douelles", "NODES").node_group = bpy.data.node_groups["Demo Douelles"]
    bombe.modifiers.new("Tonneau", "NODES").node_group = bpy.data.node_groups["Tonneau"]
    demo.hide_render = True
    render_preview(bpy.data.node_groups["Tonneau"])
    bpy.data.objects.remove(bombe)
    demo.hide_render = False
    render_preview(bpy.data.node_groups["Tonneau Fermé"], PREVIEW_PATH)

    os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Asset ecrit :", BLEND_PATH)


main()
