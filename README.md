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

## Dépôt d'extensions (Blender 4.2+)

Les mini add-ons sont publiés comme dépôt d'extensions, sur le même GitHub Pages :

```
https://marcgardent.github.io/marcs-blender-library/extensions/index.json
```

Dans Blender : Préférences > Get Extensions > Repositories > `+` > **Add Remote
Repository**, coller l'URL, cocher *Check for Updates on Startup*. Les extensions
apparaissent ensuite dans Get Extensions, à installer en un clic.

### Quick Flatten Axis

Blender 4.2+. Edit Mode, mesh.

| Raccourci | Action |
|---|---|
| Ctrl+Alt+X / Y / Z | Aplatit la sélection sur l'axe X / Y / Z |
| Ctrl+Alt+M | Ramène la sélection à un point et fusionne les sommets |

Option (panneau Adjust Last Operation) : *Merge Distance* pour Ctrl+Alt+M.

### Constant Brush Size

Blender 5.0+. Texture Paint.

Sidebar (N) > Tool > **Constant Brush Size (TPaint)** :

- **Constant Size: ON/OFF** : garde la même taille de pinceau sur l'objet quand on zoome.
- **Min / Max Radius (px)** : bornes du rayon à l'écran.

Changer la taille avec F ou le slider redéfinit la taille de référence.

### Grease Pencil Tools

Blender 5.0+. Edit Mode Grease Pencil. Remplace l'ancienne extension *Grease Pencil
Clean Overlaps* : la désinstaller avant d'installer celle-ci.

**Clean Overlapping Edges** : Stroke > Clean Up (ou F3). Supprime les segments superposés
qui ont le même matériau. Le premier stroke garde le segment.

- **Tolérance** : distance sous laquelle deux points sont confondus.
- **Toutes les frames** : sinon, frame courante seulement.

Les calques verrouillés et les strokes Bézier ne sont pas touchés. Les strokes nettoyés
perdent leurs poids de vertex groups.

**Sort Strokes by Material** : Stroke > Sort Strokes by Material (ou F3). Dans chaque
calque, redessine les strokes dans l'ordre de la liste des matériaux, au lieu de l'ordre
de tracé. Dans un même matériau, l'ordre de tracé est gardé.

- **Haut de liste devant** : le premier matériau est dessiné devant, comme les calques.
- **Toutes les frames** : sinon, frame courante seulement.

