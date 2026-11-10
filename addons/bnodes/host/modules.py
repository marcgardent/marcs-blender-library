"""Where a `use` finds its module: a text of the .blend, or a .bn file.

`use maths` reads the text maths.bn; `use maths from "//lib/maths.bn"` a file
relative to the .blend, as everywhere in Blender. Libraries, URLs and
{project_root} come later.
"""

import os

import bpy

# Custom properties of a group built by a `use`, for Tree → Text to write the use back
MODULE = "bnodes_module"
SOURCE = "bnodes_source"


def load(name, source):
    """(text, filename) of a module. Raises LookupError with the reason."""
    if source is None:
        text = bpy.data.texts.get(name + ".bn")
        if text is None:
            raise LookupError(f"pas de texte « {name}.bn » dans ce fichier ; "
                              f"pour un fichier : use {name} from \"//chemin/{name}.bn\"")
        return text.as_string(), text.name
    if source.startswith(("http://", "https://")):
        raise LookupError("les modules en ligne ne sont pas encore pris en charge")
    if "{project_root}" in source:
        raise LookupError("{project_root} attend Blender 5.3")
    if source.startswith(("./", "../")):
        raise LookupError(f"un chemin relatif au .blend commence par « // », comme partout dans Blender : "
                          f"« //{source.removeprefix('./')} »")
    if source.startswith("//"):
        if not bpy.data.filepath:
            raise LookupError("« // » part du dossier du .blend : enregistrer le fichier d'abord")
        path = os.path.normpath(bpy.path.abspath(source))
    elif os.path.isabs(source):
        path = source
    else:
        raise LookupError(f"« {source} » : un chemin « //… » relatif au .blend, ou un chemin absolu ; "
                          "les libraries d'assets ne sont pas encore prises en charge")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), source
    except OSError as e:
        raise LookupError(f"« {source} » illisible : {e.strerror}") from None


def module_of(tree):
    """(name, source) of the module a group was built from by a `use`, or None."""
    name = tree.get(MODULE)
    return (name, tree.get(SOURCE) or None) if name else None
