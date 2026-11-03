import bpy
import numpy as np
from mathutils.kdtree import KDTree

# Composantes et clé foreach par type d'attribut
ATTR_LAYOUT = {
    'FLOAT': ("value", 1, np.float32),
    'INT': ("value", 1, np.int32),
    'INT8': ("value", 1, np.int8),
    'BOOLEAN': ("value", 1, bool),
    'FLOAT2': ("vector", 2, np.float32),
    'INT32_2D': ("value", 2, np.int32),
    'FLOAT_VECTOR': ("vector", 3, np.float32),
    'FLOAT_COLOR': ("color", 4, np.float32),
    'BYTE_COLOR': ("color", 4, np.float32),
    'QUATERNION': ("value", 4, np.float32),
    'FLOAT4X4': ("value", 16, np.float32),
}

# Les Bézier et NURBS ne passent pas par leurs points de contrôle : on n'y touche pas
SEGMENT_TYPES = {0, 1}  # CATMULL_ROM, POLY


def read_attributes(drawing):
    """Copie numpy de tous les attributs point et courbe du drawing."""
    out = {}
    for attr in drawing.attributes:
        if attr.domain not in {'POINT', 'CURVE'} or attr.data_type not in ATTR_LAYOUT:
            continue
        key, comps, dtype = ATTR_LAYOUT[attr.data_type]
        buf = np.empty(len(attr.data) * comps, dtype=dtype)
        attr.data.foreach_get(key, buf)
        out[attr.name] = (attr.domain, attr.data_type, buf.reshape(-1, comps))
    return out


def point_clusters(positions, tolerance):
    """Regroupe les points à moins de `tolerance` les uns des autres (union-find)."""
    n = len(positions)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tree = KDTree(n)
    for i, co in enumerate(positions):
        tree.insert(co, i)
    tree.balance()
    for i, co in enumerate(positions):
        for _co, j, _dist in tree.find_range(co, tolerance):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[max(ri, rj)] = min(ri, rj)
    return [find(i) for i in range(n)]


def material_keys(obj, count):
    """Clé de comparaison par slot : le matériau lui-même, pour que deux slots du même matériau se confondent."""
    keys = []
    for i in range(count):
        mat = obj.material_slots[i].material if i < len(obj.material_slots) else None
        keys.append(mat.name_full if mat else ("slot", i))
    return keys


