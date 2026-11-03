import bpy

class MESH_OT_quick_flatten_axis(bpy.types.Operator):
    """Aplatit la sélection sur l'axe spécifié (S + Axe + 0 + Enter)"""
    bl_idname = "mesh.quick_flatten_axis"
    bl_label = "Flatten on Axis"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "Axe X"),
            ('Y', "Y", "Axe Y"),
            ('Z', "Z", "Axe Z"),
        ],
        default='Z'
    )

    def execute(self, context):
        if context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "Doit être utilisé en Edit Mode")
            return {'CANCELLED'}

        scale_vec = (
            0.0 if self.axis == 'X' else 1.0,
            0.0 if self.axis == 'Y' else 1.0,
            0.0 if self.axis == 'Z' else 1.0
        )
        constraint = (self.axis == 'X', self.axis == 'Y', self.axis == 'Z')

        bpy.ops.transform.resize(
            value=scale_vec,
            constraint_axis=constraint,
            mirror=False,
            use_proportional_edit=False
        )
        return {'FINISHED'}


class MESH_OT_quick_collapse_merge(bpy.types.Operator):
    """Met à l'échelle à 0 sur tous les axes puis fusionne par distance (S + 0 + Enter + Merge)"""
    bl_idname = "mesh.quick_collapse_merge"
    bl_label = "Scale 0 and Merge by Distance"
    bl_options = {'REGISTER', 'UNDO'}

    distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description="Distance seuil pour fusionner les sommets",
        default=0.0001,
        min=0.0,
        precision=6
    )

    def execute(self, context):
        if context.mode != 'EDIT_MESH':
            self.report({'WARNING'}, "Doit être utilisé en Edit Mode")
            return {'CANCELLED'}

        # 1. Échelle à 0 globale
        bpy.ops.transform.resize(
            value=(0.0, 0.0, 0.0),
            mirror=False,
            use_proportional_edit=False
        )
        # 2. Merge by distance
        bpy.ops.mesh.remove_doubles(threshold=self.distance)
        return {'FINISHED'}


classes = (
    MESH_OT_quick_flatten_axis,
    MESH_OT_quick_collapse_merge,
)

addon_keymaps = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Mesh', space_type='EMPTY')

        # Ctrl + Alt + X
        kmi_x = km.keymap_items.new(MESH_OT_quick_flatten_axis.bl_idname, 'X', 'PRESS', ctrl=True, alt=True)
        kmi_x.properties.axis = 'X'
        addon_keymaps.append((km, kmi_x))

        # Ctrl + Alt + Y
        kmi_y = km.keymap_items.new(MESH_OT_quick_flatten_axis.bl_idname, 'Y', 'PRESS', ctrl=True, alt=True)
        kmi_y.properties.axis = 'Y'
        addon_keymaps.append((km, kmi_y))

        # Ctrl + Alt + Z
        kmi_z = km.keymap_items.new(MESH_OT_quick_flatten_axis.bl_idname, 'Z', 'PRESS', ctrl=True, alt=True)
        kmi_z.properties.axis = 'Z'
        addon_keymaps.append((km, kmi_z))

        # Ctrl + Alt + M
        kmi_merge = km.keymap_items.new(MESH_OT_quick_collapse_merge.bl_idname, 'M', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi_merge))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
