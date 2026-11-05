import bpy
from bpy_extras import anim_utils

EPS = 1e-3
# Frames hors de la timeline (Blender borne à -1048574) où garer les frames Grease Pencil
GP_TEMP = -1_000_000
GP_PARK = -1_040_000


def scene_ids(scene):
    """Datablocks de la scène qui peuvent porter des keys, sans doublon."""
    ids = [scene, scene.world, scene.world and scene.world.node_tree]
    for ob in scene.objects:
        ids += [ob, ob.data, getattr(ob.data, "shape_keys", None)]
        for slot in ob.material_slots:
            ids += [slot.material, slot.material and slot.material.node_tree]
        ids += [ps.settings for ps in ob.particle_systems]
    seen = set()
    for id_ in ids:
        if id_ is not None and id_.as_pointer() not in seen:
            seen.add(id_.as_pointer())
            yield id_


def on_marker(x, frames):
    f = round(x)
    return f in frames and abs(x - f) < EPS


class CurveKeys:
    """Keys d'une F-curve posées sur un marker. Les valeurs d'origine servent à chaque pas."""

    def __init__(self, fc, moved):
        self.fc = fc
        self.moved = moved
        n = len(fc.keyframe_points)
        self.orig = {}
        for attr in ("co", "handle_left", "handle_right"):
            values = [0.0] * (2 * n)
            fc.keyframe_points.foreach_get(attr, values)
            self.orig[attr] = values

    @classmethod
    def collect(cls, fc, frames):
        if fc.lock:
            return None
        n = len(fc.keyframe_points)
        co = [0.0] * (2 * n)
        fc.keyframe_points.foreach_get("co", co)
        moved = [i for i in range(n) if on_marker(co[2 * i], frames)]
        return cls(fc, moved) if moved else None

    def apply(self, delta):
        # Pas de tri pendant le déplacement : les index restent ceux du départ
        for attr, orig in self.orig.items():
            values = orig.copy()
            for i in self.moved:
                values[2 * i] += delta
            self.fc.keyframe_points.foreach_set(attr, values)

    def finish(self, delta):
        if delta:
            # Une key déplacée remplace la key fixe qu'elle recouvre, comme le G natif
            co = self.orig["co"]
            targets = {round((co[2 * i] + delta) / EPS) for i in self.moved}
            moved = set(self.moved)
            covered = [i for i in range(len(co) // 2)
                       if i not in moved and round(co[2 * i] / EPS) in targets]
            kps = self.fc.keyframe_points
            for i in reversed(covered):
                kps.remove(kps[i], fast=True)
        self.fc.update()


class LayerFrames:
    """Frames d'un calque Grease Pencil posées sur un marker."""

    def __init__(self, layer, moved, others):
        self.layer = layer
        self.moved = moved
        self.others = others
        self.delta = 0
        self.parked = {}  # frame fixe recouverte -> frame où elle est garée

    @classmethod
    def collect(cls, layer, frames):
        if layer.lock:
            return None
        numbers = {fr.frame_number for fr in layer.frames}
        moved = sorted(numbers & frames)
        return cls(layer, moved, numbers - frames) if moved else None

    def apply(self, delta):
        if delta == self.delta:
            return
        frames = self.layer.frames
        # move() refuse une frame occupée : on écarte tout, puis on repose
        for k, f in enumerate(self.moved):
            frames.move(f + self.delta, GP_TEMP - k)
        for f, p in self.parked.items():
            frames.move(p, f)
        self.parked.clear()
        for f in self.moved:
            t = f + delta
            if t in self.others:
                p = GP_PARK - len(self.parked)
                frames.move(t, p)
                self.parked[t] = p
        for k, f in enumerate(self.moved):
            frames.move(GP_TEMP - k, f + delta)
        self.delta = delta

    def finish(self, delta):
        for p in self.parked.values():
            self.layer.frames.remove(p)
        self.parked.clear()


class MARKER_OT_move_with_keys(bpy.types.Operator):
    """Déplace les markers sélectionnés et toutes les keys posées sur eux"""
    bl_idname = "marker.move_with_keys"
    bl_label = "Move Markers with Keys"
    bl_options = {'REGISTER', 'UNDO'}

    frames: bpy.props.IntProperty(
        name="Frames",
        description="Décalage en frames",
        default=0,
    )

    @classmethod
    def poll(cls, context):
        scene = context.scene
        if scene is None or scene.tool_settings.lock_markers:
            return False
        return any(m.select for m in scene.timeline_markers)

    def collect(self, context):
        scene = context.scene
        self.markers = [(m, m.frame) for m in scene.timeline_markers if m.select]
        frames = {f for _, f in self.markers}
        self.items = []
        self.grease_pencils = []
        bags = set()
        for id_ in scene_ids(scene):
            ad = getattr(id_, "animation_data", None)
            if ad and ad.action and ad.action_slot and not ad.action.library:
                bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
                if bag and bag.as_pointer() not in bags:
                    bags.add(bag.as_pointer())
                    self.items += filter(None, (CurveKeys.collect(fc, frames) for fc in bag.fcurves))
            if isinstance(id_, bpy.types.GreasePencil) and not id_.library:
                self.grease_pencils.append(id_)
                self.items += filter(None, (LayerFrames.collect(layer, frames) for layer in id_.layers))
        self.key_count = sum(len(item.moved) for item in self.items)

    def apply(self, context, delta):
        for marker, frame in self.markers:
            marker.frame = frame + delta
        for item in self.items:
            item.apply(delta)
        for gp in self.grease_pencils:
            gp.update_tag()
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()

    def finish(self, context, delta):
        for item in self.items:
            item.finish(delta)
        scene = context.scene
        scene.frame_set(scene.frame_current, subframe=scene.frame_current_final % 1)

    def report_done(self):
        self.report({'INFO'}, f"{len(self.markers)} marker(s), {self.key_count} key(s) décalé(s) de {self.frames}")

    def execute(self, context):
        self.collect(context)
        self.apply(context, self.frames)
        self.finish(context, self.frames)
        self.report_done()
        return {'FINISHED'}

    def invoke(self, context, event):
        region = context.region
        if region is None or region.type != 'WINDOW' or not hasattr(region, "view2d"):
            return self.execute(context)
        self.collect(context)
        self.start_x = self.view_x(context, event)
        self.typed = ""
        self.frames = 0
        context.window_manager.modal_handler_add(self)
        self.update_header(context)
        return {'RUNNING_MODAL'}

    @staticmethod
    def view_x(context, event):
        return context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y)[0]

    def update_header(self, context):
        typed = f"  [{self.typed}]" if self.typed else ""
        context.area.header_text_set(
            f"Markers + keys : {self.frames:+d} frame(s){typed}   ({self.key_count} key(s))")

    def end(self, context):
        context.area.header_text_set(None)

    def modal(self, context, event):
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self.end(context)
            self.finish(context, self.frames)
            self.report_done()
            return {'FINISHED'}
        if event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS':
            self.end(context)
            self.apply(context, 0)
            self.finish(context, 0)
            return {'CANCELLED'}

        # Saisie au clavier, comme G : chiffres, moins pour le signe, retour arrière
        if event.value == 'PRESS' and event.unicode and event.unicode in "0123456789":
            self.typed += event.unicode
        elif event.value == 'PRESS' and event.type in {'MINUS', 'NUMPAD_MINUS'}:
            self.typed = self.typed[1:] if self.typed.startswith("-") else "-" + self.typed
        elif event.value == 'PRESS' and event.type == 'BACK_SPACE':
            self.typed = self.typed[:-1]
        elif event.type != 'MOUSEMOVE':
            return {'RUNNING_MODAL'}

        if self.typed.strip("-"):
            delta = int(self.typed)
        elif self.typed:
            delta = 0
        else:
            delta = round(self.view_x(context, event) - self.start_x)
        if delta != self.frames:
            self.frames = delta
            self.apply(context, delta)
        self.update_header(context)
        return {'RUNNING_MODAL'}


MARKER_MENUS = ("DOPESHEET_MT_marker", "GRAPH_MT_marker", "NLA_MT_marker", "SEQUENCER_MT_marker")


def menu_func(self, context):
    self.layout.operator(MARKER_OT_move_with_keys.bl_idname)


addon_keymaps = []


def register():
    bpy.utils.register_class(MARKER_OT_move_with_keys)
    for name in MARKER_MENUS:
        getattr(bpy.types, name).append(menu_func)

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        # Keymap Markers : actif quand la souris est sur la bande des markers, comme G
        km = kc.keymaps.new(name="Markers", space_type='EMPTY', region_type='WINDOW')
        kmi = km.keymap_items.new(MARKER_OT_move_with_keys.bl_idname, 'G', 'PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for name in MARKER_MENUS:
        getattr(bpy.types, name).remove(menu_func)
    bpy.utils.unregister_class(MARKER_OT_move_with_keys)
