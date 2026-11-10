# Nodes as Text : exemples

Nodes as Text écrit un arbre Geometry Nodes comme une fonction, dans un texte `.bn`
du Text Editor de Blender, et relit un arbre existant en texte. L'installation et les
raccourcis sont dans le [README](../README.md#nodes-as-text).

Les trois exemples ci-dessous couvrent toute la syntaxe. Ce sont de vrais fichiers,
dans [`exemples/`](exemples/) : un test les construit dans Blender et vérifie que
l'arbre se relit en texte à l'identique.

**Pour en essayer un** : ouvrir le `.bn` dans un Text Editor, Ctrl+Entrée, puis dans le
panneau Nodes, **Add as Modifier** sur un objet sélectionné, et régler ses entrées dans
le modifier.

## La syntaxe en bref

| Écrit | Donne |
|---|---|
| `geometry graph herbe(sol: Geometry, densité: Float) -> Geometry { … }` | un node group, ses entrées et sa sortie |
| `"Pente max": Float`, puis `pente_max` | un nom avec espaces, utilisé en snake_case |
| `force: Float = 0.25 in 0.0..1.0`, `p: Vector = Position()` | une entrée avec sa valeur par défaut et ses bornes, une entrée qui prend la position |
| `r = repeat(n, somme: 0.0) { return somme + iteration }` | une zone Repeat : ses états, le numéro du tour, les états suivants |
| `-> (Mesh: Geometry, Hauteur: Float)` et `return (Mesh: m, Hauteur: h)` | plusieurs sorties |
| `points = DistributePointsOnFaces(sol, density: 2.0)` | un nœud, entrées dans l'ordre puis par nom |
| `points.rotation`, `p.z` | une sortie d'un nœud, une composante d'un vecteur |
| `a \|> SetShadeSmooth() \|> …` | enchaîne : `a` devient la première entrée |
| `a + b` entre géométries | un seul Join Geometry, même pour `a + b + c` |
| `+ - * /`, `-x`, `sin`, `cos`, `min`, `max`, `normalize`… | Math et Vector Math |
| `n ⋅ u`, `n × u` (au clavier : `n dot u`, `n cross u`) | produit scalaire, produit vectoriel |
| `< <= > >= == !=` | Compare |
| `and`, `or`, `xor`, `not` | Boolean Math (`and` lie plus fort que `or` et `xor`) |
| `rocher_brut(1.0, 4).mesh` | l'appel d'un autre graph du fichier |
| `"Titre" #couleur { … }`, `#e07030 { … }`, `{ … }` | un frame autour des nœuds du bloc |
| `"À régler" #tomato {}` | une note : un frame vide |
| `// …` | un commentaire |

Les couleurs s'écrivent en hexa (`#e07030`, `#e73`) ou par un des 148 noms CSS
(`#orange`, `#steelblue`…). Un frame n'est pas une portée : un nom défini dedans reste
utilisable après.

## 1. L'herbe sur les pentes douces

De l'herbe sur les zones plates et basses d'un terrain, et quelques brins au hasard
partout ailleurs. Le produit scalaire de la normale et de la verticale donne le cosinus
de la pente ; il suffit de le comparer au cosinus de la pente maximale.

```
// De l'herbe sur les zones plates et basses d'un terrain, et quelques brins au hasard ailleurs.
geometry graph herbe(sol: Geometry, brin: Object, "Pente max": Float, densité: Float) -> Geometry {
  "Où pousser" #yellowgreen {
    // Normale ⋅ verticale = cosinus de la pente
    plat = Normal().normal ⋅ (0.0, 0.0, 1.0) > cos(radians(pente_max))
    haut = Position().z > 3.0
    rare = RandomValue(0.05, data_type: BOOLEAN)
    // and lie plus fort que xor : (plat and not haut) xor rare
    pousse = plat and not haut xor rare
  }
  "Semis" #olivedrab {
    points = DistributePointsOnFaces(sol, pousse, densité)
    brins = InstanceOnPoints(
      points.points,
      instance: ObjectInfo(brin).geometry,
      rotation: points.rotation)
  }
  return sol + brins
}
```

| Le terrain (pente max 22°, densité 150) | L'arbre construit |
|---|---|
| ![L'herbe pousse sur les crêtes et dans les creux](images/herbe-vue.png) | ![Les deux frames, Où pousser et Semis](images/herbe-noeuds.png) |

À voir :
- `Normal().normal ⋅ (0.0, 0.0, 1.0)` : le produit scalaire, et `.normal` qui choisit la
  sortie du nœud Normal (il en a deux) ;
- `> cos(radians(pente_max))` : une comparaison avec un calcul ;
- `plat and not haut xor rare` : `and` lie plus fort que `xor`, donc
  `(plat and not haut) xor rare` ;
- `brin: Object` et `ObjectInfo(brin).geometry` : un objet choisi dans le modifier ;
- `sol + brins` : le terrain et l'herbe joints en un seul Join Geometry ;
- deux frames colorés par des noms CSS.

## 2. Le serpent

Un tuyau qui ondule à l'horizontale de part et d'autre d'une courbe. Le côté vers
lequel onduler est perpendiculaire à la fois à la courbe et à la verticale : c'est leur
produit vectoriel.

```
// Un tuyau qui ondule de part et d'autre d'une courbe, à l'horizontale.
geometry graph serpent(
    courbe: Geometry,
    amplitude: Float,
    ondulations: Float,
    épaisseur: Float
) -> Geometry {
  "Ondulation" #steelblue {
    // Tangente × verticale : à plat et perpendiculaire à la courbe
    côté = normalize(Tangent() × (0.0, 0.0, 1.0))
    onde = sin(SplineParameter().factor * ondulations * 6.2832) * amplitude
  }
  return courbe |> SetPosition(offset: côté * onde)
    |> CurveToMesh(CurvePrimitiveCircle(radius: épaisseur), fill_caps: true)
    |> SetShadeSmooth()
}
```

| La courbe (amplitude 0.4, 6 ondulations, épaisseur 0.12) | L'arbre construit |
|---|---|
| ![Un tuyau bleu qui ondule](images/serpent-vue.png) | ![Le frame Ondulation et la chaîne de nœuds](images/serpent-noeuds.png) |

À voir :
- `Tangent() × (0.0, 0.0, 1.0)` puis `normalize(…)` : le produit vectoriel ;
- `côté * onde` : un vecteur multiplié par un nombre (Vector Math *Scale*) ;
- un en-tête de plus de 100 caractères : une entrée par ligne ;
- trois `|>` : le premier reste sur la ligne, les suivants vont à la ligne ;
- `CurvePrimitiveCircle(radius: épaisseur)` en argument, `fill_caps: true` par son nom.

## 3. Les rochers

Trois graphs dans un seul fichier : un bruit, un rocher qui s'en sert, et le semis des
rochers sur un sol.

```
// Des rochers semés sur un sol : un bruit pour le relief, un rocher, puis le semis.

// Un relief entre -1 et 1
geometry graph relief(p: Vector, échelle: Float) -> Float {
  return (TexNoise(p, échelle).factor - 0.5) * 2.0
}

geometry graph "Rocher brut"(taille: Float, détail: Int) -> (Mesh: Geometry, Hauteur: Float) {
  boule = MeshIcoSphere(taille, détail)
  p = Position()
  "Forme" #e07030 {
    "Bosses" {
      bosses = relief(p, 1.5) * taille * 0.8
    }
    // Le dessous est aplati
    bas = max(p.z, -(taille * 0.4))
  }
  forme = SetPosition(boule.mesh, position: CombineXYZ(p.x, p.y, bas) + Normal().normal * bosses)
  return (Mesh: forme, Hauteur: BoundBox(forme).max.z)
}

geometry graph rochers(sol: Geometry, densité: Float, graine: Int) -> Geometry {
  {
    rocher = rocher_brut(1.0, 4)
  }
  "Semis" #slategray {
    points = DistributePointsOnFaces(sol, density: densité, seed: graine)
    // Entre 0.3 et 1.0, le maximum par défaut
    taille = RandomValue(0.3, seed: graine)
    // Enfoncés d'un cinquième de leur hauteur
    posés = points.points |> InstanceOnPoints(instance: rocher.mesh, rotation: points.rotation, scale: taille)
      |> TranslateInstances(translation: CombineXYZ(z: -(rocher.hauteur * taille * 0.2)))
  }
  "À régler : la densité dépend de l'aire du sol" #tomato {}
  return sol + RealizeInstances(posés)
}
```

| Le sol (densité 0.35, graine 3) | L'arbre principal |
|---|---|
| ![Des rochers gris sur un sol](images/rochers-vue.png) | ![Le frame Semis et la note À régler](images/rochers-noeuds.png) |

À voir :
- `relief` est appelé par `"Rocher brut"`, lui-même appelé `rocher_brut(1.0, 4)` par
  `rochers` : le nom entre guillemets s'appelle en snake_case ;
- `-> (Mesh: Geometry, Hauteur: Float)` et `return (Mesh: …, Hauteur: …)` : deux
  sorties, reprises par `rocher.mesh` et `rocher.hauteur` ;
- `BoundBox(forme).max.z` : une sortie, puis sa composante ;
- `-(taille * 0.4)`, `max(…)`, `(… - 0.5) * 2.0` : les calculs ;
- un frame `"Bosses"` dans le frame `"Forme"`, un frame sans titre `{ … }`, une couleur
  en hexa `#e07030` et une note `"À régler : …" #tomato {}` ;
- `points.points |> InstanceOnPoints(…) |> TranslateInstances(…)` : une chaîne dans une
  affectation, indentée sous elle.

## Ce que le texte ne sait pas encore écrire

Les zones Simulation et For Each, les nœuds aux sockets ajoutés à la main
(Capture Attribute, Bake, Menu Switch…), le sous-type des entrées (Factor, Distance…),
les arbres de shaders et de compositing. « Tree → Text » les signale par un
avertissement.

Les images de cette page sont prises par
`blender --factory-startup --python tests/bnodes/gui/shoot_examples.py -- docs/images`.
