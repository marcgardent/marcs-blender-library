# Les node groups livrés avec Blender

Inventaire des groupes livrés avec Blender 5.2.2, lu par Nodes as Text (Tree → Text) :
ce qu'ils font, ce qu'on peut en reprendre, ce que le texte ne sait pas encore relire,
et ce qui se trouve ailleurs. Fait le 10 novembre 2026.

## Ce qui est livré

Les groupes sont dans `<Blender>/5.2/datafiles/assets/nodes/` (bibliothèque
*Essentials*) : 150 groupes, dont 78 assets visibles dans Add > … ; les autres sont des
sous-groupes internes (nom en `.xxx` ou sans catalogue).

| Fichier | Groupes | Assets | Relus sans avertissement |
|---|---|---|---|
| `geometry_nodes_essentials.blend` | 33 | 27 | 19 |
| `procedural_hair_node_assets.blend` | 32 | 22 | 27 |
| `geometry_nodes_dynamics_assets.blend` (simulation) | 55 | 6 | 51 |
| `principal_components.blend` | 2 | 2 | 2 |
| `compositing_nodes_essentials.blend` | 24 | 17 | 24 |
| `shading_nodes_essentials.blend` | 4 | 4 | 4 |
| **Total** | **150** | **78** | **127** |

Par usage :

- **Géométrie** : Array, Scatter on Surface, Instance on Elements, Curve to Tube,
  Randomize Transforms, Smooth Geometry, Smooth by Angle, Displace Geometry, Geometry
  Input, Capture Rest Geometry.
- **Lecture du maillage** : Is Edge Boundary / Loose / Manifold, Is UV Split, Face
  Corner Angle, Edge Length.
- **Sélections** : Box Selection, Sphere Selection, Normal Selection.
- **Vecteurs et repères** : Combine / Separate Spherical, Combine / Separate
  Cylindrical, Transform and Project, Project with Depth, 3D to Screen Space, Screen to
  3D Space, Random Rotation, Principal Components. Les mêmes existent en double ou en
  triple pour les shaders et le compositing.
- **Cheveux** : 22 assets (Generate, Interpolate, Clump, Curl, Frizz, Braid, Trim…).
- **Simulation** : Hair Dynamics, Cloth Dynamics (expérimental), Collider, Custom Force,
  Custom Effector, et 49 sous-groupes du solveur XPBD.

## Ce qu'on peut en reprendre

Les nœuds les plus employés dans ces 150 groupes : Math (557), Switch (293), Vector
Math (279), Compare (131), Capture Attribute (110), Boolean Math (75). La moitié du
travail est du calcul, ce que le texte écrit en formules.

Les petits groupes mathématiques se relisent en quelques lignes. Par exemple :

```
geometry graph "Separate Spherical"(Vector: Vector) -> (R: Float, Phi: Float, Theta: Float) {
  vector_math = length(Vector)
  return (R: vector_math, Phi: atan2(Vector.y, Vector.x), Theta: asin(Vector.z / vector_math))
}

geometry graph "Sphere Selection"(Center: Vector, Radius: Float) -> (Selection: Bool) {
  return (Selection: distance(Position(), Center) <= Radius)
}
```

Random Rotation, Principal Components, Face Corner Angle ou `.shape_range` (le profil
des cheveux) se relisent aussi en entier. Ce sont de bons modèles, et ils montrent que
Blender couvre déjà les repères (sphérique, cylindrique, écran), mais pas les courbes de
réglage, les ondes ni les champs de distance. La boîte à outils [Maths](maths.md)
comble ce manque.

## Ce que le texte ne sait pas encore relire

Presque plus rien. Sur les 122 arbres Geometry Nodes livrés, **121 se reconstruisent à
l'identique** depuis leur texte : mêmes nœuds (y compris ceux sans effet sur la sortie),
mêmes réglages, mêmes items, même interface avec ses panneaux, même présentation. Ils
étaient 57 avant les nœuds à items, 77 à la version 0.5. Le seul qui manque, Curve to
Tube, a un Capture Attribute dont un item s'appelle « Selection », comme une entrée fixe
du nœud.