Les calques verrouillés ne sont pas touchés. Il faut *Stroke Depth Order* sur
*2D Layers* (Object Data > Strokes). Pour un tri qui suit aussi les strokes tracés
ensuite, utiliser plutôt le modifier [Tri par Matériau](#tri-par-matériau).

### Move Markers with Keys

Blender 5.0+. Dope Sheet, Timeline, Graph Editor, NLA, Sequencer.

| Raccourci | Action |
|---|---|
| Ctrl+G (souris sur la bande des markers) | Déplace les markers sélectionnés et toutes les keys posées sur eux |

Aussi dans le menu Marker > **Move Markers with Keys**. Comme G : la souris ou un nombre
tapé au clavier donne le décalage en frames, clic ou Entrée valide, clic droit ou Échap
annule. Le décalage se règle ensuite dans le panneau Adjust Last Operation.

- Keys concernées : toutes celles de la scène qui sont sur la frame d'un marker sélectionné
  (objets, leurs données, shape keys, matériaux, monde, scène) et les frames Grease Pencil.
- Une key déplacée remplace la key qu'elle recouvre, comme avec G.
- Les F-curves verrouillées, les calques Grease Pencil verrouillés et les actions liées
  depuis une autre library ne bougent pas. Les strips NLA non plus : seule l'action active compte.
- Ne marche pas si *Lock Markers* est activé.

Ailleurs que sur la bande des markers, Ctrl+G garde son rôle natif (Jump to Keyframes,
Group Channels…). En natif, Blender ne fait que l'inverse dans le Dope Sheet :
Marker > *Sync Markers* déplace les markers avec les keys, après Select > *Columns on
Selected Markers* (Shift+K) puis G.

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
| Tri par Matériau | Geometry Nodes (modifier Grease Pencil) | Geometry Nodes/Grease Pencil | `assets/geometry_nodes/gp_tri_materiau.blend` |
| Tonneau Fermé, Tonneau | Geometry Nodes (modifier) | Geometry Nodes/Tonneau | `assets/geometry_nodes/tonneau.blend` |
| Cerclage, Fond Planches | Geometry Nodes (groupe) | Geometry Nodes/Tonneau | `assets/geometry_nodes/tonneau.blend` |
| Centre Mesh, Box Normalisée, Profil Cloche, Poussée Radiale, Choix Axe, Orienter Axe, Paire Miroir | Geometry Nodes (groupe) | Geometry Nodes/Outils | `assets/geometry_nodes/tonneau.blend` |

### Outline Backface

![Outline Backface](previews/outline_backface.png)

Contour par backface culling (inverted hull) : une copie du mesh gonflée le long
des normales, faces retournées, avec le matériau `Outline` qui ne garde que les
faces arrière. Marche en EEVEE et en Cycles (le culling est refait dans le shader,
et la coque n'est visible que depuis la caméra).

- Entrées : **Epaisseur** (0,03 par défaut), **Poids**, **Materiau** (`Outline`, noir).
- **Poids** multiplie l'épaisseur (1 par défaut). Pour le piloter par un vertex group :
  dans le modifier, cliquer l'icône attribut à droite de *Poids* et taper le nom du
  vertex group. Poids 0 = pas de contour. Un nom de vertex group inexistant donne 0
  partout, donc plus de contour du tout. L'aperçu ci-dessous utilise un vertex group
  qui va de 0 au menton à 1 en haut du crâne.
- À mettre en dernier dans la pile de modifiers.
- Si l'objet a des booléens, masquer leurs objets à la caméra (Object > Visibility >
  Ray Visibility > Camera), sinon ils recouvrent le contour.
- En mode Solid, activer Backface Culling dans les options du viewport.

Ajout : Add Modifier > Geometry Nodes > Outline, ou glisser depuis l'Asset Browser.

### Tri par Matériau

![Tri par Matériau](previews/gp_tri_materiau.png)

Modifier pour Grease Pencil : dans chaque calque, les strokes sont dessinés dans l'ordre
de la liste des matériaux, pas dans l'ordre de tracé. Non destructif : les strokes
tracés ensuite sont triés aussi. L'aperçu montre trois disques tracés Rouge, Vert puis
Bleu : avec le modifier, Rouge (haut de la liste) passe devant.

- **Haut de liste devant** (coché par défaut) : le premier matériau est dessiné devant,
  comme pour les calques. Décoché : il passe derrière.
- Dans un même matériau, l'ordre de tracé est gardé.
- Il faut *Stroke Depth Order* sur *2D Layers* (Object Data > Strokes).
- Les calques, leurs réglages et les matériaux sont conservés.

Ajout : Add Modifier > Geometry Nodes > Grease Pencil, ou glisser depuis l'Asset
Browser. Version destructive : l'opérateur *Sort Strokes by Material* de
[Grease Pencil Tools](#grease-pencil-tools).

### Tonneau Fermé

![Tonneau Fermé](previews/tonneau.png)

Tonneau complet à partir de douelles (les planches verticales) : bombé au milieu,
deux cerclages, deux fonds en planches. Le bombé s'applique à tout l'ensemble, donc
cerclages et fonds suivent la courbe des douelles.

- Entrée : des douelles **réalisées**. Si elles viennent d'un Instance on Points,
  mettre un Realize Instances avant.
- **Axe** (X / Y / Z, Z par défaut) : axe du tonneau, Z = debout.
- **Bombé** (0,35) : 0,35 = rayon × 1,35 au milieu, rien aux bouts. Négatif = diabolo.
- Panneau **Cerclages** : Position (0 = au bout, 1 = au milieu), Largeur, Épaisseur, Matériau.
  Leur rayon intérieur est la distance maximale des douelles à l'axe : ils reposent
  sur les coins.
- Panneau **Fonds** : Retrait depuis le bout, Paroi (épaisseur des douelles : le fond
  s'arrête à leur face intérieure), Épaisseur, nombre de Planches, Jeu, Matériau.
- Attribut `partie` en sortie : 0 douelles, 1 cerclages, 2 fonds (pour un shader).

**Tonneau** fait seulement le bombé, sans cerclages ni fonds. Le fichier contient une
scène d'exemple (objet *Demo Tonneau*, douelles générées par le groupe *Demo Douelles*).

Groupes réutilisables seuls :

| Groupe | Entrées → Sorties | Rôle |
|---|---|---|
| Cerclage | Rayon, Largeur, Épaisseur, Résolution → Mesh | Anneau plat le long de Z |
| Fond Planches | Rayon, Planches, Épaisseur, Jeu → Mesh | Disque de planches parallèles découpées en cercle |
| Centre Mesh | Geometry → Centre, Taille, Min, Max | Centre réel de la boîte englobante, quel que soit le pivot |
| Box Normalisée | Geometry, Axe → Normalisée, Valeur | Position dans la boîte entre −1 et +1 ; Valeur = sur l'axe choisi |
| Profil Cloche | t → Profil | 1 − t² : 0 aux bouts, 1 au milieu |
| Poussée Radiale | Geometry, Centre, Facteur, Axe → Geometry | Écarte les points de l'axe, d'un facteur par point |
| Choix Axe | Axe → Direction, Masque | Z → (0,0,1) et (1,1,0) |
| Orienter Axe | Geometry, Axe, Centre → Geometry | Tourne une pièce construite le long de Z vers l'axe choisi |
| Paire Miroir | Geometry, Distance → Geometry | Deux copies à ±Distance le long de Z |

Une entrée Axe ne peut alimenter qu'une seule définition du menu X / Y / Z : un
nouveau groupe avec un choix d'axe doit passer par **Choix Axe**.

Ajout : Add Modifier > Geometry Nodes > Tonneau, ou glisser depuis l'Asset Browser.

## Structure

```
blender_assets.cats.txt   catalogues de la library
assets/                   fichiers .blend des assets et leurs vignettes (Git LFS)
previews/                 aperçus PNG pour ce README (Git LFS)
src/                      scripts qui génèrent les assets
install.py                déclare la library locale dans Blender
_asset-library-meta.json  point d'entrée de l'endpoint distant (nom, contact)
_v1/                      index de l'endpoint, généré par Blender
addons/                   sources des extensions (un dossier + blender_manifest.toml chacune)
extensions/               dépôt d'extensions publié : zips et index.json, générés par Blender
.github/workflows/        publication de l'endpoint et des extensions sur GitHub Pages
```

## Rebuilder les extensions

Après un changement dans `addons/`, monter `version` dans le `blender_manifest.toml`
(sinon Blender ne propose pas la mise à jour), puis :

```bash
for d in addons/*/; do blender --factory-startup --command extension build --source-dir "$d" --output-dir extensions; done
blender --factory-startup --command extension server-generate --repo-dir=extensions
```

Supprimer l'ancien zip de `extensions/` avant le `server-generate`, sinon les deux
versions restent dans l'index.

## Reconstruire un asset

Les `.blend` sont générés par les scripts de `src/`. Après tout changement d'asset,
régénérer l'index de l'endpoint (sinon les hash ne correspondent plus et Blender refuse
le téléchargement) :

```bash
blender -b --factory-startup --python src/outline_backface.py
blender -b --factory-startup --python src/tonneau.py
blender -b --factory-startup --python src/gp_tri_materiau.py
blender -b -c asset_listing generate .
```

## Sauvegarde

Dépôt git, binaires en Git LFS. Après un changement :

```bash
git add -A && git commit -m "…" && git push
```
