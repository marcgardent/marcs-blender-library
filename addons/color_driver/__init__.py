"""Color Driver : une couleur en propriété d'objet, collée en driver sur n'importe quelle couleur.

Properties > Object > Color Drivers : créer une couleur, la copier. Puis clic droit sur une
couleur (matériau, lumière, monde, entrée de modifier…) > Paste Color Driver : chaque canal
reçoit un driver qui lit la couleur de l'objet.
"""
import bpy
from bpy.props import FloatVectorProperty, PointerProperty, StringProperty
from bpy.utils import escape_identifier

COLOR_SUBTYPES = {'COLOR', 'COLOR_GAMMA'}


def prop_path(name):
    return f'["{escape_identifier(name)}"]'


def idprop_subtype(owner, key):
    try:
        return owner.id_properties_ui(key).as_dict().get("subtype")
    except (TypeError, KeyError):
        return None


def is_color_idprop(owner, key):
    value = owner.get(key)
    return (hasattr(value, "to_list") and len(value) in (3, 4)
            and isinstance(value[0], float) and idprop_subtype(owner, key) in COLOR_SUBTYPES)


def color_props(obj):
    """Noms des propriétés couleur de l'objet, dans l'ordre de création."""
    return [key for key in obj.keys() if is_color_idprop(obj, key)]


def source(context):
    """(objet, nom) de la couleur copiée, ou None si elle n'existe plus."""
    wm = context.window_manager
    obj, name = wm.color_driver_object, wm.color_driver_prop
    if obj is None or name not in obj.keys() or not is_color_idprop(obj, name):
        return None
    return obj, name


def hovered(context):
    """(datablock, chemin, taille) de la couleur sous la souris, ou None."""
    ptr = getattr(context, "button_pointer", None)
    prop = getattr(context, "button_prop", None)
    if ptr is None or prop is None:
        return None
    id_ = ptr.id_data
    if id_ is None or id_.library is not None:
        return None

    key = getattr(prop, "identifier", "")
    try:
        if key in ptr.bl_rna.properties:
            # Propriété RNA : base color d'un matériau, couleur de lumière, socket,
            # entrée de modifier Geometry Nodes…
            if (not isinstance(prop, bpy.types.FloatProperty) or prop.subtype not in COLOR_SUBTYPES
                    or prop.array_length not in (3, 4) or prop.is_readonly):
                return None
            return id_, ptr.path_from_id(key), prop.array_length

        # Propriété custom, comme celles que crée ce panneau
        if not is_color_idprop(ptr, key):
            return None
        base = "" if ptr == id_ else ptr.path_from_id()
        return id_, base + prop_path(key), len(ptr[key])
    except (ValueError, AttributeError, TypeError):
        # Struct sans chemin depuis son datablock, ou sans ID properties
        return None


def add_color_drivers(target_id, path, size, src_obj, src_name):
    """Pose un driver par canal sur target_id.path, qui lit src_obj[src_name]. Rend le nombre de canaux."""
    n = min(size, len(src_obj[src_name]))
    for i in range(n):
        target_id.driver_remove(path, i)
        fc = target_id.driver_add(path, i)
        for mod in list(fc.modifiers):
            fc.modifiers.remove(mod)
        drv = fc.driver
        drv.type = 'AVERAGE'
        for var in list(drv.variables):
            drv.variables.remove(var)
        var = drv.variables.new()
        var.name = "c"
        var.type = 'SINGLE_PROP'
        t = var.targets[0]
        t.id_type = 'OBJECT'
        t.id = src_obj
        t.data_path = f"{prop_path(src_name)}[{i}]"
    return n


class OBJECT_OT_color_driver_add(bpy.types.Operator):
    """Ajoute une propriété couleur à l'objet, à copier ensuite en driver"""
    bl_idname = "object.color_driver_add"
    bl_label = "Add Color"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(name="Nom", default="Couleur")
    color: FloatVectorProperty(
        name="Couleur", subtype='COLOR', size=4, min=0.0, soft_max=1.0,
        default=(1.0, 1.0, 1.0, 1.0),
    )

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.library is None

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        obj = context.object
        base = self.name.strip() or "Couleur"
        name, k = base, 1
        while name in obj.keys():
            name = f"{base}.{k:03d}"
            k += 1
        obj[name] = list(self.color)
        obj.id_properties_ui(name).update(
            subtype='COLOR', min=0.0, soft_min=0.0, soft_max=1.0, default=list(self.color))
        obj.property_overridable_library_set(prop_path(name), True)
        set_source(context, obj, name)
        self.report({'INFO'}, f"« {name} » créée et copiée : clic droit sur une couleur > Paste Color Driver")
        return {'FINISHED'}


def set_source(context, obj, name):
    wm = context.window_manager
    wm.color_driver_object = obj
    wm.color_driver_prop = name


