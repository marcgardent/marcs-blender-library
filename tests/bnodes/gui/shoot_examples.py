"""Build the examples of docs/exemples in a real Blender window, check what they make, take their pictures.

    blender --factory-startup --python tests/bnodes/gui/shoot_examples.py [-- docs/images]

For each example: a small scene to work on, the tree as a modifier, a check
that it makes geometry, then a picture of the 3D view and of the node editor.
Prints PASS/FAIL lines and exits 1 on a failure.
"""

import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Euler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

import bnodes  # noqa: E402
from bnodes.ui import actions  # noqa: E402

EXAMPLES = ROOT / "docs" / "exemples"
SHOTS = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else None
WIDTH = 1200  # pictures are scaled down to this width
failures = []
areas = {}


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def window_region(area):
    return next(r for r in area.regions if r.type == "WINDOW")


# Scenes

def material(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    return mat


def mesh_object(name, verts, faces, color):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.shade_smooth()
    mesh.materials.append(material(name, color))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def terrain(name, n, size, height, color=(0.55, 0.45, 0.32)):
    step = size / n
    verts = [(-size / 2 + i * step, -size / 2 + j * step, height(-size / 2 + i * step, -size / 2 + j * step))
             for j in range(n + 1) for i in range(n + 1)]
    faces = [(j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i)
             for j in range(n) for i in range(n)]
    return mesh_object(name, verts, faces, color)


def blade():
    verts = [(-0.02, 0, 0), (0.02, 0, 0), (0, 0.01, 0.35)]
    obj = mesh_object("Brin", verts, [(0, 1, 2)], (0.25, 0.6, 0.15))
    obj.location = (0, 0, -20)
    obj.hide_render = obj.hide_viewport = True
    return obj


def curve_object(name, points):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1.0)
    data.materials.append(material(name, (0.3, 0.45, 0.7)))
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def scene_for(name):
    """(object to modify, {input name: value})."""
    if name == "herbe":
        sol = terrain("Sol", 60, 12.0, lambda x, y: 2.2 * math.sin(x * 0.55) * math.cos(y * 0.4) + 0.2 * x)
        return sol, {"brin": blade(), "Pente max": 22.0, "densité": 150.0}
    if name == "serpent":
        points = [(-4 + t * 0.08, 1.8 * math.sin(t * 0.05), 0.0) for t in range(101)]
        return curve_object("Courbe", points), {"amplitude": 0.4, "ondulations": 6.0, "épaisseur": 0.12}
    sol = terrain("Sol", 2, 10.0, lambda x, y: 0.0)
    return sol, {"densité": 0.35, "graine": 3}


def build(name):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    text = bpy.data.texts.new(f"{name}.bn")
    text.from_string((EXAMPLES / f"{name}.bn").read_text())
    trees = actions.text_to_tree(text)
    tree = trees[-1]
    obj, values = scene_for(name)
    mod = obj.modifiers.new(tree.name, "NODES")
    mod.node_group = tree
    # Blender 5.2 keeps modifier inputs in mod.properties.inputs, one struct per socket identifier
    for item in tree.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name in values:
            getattr(mod.properties.inputs, item.identifier).value = values[item.name]
    obj.update_tag()
    return obj, tree


# Steps

def close_splash():
    bpy.ops.wm.read_homefile()
    return 0.5


def setup():
    bnodes.register()
    win = bpy.context.window
    view = next(a for a in win.screen.areas if a.type == "VIEW_3D")
    with bpy.context.temp_override(window=win, area=view, region=window_region(view)):
        bpy.ops.screen.area_split(direction="VERTICAL", factor=0.5)
    left, right = sorted((a for a in win.screen.areas if a.type == "VIEW_3D"), key=lambda a: a.x)
    right.type = "NODE_EDITOR"
    right.ui_type = "GeometryNodeTree"
    space3d = left.spaces.active
    space3d.overlay.show_overlays = False
    space3d.shading.type = "SOLID"
    space3d.shading.light = "STUDIO"
    space3d.shading.color_type = "MATERIAL"
    space3d.shading.show_cavity = True
    space3d.show_gizmo = False
    space3d.show_region_header = space3d.show_region_toolbar = space3d.show_region_ui = False
    # No grid dots: the pictures are cropped to what stands out of the background
    theme = bpy.context.preferences.themes[0].node_editor
    theme.grid = theme.space.back[:3]
    nodes = right.spaces.active
    nodes.show_region_header = nodes.show_region_toolbar = nodes.show_region_ui = False
    areas.update(view=left, nodes=right)
    return 0.5


