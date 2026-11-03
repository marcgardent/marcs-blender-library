import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator, Panel, PropertyGroup


def get_image_paint_settings(context):
    """Retrieves tool_settings.image_paint safely across scene and context."""
    ts = getattr(context, "tool_settings", None)
    if not ts and hasattr(context, "scene"):
        ts = context.scene.tool_settings
    return getattr(ts, "image_paint", None) if ts else None


def get_current_brush_size(context):
    """Reads the active brush radius, accounting for unified paint settings in Blender 5."""
    ip = get_image_paint_settings(context)
    if not ip:
        return None

    # Check Blender 5.x mode-specific unified paint settings
    ups_ip = getattr(ip, "unified_paint_settings", None)
    if ups_ip and getattr(ups_ip, "use_unified_size", False):
        return ups_ip.size

    # Check root unified settings if present
    ts = getattr(context, "tool_settings", None) or getattr(context.scene, "tool_settings", None)
    ups_root = getattr(ts, "unified_paint_settings", None) if ts else None
    if ups_root and getattr(ups_root, "use_unified_size", False):
        return ups_root.size

    # Fallback to direct brush size
    if ip.brush:
        return ip.brush.size

    return None


def set_current_brush_size(context, size_px):
    """
    Applies the new radius simultaneously to the brush and all unified paint
    structs in Blender 5 so the stroke physically changes regardless of settings.
    """
    ip = get_image_paint_settings(context)
    if not ip:
        return False

    # 1. Update the active brush datablock directly
    if ip.brush and hasattr(ip.brush, "size"):
        ip.brush.size = size_px

    # 2. Update Blender 5.x mode-specific unified paint settings
    ups_ip = getattr(ip, "unified_paint_settings", None)
    if ups_ip and hasattr(ups_ip, "size"):
        ups_ip.size = size_px

    # 3. Update root unified paint settings (if defined)
    ts = getattr(context, "tool_settings", None) or getattr(context.scene, "tool_settings", None)
    if ts:
        ups_root = getattr(ts, "unified_paint_settings", None)
        if ups_root and hasattr(ups_root, "size"):
            ups_root.size = size_px

    return True


def get_view3d_region(context):
    """Finds the active 3D Viewport Region3D even during background timer callbacks."""
    # Direct space inspection
    sd = getattr(context, "space_data", None)
    if sd and getattr(sd, "type", "") == 'VIEW_3D' and getattr(sd, "region_3d", None):
        return sd.region_3d

    # Screen traversal
    wm = getattr(context, "window_manager", None) or (bpy.data.window_managers[0] if bpy.data.window_managers else None)
    if not wm:
        return None

    for win in wm.windows:
        screen = win.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D' and space.region_3d:
                        return space.region_3d
    return None


def force_viewport_redraw(context):
    """Forces all 3D viewports and regions to redraw immediately, updating the brush circle cursor."""
    wm = getattr(context, "window_manager", None) or (bpy.data.window_managers[0] if bpy.data.window_managers else None)
    if not wm:
        return

    for win in wm.windows:
        screen = win.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


class VIEW3D_OT_constant_brush_engine(Operator):
    """Background modal operator continuously syncing Texture Paint brush size with view distance."""
    bl_idname = "view3d.constant_brush_engine"
    bl_label = "Texture Paint Constant Engine"
    bl_options = {'INTERNAL'}

    _timer = None

    def modal(self, context, event):
        props = getattr(context.scene, "constant_brush_props", None)
        if not props or not props.is_enabled:
            self.cancel(context)
            return {'FINISHED'}

        if event.type == 'TIMER':
            # Run only while Texture Paint is active
            if context.mode != 'PAINT_TEXTURE':
                return {'PASS_THROUGH'}

            r3d = get_view3d_region(context)
            current_size = get_current_brush_size(context)

            if r3d and current_size is not None:
                current_dist = r3d.view_distance

                # Initialize world scale baseline
                if props.reference_world_size <= 0:
                    props.reference_world_size = float(current_size) * current_dist
                    props.last_view_distance = current_dist
                    props.last_pixel_size = current_size

                # Case 1: Artist manually changed size (F shortcut or panel slider)
                if abs(props.last_pixel_size - current_size) >= 1 and abs(current_dist - props.last_view_distance) < 0.001:
                    props.reference_world_size = float(current_size) * current_dist
                    props.last_pixel_size = current_size

                # Case 2: Viewport zoom changed (view_distance difference)
                elif abs(current_dist - props.last_view_distance) > 0.0005 and current_dist > 0.0001:
                    target_px = int(round(props.reference_world_size / current_dist))
                    clamped_px = max(props.min_size, min(target_px, props.max_size))

                    if current_size != clamped_px:
                        set_current_brush_size(context, clamped_px)
                        props.last_pixel_size = clamped_px
                        props.last_view_distance = current_dist
                        force_viewport_redraw(context)

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        props = context.scene.constant_brush_props
        r3d = get_view3d_region(context)
        current_size = get_current_brush_size(context)

        if r3d and current_size is not None:
            props.last_view_distance = r3d.view_distance
            props.last_pixel_size = current_size
            props.reference_world_size = float(current_size) * r3d.view_distance

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.02, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = getattr(context, "window_manager", None)
        if wm and self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None


