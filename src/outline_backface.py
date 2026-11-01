"""Construit l'asset « Outline Backface » de Marc's Blender Library.

Contour par backface culling (inverted hull) en Geometry Nodes : une copie du
mesh gonflée le long des normales, faces retournées, avec un matériau qui ne
garde que les faces arrière.

    blender -b --factory-startup --python src/outline_backface.py

Écrit assets/geometry_nodes/outline_backface.blend et previews/outline_backface.png.
"""
import os

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLEND_PATH = os.path.join(ROOT, "assets", "geometry_nodes", "outline_backface.blend")
PREVIEW_PATH = os.path.join(ROOT, "previews", "outline_backface.png")

GROUP_NAME = "Outline Backface"
MAT_NAME = "Outline"
# « Geometry Nodes/Outline » dans blender_assets.cats.txt.
CATALOG_ID = "50bb5659-02be-406f-9c02-87b386b9944f"


def build_material():
    mat = bpy.data.materials.new(MAT_NAME)
    # EEVEE / viewport : on ne voit que les faces arrière de la coque retournée.
    mat.use_backface_culling = True
    mat.diffuse_color = (0.0, 0.0, 0.0, 1.0)

    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    geo.location = (-400, 200)
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.location = (-200, 0)
    emit.label = "Couleur du contour"
    emit.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    transp.location = (-200, -150)
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.location = (0, 0)
    path = nt.nodes.new("ShaderNodeLightPath")
    path.location = (0, 300)
    camera_only = nt.nodes.new("ShaderNodeMixShader")
    camera_only.location = (200, 0)

    # Cycles ignore le backface culling : on le refait dans le shader.
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
    nt.links.new(emit.outputs[0], mix.inputs[1])
    nt.links.new(transp.outputs[0], mix.inputs[2])
    # Visible seulement depuis la caméra : la coque ne fait ni ombre ni reflet.
    nt.links.new(path.outputs["Is Camera Ray"], camera_only.inputs[0])
    nt.links.new(transp.outputs[0], camera_only.inputs[1])
    nt.links.new(mix.outputs[0], camera_only.inputs[2])
    nt.links.new(camera_only.outputs[0], out.inputs["Surface"])
    return mat


def build_group(mat):
    ng = bpy.data.node_groups.new(GROUP_NAME, "GeometryNodeTree")
    ng.is_modifier = True

    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    thickness = ng.interface.new_socket("Epaisseur", in_out="INPUT", socket_type="NodeSocketFloat")
    thickness.subtype = "DISTANCE"
    thickness.default_value = 0.03
    thickness.min_value = 0.0
    # Field : dans le modifier, l'icône attribut permet de choisir un vertex group.
    weight = ng.interface.new_socket("Poids", in_out="INPUT", socket_type="NodeSocketFloat")
    weight.structure_type = "FIELD"
    weight.subtype = "FACTOR"
    weight.default_value = 1.0
    weight.min_value = 0.0
    weight.max_value = 1.0
    weight.description = "Multiplie l'épaisseur. Choisir un vertex group via l'icône attribut ; 0 = pas de contour"
    material = ng.interface.new_socket("Materiau", in_out="INPUT", socket_type="NodeSocketMaterial")
    material.default_value = mat
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    n = ng.nodes
    gin = n.new("NodeGroupInput")
    gin.location = (-800, 0)
    gout = n.new("NodeGroupOutput")
    gout.location = (600, 0)

    # Pas de coque là où le poids est nul : elle se confondrait avec la surface.
    no_weight = n.new("FunctionNodeCompare")
    no_weight.data_type = "FLOAT"
    no_weight.operation = "LESS_EQUAL"
    no_weight.inputs["B"].default_value = 0.0001
    no_weight.location = (-600, 200)
    delete = n.new("GeometryNodeDeleteGeometry")
    delete.domain = "POINT"
    delete.location = (-400, 100)

    normal = n.new("GeometryNodeInputNormal")
    normal.location = (-600, -200)
    weighted = n.new("ShaderNodeMath")
    weighted.operation = "MULTIPLY"
    weighted.location = (-600, -350)
    weighted.label = "Epaisseur x Poids"
    scale = n.new("ShaderNodeVectorMath")
    scale.operation = "SCALE"
    scale.location = (-400, -200)

    set_pos = n.new("GeometryNodeSetPosition")
    set_pos.location = (-200, 0)
    set_pos.label = "Gonfle la coque"
    flip = n.new("GeometryNodeFlipFaces")
    flip.location = (0, 0)
    set_mat = n.new("GeometryNodeSetMaterial")
    set_mat.location = (200, 0)
    join = n.new("GeometryNodeJoinGeometry")
    join.location = (400, 0)

    L = ng.links.new
    L(gin.outputs["Poids"], no_weight.inputs["A"])
    L(gin.outputs["Geometry"], delete.inputs["Geometry"])
    L(no_weight.outputs["Result"], delete.inputs["Selection"])
    L(gin.outputs["Epaisseur"], weighted.inputs[0])
    L(gin.outputs["Poids"], weighted.inputs[1])
    L(normal.outputs["Normal"], scale.inputs[0])
    L(weighted.outputs["Value"], scale.inputs["Scale"])
    L(delete.outputs["Geometry"], set_pos.inputs["Geometry"])
    L(scale.outputs["Vector"], set_pos.inputs["Offset"])
    L(set_pos.outputs["Geometry"], flip.inputs["Mesh"])
    L(flip.outputs["Mesh"], set_mat.inputs["Geometry"])
    L(gin.outputs["Materiau"], set_mat.inputs["Material"])
    # Original + coque retournée.
    L(gin.outputs["Geometry"], join.inputs["Geometry"])
    L(set_mat.outputs["Geometry"], join.inputs["Geometry"])
    L(join.outputs["Geometry"], gout.inputs["Geometry"])
    return ng