def make_steps(name):
    state = {}

    def show():
        obj, tree = build(name)
        state.update(obj=obj, tree=tree)
        geometry = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).evaluated_geometry()
        mesh, instances = geometry.mesh, geometry.instances_pointcloud()
        base = len(obj.data.vertices) if obj.type == "MESH" else 0
        count = (len(mesh.vertices) if mesh else 0) + (len(instances.points) if instances else 0)
        check(f"{name} makes geometry", count > base, f"{base} -> {count}")
        nodes = areas["nodes"].spaces.active
        nodes.pin = True
        nodes.node_tree = tree
        r3d = areas["view"].spaces.active.region_3d
        r3d.view_perspective = "PERSP"
        r3d.view_rotation = Euler((math.radians(55), 0, math.radians(30))).to_quaternion()
        r3d.view_location = (0, 0, 0.3)
        r3d.view_distance = {"herbe": 12.5, "serpent": 8.0, "rochers": 11.0}[name]
        return 0.6

    def frame():
        with bpy.context.temp_override(window=bpy.context.window, area=areas["nodes"],
                                       region=window_region(areas["nodes"])):
            bpy.ops.node.view_all()
        return 0.8

    def shoot():
        if SHOTS:
            SHOTS.mkdir(parents=True, exist_ok=True)
            for kind, area in (("vue", areas["view"]), ("noeuds", areas["nodes"])):
                path = SHOTS / f"{name}-{kind}.png"
                with bpy.context.temp_override(window=bpy.context.window, area=area):
                    bpy.ops.screen.screenshot_area(filepath=str(path))
                shrink(path)
                print("SHOT", path)
        return 0.3

    return [show, frame, shoot]


def shrink(path, margin=24):
    """Crop the picture to what differs from its background, then scale it down to WIDTH."""
    import numpy as np
    img = bpy.data.images.load(str(path))
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    background = px[h // 2, w - 12]
    # Away from the area's border and its header strip (Blender pixels go bottom up); a row or
    # a column counts when enough of it differs, which leaves out the grid dots and the dithering
    inner = np.zeros((h, w), dtype=bool)
    inner[10:h - 60, 10:w - 10] = True
    differs = (np.abs(px[:, :, :3] - background[:3]).max(axis=2) > 0.04) & inner
    rows = np.nonzero(differs.sum(axis=1) > w // 50)[0]
    cols = np.nonzero(differs.sum(axis=0) > h // 50)[0]
    y0, y1 = max(0, rows.min() - margin), min(h, rows.max() + margin)
    x0, x1 = max(0, cols.min() - margin), min(w, cols.max() + margin)
    crop = px[y0:y1, x0:x1].copy()
    bpy.data.images.remove(img)
    out = bpy.data.images.new("shot", x1 - x0, y1 - y0)
    out.pixels.foreach_set(crop.ravel())
    if out.size[0] > WIDTH:
        out.scale(WIDTH, round(out.size[1] * WIDTH / out.size[0]))
    out.filepath_raw = str(path)
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)


def finish():
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.stdout.flush()
    os._exit(1 if failures else 0)


STEPS = [close_splash, setup] + [s for n in ("herbe", "serpent", "rochers") for s in make_steps(n)]


def run():
    step = STEPS.pop(0)
    try:
        delay = step()
    except Exception as e:
        import traceback
        traceback.print_exc()
        check(step.__name__, False, repr(e))
        return finish()
    if not STEPS:
        return finish()
    return delay


bpy.app.timers.register(run, first_interval=1.0, persistent=True)
