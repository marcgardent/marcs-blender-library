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

## Corps

Le corps d'un graph est une suite d'instructions :

| Instruction | Sens |
|---|---|
| `nom = expression` | Nomme une valeur. Le nœud qui la calcule prend ce nom dans Blender. Un nom ne se définit qu'une fois. |
| `return expression` | La sortie d'un graph à une sortie. |
| `return (Sortie: e, …)` | Les sorties d'un graph ; une sortie omise reste non reliée. |
| `"Titre" #couleur { … }` | Un frame autour des nœuds des instructions du bloc. Titre et couleur sont facultatifs. |
| `"Note" #couleur {}` | Un frame vide : une note. |
| `nom = repeat(…) { … }` | Une [zone Repeat](#zone-repeat). |

`return` est la dernière instruction. Un frame n'est pas une portée : les noms qu'il
définit restent utilisables après lui. Les frames s'imbriquent. La couleur s'écrit en
hexadécimal (`#e07030`, `#e73`) ou par un des 148 noms CSS (`#orange`, `#teal`…).

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
- Une entrée multiple (Join Geometry) reçoit chaque argument donné pour elle.
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

- la présentation des nœuds : libellé, couleur, nœud replié ; un nœud désactivé (mute)
  s'écrit actif ;
- les panneaux de l'interface, et deux entrées du même nom dans deux panneaux ;
- les réglages d'outil de l'arbre (`is_tool`…), et le bouton de gestion du modifier ;
- un item qui porte le nom d'une entrée fixe ou d'un réglage de son nœud (un item
  « Selection » de Capture Attribute) ;
- un item typé (Capture Attribute, Bake, Format String…) sans lien ni valeur que le texte sache
  écrire (une géométrie non reliée) ;
- les zones Simulation et For Each, les bundles et closures, Closure to List, le
  Viewer et les gizmos ;
- les nœuds qui n'influencent aucune sortie.

Reconstruit à sa place, un groupe garde ses panneaux, et ses modifiers et appels gardent
leurs réglages tant que leurs entrées existent encore.

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
