# Marc's Blender Library

Bibliothèque d'assets Blender perso, déclarée dans Blender (Préférences > File Paths >
Asset Libraries) sous le nom **Marc's Blender Library**, import en *Append*.

## Assets

| Asset | Type | Catalogue | Fichier |
|---|---|---|---|
| Outline Backface | Geometry Nodes (modifier) | Geometry Nodes/Outline | `assets/geometry_nodes/outline_backface.blend` |

### Outline Backface

![Outline Backface](previews/outline_backface.png)

Contour par backface culling (inverted hull) : une copie du mesh gonflée le long
des normales, faces retournées, avec le matériau `Outline` qui ne garde que les
faces arrière. Marche en EEVEE et en Cycles (le culling est refait dans le shader,
et la coque n'est visible que depuis la caméra).

- Entrées : **Epaisseur** (0,03 par défaut), **Materiau** (`Outline`, noir).
- À mettre en dernier dans la pile de modifiers.
- Si l'objet a des booléens, masquer leurs objets à la caméra (Object > Visibility >
  Ray Visibility > Camera), sinon ils recouvrent le contour.
- En mode Solid, activer Backface Culling dans les options du viewport.

Ajout : Add Modifier > Geometry Nodes > Outline, ou glisser depuis l'Asset Browser.

## Structure

```
blender_assets.cats.txt   catalogues de la library
assets/                   fichiers .blend des assets (Git LFS)
previews/                 aperçus PNG (Git LFS)
src/                      scripts qui génèrent les assets
```

## Reconstruire un asset

Les `.blend` sont générés par les scripts de `src/` :

```bash
blender -b --factory-startup --python src/outline_backface.py
```

## Sauvegarde

Dépôt git, binaires en Git LFS. Après un changement :

```bash
git add -A && git commit -m "…" && git push
```
