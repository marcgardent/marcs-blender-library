# Maths : la boîte à outils

47 petites fonctions pour Geometry Nodes, qui manquent à Blender : courbes de réglage et
d'animation, ondes, vecteurs, angles, couleurs, champs de distance signée (SDF), bruits
fractals, tirages au hasard et répartitions régulières de points. Elles
sont écrites en texte dans [`src/maths.bn`](../src/maths.bn), avec
[Base Node for Blender](https://github.com/marcgardent/base-node-library), et livrées en assets dans
`assets/geometry_nodes/maths.blend`, catalogue **Geometry Nodes/Maths**.

Les fonctions déjà dans Blender (Map Range, Clamp, Smooth Min…) n'y sont pas : la
[liste de ce qui existe déjà](analyse-groupes-blender.md#ce-que-blender-sait-déjà-faire)
dit comment les écrire.

## Deux façons de s'en servir

**En assets** : Add (Maj+A) dans le Node Editor > Geometry Nodes > Maths, ou glisser
depuis l'Asset Browser. Chaque asset a sa vignette (sa courbe, la coupe de son SDF ou
ses points), sa description, ses valeurs par défaut et ses bornes, écrites dans le texte
(`force: Float = 0.25 in 0.001..0.999`). Une entrée `p = Position()` prend la position du
point si elle n'est pas reliée, une entrée `id = ID()` son identifiant.

**En texte** : écrire `use maths` en tête d'un texte `.bn` et appeler les fonctions par
leur nom, en snake_case :

```
use maths

geometry graph cratères(sol: Geometry) -> Geometry {
  p = Position()
  // La distance au centre, remise de 0 à 1 puis passée dans une bosse
  h = bosse(length(p) / 3.0, 0.5, 0.2) * 0.4
  return SetPosition(sol, offset: CombineXYZ(z: h))
}
```

`use maths` prend le texte `maths.bn` du fichier. Il y arrive avec le premier asset
Maths ajouté : chaque groupe garde le lien vers son texte. Sans asset, le texte peut
rester à côté du `.blend` : `use maths from "//lib/maths.bn"`. `use maths (bosse)` ne
construit que `bosse` et ce qu'elle appelle. Tree → Text écrit le `use` au lieu de
recopier les fonctions.

Le fichier `maths.blend` contient `maths.bn` et `maths_demo.bn` dans son Text Editor :
avec l'extension, Ctrl+Entrée les reconstruit.

## Les fonctions

### Courbes et ondes

x de 0 à 1 donne de 0 à 1, sauf `marches` qui monte d'une marche par unité. `élastique`
dépasse 1 et `recul` passe sous 0 : c'est leur rôle.

![Les quinze courbes tracées par Blender](images/maths-courbes.png)

| Fonction | Entrées | Rôle |
|---|---|---|
| `biais` | x, force | Pousse vers 0 (force < 0.5) ou vers 1 (> 0.5) ; 0.5 ne change rien |
| `gain` | x, contraste | Courbe en S (contraste < 0.5) ou son inverse |
| `accélère` | t, puissance | Démarre lentement : t^puissance |
| `freine` | t, puissance | Finit lentement |
| `accélère_freine` | t, puissance | Démarre et finit lentement |
| `rebond` | t | Rebondit trois fois avant de se poser sur 1 : une balle |
| `élastique` | t | Dépasse 1 puis y revient en oscillant : un ressort |
| `recul` | t, force | Recule avant de partir ; force 1.70158 recule de 10 % |
| `impulsion` | x, raideur | Monte à 1 en x = 1 / raideur, puis retombe : un choc, un rebond |
| `bosse` | x, centre, demi largeur | 1 au centre, 0 au-delà de la demi-largeur, lisse |
| `parabole` | x, finesse | 0 aux bords, 1 au milieu |
| `marches` | x, montée | Un escalier : chaque marche monte en douceur sur sa fraction `montée` |
| `triangle` | x | 0 sur les entiers, 1 au milieu, période 1 |
| `créneau` | x, cycle | 1 pendant la fraction `cycle` de chaque période, puis 0 |
| `sinus01` | x | Un sinus de période 1, entre 0 et 1 |

### Vecteurs et angles

| Fonction | Entrées → Sorties | Rôle |
|---|---|---|
| `sur_le_plan` | v, normale → Vector | La projection de v sur le plan de la normale |
| `perpendiculaire` | v → Vector | Un vecteur unitaire perpendiculaire à v |
| `composante_max`, `composante_min` | v → Float | La plus grande, la plus petite des trois composantes |
| `proche_sur_segment` | p, a, b → Distance, Facteur, Point | Le point de [a, b] le plus proche de p |
| `angle_ramené` | angle → Float | L'angle ramené entre −π et π |
| `angle_entre` | u, v → Float | De 0 à π, précis même pour des vecteurs presque alignés |
| `angle_signé` | u, v, axe → Float | De −π à π, en tournant autour de l'axe |

### Couleurs

| Fonction | Entrées → Sorties | Rôle |
|---|---|---|
| `luminance` | couleur → Float | La clarté perçue d'une couleur (Rec. 709) |
| `palette` | t, a, b, c, d → Color | Une palette cosinus : a + b × cos(2π (c × t + d)) ; par défaut un arc-en-ciel |

`palette(fract(t))` donne une couleur par valeur ; changer `d` décale les teintes, `c` en
règle le nombre de cycles. Les palettes de l'article d'Inigo Quilez se recopient telles
quelles.

### Champs de distance signée

Négatifs dedans, nuls sur la surface, positifs dehors. Formes centrées sur l'origine :
pour en déplacer une, lui passer `p - centre`.

![Les douze formes de la démo](images/maths-sdf.png)

De gauche à droite. En haut : sphère, boîte arrondie (sa distance moins le rayon de
l'arrondi), tore, cylindre. Au milieu : capsule, boîte creusée par une sphère
(`soustraction_douce`), bol (`coque` d'une sphère coupée par un plan), billes
(`répétition` d'une sphère, gardée dans une boîte). En bas : tronc de cône, ellipsoïde,
octaèdre, colonne carrée passée par `torsion`.

| Fonction | Entrées | Rôle |
|---|---|---|
| `sdf_sphère` | p, rayon | Une sphère |
| `sdf_boîte` | p, demi taille | Une boîte de demi-côtés donnés |
| `sdf_tore` | p, grand rayon, petit rayon | Un tore à plat autour de Z |
| `sdf_cylindre` | p, rayon, demi hauteur | Un cylindre fermé le long de Z |
| `sdf_capsule` | p, a, b, rayon | Le segment [a, b] épaissi du rayon |
| `sdf_cône` | p, demi hauteur, rayon bas, rayon haut | Un tronc de cône le long de Z ; rayon haut 0 pour un cône |
| `sdf_ellipsoïde` | p, rayons | Un ellipsoïde ; distance approchée, juste sur la surface |
| `sdf_octaèdre` | p, taille | Un octaèdre ; distance approchée |
| `sdf_cercle`, `sdf_rectangle` | p, rayon / demi taille | Formes du plan XY (z ne compte pas), pour des motifs |
| `soustraction_douce` | a, b, douceur | Creuse b dans a avec un raccord arrondi |
| `coque` | distance, épaisseur | Une coque centrée sur la surface |
| `répétition` | p, cellule | Répète l'espace : p ramené dans sa cellule |
| `torsion` | p, force → Vector | Tord l'espace autour de Z, de `force` radians par unité de hauteur |
| `courbure` | p, force → Vector | Courbe l'espace vers le haut le long de X |
| `normale_sdf` | d, dx, dy, dz → Vector | La normale d'un SDF, à partir de sa valeur en p et en p un peu décalé |

`torsion`, `courbure` et `répétition` transforment p avant le SDF :
`sdf_boîte(torsion(p, 0.7), (0.5, 0.5, 1.0))`. La surface reste juste, mais la distance
loin d'elle ne l'est plus tout à fait.

Un graph ne peut pas en recevoir un autre : `normale_sdf` prend donc les quatre valeurs
du même SDF, à calculer avec un petit pas `e` :

```
e = 0.01
n = normale_sdf(sdf_tore(p), sdf_tore(p + CombineXYZ(e)), sdf_tore(p + CombineXYZ(y: e)), sdf_tore(p + CombineXYZ(z: e)))
```

Les combinaisons simples sont des nœuds Math : `min(a, b)` réunit, `max(a, b)` garde
l'intersection, `max(a, -b)` creuse, `Math(a, b, k, operation: SMOOTH_MIN)` réunit en
douceur, `d - r` arrondit.

Pour faire un maillage d'un SDF : un **Volume Cube** dont la densité est `-distance`,
avec un fond (Background) négatif, puis **Volume to Mesh** au seuil 0. C'est ce que fait
`surface` dans [`src/maths_demo.bn`](../src/maths_demo.bn). Sans le fond négatif, le
bord du cube devient lui aussi une surface. Un SDF sert aussi de sélection
(`sdf_sphère(p - c, r) < 0.0`) ou de masque doux (`bosse`, Map Range).

### Bruits fractals

Plusieurs octaves d'un même bruit, chacune deux fois plus fine et deux fois plus faible
que la précédente. Écrits avec une zone Repeat, un tour par octave.

![Des montagnes relevées par fbm_crêtes](images/maths-bruits.png)

| Fonction | Entrées | Rôle |
|---|---|---|
| `fbm` | p, octaves, lacunarité, persistance | Un bruit fractal entre −1 et 1 environ : nuages, terrains doux |
| `fbm_crêtes` | p, octaves, lacunarité, persistance | Des crêtes vives, entre 0 et 1 environ : montagnes |

`lacunarité` multiplie la fréquence d'une octave à la suivante (2 par défaut),
`persistance` l'amplitude (0.5). Les montagnes ci-dessus :
`fbm_crêtes(Position() * 0.2, 6) * 2.2` en hauteur d'une grille.

### Hasard

| Fonction | Entrées | Rôle |
|---|---|---|
| `direction_aléatoire` | id, graine | Une direction uniforme sur la sphère |
| `point_dans_disque` | id, graine | Un point uniforme dans le disque de rayon 1 du plan XY |

### Répartitions régulières

Sans hasard : des points répartis sans trou ni amas, les mêmes à chaque fois.

| Fonction | Entrées | Rôle |
|---|---|---|
| `point_fibonacci` | index, nombre | Le point `index` de `nombre` points répartis sur la sphère de rayon 1 |
| `suite_r2` | index | Le point `index` de la suite R2, dans le carré [0, 1]² du plan XY |

Sur un **Points** de 500 points, `SetPosition(position: point_fibonacci(nombre: 500))` en
fait une sphère régulière : l'index vient tout seul.

## Reconstruire

Après un changement de `src/maths.bn` ou de `src/maths_demo.bn` :

```bash
blender -b --factory-startup --python src/maths.py
blender -b -c asset_listing generate .
```

Le script reconstruit les groupes depuis le texte, valeurs par défaut comprises, pose les
catalogues et les descriptions (la chaîne en tête de chaque graph), trace les
vignettes à partir des valeurs calculées par Blender, puis rend les images de
cette page et `previews/maths.png`.

Les formules des courbes et des SDF suivent celles qu'Inigo Quilez publie sur
[iquilezles.org](https://iquilezles.org/articles/).
