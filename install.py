"""Déclare Marc's Blender Library dans les préférences de Blender.

Dans Blender ouvert : onglet Scripting > Open > install.py > Run Script
(la library apparaît tout de suite dans l'Asset Browser).

En ligne de commande, Blender fermé :

    blender -b --python install.py

La library pointe sur le dossier qui contient ce script. Relancer le script
met le chemin à jour sans créer de doublon.
"""
import os

import bpy

NAME = "Marc's Blender Library"
ROOT = os.path.dirname(os.path.abspath(__file__))

libs = bpy.context.preferences.filepaths.asset_libraries
lib = libs.get(NAME) or libs.new(name=NAME, directory=ROOT)
lib.path = ROOT
lib.import_method = "APPEND"
bpy.ops.wm.save_userpref()
print("Library installee :", NAME, "->", ROOT)
