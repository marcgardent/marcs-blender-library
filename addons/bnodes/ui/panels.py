import bpy

from . import actions, prefs
from .operators import edit_tree


class TEXT_PT_bnodes(bpy.types.Panel):
    bl_space_type = "TEXT_EDITOR"
    bl_region_type = "UI"
    bl_category = "Nodes"
    bl_label = "Nodes as Text"

    @classmethod
    def poll(cls, context):
        return actions.is_bn(context.space_data.text)

    def draw(self, context):
        layout = self.layout
        text = context.space_data.text
        col = layout.column(align=True)
        col.operator("bnodes.text_to_tree", icon="NODETREE")
        col.operator("bnodes.format", text="Formater", icon="ALIGN_LEFT")
        layout.prop(context.window_manager, "bnodes_sync")
        options = prefs.get()
        if isinstance(options, bpy.types.AddonPreferences):
            row = layout.row(align=True)
            row.prop(options, "highlight", toggle=True)
            row.prop(options, "auto_complete", text="Suggestions auto", toggle=True)

        trees = actions.linked_trees(text)
        if trees:
            box = layout.box()
            box.label(text="Arbres liés")
            for tree in trees:
                row = box.row(align=True)
                row.label(text=tree.name, icon="GEOMETRY_NODES")
                if tree.is_modifier:
                    row.operator("bnodes.add_modifier", text="", icon="MODIFIER").tree = tree.name
                row.operator("bnodes.tree_to_text", text="", icon="TEXT").tree = tree.name

        diags = actions.DIAGNOSTICS.get(text.name)
        if diags:
            box = layout.box()
            box.label(text=f"{len(diags)} erreur(s)", icon="ERROR")
            for d in diags:
                op = box.operator("bnodes.goto", text=f"{d.line}:{d.col}  {d.message}", emboss=False)
                op.line, op.col = d.line, d.col

        warnings = actions.WARNINGS.get(text.name)
        if warnings:
            box = layout.box()
            box.label(text=f"{len(warnings)} avertissement(s) d'export", icon="INFO")
            for w in warnings:
                box.label(text=w)


class NODE_PT_bnodes(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "Text"
    bl_label = "Nodes as Text"

    @classmethod
    def poll(cls, context):
        return edit_tree(context) is not None

    def draw(self, context):
        layout = self.layout
        tree = edit_tree(context)
        layout.operator("bnodes.tree_to_text", text="Ouvrir en texte", icon="TEXT")
        if tree.bnodes_text:
            layout.label(text=f"Texte : {tree.bnodes_text.name}", icon="LINKED")
        layout.prop(context.window_manager, "bnodes_sync")


classes = (TEXT_PT_bnodes, NODE_PT_bnodes)
