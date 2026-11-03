"""Construit l'asset « Tri par Matériau » de Marc's Blender Library.

Modifier Geometry Nodes pour Grease Pencil : dans chaque calque, les strokes sont
redessinés dans l'ordre de la liste des matériaux, au lieu de l'ordre de tracé.
Non destructif : les strokes ajoutés plus tard sont triés aussi.

    blender -b --factory-startup --python src/gp_tri_materiau.py

Écrit assets/geometry_nodes/gp_tri_materiau.blend et previews/gp_tri_materiau.png.
"""
import math
import os

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(ROOT, "assets", "geometry_nodes", "gp_tri_materiau.blend")
PREVIEW_PATH = os.path.join(ROOT, "previews", "gp_tri_materiau.png")

GROUP_NAME = "Tri par Matériau"
# « Geometry Nodes/Grease Pencil » dans blender_assets.cats.txt.
CATALOG_ID = "167fb2b4-a6a2-4e99-891a-7769742d72a1"
# Attribut de calque temporaire, retiré avant la sortie.
TAG = "_tri_vide"


def build_group():
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng.is_modifier = True

    ng.interface.new_socket("Grease Pencil", in_out="INPUT", socket_type="NodeSocketGeometry")
    top = ng.interface.new_socket("Haut de liste devant", in_out="INPUT", socket_type="NodeSocketBool")
    top.default_value = True
    top.description = "Le premier matériau de la liste est dessiné devant, comme pour les calques"
    ng.interface.new_socket("Grease Pencil", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n = ng.nodes
    gin = n.new("NodeGroupInput")
    gin.location = (-900, 0)
    gout = n.new("NodeGroupOutput")
    gout.location = (900, 0)

    # Sort Elements ne lit pas le Grease Pencil : on trie les courbes de chaque calque.
    to_curves = n.new("GeometryNodeGreasePencilToCurves")
    to_curves.location = (-600, 0)
    to_curves.inputs["Layers as Instances"].default_value = True

    # Le dernier stroke dessiné passe devant : poids = −index pour finir par le slot 0.
    mat_index = n.new("GeometryNodeInputMaterialIndex")
    mat_index.location = (-800, -250)
    sign = n.new("GeometryNodeSwitch")
    sign.input_type = "FLOAT"
    sign.location = (-600, -350)
    sign.inputs["False"].default_value = 1.0
    sign.inputs["True"].default_value = -1.0
    weight = n.new("ShaderNodeMath")
    weight.operation = "MULTIPLY"
    weight.location = (-400, -250)
    weight.label = "Poids de tri"

    sort = n.new("GeometryNodeSortElements")
    sort.domain = "CURVE"
    sort.location = (-200, 0)
    to_gp = n.new("GeometryNodeCurvesToGreasePencil")
    to_gp.location = (0, 0)
    to_gp.inputs["Instances as Layers"].default_value = True

    # Le retour en Grease Pencil perd la liste des matériaux : on la reprend en joignant
    # l'original vidé de ses strokes, dont on retire ensuite les calques vides.
    empty = n.new("GeometryNodeDeleteGeometry")
    empty.domain = "CURVE"
    empty.location = (-200, 300)
    empty.label = "Original sans strokes"
    tag = n.new("GeometryNodeStoreNamedAttribute")
    tag.domain = "LAYER"
    tag.data_type = "BOOLEAN"
    tag.location = (0, 300)
    tag.inputs["Name"].default_value = TAG
    tag.inputs["Value"].default_value = True
    join = n.new("GeometryNodeJoinGeometry")
    join.location = (250, 100)
    tagged = n.new("GeometryNodeInputNamedAttribute")
    tagged.data_type = "BOOLEAN"
    tagged.location = (250, -150)
    tagged.inputs["Name"].default_value = TAG
    drop = n.new("GeometryNodeDeleteGeometry")
    drop.domain = "LAYER"
    drop.location = (450, 100)
    drop.label = "Retire les calques vides"
    clean = n.new("GeometryNodeRemoveAttribute")
    clean.location = (650, 100)
    clean.inputs["Name"].default_value = TAG

    L = ng.links.new
    L(gin.outputs["Grease Pencil"], to_curves.inputs["Grease Pencil"])
    L(gin.outputs["Haut de liste devant"], sign.inputs["Switch"])
    L(mat_index.outputs["Material Index"], weight.inputs[0])
    L(sign.outputs["Output"], weight.inputs[1])
    L(to_curves.outputs[0], sort.inputs["Geometry"])
    L(weight.outputs["Value"], sort.inputs["Sort Weight"])
    L(sort.outputs["Geometry"], to_gp.inputs["Curves"])
    L(gin.outputs["Grease Pencil"], empty.inputs["Geometry"])
    L(empty.outputs["Geometry"], tag.inputs["Geometry"])
    # L'original vidé en premier : sa liste de matériaux garde l'ordre et les index.
    L(tag.outputs["Geometry"], join.inputs["Geometry"])
    L(to_gp.outputs[0], join.inputs["Geometry"])
    L(join.outputs["Geometry"], drop.inputs["Geometry"])
    L(tagged.outputs["Attribute"], drop.inputs["Selection"])
    L(drop.outputs["Geometry"], clean.inputs["Geometry"])
    L(clean.outputs["Geometry"], gout.inputs["Grease Pencil"])
    return ng


def mark_asset(ng):
    ng.asset_mark()
    data = ng.asset_data
    data.catalog_id = CATALOG_ID
    data.author = "Marc Gardent"
    data.description = (
        "Grease Pencil : dans chaque calque, dessine les strokes dans l'ordre de la liste "
        "des matériaux. Haut de liste devant par défaut. L'ordre de tracé est gardé "
        "dans un même matériau. Stroke Depth Order doit être en 2D Layers."
    )
    for tag in ("grease pencil", "tri", "sort", "matériau", "material", "draw order", "ordre"):
        data.tags.new(tag, skip_if_exists=True)


def gp_material(name, color):
    mat = bpy.data.materials.new(name)
    bpy.data.materials.create_gpencil_data(mat)
    style = mat.grease_pencil
    style.color = (0.05, 0.05, 0.05, 1.0)
    style.show_fill = True
    style.fill_color = color
    return mat


def build_demo(ng):
    """Trois disques qui se chevauchent, tracés dans le désordre : Rouge, Vert, Bleu
    dans la liste, Bleu tracé en dernier. Avec le modifier, Rouge passe devant."""
    gp = bpy.data.grease_pencils.new("Demo Tri")
    for name, color in (("Rouge", (0.9, 0.15, 0.1, 1.0)),
                        ("Vert", (0.2, 0.75, 0.25, 1.0)),
                        ("Bleu", (0.15, 0.35, 0.9, 1.0))):
        gp.materials.append(gp_material(name, color))
    demo = bpy.data.objects.new("Demo Tri", gp)
    bpy.context.scene.collection.objects.link(demo)

    drawing = gp.layers.new("Disques").frames.new(1).drawing
    # (slot, centre x, centre z) dans l'ordre de tracé
    disks = ((0, -0.55, 0.3), (1, 0.55, 0.3), (2, 0.0, -0.45))
    seg = 48
    drawing.add_strokes(sizes=[seg] * len(disks))
    pos = []
    for _slot, cx, cz in disks:
        for i in range(seg):
            a = 2 * math.pi * i / seg
            pos.append((cx + 0.8 * math.cos(a), 0.0, cz + 0.8 * math.sin(a)))
    drawing.attributes["position"].data.foreach_set("vector", np.array(pos, np.float32).ravel())
    radius = drawing.attributes.get("radius") or drawing.attributes.new("radius", "FLOAT", "POINT")
    radius.data.foreach_set("value", np.full(len(pos), 0.02, np.float32))
    cyclic = drawing.attributes.get("cyclic") or drawing.attributes.new("cyclic", "BOOLEAN", "CURVE")
    cyclic.data.foreach_set("value", [True] * len(disks))
    mat_index = drawing.attributes.get("material_index") or drawing.attributes.new("material_index", "INT", "CURVE")
    mat_index.data.foreach_set("value", [slot for slot, _x, _z in disks])
    # Depuis Blender 5, le remplissage est porté par le stroke : fill_id > 0 = rempli
    fill = drawing.attributes.get("fill_id") or drawing.attributes.new("fill_id", "INT", "CURVE")
    fill.data.foreach_set("value", list(range(1, len(disks) + 1)))
    drawing.tag_positions_changed()

    demo.modifiers.new("Tri par Matériau", "NODES").node_group = ng

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 3.4
    cam = bpy.data.objects.new("Camera", cam_data)
    cam.location = (0, -5, 0)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    bpy.context.scene.frame_set(1)
    return demo


def check(demo):
    """Contrôle : ordre des slots dans le calque évalué, matériaux et calques conservés."""
    ev = demo.evaluated_get(bpy.context.evaluated_depsgraph_get())
    layers = list(ev.data.layers)
    drawing = layers[0].current_frame().drawing
    order = np.empty(len(drawing.strokes), np.int32)
    drawing.attributes["material_index"].data.foreach_get("value", order)
    slots = [s.material.name if s.material else None for s in ev.material_slots]
    print("Contrôle :")
    print(f"  calques    {[l.name for l in layers]}  (attendu ['Disques'])")
    print(f"  ordre      {order.tolist()}  (attendu [2, 1, 0])")
    print(f"  matériaux  {slots}  (attendu ['Rouge', 'Vert', 'Bleu'])")
    print(f"  attributs  {[a.name for a in ev.data.attributes]}  (attendu sans {TAG})")
    assert [l.name for l in layers] == ["Disques"]
    assert order.tolist() == [2, 1, 0]
    assert slots == ["Rouge", "Vert", "Bleu"]
    assert TAG not in ev.data.attributes


def render_preview(ng):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(PREVIEW_PATH)
    preview = ng.preview_ensure()
    preview.image_size = img.size
    preview.image_pixels_float = list(img.pixels)
    bpy.data.images.remove(img)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ng = build_group()
    mark_asset(ng)
    demo = build_demo(ng)
    check(demo)
    render_preview(ng)
    os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Asset ecrit :", BLEND_PATH)


main()
