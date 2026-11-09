# lang/ is pure Python (no bpy), host/ turns its output into node trees,
# ui/ is the text editor side: operators, panels and the selection sync.


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
