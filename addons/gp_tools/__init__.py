from . import clean_overlaps, sort_by_material

# Un module par outil, chacun avec son register / unregister
modules = (clean_overlaps, sort_by_material)


def register():
    for mod in modules:
        mod.register()


def unregister():
    for mod in reversed(modules):
        mod.unregister()
