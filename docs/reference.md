# Nodes as Text : référence du langage

La référence du texte `.bn`, version 1. Elle décrit chaque construction, et la promesse
de compatibilité de la LTS 1. Des exemples commentés sont dans
[nodes-as-text.md](nodes-as-text.md) ; la boîte à outils [Maths](maths.md) est écrite
dans ce langage.

**Périmètre de la 1.0 :** les arbres **Geometry Nodes**, construits et relus dans
**Blender 5.2 LTS**. Les arbres de shaders et de compositing se relisent mais ne se
construisent pas : ils viendront en 1.x, comme Blender 5.3 LTS quand il sera testé.

## Un fichier

Un texte `.bn` contient, dans cet ordre :

1. des lignes `use`, facultatives, qui importent d'autres textes ([modules](#modules)) ;
2. un ou plusieurs `graph`, chacun donnant un node group.

`//` commence un commentaire, jusqu'à la fin de la ligne (sauf dans une chaîne). Les
espaces et les retours à la ligne ne comptent pas : une instruction finit là où la
suivante ne peut pas la continuer.

```
use maths (bosse)

// Un relief en bosse au centre de la grille
geometry graph relief(geometry: Geometry, hauteur: Float = 0.4) -> Geometry {
  "Soulève le centre"
  h = bosse(length(Position()) / 3.0, 0.5, 0.2) * hauteur
  return SetPosition(geometry, offset: CombineXYZ(z: h))
}
```

## Noms

- Un **nom** est un identifiant : lettres (accents compris), chiffres et `_`, sans
  chiffre en tête. `hauteur`, `fréquence_2`, `p`.
- Un nom qui n'est pas un identifiant se déclare **entre guillemets** et s'emploie par
  sa **clé**, en snake_case : `"Point Count": Int` se lit `point_count`. Les sockets des
  nœuds suivent la même règle : `Shade Smooth` se dit `shade_smooth`.
- **Mots réservés** : `graph`, `return`, `true`, `false`, `and`, `or`, `xor`, `not`,
  `repeat`, `dot`, `cross`. Un socket qui porte un de ces noms prend un `_` à la fin
  (`not_`).
- `use` et `from` ne sont des mots-clés qu'en tête de fichier ; ailleurs, ce sont des noms.
  De même `simulate` et `foreach` ne le sont que dans `nom = simulate(…) {` et
  `nom = foreach(…) {`, et `closure` n'ouvre une [zone Closure](#bundles-et-closures) que
  sous la forme `nom = closure(…) -> … {`.
