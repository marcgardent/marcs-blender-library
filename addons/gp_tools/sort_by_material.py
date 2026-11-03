import bpy
import numpy as np


def sort_drawing(drawing, top_in_front):
    """Réordonne les strokes selon leur slot de matériau. Renvoie True si l'ordre a changé."""
    count = len(drawing.strokes)
    attr = drawing.attributes.get("material_index")
    if count < 2 or attr is None:
        return False
    mat_index = np.empty(count, dtype=np.int32)
    attr.data.foreach_get("value", mat_index)
    # Le dernier stroke dessiné passe devant : le slot 0 (haut de la liste) va à la fin
    key = -mat_index if top_in_front else mat_index
    order = np.argsort(key, kind='stable')  # stable : l'ordre de tracé est gardé dans un même matériau
    if (order == np.arange(count)).all():
        return False
    drawing.reorder_strokes(new_indices=order.tolist())
    return True


class GREASE_PENCIL_OT_sort_by_material(bpy.types.Operator):
    """Réordonne les strokes de chaque calque selon l'ordre de la liste des matériaux"""
    bl_idname = "grease_pencil.sort_strokes_by_material"
    bl_label = "Sort Strokes by Material"
    bl_options = {'REGISTER', 'UNDO'}

    top_in_front: bpy.props.BoolProperty(
        name="Haut de liste devant",
        description="Le premier matériau de la liste est dessiné devant, comme pour les calques",
        default=True,
    )
    all_frames: bpy.props.BoolProperty(
        name="Toutes les frames",
        description="Trie toutes les keyframes, pas seulement la frame courante",
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
        sorted_count = 0
        for obj in self.target_objects(context):
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
                    sorted_count += sort_drawing(fr.drawing, self.top_in_front)
            obj.data.update_tag()

        self.report({'INFO'}, f"{sorted_count} drawing(s) réordonné(s)")
        return {'FINISHED'}


def menu_func(self, context):
    self.layout.operator(GREASE_PENCIL_OT_sort_by_material.bl_idname)


def register():
    bpy.utils.register_class(GREASE_PENCIL_OT_sort_by_material)
    bpy.types.VIEW3D_MT_edit_greasepencil_stroke.append(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_edit_greasepencil_stroke.remove(menu_func)
    bpy.utils.unregister_class(GREASE_PENCIL_OT_sort_by_material)
