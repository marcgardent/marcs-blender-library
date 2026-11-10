# Maths : la boîte à outils

31 petites fonctions pour Geometry Nodes, qui manquent à Blender : courbes de réglage,
ondes, vecteurs, angles, champs de distance signée (SDF) et tirages au hasard. Elles
sont écrites en texte dans [`src/maths.bn`](../src/maths.bn), avec
[Nodes as Text](nodes-as-text.md), et livrées en assets dans
`assets/geometry_nodes/maths.blend`, catalogue **Geometry Nodes/Maths**.

Les fonctions déjà dans Blender (Map Range, Clamp, Smooth Min…) n'y sont pas : la
[liste de ce qui existe déjà](analyse-groupes-blender.md#ce-que-blender-sait-déjà-faire)
dit comment les écrire.

## Deux façons de s'en servir

**En assets** : Add (Maj+A) dans le Node Editor > Geometry Nodes > Maths, ou glisser
depuis l'Asset Browser. Chaque asset a sa vignette (sa courbe, la coupe de son SDF ou
ses tirages), sa description et des valeurs par défaut. Une entrée `p` prend la position
du point si elle n'est pas reliée, une entrée `id` l'index.

**En texte** : coller `src/maths.bn` en tête d'un texte `.bn` et appeler les fonctions
par leur nom, en snake_case :

```
geometry graph cratères(sol: Geometry) -> Geometry {
  p = Position()
  // La distance au centre, remise de 0 à 1 puis passée dans une bosse
  h = bosse(length(p) / 3.0, 0.5, 0.2) * 0.4
  return SetPosition(sol, offset: CombineXYZ(z: h))
}
```

Le fichier `maths.blend` contient aussi `maths.bn` et `maths_demo.bn` dans son Text
Editor : avec l'extension, Ctrl+Entrée les reconstruit.

## Les fonctions

### Courbes et ondes

x de 0 à 1 donne de 0 à 1, sauf `marches` qui monte d'une marche par unité.

![Les douze courbes tracées par Blender](images/maths-courbes.png)

| Fonction | Entrées | Rôle |
|---|---|---|
| `biais` | x, force | Pousse vers 0 (force < 0.5) ou vers 1 (> 0.5) ; 0.5 ne change rien |
| `gain` | x, contraste | Courbe en S (contraste < 0.5) ou son inverse |
| `accélère` | t, puissance | Démarre lentement : t^puissance |
| `freine` | t, puissance | Finit lentement |
| `accélère_freine` | t, puissance | Démarre et finit lentement |
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
| `luminance` | couleur → Float | La clarté perçue d'une couleur (Rec. 709) |
| `proche_sur_segment` | p, a, b → Distance, Facteur, Point | Le point de [a, b] le plus proche de p |
| `angle_ramené` | angle → Float | L'angle ramené entre −π et π |
| `angle_entre` | u, v → Float | De 0 à π, précis même pour des vecteurs presque alignés |
| `angle_signé` | u, v, axe → Float | De −π à π, en tournant autour de l'axe |

### Champs de distance signée

Négatifs dedans, nuls sur la surface, positifs dehors. Formes centrées sur l'origine :
pour en déplacer une, lui passer `p - centre`.

![Les huit formes de la démo](images/maths-sdf.png)

De gauche à droite, en haut : sphère, boîte arrondie (sa distance moins le rayon de
l'arrondi), tore, cylindre ; en bas : capsule, boîte creusée par une sphère
(`soustraction_douce`), bol (`coque` d'une sphère coupée par un plan), billes
(`répétition` d'une sphère, gardée dans une boîte).

| Fonction | Entrées | Rôle |
|---|---|---|
| `sdf_sphère` | p, rayon | Une sphère |
| `sdf_boîte` | p, demi taille | Une boîte de demi-côtés donnés |
| `sdf_tore` | p, grand rayon, petit rayon | Un tore à plat autour de Z |
| `sdf_cylindre` | p, rayon, demi hauteur | Un cylindre fermé le long de Z |
| `sdf_capsule` | p, a, b, rayon | Le segment [a, b] épaissi du rayon |
| `soustraction_douce` | a, b, douceur | Creuse b dans a avec un raccord arrondi |
| `coque` | distance, épaisseur | Une coque centrée sur la surface |
| `répétition` | p, cellule | Répète l'espace : p ramené dans sa cellule |

Les combinaisons simples sont des nœuds Math : `min(a, b)` réunit, `max(a, b)` garde
l'intersection, `max(a, -b)` creuse, `Math(a, b, k, operation: SMOOTH_MIN)` réunit en
douceur, `d - r` arrondit.

Pour faire un maillage d'un SDF : un **Volume Cube** dont la densité est `-distance`,
avec un fond (Background) négatif, puis **Volume to Mesh** au seuil 0. C'est ce que fait
`surface` dans [`src/maths_demo.bn`](../src/maths_demo.bn). Sans le fond négatif, le
bord du cube devient lui aussi une surface. Un SDF sert aussi de sélection
(`sdf_sphère(p - c, r) < 0.0`) ou de masque doux (`bosse`, Map Range).

### Hasard

| Fonction | Entrées | Rôle |
|---|---|---|
| `direction_aléatoire` | id, graine | Une direction uniforme sur la sphère |
| `point_dans_disque` | id, graine | Un point uniforme dans le disque de rayon 1 du plan XY |

## Fiabilité

Un test calcule chaque fonction dans Blender, sur 64 points, et la compare à la même
formule en Python ; il vérifie aussi que chaque arbre se relit en texte à l'identique :

```bash
blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_maths.py
```

## Reconstruire

Après un changement de `src/maths.bn` ou de `src/maths_demo.bn` :

```bash
blender -b --factory-startup --python src/maths.py
blender -b -c asset_listing generate .
```

Le script reconstruit les groupes depuis le texte, pose les catalogues, les descriptions
(le commentaire au-dessus de chaque graph) et les valeurs par défaut (table `DEFAULTS`),
trace les vignettes à partir des valeurs calculées par Blender, puis rend les images de
cette page et `previews/maths.png`.

Les formules des courbes et des SDF suivent celles qu'Inigo Quilez publie sur
[iquilezles.org](https://iquilezles.org/articles/).