def mark_asset(ng):
    ng.asset_mark()
    data = ng.asset_data
    data.catalog_id = CATALOG_ID
    data.author = "Marc Gardent"
    data.description = (
        "Contour par backface culling (inverted hull). Gonfle une copie du mesh, "
        "retourne ses faces et ne garde que les faces arrière. EEVEE et Cycles. "
        "Poids : vertex group qui module l'épaisseur. "
        "A mettre en dernier modifier ; masquer à la caméra les objets des booléens."
    )
    for tag in ("outline", "contour", "npr", "toon", "inverted hull", "backface culling", "vertex weight"):
        data.tags.new(tag, skip_if_exists=True)


def modifier_input(mod, name):
    item = mod.node_group.interface.items_tree[name]
    return getattr(mod.properties.inputs, item.identifier)


def build_demo(ng):
    """Suzanne avec le contour : sert d'aperçu et de scène d'exemple dans le fichier.

    Le vertex group « Contour » va de 0 (menton) à 1 (haut du crâne) : le trait
    s'épaissit vers le haut.
    """
    bpy.ops.mesh.primitive_monkey_add(size=2.0)
    demo = bpy.context.active_object
    demo.name = "Demo Outline"
    zs = [v.co.z for v in demo.data.vertices]
    z_min, z_max = min(zs), max(zs)
    group = demo.vertex_groups.new(name="Contour")
    for v in demo.data.vertices:
        group.add([v.index], (v.co.z - z_min) / (z_max - z_min), "REPLACE")
    demo.modifiers.new("Subdivision", "SUBSURF").levels = 2
    bpy.ops.object.shade_smooth()
    body = bpy.data.materials.new("Demo Citrouille")
    body.diffuse_color = (1.0, 0.35, 0.02, 1.0)
    bsdf = body.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (1.0, 0.35, 0.02, 1.0)
    demo.data.materials.append(body)
    outline = demo.modifiers.new("Outline", "NODES")
    outline.node_group = ng
    modifier_input(outline, "Epaisseur").value = 0.06
    weight = modifier_input(outline, "Poids")
    weight.type = "ATTRIBUTE"
    weight.attribute_name = "Contour"

    bpy.ops.object.camera_add(location=(0, -6.5, 0.3), rotation=(1.53, 0, 0))
    scene = bpy.context.scene
    scene.camera = bpy.context.active_object
    scene.camera.data.lens = 70
    bpy.ops.object.light_add(type="SUN", rotation=(0.8, 0.3, 0.6))
    bpy.context.active_object.data.energy = 4.0


def render_preview(ng):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = PREVIEW_PATH
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(PREVIEW_PATH)
    preview = ng.preview_ensure()
    preview.image_size = img.size
    preview.image_pixels_float = list(img.pixels)
    bpy.data.images.remove(img)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat = build_material()
    ng = build_group(mat)
    mark_asset(ng)
    build_demo(ng)
    render_preview(ng)
    os.makedirs(os.path.dirname(BLEND_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True)
    print("Asset ecrit :", BLEND_PATH)


main()
