"""Shortcuts of the Text Editor; the operators' polls let other texts through."""

import bpy

from . import prefs

_items = []


def bind():
    unbind()
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return  # no add-on keyconfig in background mode
    km = kc.keymaps.new("Text", space_type="TEXT_EDITOR")
    # Ctrl+Enter builds; Alt+P stays Python's
    _items.append((km, km.keymap_items.new("bnodes.text_to_tree", "RET", "PRESS", ctrl=True)))
    mod = prefs.get().complete_key
    _items.append((km, km.keymap_items.new("bnodes.complete", "SPACE", "PRESS",
                                           alt=mod == "ALT", shift=mod == "SHIFT", ctrl=mod == "CTRL")))


def unbind():
    for km, kmi in _items:
        km.keymap_items.remove(kmi)
    _items.clear()
