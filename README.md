# Marc's Blender Library

Bibliothèque d'assets Blender perso, déclarée dans Blender (Préférences > File Paths >
Asset Libraries) sous le nom **Marc's Blender Library**, import en *Append*.

## Library distante (Blender 5.2+)

Endpoint officiel de library distante Blender, publié par GitHub Pages :

```
https://marcgardent.github.io/marcs-blender-library/
```

Dans Blender : Préférences > File Paths > Asset Libraries > `+` > **Add Remote Asset
Library**, coller l'URL. Blender télécharge l'index et les assets à la demande, rien à
cloner.

## Installation locale (clone git)

```bash
git lfs install
git clone git@github.com:marcgardent/marcs-blender-library.git ~/marcs-blender-library
blender -b --python ~/marcs-blender-library/install.py
```

Blender déjà ouvert : onglet Scripting > Open > `install.py` > Run Script, la library
apparaît tout de suite. Sinon, à la main : Préférences > File Paths > Asset Libraries >
`+`, choisir le dossier, Import Method *Append*.

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
assets/                   fichiers .blend des assets et leurs vignettes (Git LFS)
previews/                 aperçus PNG pour ce README (Git LFS)
src/                      scripts qui génèrent les assets
install.py                déclare la library locale dans Blender
_asset-library-meta.json  point d'entrée de l'endpoint distant (nom, contact)
_v1/                      index de l'endpoint, généré par Blender
.github/workflows/        publication de l'endpoint sur GitHub Pages
```

## Reconstruire un asset

Les `.blend` sont générés par les scripts de `src/`. Après tout changement d'asset,
régénérer l'index de l'endpoint (sinon les hash ne correspondent plus et Blender refuse
le téléchargement) :

```bash
blender -b --factory-startup --python src/outline_backface.py
blender -b -c asset_listing generate .
```

## Sauvegarde

Dépôt git, binaires en Git LFS. Après un changement :

```bash
git add -A && git commit -m "…" && git push
```
