from types import SimpleNamespace

import bpy

# The add-on's own package: "bnodes" from the sources, "bl_ext.<repo>.bnodes" once installed
ROOT = __package__.rpartition(".")[0]

KEYS = (
    ("ALT", "Alt+Espace", "Libre dans Blender ; KDE l'utilise parfois pour KRunner"),
    ("SHIFT", "Maj+Espace", "Toujours libre, moins pratique"),
    ("CTRL", "Ctrl+Espace", "Pris par Blender pour agrandir la zone : ne le remplace que sur les textes .bn"),
)

# When the add-on runs from the sources (tests), it has no preferences entry
DEFAULTS = SimpleNamespace(complete_key="ALT", auto_complete=True, highlight=True)


def get():
    addon = bpy.context.preferences.addons.get(ROOT)
    return addon.preferences if addon else DEFAULTS


def update_keys(self, context):
    from . import keys
    keys.bind()


class BnodesPreferences(bpy.types.AddonPreferences):
    bl_idname = ROOT

    complete_key: bpy.props.EnumProperty(
        name="Suggestions", items=KEYS, default="ALT", update=update_keys,
        description="Raccourci qui ouvre les suggestions dans un texte .bn")
    auto_complete: bpy.props.BoolProperty(
        name="Ouvrir après ( . :", default=True,
        description="Les suggestions s'ouvrent seules après une parenthèse, un point ou deux-points")
    highlight: bpy.props.BoolProperty(
        name="Surlignage", default=True,
        description="Surligne mots-clés, nœuds, types et valeurs dans les textes .bn")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "complete_key")
        layout.prop(self, "auto_complete")
        layout.prop(self, "highlight")
        layout.label(text="Ctrl+Entrée construit l'arbre depuis le texte.", icon="INFO")


classes = (BnodesPreferences,)
