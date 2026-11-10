"""Tests of the maths toolbox (src/maths.bn), run inside Blender:

    blender --background --factory-startup --python-exit-code 1 --python tests/bnodes/host/test_maths.py

Every function is evaluated by Blender on the points of a line, and compared
with the same formula in Python.
"""

import math
import sys
import traceback
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "addons"))

from bnodes.host import build_source, export_tree  # noqa: E402
from bnodes.lang import parse  # noqa: E402
from bnodes.lang.format import format_source  # noqa: E402
from bnodes.lang.printer import to_source  # noqa: E402

SRC = (ROOT / "src" / "maths.bn").read_text()
N = 64

# Inputs of point i, the same in the tree and in Python: spread by golden-ratio steps
X = "fract(i * 0.618034 + 0.05)"
Y = "fract(i * 0.414214 + 0.3)"
U = "CombineXYZ(fract(i * 0.618034), fract(i * 0.732051), fract(i * 0.236068)) * 4.0 - (2.0, 2.0, 2.0)"
V = "CombineXYZ(fract(i * 0.381966), fract(i * 0.302776), fract(i * 0.828427)) * 4.0 - (2.0, 2.0, 2.0)"


def fract(v):
    return v - math.floor(v)


def x_(i):
    return fract(i * 0.618034 + 0.05)


def y_(i):
    return fract(i * 0.414214 + 0.3)


def u_(i):
    return tuple(fract(i * k) * 4.0 - 2.0 for k in (0.618034, 0.732051, 0.236068))


def v_(i):
    return tuple(fract(i * k) * 4.0 - 2.0 for k in (0.381966, 0.302776, 0.828427))