23 groupes sur 150 donnent encore un avertissement à la relecture (108 à la version
0.5). Nombre de groupes touchés, par cause :

| Cause | Groupes |
|---|---|
| Libellé ou couleur d'un nœud Group Input (le texte n'a pas de nœud Group Input) | 14 |
| Frame coupé par un autre frame du même titre | 5 |
| Guillemets ou retours à la ligne dans un texte, remplacés | 4 |
| Item au nom d'une entrée fixe de son nœud | 1 |

Tout le reste s'écrit : zones Repeat, Simulation, For Each et Closure, bundles, nœuds à
items (Capture Attribute, Menu et Index Switch, Format String, Bake, Field to List,
Viewer…), gizmos, panneaux et noms répétés de l'interface, réglages d'outil de l'arbre,
nœuds désactivés ou sans effet, libellés, couleurs et nœuds repliés. La
[référence du langage](reference.md) décrit chaque écriture.

À noter : les arbres de shaders et de compositing se relisent aussi (`shader graph`,
`compositor graph`), alors que la construction n'est garantie que pour Geometry Nodes.

## Ce qui existe ailleurs

| Source | Contenu | Accès |
|---|---|---|
| [Higgsas Geometry Nodes Toolset](https://superhivemarket.com/products/geometry-nodes-groups) ([manuel](https://higgsas-geo-nodes-manual.readthedocs.io/)) | ~180 groupes : SDF, easing, algèbre linéaire, mesures | Payant (~10 €), libre de droits pour ses rendus |
| [GN Library](https://blendermarket.com/products/gn-library) | 100+ convertisseurs, aides, visualiseurs | Payant |
| [SDF NodeBox](https://superhivemarket.com/products/sdfnodebox) | 45 groupes SDF, pour les shaders | Payant |
| [b3dsdf](https://www.github.com/williamchange/b3dsdf) | SDF 2D en shader nodes | GitHub, licence à vérifier |
| [Inigo Quilez](https://iquilezles.org/articles/) | Les formules de référence : SDF, courbes, opérations | Articles en ligne |

Les packs payants ne se redistribuent pas dans une library publique comme celle-ci.
Réécrire les formules en texte coûte peu (une à cinq lignes chacune) et donne des
groupes testés, relisibles et modifiables : c'est le choix fait pour Maths.

## Ce que Blender sait déjà faire

À écrire avec les nœuds natifs plutôt que d'en refaire un groupe :

| Besoin | En texte |
|---|---|
| Remettre une valeur d'un intervalle dans un autre | `MapRange(x, de_min, de_max, vers_min, vers_max)` |
| smoothstep, smootherstep | `MapRange(x, bord0, bord1, interpolation_type: SMOOTHSTEP)` ou `SMOOTHERSTEP` |
| Borner | `Clamp(x, min, max)` |
| Interpoler (lerp) | `a + (b - a) * t`, ou le nœud Mix |
| Union / intersection douces de SDF | `Math(a, b, k, operation: SMOOTH_MIN)`, `SMOOTH_MAX` |
| Boucler, arrondir à un pas, aller-retour | `Math(x, max, min, operation: WRAP)`, `SNAP`, `PINGPONG` |
| Réfléchir, réfracter, projeter un vecteur | Vector Math : `REFLECT`, `REFRACT`, `PROJECT`, `FACEFORWARD` |
| Tourner un vecteur | `VectorRotate(v, angle: a, rotation_type: Z_AXIS)` |
| Coordonnées sphériques, cylindriques | Les assets Combine / Separate Spherical et Cylindrical |
| Rotation au hasard | L'asset Random Rotation |

## Refaire l'inventaire

Après une mise à jour de Blender ou de Nodes as Text :

```bash
blender --background --factory-startup --python tests/bnodes/host/survey_essentials.py
```

Le script ajoute au fichier vide les groupes des `.blend` de `datafiles/assets/nodes/`,
relit chacun en texte et compte les nœuds et les avertissements, par cause.