class VIEW3D_OT_toggle_constant_brush(Operator):
    """Toggle constant brush scaling on or off"""
    bl_idname = "view3d.toggle_constant_brush"
    bl_label = "Toggle Constant Brush"

    def execute(self, context):
        props = context.scene.constant_brush_props
        props.is_enabled = not props.is_enabled

        if props.is_enabled:
            r3d = get_view3d_region(context)
            current_size = get_current_brush_size(context)
            if r3d and current_size is not None:
                props.last_view_distance = r3d.view_distance
                props.last_pixel_size = current_size
                props.reference_world_size = float(current_size) * r3d.view_distance

            bpy.ops.view3d.constant_brush_engine('INVOKE_DEFAULT')
            self.report({'INFO'}, "Texture Paint Constant Size: ENABLED")
        else:
            self.report({'INFO'}, "Texture Paint Constant Size: DISABLED")

        return {'FINISHED'}


class ConstantBrushProperties(PropertyGroup):
    is_enabled: BoolProperty(
        name="Enabled",
        description="Preserves physical paint stroke size across camera zoom levels",
        default=False
    )
    reference_world_size: FloatProperty(
        name="Reference World Size",
        description="Target physical scale in 3D scene units",
        default=100.0
    )
    last_view_distance: FloatProperty(
        name="Last View Distance",
        default=1.0
    )
    last_pixel_size: IntProperty(
        name="Last Pixel Size",
        default=50
    )
    min_size: IntProperty(
        name="Min Radius (px)",
        description="Minimum allowed brush radius in pixels",
        default=2,
        min=1,
        max=500
    )
    max_size: IntProperty(
        name="Max Radius (px)",
        description="Maximum allowed brush radius in pixels",
        default=3000,
        min=50,
        max=10000
    )


class VIEW3D_PT_constant_brush_panel(Panel):
    """UI Panel in View3D > Sidebar (N) > Tool tab"""
    bl_label = "Constant Brush Size (TPaint)"
    bl_idname = "VIEW3D_PT_constant_brush_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tool"

    def draw(self, context):
        layout = self.layout
        props = getattr(context.scene, "constant_brush_props", None)
        if not props:
            return

        box = layout.box()
        col = box.column(align=True)

        if props.is_enabled:
            col.operator(
                "view3d.toggle_constant_brush",
                text="Constant Size: ON",
                icon='CHECKBOX_HLT',
                depress=True
            )
        else:
            col.operator(
                "view3d.toggle_constant_brush",
                text="Constant Size: OFF",
                icon='CHECKBOX_DEHLT',
                depress=False
            )

        col = layout.column(align=True)
        col.prop(props, "min_size")
        col.prop(props, "max_size")

        current_size = get_current_brush_size(context)
        if current_size is not None:
            layout.label(text=f"Active Radius: {current_size} px", icon='BRUSH_DATA')
        else:
            layout.label(text="No active Texture Paint brush", icon='INFO')


classes = (
    ConstantBrushProperties,
    VIEW3D_OT_constant_brush_engine,
    VIEW3D_OT_toggle_constant_brush,
    VIEW3D_PT_constant_brush_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.constant_brush_props = bpy.props.PointerProperty(type=ConstantBrushProperties)

def unregister():
    if hasattr(bpy.types.Scene, "constant_brush_props"):
        del bpy.types.Scene.constant_brush_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