- `_` seul veut dire « pas de valeur », pour un [item vide](#nœuds-à-items).
- Un nom qui n'est ni une entrée ni un nom défini est une **valeur** : d'une propriété
  (`domain: FACE`, `operation: POWER`) ou d'un menu (`Lisse`).

## Graph

```
geometry graph nom(entrée: Type, …) -> Type { … }
geometry graph nom(entrée: Type, …) -> (Sortie: Type, …) { … }
```

- `geometry` est le type d'arbre (`shader` et `compositor` se relisent seulement).
- Le nom du graph est celui du node group ; il s'appelle depuis un autre graph par sa
  clé.
- `-> Type` : une seule sortie, nommée comme son type (`-> Geometry` donne une sortie
  « Geometry »). `-> (a: Float, b: Vector)` : plusieurs sorties, ou une seule nommée
  autrement.
- Une **chaîne seule en première ligne** du corps est la description du groupe : son
  infobulle, et celle de son asset.
- Un graph dont la première entrée et la première sortie sont des `Geometry`, et que
  personne n'appelle, est proposé comme modifier.
- **Les réglages de l'arbre** s'écrivent entre parenthèses après son type, sous leur nom
  Blender : `geometry(is_tool: true, is_mode_edit: true, is_type_mesh: true) graph …`.
  Réglages : `is_modifier`, `is_tool`, `is_mode_object`, `is_mode_edit`,
  `is_mode_sculpt`, `is_mode_paint`, `is_type_mesh`, `is_type_curve`,
  `is_type_pointcloud`, `is_type_grease_pencil`, `use_wait_for_click`,
  `show_modifier_manage_panel`. Un réglage absent garde celui d'un arbre neuf ;
  `is_modifier` absent suit la règle du point précédent, et ne s'écrit que pour la
  contredire (`is_modifier: false`, ou `true` pour un groupe appelé).

### Types

| Type | Socket | Valeur par défaut écrite |
|---|---|---|
| `Float` | Float | `0.5` |
| `Int` | Integer | `3` |
| `Bool` | Boolean | `true`, `false` |
| `Vector` | Vector | `(1.0, 0.0, 0.0)` ; 2 ou 4 nombres donnent un vecteur de cette dimension |
| `Color` | Color | `(1.0, 0.5, 0.0)` ou `(1.0, 0.5, 0.0, 1.0)` |
| `Rotation` | Rotation | `(0.0, 0.0, 1.57)`, en radians |
| `Matrix` | Matrix | aucune |
| `String` | String | `"texte"` |
| `Menu` | Menu | `Lisse`, le nom d'un item du menu qu'elle alimente |
| `Geometry`, `Shader`, `Bundle`, `Closure` | | aucune |
| `Object`, `Collection`, `Material`, `Image`, `Texture` | | `"Nom"`, un datablock du fichier |

### Entrées et sorties

```
nom: Type(option: valeur, …) = défaut in min..max
```

Tout est facultatif après le type :

- **`= défaut`** : la valeur de l'entrée quand rien n'y est relié. Pour un champ pris du
  contexte, un appel sans argument : `p: Vector = Position()`, de même `Normal()`,
  `Index()`, `ID()`, `InstanceTransform()` (Matrix) et `SelfObject()` (Object).
- **`in min..max`** : les bornes, pour `Float`, `Int` et `Vector`. Un côté peut rester
  ouvert : `in 0.0..`, `in ..1.0`.
- **`(option: valeur, …)`** : les autres réglages du socket, sous leur nom Blender :
  `subtype: FACTOR` (ou `DISTANCE`, `ANGLE`, `TRANSLATION`, `XYZ`…), `description: "…"`,
  `structure_type: SINGLE`, `hide_value: true`, `hide_in_modifier: true`,
  `default_attribute_name: "…"`, etc. Une option absente garde le réglage d'un socket
  neuf. Les réglages qui ont leur propre écriture (`default_value`, `min_value`,
  `max_value`, `default_input`) ne s'écrivent pas en option.

Les sorties prennent des options, mais ni défaut ni bornes.

### Panneaux

```
geometry(show_modifier_manage_panel: false) graph semis(
    geometry: Geometry,
    densité: Float = 10.0,
    "Taille"(description: "La taille de chaque copie") {
        échelle: Float = 1.0,
        "Aléa"(default_closed: true) {
            Aléa: Bool(is_panel_toggle: true),
            échelle as aléa_échelle: Float = 0.2 in 0.0..1.0,
            graine: Int
        }
    },
    "Rotation" {
        graine as rotation_graine: Int,
        angle: Float(subtype: ANGLE)
    }
) -> (
    Geometry: Geometry,
    "Rotation" {
        Angle: Float
    }
) { … }
```

- **`"Titre" { … }`** dans la liste des entrées ou des sorties : un panneau de
  l'interface, qui regroupe les entrées écrites entre ses accolades. Les panneaux
  s'emboîtent ; un panneau vide s'écrit `"Titre" {}`. Les entrées y gardent tout ce
  qu'elles prennent ailleurs (type, options, défaut, bornes).
- **`"Titre"(description: "…", default_closed: true)`** : les réglages du panneau, son
  infobulle et s'il est fermé au départ. Ils s'écrivent une fois, là où le panneau paraît
  en premier.
- Un panneau qui tient des entrées et des sorties s'écrit dans les deux listes, sous le
  même titre : c'est le même panneau. Les panneaux d'un niveau se suivent dans l'ordre des
  entrées, puis dans celui des sorties pour ceux qui n'ont que des sorties.
- Comme Blender les range, à chaque niveau les sockets viennent avant les panneaux : une
  entrée écrite après un panneau de son niveau est une erreur.
- **L'interrupteur** d'un panneau est une entrée `Bool` en tête du panneau, qui porte son
  nom et l'option `is_panel_toggle: true` : `Aléa: Bool(is_panel_toggle: true)`.
- **`nom as clé`** : deux entrées (ou deux sorties) peuvent porter le même nom, dans deux
  panneaux ou dans un seul, si l'une prend une clé à elle : `échelle as aléa_échelle`.
  Le corps les dit `échelle` et `aléa_échelle` ; Blender les nomme toutes les deux
  « échelle ». Sans `as`, un nom en double est une erreur.
- Un autre graph les appelle par position, ou par clé :
  `semis(geometry, 5.0, 2.0, aléa_échelle: 0.5, rotation_graine: 3)`. Le nom Blender
  partagé (`"Fur Density": …`) est ambigu, et refusé.
- Relu d'un arbre, un nom en double garde sa clé pour le premier socket ; les suivants
  prennent celle de leur panneau (`guide_map_seed`), sinon de leur type (`seed_vector`),
  sinon un numéro (`seed_2`). Une clé donnée par `as` se relit telle quelle tant que le
  socket garde son nom.
- Un graph sans panneau s'écrit comme avant ; un graph qui en a prend une entrée par
  ligne, le contenu d'un panneau un cran plus loin.

## Corps

Le corps d'un graph est une suite d'instructions :

| Instruction | Sens |
|---|---|
| `nom = expression` | Nomme une valeur. Le nœud qui la calcule prend ce nom dans Blender. Un nom ne se définit qu'une fois. |
| `return expression` | La sortie d'un graph à une sortie. |
| `return (Sortie: e, …)` | Les sorties d'un graph ; une sortie omise reste non reliée. |
| `"Titre" #couleur { … }` | Un frame autour des nœuds des instructions du bloc. Titre et couleur sont facultatifs. |
| `"Note" #couleur {}` | Un frame vide : une note. |
| `"Titre" .. { … }` | La suite du dernier frame de ce titre ouvert dans le même bloc (`.. { … }` pour un frame sans titre) : le même frame, pas un second. |
| `nom = repeat(…) { … }` | Une [zone Repeat](#zone-repeat). |
| `nom = simulate(…) { … }` | Une [zone Simulation](#zone-simulation). |
| `nom = foreach(…) { … }` | Une [zone For Each](#zone-for-each). |
| `nom = closure(…) -> … { … }` | Une [zone Closure](#bundles-et-closures). |

`return` est la dernière instruction. Un nom que rien ne lit fait quand même son nœud :
c'est ainsi que s'écrivent un Warning, un gizmo ou un nœud mis de côté, qui
n'alimentent aucune sortie (`alerte = Warning(taille < 0.0, "Taille négative")`). Un
frame n'est pas une portée : les noms qu'il
définit restent utilisables après lui. Les frames s'imbriquent. La couleur s'écrit en
hexadécimal (`#e07030`, `#e73`) ou par un des 148 noms CSS (`#orange`, `#teal`…).

Les instructions d'un frame ne se suivent pas toujours : un nœud du frame peut dépendre
d'un nœud d'ailleurs, qui dépend lui-même du frame. Le texte rouvre alors le frame par
`..`, sans répéter sa couleur :

```
"Bouts" #teal {
  p = Position()
}
h = sin(p.x + t) * 0.2
"Bouts" .. {
  return SetPosition(geometry, offset: CombineXYZ(z: h))
}
```

Deux blocs `"Bouts" { … }` sans `..` font deux frames du même titre. Une note ne se
continue pas.

### Présentation d'un nœud

Une instruction peut finir par `@` suivi de la présentation du nœud qu'elle fait, celui
que son nom désigne (le dernier d'un `|>`). Chaque partie est facultative, dans cet
ordre, sur la ligne du `@` :

```
p = Position() @ hide
h = sin(p.x + t) * 0.2 @ "Hauteur" #e07030
plus = SetPosition(geometry, offset: centre) @ #orange hide mute
return h @ "Fin"
```

- `"Libellé"` : le titre affiché du nœud, à la place de son nom de type ;
- `#couleur` : sa couleur, écrite comme celle d'un frame ;
- `hide` : le nœud est replié ;
- `mute` : le nœud est désactivé ; il laisse passer sa première entrée.

Un nœud présenté autrement qu'un nœud neuf est toujours une instruction nommée : un nœud
écrit dans une expression n'a pas de place pour sa présentation. Un arbre sans
présentation particulière s'écrit sans aucun `@`.

Après `return`, la présentation est celle du Group Output ou, dans le bloc d'une zone
(`repeat`, `simulate`, `foreach`, `closure`), celle du nœud de sortie de la zone ; une
zone ne prend pas de `@` après son accolade. Une instruction qui ne fait pas de nœud à
elle (`a = b`) n'en prend pas. Le `@` vient après tout le reste de l'instruction, y
compris un `-> (…)` : `s = SeparateBundle(b) -> (a: Float) @ hide`.

## Expressions

### Valeurs

- Nombres : `3` est un entier, `3.0`, `0.5`, `1e-3` des décimaux. Un décimal ne va pas
  dans une entrée `Int`.
- Chaînes : `"texte"`, sur une ligne, sans guillemet dedans.
- `true`, `false`.
- Tuples de 2 à 4 nombres : `(0.5, 0.5)`, `(1.0, 0.0, 0.0)`, `(1.0, 0.5, 0.0, 1.0)`.
- Un nom : une entrée du graph, un nom défini plus haut, ou une valeur d'énumération.

### Nœuds

```
NomDuNœud(entrée, entrée, nom: entrée, propriété: VALEUR)
```

- Le nom d'un nœud est son nom anglais sans préfixe : `SetPosition`, `MeshGrid`,
  `DistributePointsOnFaces`. Les nœuds `Input…` perdent aussi `Input` quand le nom est
  libre : `Position()`, `Index()`. Le `bl_idname` complet marche toujours
  (`GeometryNodeSetPosition`).
- Les arguments donnent d'abord les entrées dans l'ordre, puis par leur clé. Un argument
  positionnel ne suit pas un argument nommé.
- Un argument nommé qui est une propriété du nœud (et pas une entrée) règle cette
  propriété : `domain: FACE`, `operation: POWER`, `use_clamp: true`.
- Une entrée multiple (Join Geometry, la valeur d'un gizmo) reçoit chaque argument
  positionnel à partir d'elle : les entrées qui la suivent se donnent par leur clé,
  `MeshBoolean(a, b, c, self_intersection: true)`.
- Un **gizmo** se relie à la valeur qu'il déplace, comme dans l'éditeur :
  `GizmoLinear(hauteur, position: centre)`, `GizmoTransform(CombineTransform(centre))`.
  Sa sortie Transform se joint à la géométrie rendue.
- **`n.sortie`** choisit une sortie d'un nœud qui en a plusieurs : `points.rotation`.
  Sans choix, c'est la première.
- **`v.x`, `v.y`, `v.z`** : une composante d'un vecteur, par un Separate XYZ partagé.

### Enchaîner

`a |> F(b)` vaut `F(a, b)` : la valeur de gauche devient la première entrée. Les chaînes
se lisent de haut en bas :

```
sol |> SubdivideMesh(2)
  |> SetShadeSmooth()
```

`+` entre géométries donne un seul Join Geometry : `a + b + c` les joint dans cet ordre,
quelles que soient les parenthèses.
Un Join qui en alimente un autre se relit donc sous un nom : `ab = a + b` puis
`ab + c`.

### Formules

Les opérateurs et les fonctions donnent des nœuds Math, Vector Math, Compare et Boolean
Math, choisis selon le type des opérandes (un `Vector` mêlé à un nombre donne un Vector
Math).

| Écrit | Nœud |
|---|---|
| `a + b`, `a - b`, `a * b`, `a / b`, `-a` | Math ou Vector Math ; `v * 2.0` est un Scale |
| `u ⋅ v`, `u × v` (au clavier `u dot v`, `u cross v`) | Vector Math, produit scalaire et vectoriel |
| `a < b`, `<=`, `>`, `>=`, `==`, `!=` | Compare (Float, Int, Vector, Color ou String) |
| `a and b`, `a or b`, `a xor b`, `not a` | Boolean Math |
| `xnor(a, b)`, `nand`, `nor`, `imply`, `nimply` | Boolean Math |
| `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sinh`, `cosh`, `tanh` | Math (et Vector Math pour `sin`, `cos`, `tan`) |
| `sqrt`, `exp`, `log`, `pow`, `radians`, `degrees`, `round`, `trunc` | Math |
| `abs`, `min`, `max`, `floor`, `ceil`, `fract`, `sign`, `mod` | Math ou Vector Math |
| `length`, `normalize`, `distance`, `dot`, `cross` | Vector Math |

Ordre de priorité, du plus lâche au plus fort : `|>` ; `or` et `xor` ; `and` ; `not` ;
les comparaisons ; `+ -` ; `* / ⋅ ×` ; `-` unaire ; `.sortie`. Une seule comparaison à
la fois : `a < b < c` est une erreur. Un Compare ou un Math qu'aucune formule ne dit
(un epsilon changé, une opération sans signe) s'écrit en appel :
`Math(a, b, operation: WRAP)`.

### Nœuds à items

Les nœuds dont les sockets sont une liste d'items reçoivent leurs items de l'appel,
après leurs entrées fixes :

| Écrit | Items |
|---|---|
| `c = CaptureAttribute(geometry, hauteur: h, "Rest Position": p, domain: FACE)` | un item par valeur nommée, du type de sa valeur ; `c.hauteur` la relit |
| `IndexSwitch(i, a, b, c)` | un item par valeur après l'index |
| `m = MenuSwitch(mode, Lisse: a, Rugueux: b)` | un item par nom ; `m.output` est la valeur choisie, `m.lisse` vrai quand Lisse l'est |
| `FormatString("{nom} n°{n}", nom: s, n: i)` | un item par valeur nommée (`Float`, `Int` ou `String`), lu par `{nom}` dans le format |
| `b = Bake(Geometry: g, h: hauteur)` | un item par valeur nommée, entrée et sortie : `b.geometry`, `b.h` |
| `l = FieldToList(n, valeur: Index())` | après le nombre d'éléments, un champ par nom ; `l.valeur` est sa liste |
| `f = FieldToGrid(topologie, a: champ)` | après la topologie, un champ par nom (`Float`, `Int`, `Bool`, `Vector`) ; `f.a` est sa grille |
| `r = RasterizePoints(points, densité: d, vitesse: v)` | après les entrées fixes, un item par nom, `Float` ou `Vector` ; `r.densité` |
| `CombineList(a, b, c)` | un item par valeur ; la liste de ces valeurs |
| `vue = Viewer(geometry: g, hauteur: h)` | un item par valeur nommée, montrée dans l'éditeur ; une instruction que rien ne lit |

Les items d'un switch et de Combine List ont le type de la première valeur, ou celui de
`data_type:` écrit ; ceux des autres nœuds, chacun le type de sa valeur.
`_` laisse un item vide, sans lien ni valeur, quand les items partagent un type :
`IndexSwitch(i, geometry, _, cube)`.

**Options d'un item.** Les autres réglages d'un item nommé s'écrivent entre parenthèses
après son nom, sous leur nom Blender, comme les [options d'une entrée](#entrées-et-sorties) :

```
MenuSwitch(mode, Lisse(description: "Garde la géométrie telle quelle"): a, Rugueux: b)
Bake(Geometry: g, h(attribute_domain: FACE, is_attribute: true): hauteur)
```

Une option absente garde le réglage d'un item neuf ; le nom et le type ne s'écrivent
pas en option. Le constructeur refuse une option que l'item n'a pas, et un nom que
Blender changerait (Format String n'accepte que des identifiants : `{a b}` deviendrait
`a_b`). Sur un item Bake qui n'est pas un champ (une géométrie…), Blender règle
lui-même `is_attribute` et `attribute_domain` : le texte ne les écrit pas.

**Type d'un item.** Un item prend le type de sa valeur. Quand elle ne le dit pas (un `Int`
pour un item `Float`, un tuple pour une `Rotation`, un texte pour un `Object`), le type
s'écrit avant `=` : `hauteur: Float = i`, `angle: Rotation = (0.0, 0.0, 1.57)`. Un item
sans lien ni valeur s'écrit par son **type seul** : `cache: Bundle`, `g: Geometry` ; quand
un nom du texte porte déjà ce nom de type (une entrée `Geometry`), `g: Geometry = _`. Les
options restent après le nom : `CombineBundle(n(structure_type: SINGLE): Float = i)`. La règle vaut pour
les nœuds à items dont chaque item a son type (Capture Attribute, Bake, Format String…),
les états et items des zones, CombineBundle et EvaluateClosure ; Tree → Text n'écrit le
type que quand il le faut.

### Zone Repeat

```
r = repeat(tours, état: départ, …) {
  …
  return (état: suivant, …)
}
```

Le nombre de tours d'abord, puis chaque état avec sa valeur de départ. Dans le bloc,
chaque état est un nom, et `iteration` le numéro du tour (0, 1, 2…). `return` donne les
états du tour suivant ; un état non rendu passe tel quel. Après le bloc, `r.état` est sa
dernière valeur (`r` seul quand il n'y a qu'un état). Les noms du bloc y restent ; les
zones s'imbriquent.

Un état prend le type de sa valeur de départ, ou celui écrit avant `=` ; sans valeur de
départ, il s'écrit par son type seul (voir le [type d'un item](#nœuds-à-items)) :
`repeat(n, mesh: Geometry)` part d'une géométrie vide, `cache: Bundle` d'un bundle vide,
`angle: Rotation = (0.0, 0.0, 1.57)` d'une rotation. De même dans `return`, et pour les
items de `simulate` et `foreach`.

### Zone Simulation

```
s = simulate(état: départ, …) {
  …
  return (état: suivant, …, skip: condition)
}
```

Comme `repeat`, sans nombre de tours : le bloc fait un pas par image. Dans le bloc,
chaque état est un nom, et `delta_time` le temps écoulé depuis le pas précédent, en
secondes. `return` donne les états du pas suivant ; un état non rendu passe tel quel ;
`skip: condition` (facultatif) saute le pas tant que la condition est vraie. Après le
bloc, `s.état` est la valeur du pas courant (`s` seul quand il n'y a qu'un état). Les
états peuvent être `Float`, `Int`, `Bool`, `Vector`, `Color`, `Rotation`, `Matrix`,
`String`, `Geometry` et `Bundle` ; ils ne s'appellent ni `delta_time` ni `skip`.

```
geometry graph chute(geometry: Geometry, gravité: Float = -9.8) -> Geometry {
  s = simulate(points: geometry, vitesse: 0.0) {
    v = vitesse + gravité * delta_time
    return (points: SetPosition(points, offset: CombineXYZ(z: v * delta_time)), vitesse: v)
  }
  return s.points
}
```

### Zone For Each

```
e = foreach(géométrie, domain: FACE, selection: masque, item: champ, …) {
  …
  return (principal: v, …, mesh: g, attribut: a, …)
}
```

Le bloc s'exécute une fois par élément du domaine (`POINT` par défaut ; `EDGE`, `FACE`,
`CORNER`, `CURVE`, `INSTANCE`, `LAYER`), pour les éléments de la sélection (tous par
défaut). Chaque autre valeur nommée est un **item d'entrée** : un champ, évalué sur le
domaine, dont le bloc lit la valeur de l'élément sous son nom. Le bloc lit aussi `index`,
le numéro de l'élément, et `element`, sa géométrie seule (sauf pour `CORNER`).

`return` donne les items de sortie, tous par nom, et leur ordre a un sens :

- les valeurs avant la première `Geometry` sont les **items principaux** : un champ sur
  la géométrie d'entrée, une valeur par élément ;
- chaque `Geometry` est un **item généré** : les géométries de tous les éléments, jointes ;
  les valeurs qui la suivent sont ses attributs.

Après le bloc, `e` seul est la géométrie d'entrée, sur laquelle se lisent les items
principaux ; `e.nom` est un item (`e.geometry` est la géométrie d'entrée tant qu'aucun
item ne s'appelle `geometry`).

```
geometry graph semis(mesh: Geometry) -> (Geometry: Geometry, Double: Float, Points: Geometry) {
  e = foreach(mesh, domain: FACE, centre: Position()) {
    return (double: index * 2.0, points: Points(position: centre), rang: index)
  }
  return (Geometry: e, Double: e.double, Points: e.points)
}
```

Ici `double` est un item principal, `points` une géométrie générée (un point par face)
et `rang` son attribut. Les items d'entrée sont `Float`, `Int`, `Bool`, `Vector`,
`Color`, `Rotation`, `Matrix` ou `Menu` ; les items principaux et les attributs, les
mêmes sauf `Menu`.

### Bundles et closures

Un **bundle** porte plusieurs valeurs nommées dans un seul socket ; une **closure** est un
calcul qu'on passe comme une valeur, et qu'on évalue ailleurs, même dans un autre graph.

```
geometry graph ressort(force: Float) -> (f: Closure, b: Bundle) {
  f = closure(x: Float, "Point Count": Int(structure_type: SINGLE)) -> (r: Float) {
    return x * force + point_count
  }
  b = CombineBundle(hauteur: force * 2.0, f: f, nid: CombineBundle(n: 3))
  return (f: f, b: b)
}

geometry graph appliquer(geometry: Geometry, f: Closure, b: Bundle) -> Geometry {
  s = SeparateBundle(b) -> (hauteur: Float, nid: Bundle)
  h = EvaluateClosure(f, x: Position().z, "Point Count": 2) -> (r: Float)
  return SetPosition(geometry, offset: CombineXYZ(z: h + s.hauteur))
}
```

| Écrit | Nœuds |
|---|---|
| `b = CombineBundle(hauteur: h, forme: g)` | Combine Bundle : un item par valeur nommée, du type de sa valeur |
| `s = SeparateBundle(b) -> (hauteur: Float, forme: Geometry)` | Separate Bundle : ses items déclarés après `->` ; `s.hauteur` en lit un |
| `f = closure(x: Float, …) -> (r: Float, …) { … }` | une zone Closure : ses entrées entre parenthèses, ses sorties après `->` |
| `f(x: 1.0)` | Evaluate Closure, avec les items de la closure `f` définie dans ce graph |
| `EvaluateClosure(f, x: 1.0, g: Geometry) -> (r: Float)` | Evaluate Closure, ses items écrits |

- **Les items déclarés** (les entrées et sorties d'une closure, `-> (…)`) s'écrivent comme
  les entrées d'un graph : `nom: Type`, et `nom: Type(structure_type: SINGLE)` pour leur
  structure (`SINGLE`, `FIELD`, `GRID`, `LIST`, `DYNAMIC` ; `AUTO` par défaut). Ceux qui
  reçoivent une valeur (CombineBundle, EvaluateClosure) suivent la règle du
  [type d'un item](#nœuds-à-items) : `"Pin"(structure_type: SINGLE): p`.
- **Les noms d'items** sont libres, entre guillemets s'ils ne sont pas des
  identifiants : `"Pin Positions": p`, relu `s.pin_positions`. Ce ne sont pas des
  chemins : Blender remplace `/`, `.`, `-` et `:`, et le texte le refuse. Un bundle dans
  un bundle est un item de type `Bundle`, qu'on sépare à son tour ; `GetBundleItem` et
  `StoreBundleItem` prennent, eux, un chemin (`"nid/n"`).
- **Les sorties déclarées** `-> (…)` finissent l'appel : pour en choisir une sans passer
  par un nom, des parenthèses, `(SeparateBundle(b) -> (a: Float, c: Float)).c`. `-> Float`
  seul déclare un item nommé `Float`, comme pour un graph.
- **Une zone Closure** : dans son bloc, ses entrées sont des noms, et les noms du dehors
  restent visibles : la closure les **capture**. `return` donne ses sorties
  (`return valeur` quand elle n'en a qu'une) ; une sortie non rendue reste non reliée.
  Les noms du bloc y restent.
- **Évaluer une closure.** Un appel sur un nom qui tient une closure l'évalue, quand
  aucun graph, nœud, fonction ou node group du fichier ne porte ce nom. Sans `->`,
  les items sont ceux de la closure définie dans ce graph, et les entrées omises gardent
  la valeur d'un item neuf. Une closure reçue en entrée, ou tirée d'un bundle, ne dit pas
  ses items : on les écrit, avec `->` pour les sorties.
- `define_signature: true` règle l'option du même nom de CombineBundle, SeparateBundle et
  EvaluateClosure.
- Deux SeparateBundle sur un même bundle restent deux nœuds : le texte n'en fusionne
  aucun.

## Modules

Un graph appelle un autre graph par sa clé : `relief(sol, 0.5)`, `r.hauteur` pour une
de ses sorties. Le graph appelé est cherché, dans l'ordre :

1. parmi les graphs du même texte ;
2. parmi ceux qu'importent les lignes `use` ;
3. parmi les nœuds de Blender ;
4. parmi les node groups déjà dans le `.blend`, par leur clé : un asset ajouté, les
   Essentials (`smooth_by_angle(mesh, angle: 0.5)`). Ils sont utilisés tels quels.

| Écrit | Importe |
|---|---|
| `use maths` | les graphs du texte `maths.bn` du même `.blend` |
| `use maths from "//lib/maths.bn"` | ceux d'un fichier, chemin relatif au `.blend` (comme partout dans Blender) |
| `use maths from "/chemin/maths.bn"` | ceux d'un fichier, chemin absolu |
| `use maths (fbm, bosse)` | seulement ceux-là, et ce qu'ils appellent |

Construire un texte construit aussi les groupes de ses modules. Un nom importé de deux
modules, ou défini ici et importé, est une erreur ; deux `use` du même module aussi.
Les modules peuvent en importer d'autres, sans cycle. Tree → Text écrit le `use` d'un
groupe venu d'un module au lieu de recopier son graph. Les sources `https://…`, les
libraries d'assets et `{project_root}` ne sont pas encore prises en charge.

## Types et liens

Un lien relie deux sockets de même type. Entre `Float`, `Int`, `Bool`, `Vector`, `Color`
et `Rotation`, Blender convertit, et le texte le laisse faire. Une `Rotation` se relie
aussi à une `Matrix`. Les autres types (`Geometry`, `String`, `Menu`, `Matrix`, les
datablocks, `Bundle`, `Closure`, `Shader`) ne se relient qu'à leur propre type. Une
entrée `Menu` accepte aussi le nom d'un item (`Lisse` ou `"Lisse"`), une entrée de
datablock le nom du datablock (`material: "Rouille"`).

## Forme canonique

Il n'y a qu'une façon d'imprimer un texte : celle de **Formater** et de **Tree → Text**.
Les `use` triés en tête, puis une ligne vide ; une ligne vide entre deux graphs ; deux
espaces d'indentation ; un en-tête trop long (plus de 100 caractères) à une entrée par
ligne, de même pour les sorties ; un `|>` en bout de ligne puis un par ligne à partir
du deuxième ; les
appels trop longs à un argument par ligne ; `dot` et `cross` remplacés par `⋅` et `×`.
Formater garde les commentaires et les lignes vides entre instructions.

## Ce que le texte n'écrit pas

Tree → Text écrit tout l'arbre, sauf ce qui suit, qu'il signale chaque fois par un
avertissement :

- la présentation des Group Input (libellé, couleur, replié), que le texte n'a pas en
  nœuds, et celle du nœud d'entrée d'une zone (celle de sa sortie s'écrit sur le
  `return` de son bloc) ;
- un item qui porte le nom d'une entrée fixe ou d'un réglage de son nœud (un item
  « Selection » de Capture Attribute) ;
- un item d'un type que le texte ne connaît pas (Font…) ;
- le domaine d'un état de simulation ou d'un attribut généré par For Each, quand il
  n'est pas `POINT` ; la valeur d'un item de menu non relié ;
- le réglage `define_signature` d'une zone Closure ;
- Closure to List ;
- les Group Output inactifs (ce qui les alimente est écrit).

Reconstruit à sa place, un groupe prend les panneaux du texte ; ses modifiers et appels
gardent leurs réglages tant que leurs entrées existent encore, même passées d'un panneau
à l'autre.

## Compatibilité de la LTS 1

**La règle :** un texte que Nodes as Text 1.0 construit sans erreur se construit, dans
toutes les versions 1.x, en les mêmes arbres : mêmes nœuds, mêmes réglages et valeurs,
mêmes liens, même interface.

Une version 1.x peut :

- ajouter de la syntaxe : un texte écrit pour la 1.2 peut ne pas se construire en 1.0 ;
- écrire en texte ce que la 1.0 signalait par un avertissement ;
- donner des messages d'erreur et des avertissements plus précis, ou en ajouter ;
- corriger un bogue, quand la 1.0 construisait un arbre qui ne correspond pas à son
  texte. La correction est dite dans les notes de version.

Elle ne change ni le sens d'un texte valide, ni sa forme canonique.

**Comment c'est tenu :** [`tests/bnodes/compat/1.0`](../tests/bnodes/compat/1.0) contient un
texte qui emploie chaque construction du langage (`tout.bn`, avec son module
`outils.bn`), les autres écritures acceptées (`formes.bn`), et, sous `autres/`, les
arbres des fixtures, des exemples et de Maths. Pour chaque texte, l'arbre construit en
1.0 est gardé en JSON. `tests/bnodes/host/test_compat.py` reconstruit tout et compare ;
il fait partie de `tests/run.sh`.

**Versions de Blender :** la 1.0 est testée sur Blender 5.2 LTS. Blender 5.3 LTS le sera
dès sa sortie, avec le même corpus.