def dot(a, b):
    return sum(p * q for p, q in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def sub(a, b):
    return tuple(p - q for p, q in zip(a, b))


def scale(a, s):
    return tuple(p * s for p in a)


def length(a):
    return math.sqrt(dot(a, a))


def clamp(v, lo=0.0, hi=1.0):
    return min(max(v, lo), hi)


def smoothstep(e0, e1, v):
    t = clamp((v - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def bias(x, b):
    return x / ((1.0 / b - 2.0) * (1.0 - x) + 1.0)


def on_plane(v, n):
    n = scale(n, 1.0 / length(n))
    return sub(v, scale(n, dot(v, n)))


def segment(p, a, b):
    ab = sub(b, a)
    t = clamp(dot(sub(p, a), ab) / dot(ab, ab))
    return t, tuple(q + r * t for q, r in zip(a, ab))


def box(p, b):
    q = sub(tuple(abs(c) for c in p), b)
    return length(tuple(max(c, 0.0) for c in q)) + min(max(q), 0.0)


def cylinder(p, r, h):
    d = (math.hypot(p[0], p[1]) - r, abs(p[2]) - h)
    return min(max(d), 0.0) + math.hypot(max(d[0], 0.0), max(d[1], 0.0))


def bounce(t):
    for edge, shift, top in ((1 / 2.75, 0.0, 0.0), (2 / 2.75, 1.5 / 2.75, 0.75),
                             (2.5 / 2.75, 2.25 / 2.75, 0.9375), (2.0, 2.625 / 2.75, 0.984375)):
        if t < edge:
            return 7.5625 * (t - shift) ** 2 + top


def cone(p, h, r1, r2):
    q = (math.hypot(p[0], p[1]), p[2])
    ca = (q[0] - min(q[0], r1 if q[1] < 0 else r2), abs(q[1]) - h)
    k1, k2 = (r2, h), (r2 - r1, 2 * h)
    t = clamp(dot(sub(k1, q), k2) / dot(k2, k2))
    cb = (q[0] - k1[0] + k2[0] * t, q[1] - k1[1] + k2[1] * t)
    s = -1.0 if cb[0] < 0 and ca[1] < 0 else 1.0
    return s * math.sqrt(min(dot(ca, ca), dot(cb, cb)))


def ellipsoid(p, r):
    k0 = length(tuple(a / b for a, b in zip(p, r)))
    return k0 * (k0 - 1) / length(tuple(a / (b * b) for a, b in zip(p, r)))


def twist(p, k):
    a = p[2] * k
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a), p[2])


def bend(p, k):
    a = p[0] * k
    return (p[0] * math.cos(a) - p[2] * math.sin(a), p[1], p[0] * math.sin(a) + p[2] * math.cos(a))


def sphere_normal(p, e):
    d = length(p) - 1.0
    g = [length(tuple(c + (e if j == k else 0.0) for j, c in enumerate(p))) - 1.0 - d for k in range(3)]
    return scale(g, 1.0 / length(g))


def fibonacci(i, n):
    z = 1 - (2 * i + 1) / n
    r = math.sqrt(1 - z * z)
    return (r * math.cos(i * 2.399963), r * math.sin(i * 2.399963), z)


def wrap(v, lo, hi):
    return v - (hi - lo) * math.floor((v - lo) / (hi - lo))


# name: (call in text, Python reference of point i)
FLOATS = {
    "biais": (f"biais({X}, 0.25)", lambda i: bias(x_(i), 0.25)),
    "gain": (f"gain({X}, 0.3)", lambda i: (bias(2 * x_(i), 0.3) / 2 if x_(i) < 0.5
                                            else 1 - bias(2 - 2 * x_(i), 0.3) / 2)),
    "accélère": (f"accélère({X}, 3.0)", lambda i: x_(i) ** 3),
    "freine": (f"freine({X}, 3.0)", lambda i: 1 - (1 - x_(i)) ** 3),
    "accélère_freine": (f"accélère_freine({X}, 2.5)", lambda i: (
        0.5 * (2 * x_(i)) ** 2.5 if x_(i) < 0.5 else 1 - 0.5 * (2 - 2 * x_(i)) ** 2.5)),
    "rebond": (f"rebond({X})", lambda i: bounce(x_(i))),
    "élastique": (f"élastique({X})", lambda i: math.exp(-6.931472 * x_(i)) * math.sin((10 * x_(i) - 0.75) * 2.094395) + 1),
    "recul": (f"recul({X})", lambda i: 2.70158 * x_(i) ** 3 - 1.70158 * x_(i) ** 2),
    "impulsion": (f"impulsion({X}, 6.0)", lambda i: 6 * x_(i) * math.exp(1 - 6 * x_(i))),
    "bosse": (f"bosse({X}, 0.4, 0.25)", lambda i: 1 - smoothstep(0.0, 1.0, abs(x_(i) - 0.4) / 0.25)),
    "parabole": (f"parabole({X}, 2.0)", lambda i: (4 * x_(i) * (1 - x_(i))) ** 2),
    "marches": (f"marches({X} * 5.0, 0.3)", lambda i: (
        math.floor(x_(i) * 5) + smoothstep(0.7, 1.0, fract(x_(i) * 5)))),
    "triangle": (f"triangle({X} * 3.0)", lambda i: 1 - abs(fract(x_(i) * 3) * 2 - 1)),
    "créneau": (f"créneau({X} * 3.0, 0.3)", lambda i: float(fract(x_(i) * 3) < 0.3)),
    "sinus01": (f"sinus01({X})", lambda i: math.sin(x_(i) * 2 * math.pi) * 0.5 + 0.5),
    "angle_ramené": (f"angle_ramené(({X} - 0.5) * 20.0)", lambda i: wrap((x_(i) - 0.5) * 20, -math.pi, math.pi)),
    "angle_entre": (f"angle_entre({U}, {V})", lambda i: math.acos(
        clamp(dot(u_(i), v_(i)) / (length(u_(i)) * length(v_(i))), -1.0, 1.0))),
    "angle_signé": (f"angle_signé({U}, {V}, (0.3, -0.2, 1.0))", lambda i: (lambda a, b, n: math.atan2(
        dot(cross(a, b), scale(n, 1 / length(n))), dot(a, b)))(
            on_plane(u_(i), (0.3, -0.2, 1.0)), on_plane(v_(i), (0.3, -0.2, 1.0)), (0.3, -0.2, 1.0))),
    "composante_max": (f"composante_max({U})", lambda i: max(u_(i))),
    "composante_min": (f"composante_min({U})", lambda i: min(u_(i))),
    "luminance": (f"luminance({U})", lambda i: dot(u_(i), (0.2126, 0.7152, 0.0722))),
    "segment_distance": (f"proche_sur_segment({U}, (-1.0, 0.0, 0.5), (1.0, 1.0, -0.5)).distance",
                         lambda i: length(sub(u_(i), segment(u_(i), (-1, 0, 0.5), (1, 1, -0.5))[1]))),
    "segment_facteur": (f"proche_sur_segment({U}, (-1.0, 0.0, 0.5), (1.0, 1.0, -0.5)).facteur",
                        lambda i: segment(u_(i), (-1, 0, 0.5), (1, 1, -0.5))[0]),
    "sdf_sphère": (f"sdf_sphère({U}, 1.2)", lambda i: length(u_(i)) - 1.2),
    "sdf_boîte": (f"sdf_boîte({U}, (1.0, 0.5, 0.8))", lambda i: box(u_(i), (1.0, 0.5, 0.8))),
    "sdf_tore": (f"sdf_tore({U}, 1.0, 0.3)", lambda i: math.hypot(
        math.hypot(u_(i)[0], u_(i)[1]) - 1.0, u_(i)[2]) - 0.3),
    "sdf_cylindre": (f"sdf_cylindre({U}, 0.7, 1.1)", lambda i: cylinder(u_(i), 0.7, 1.1)),
    "sdf_capsule": (f"sdf_capsule({U}, (-1.0, 0.0, 0.5), (1.0, 1.0, -0.5), 0.4)",
                    lambda i: length(sub(u_(i), segment(u_(i), (-1, 0, 0.5), (1, 1, -0.5))[1])) - 0.4),
    "soustraction_douce": (f"soustraction_douce({X} - 0.5, {Y} - 0.5, 0.2)", lambda i: (
        # Blender's smooth max: -smin(-a, -b, k), with smin(a, b, k) = min(a, b) - h³k/6
        (lambda a, b, k: max(a, b) + (max(k - abs(a - b), 0.0) / k) ** 3 * k / 6.0)(x_(i) - 0.5, -(y_(i) - 0.5), 0.2))),
    "coque": (f"coque({X} - 0.5, 0.2)", lambda i: abs(x_(i) - 0.5) - 0.1),
    "sdf_cône": (f"sdf_cône({U}, 1.2, 1.0, 0.3)", lambda i: cone(u_(i), 1.2, 1.0, 0.3)),
    "sdf_cône_pointu": (f"sdf_cône({U}, 1.0, 0.8)", lambda i: cone(u_(i), 1.0, 0.8, 0.0)),
    "sdf_ellipsoïde": (f"sdf_ellipsoïde({U}, (1.2, 0.7, 0.5))", lambda i: ellipsoid(u_(i), (1.2, 0.7, 0.5))),
    "sdf_octaèdre": (f"sdf_octaèdre({U}, 1.3)", lambda i: (sum(abs(c) for c in u_(i)) - 1.3) * 0.5773503),
    "sdf_cercle": (f"sdf_cercle({U}, 0.9)", lambda i: math.hypot(u_(i)[0], u_(i)[1]) - 0.9),
    "sdf_rectangle": (f"sdf_rectangle({U}, (1.1, 0.4))", lambda i: box(u_(i)[:2], (1.1, 0.4))),
}

VECTORS = {
    "sur_le_plan": (f"sur_le_plan({U}, (0.3, -0.2, 1.0))", lambda i: on_plane(u_(i), (0.3, -0.2, 1.0))),
    "segment_point": (f"proche_sur_segment({U}, (-1.0, 0.0, 0.5), (1.0, 1.0, -0.5)).point",
                      lambda i: segment(u_(i), (-1, 0, 0.5), (1, 1, -0.5))[1]),
    "torsion": (f"torsion({U}, 0.8)", lambda i: twist(u_(i), 0.8)),
    "courbure": (f"courbure({U}, 0.6)", lambda i: bend(u_(i), 0.6)),
    "normale_sdf": (f"normale_sdf(sdf_sphère({U}), sdf_sphère({U} + (0.01, 0.0, 0.0)), "
                    f"sdf_sphère({U} + (0.0, 0.01, 0.0)), sdf_sphère({U} + (0.0, 0.0, 0.01)))",
                    lambda i: sphere_normal(u_(i), 0.01)),
    "palette": (f"palette({X})", lambda i: tuple(
        0.5 + 0.5 * math.cos(2 * math.pi * (x_(i) + d)) for d in (0.0, 0.33, 0.67))),
    "fibonacci": ("point_fibonacci(i, 64)", lambda i: fibonacci(i, 64)),
    "r2": ("suite_r2(i)", lambda i: (fract(i * 0.7548777 + 0.5), fract(i * 0.5698403 + 0.5), 0.0)),
    "répétition": (f"répétition({U}, (1.5, 0.7, 2.5))", lambda i: tuple(
        p - c * math.floor(p / c + 0.5) for p, c in zip(u_(i), (1.5, 0.7, 2.5)))),
    # Checked by their properties below: their value is free
    "perpendiculaire": (f"perpendiculaire({U})", None),
    "direction": ("direction_aléatoire(i, 7)", None),
    "disque": ("point_dans_disque(i, 7)", None),
}


def octaves(n, ridged=False):
    """The fbm of 3 octaves written out, without a repeat: the reference for the zone."""
    terms = []
    for k in range(n):
        f, a = 2.0 ** k, 0.5 ** (k + 1)
        shift = tuple(round(k * c, 6) for c in (1.7, 9.2, 3.1))
        noise = f"(TexNoise(({U}) * {f} + {shift}, 1.0, 0.0).factor * 2.0 - 1.0)"
        if ridged:
            noise = f"(1.0 - abs{noise}) * (1.0 - abs{noise})"
        terms.append(f"{noise} * {a}")
    return " + ".join(terms)


# name: (call, the same in Blender without the toolbox)
NOISES = {
    "fbm": (f"fbm({U}, 3)", octaves(3)),
    "fbm_crêtes": (f"fbm_crêtes({U}, 3)", octaves(3, ridged=True)),
}


def probe_source():
    stores = []
    for name, (call, unrolled) in NOISES.items():
        stores.append(f'StoreNamedAttribute(name: "{name}", value: {call})')
        stores.append(f'StoreNamedAttribute(name: "{name}_ref", value: {unrolled})')
    for name, (call, _) in FLOATS.items():
        stores.append(f'StoreNamedAttribute(name: "{name}", value: {call})')
    for name, (call, _) in VECTORS.items():
        stores.append(f'StoreNamedAttribute(name: "{name}", value: {call}, data_type: FLOAT_VECTOR)')
    chain = "\n    |> ".join(stores)
    return (f"geometry graph sonde() -> Geometry {{\n  i = Index()\n"
            f"  return MeshLine({N})\n    |> {chain}\n}}\n")


def evaluate():
    trees = build_source(SRC + "\n" + probe_source(), "sonde.bn")
    mesh = bpy.data.meshes.new("sonde")
    obj = bpy.data.objects.new("sonde", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new("sonde", "NODES").node_group = trees[-1]
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    values = {}
    for name in [*FLOATS, *NOISES, *(n + "_ref" for n in NOISES)]:
        values[name] = [d.value for d in ev.attributes[name].data]
    for name in VECTORS:
        values[name] = [tuple(d.vector) for d in ev.attributes[name].data]
    return values


VALUES = None


def values():
    global VALUES
    if VALUES is None:
        VALUES = evaluate()
    return VALUES


def close(a, b, tol=2e-4):
    return abs(a - b) <= tol * max(1.0, abs(b))


def test_source_is_formatted():
    assert format_source(SRC) == SRC


def test_every_graph_reads_back_as_written():
    trees = build_source(SRC, "maths.bn")
    assert len(trees) == 47, len(trees)
    for tree in trees:
        text, warnings = export_tree(tree)
        assert warnings == [], (tree.name, warnings)
        assert all(link.is_valid for link in tree.links), tree.name
        # A tree comes back with the graphs it calls, as in the source
        expected = {g.name for g in parse(text).graphs}
        program = parse(SRC)
        program.graphs = [g for g in program.graphs if g.name in expected]
        assert text == to_source(program), text


def test_floats_match_python():
    got = values()
    bad = []
    for name, (_, ref) in FLOATS.items():
        for i, v in enumerate(got[name]):
            if not close(v, ref(i)):
                bad.append(f"{name}[{i}] = {v}, attendu {ref(i)}")
    assert not bad, "\n".join(bad[:20])


def test_vectors_match_python():
    got = values()
    bad = []
    for name, (_, ref) in VECTORS.items():
        if ref is None:
            continue
        for i, v in enumerate(got[name]):
            if not all(close(a, b) for a, b in zip(v, ref(i))):
                bad.append(f"{name}[{i}] = {v}, attendu {ref(i)}")
    assert not bad, "\n".join(bad[:20])


def test_fractal_noises_match_their_octaves_written_out():
    got = values()
    for name in NOISES:
        assert all(close(a, b, 1e-5) for a, b in zip(got[name], got[name + "_ref"])), name
        assert max(got[name]) - min(got[name]) > 0.2, name


def test_perpendicular_is_unit_and_perpendicular():
    for i, p in enumerate(values()["perpendiculaire"]):
        assert close(length(p), 1.0) and abs(dot(p, u_(i))) < 1e-4, (i, p, u_(i))


def test_random_directions_are_unit_and_spread():
    dirs = values()["direction"]
    assert all(close(length(d), 1.0) for d in dirs)
    assert len({tuple(round(c, 3) for c in d) for d in dirs}) == N
    assert any(d[2] > 0.5 for d in dirs) and any(d[2] < -0.5 for d in dirs)


def test_random_disc_points_stay_in_the_disc():
    pts = values()["disque"]
    assert all(length(p) <= 1.0 + 1e-6 and p[2] == 0.0 for p in pts)
    assert len({tuple(round(c, 3) for c in p) for p in pts}) == N
    assert any(length(p) > 0.8 for p in pts)


def main():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


main()
