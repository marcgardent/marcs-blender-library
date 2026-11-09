import bpy

from . import operators, panels, sync

classes = operators.classes + panels.classes

_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.NodeTree.bnodes_text = bpy.props.PointerProperty(
        type=bpy.types.Text, name="Text", description="The .bn text this tree is built from")
    bpy.types.WindowManager.bnodes_sync = bpy.props.BoolProperty(
        name="Sync Selection", default=True,
        description="A node and its line follow each other between the text and node editors")

    # Ctrl+Enter builds; Alt+P stays Python's. The poll lets other texts through.
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new("Text", space_type="TEXT_EDITOR")
        _keymaps.append((km, km.keymap_items.new("bnodes.text_to_tree", "RET", "PRESS", ctrl=True)))
    sync.register()


def unregister():
    sync.unregister()
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    del bpy.types.WindowManager.bnodes_sync
    del bpy.types.NodeTree.bnodes_text
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