class OBJECT_OT_color_driver_copy(bpy.types.Operator):
    """Copie la couleur comme driver : clic droit sur une autre couleur > Paste Color Driver"""
    bl_idname = "object.color_driver_copy"
    bl_label = "Copy Color Driver"

    name: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def execute(self, context):
        obj = context.object
        if not is_color_idprop(obj, self.name):
            self.report({'ERROR'}, f"« {self.name} » n'est pas une couleur de {obj.name}")
            return {'CANCELLED'}
        set_source(context, obj, self.name)
        self.report({'INFO'}, f"{obj.name} › {self.name} copiée : clic droit sur une couleur > Paste Color Driver")
        return {'FINISHED'}


class OBJECT_OT_color_driver_remove(bpy.types.Operator):
    """Supprime la propriété couleur (les drivers qui la lisent deviennent invalides)"""
    bl_idname = "object.color_driver_remove"
    bl_label = "Remove Color"
    bl_options = {'REGISTER', 'UNDO'}

    name: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.library is None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title=f"Supprimer « {self.name} » ?",
            message="Les drivers qui la lisent deviendront invalides.", confirm_text="Supprimer")

    def execute(self, context):
        obj = context.object
        if self.name in obj.keys():
            del obj[self.name]
        obj.update_tag()
        return {'FINISHED'}


class ANIM_OT_color_driver_paste(bpy.types.Operator):
    """Pose sur cette couleur un driver par canal, qui lit la couleur copiée"""
    bl_idname = "anim.color_driver_paste"
    bl_label = "Paste Color Driver"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return source(context) is not None and hovered(context) is not None

    def execute(self, context):
        src_obj, src_name = source(context)
        target_id, path, size = hovered(context)
        if target_id == src_obj and path == prop_path(src_name):
            self.report({'ERROR'}, "Une couleur ne peut pas se lire elle-même")
            return {'CANCELLED'}
        n = add_color_drivers(target_id, path, size, src_obj, src_name)
        target_id.update_tag()
        context.view_layer.update()
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        self.report({'INFO'}, f"{n} driver(s) : {target_id.name} lit {src_obj.name} › {src_name}")
        return {'FINISHED'}


class ANIM_OT_color_driver_copy_hovered(bpy.types.Operator):
    """Copie cette propriété couleur de l'objet comme driver"""
    bl_idname = "anim.color_driver_copy_hovered"
    bl_label = "Copy as Color Driver"

    @classmethod
    def poll(cls, context):
        return hovered_object_color(context) is not None

    def execute(self, context):
        obj, name = hovered_object_color(context)
        set_source(context, obj, name)
        self.report({'INFO'}, f"{obj.name} › {name} copiée : clic droit sur une couleur > Paste Color Driver")
        return {'FINISHED'}


def hovered_object_color(context):
    """(objet, nom) quand la souris est sur une propriété couleur custom d'un objet."""
    h = hovered(context)
    if h is None:
        return None
    id_, path, _ = h
    if not isinstance(id_, bpy.types.Object) or not path.startswith('["'):
        return None
    for key in color_props(id_):
        if prop_path(key) == path:
            return id_, key
    return None


class OBJECT_PT_color_driver(bpy.types.Panel):
    bl_label = "Color Drivers"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        obj = context.object
        src = source(context)

        layout.operator(OBJECT_OT_color_driver_add.bl_idname, icon='ADD')
        names = color_props(obj)
        if names:
            col = layout.column(align=True)
            for name in names:
                row = col.row(align=True)
                row.prop(obj, prop_path(name), text=name)
                op = row.operator(OBJECT_OT_color_driver_copy.bl_idname, text="", icon='COPYDOWN',
                                  depress=src == (obj, name))
                op.name = name
                op = row.operator(OBJECT_OT_color_driver_remove.bl_idname, text="", icon='X')
                op.name = name

        if src:
            box = layout.box()
            box.label(text=f"Copiée : {src[0].name} › {src[1]}", icon='DRIVER')
            box.label(text="Clic droit sur une couleur > Paste Color Driver")


def context_menu(self, context):
    paste = source(context) is not None and hovered(context) is not None
    copy = hovered_object_color(context) is not None
    if not (paste or copy):
        return
    layout = self.layout
    layout.separator()
    if copy:
        layout.operator(ANIM_OT_color_driver_copy_hovered.bl_idname, icon='COPYDOWN')
    if paste:
        layout.operator(ANIM_OT_color_driver_paste.bl_idname, icon='DRIVER')


classes = (
    OBJECT_OT_color_driver_add,
    OBJECT_OT_color_driver_copy,
    OBJECT_OT_color_driver_remove,
    ANIM_OT_color_driver_paste,
    ANIM_OT_color_driver_copy_hovered,
    OBJECT_PT_color_driver,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.color_driver_object = PointerProperty(type=bpy.types.Object)
    bpy.types.WindowManager.color_driver_prop = StringProperty()
    bpy.types.UI_MT_button_context_menu.append(context_menu)


def unregister():
    bpy.types.UI_MT_button_context_menu.remove(context_menu)
    del bpy.types.WindowManager.color_driver_prop
    del bpy.types.WindowManager.color_driver_object
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