def clean_drawing(obj, drawing, tolerance):
    """Supprime les segments superposés de même matériau. Renvoie le nombre de segments retirés."""
    attrs = read_attributes(drawing)
    if "position" not in attrs:
        return 0
    offsets = np.empty(len(drawing.curve_offsets), dtype=np.int32)
    drawing.curve_offsets.foreach_get("value", offsets)
    curve_count = len(offsets) - 1
    if curve_count == 0:
        return 0

    positions = attrs["position"][2]
    cluster = point_clusters(positions, tolerance)
    mat_index = attrs["material_index"][2][:, 0] if "material_index" in attrs else np.zeros(curve_count, int)
    cyclic = attrs["cyclic"][2][:, 0] if "cyclic" in attrs else np.zeros(curve_count, bool)
    ctype = attrs["curve_type"][2][:, 0] if "curve_type" in attrs else np.zeros(curve_count, int)
    mkeys = material_keys(obj, int(mat_index.max()) + 1)

    seen = set()
    removed = 0
    runs = []  # (courbe source, indices de points, cyclique)
    for c in range(curve_count):
        start, end = int(offsets[c]), int(offsets[c + 1])
        pts = list(range(start, end))
        if len(pts) < 2 or int(ctype[c]) not in SEGMENT_TYPES:
            runs.append((c, pts, bool(cyclic[c])))
            continue

        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        if cyclic[c] and len(pts) > 2:
            segs.append((pts[-1], pts[0]))
        keep = []
        for a, b in segs:
            ca, cb = cluster[a], cluster[b]
            if ca == cb:  # segment de longueur nulle : rien à comparer
                keep.append(True)
                continue
            key = (mkeys[mat_index[c]], min(ca, cb), max(ca, cb))
            keep.append(key not in seen)
            seen.add(key)

        if all(keep):
            runs.append((c, pts, bool(cyclic[c])))
            continue
        removed += keep.count(False)

        # Stroke fermé : on le déroule à partir d'un segment retiré pour en faire une suite ouverte
        if len(segs) > len(pts) - 1:
            first = keep.index(False) + 1
            segs = segs[first:] + segs[:first]
            keep = keep[first:] + keep[:first]

        run = []
        for (a, b), k in zip(segs, keep):
            if k:
                if not run:
                    run.append(a)
                run.append(b)
            elif run:
                runs.append((c, run, False))
                run = []
        if run:
            runs.append((c, run, False))

    if removed == 0:
        return 0

    point_src = np.array([p for _c, run, _cy in runs for p in run], dtype=np.int64)
    curve_src = np.array([c for c, _run, _cy in runs], dtype=np.int64)
    new_cyclic = np.array([cy for _c, _run, cy in runs], dtype=bool)

    drawing.remove_strokes(indices=list(range(curve_count)))
    if runs:
        drawing.add_strokes(sizes=[len(run) for _c, run, _cy in runs])
    for name, (domain, data_type, buf) in attrs.items():
        data = buf[point_src] if domain == 'POINT' else buf[curve_src]
        if name == "cyclic":
            data = new_cyclic.reshape(-1, 1)
        attr = drawing.attributes.get(name) or drawing.attributes.new(name, data_type, domain)
        key = ATTR_LAYOUT[data_type][0]
        attr.data.foreach_set(key, data.ravel())
    if "cyclic" not in attrs and new_cyclic.any():
        drawing.attributes.new("cyclic", 'BOOLEAN', 'CURVE').data.foreach_set("value", new_cyclic)
    drawing.tag_positions_changed()
    return removed


class GREASE_PENCIL_OT_clean_overlaps(bpy.types.Operator):
    """Supprime les segments superposés entre strokes qui partagent le même matériau"""
    bl_idname = "grease_pencil.clean_overlapping_edges"
    bl_label = "Clean Overlapping Edges"
    bl_options = {'REGISTER', 'UNDO'}

    tolerance: bpy.props.FloatProperty(
        name="Tolérance",
        description="Distance sous laquelle deux points sont considérés comme confondus",
        default=0.001,
        min=0.0,
        soft_max=0.1,
        precision=4,
        subtype='DISTANCE',
    )
    all_frames: bpy.props.BoolProperty(
        name="Toutes les frames",
        description="Nettoie toutes les keyframes, pas seulement la frame courante",
        default=False,
    )

    @staticmethod
    def target_objects(context):
        objects = {o for o in (context.selected_objects or []) if o.type == 'GREASEPENCIL'}
        if context.object and context.object.type == 'GREASEPENCIL':
            objects.add(context.object)
        return objects

    @classmethod
    def poll(cls, context):
        return bool(cls.target_objects(context))

    def execute(self, context):
        objects = self.target_objects(context)
        removed = 0
        for obj in objects:
            done = set()  # un drawing peut être partagé par plusieurs keyframes
            for layer in obj.data.layers:
                if layer.lock:
                    continue
                frames = layer.frames if self.all_frames else [layer.current_frame()]
                for fr in frames:
                    if fr is None or fr.drawing is None:
                        continue
                    ptr = fr.drawing.as_pointer()
                    if ptr in done:
                        continue
                    done.add(ptr)
                    removed += clean_drawing(obj, fr.drawing, self.tolerance)
            obj.data.update_tag()

        self.report({'INFO'}, f"{removed} segment(s) superposé(s) supprimé(s)")
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(GREASE_PENCIL_OT_clean_overlaps.bl_idname)


def register():
    bpy.utils.register_class(GREASE_PENCIL_OT_clean_overlaps)
    bpy.types.VIEW3D_MT_edit_greasepencil_cleanup.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_edit_greasepencil_cleanup.remove(menu_func)
    bpy.utils.unregister_class(GREASE_PENCIL_OT_clean_overlaps)
