"""A few Geometry Nodes, shaped like what host/schema.py reads from Blender."""

from lang.schema import NodeSpec, Prop, Socket

MATH_OPS = ("ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "POWER", "MINIMUM", "MAXIMUM", "ARCTAN2",
            "SINE", "COSINE", "SQRT", "ABSOLUTE")
UNARY = {"SINE", "COSINE", "SQRT", "ABSOLUTE"}
VECTOR_OPS = ("ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "SCALE", "MINIMUM", "MAXIMUM", "DOT_PRODUCT",
              "DISTANCE", "CROSS_PRODUCT", "LENGTH", "NORMALIZE", "SINE", "ABSOLUTE")
VECTOR_UNARY = {"LENGTH", "NORMALIZE", "SINE", "ABSOLUTE"}
VECTOR_TO_FLOAT = {"LENGTH", "DOT_PRODUCT", "DISTANCE"}


def S(name, type, identifier=None, multi=False):
    return Socket(name, identifier or name, type, multi)


VALUES = [S("Value", "Float"), S("Value", "Float", "Value_001"), S("Value", "Float", "Value_002")]
VECTORS = [S("Vector", "Vector"), S("Vector", "Vector", "Vector_001"), S("Vector", "Vector", "Vector_002")]

NODES = {
    "Math": (NodeSpec("Math", "ShaderNodeMath", {
        "operation": Prop("operation", "ENUM", MATH_OPS),
        "use_clamp": Prop("use_clamp", "BOOLEAN"),
    }), None, [S("Value", "Float")]),
    "VectorMath": (NodeSpec("VectorMath", "ShaderNodeVectorMath", {
        "operation": Prop("operation", "ENUM", VECTOR_OPS),
    }), None, None),
    "Position": (NodeSpec("Position", "GeometryNodeInputPosition"), [], [S("Position", "Vector")]),
    "SeparateXYZ": (NodeSpec("SeparateXYZ", "ShaderNodeSeparateXYZ"),
                    [S("Vector", "Vector")], [S("X", "Float"), S("Y", "Float"), S("Z", "Float")]),
    "CombineXYZ": (NodeSpec("CombineXYZ", "ShaderNodeCombineXYZ"),
                   [S("X", "Float"), S("Y", "Float"), S("Z", "Float")], [S("Vector", "Vector")]),
    "SetPosition": (NodeSpec("SetPosition", "GeometryNodeSetPosition"),
                    [S("Geometry", "Geometry"), S("Selection", "Bool"), S("Position", "Vector"),
                     S("Offset", "Vector")], [S("Geometry", "Geometry")]),
    "JoinGeometry": (NodeSpec("JoinGeometry", "GeometryNodeJoinGeometry"),
                     [S("Geometry", "Geometry", multi=True)], [S("Geometry", "Geometry")]),
    "SubdivideMesh": (NodeSpec("SubdivideMesh", "GeometryNodeSubdivideMesh"),
                      [S("Mesh", "Geometry"), S("Level", "Int")], [S("Mesh", "Geometry")]),
    "SetShadeSmooth": (NodeSpec("SetShadeSmooth", "GeometryNodeSetShadeSmooth", {
        "domain": Prop("domain", "ENUM", ("EDGE", "FACE")),
    }), [S("Geometry", "Geometry"), S("Selection", "Bool"), S("Shade Smooth", "Bool")],
        [S("Geometry", "Geometry")]),
    "MeshGrid": (NodeSpec("MeshGrid", "GeometryNodeMeshGrid"),
                 [S("Size X", "Float"), S("Size Y", "Float"), S("Vertices X", "Int"), S("Vertices Y", "Int")],
                 [S("Mesh", "Geometry"), S("UV Map", "Vector")]),
    "FindInString": (NodeSpec("FindInString", "FunctionNodeFindInString"),
                     [S("String", "String"), S("Search", "String"), S("Mode", "Menu")], [S("First Found", "Int")]),
}


class FakeSchema:
    def __init__(self):
        self.calls = 0

    def node(self, kind, name):
        if kind != "geometry" or name not in NODES:
            return None
        return NODES[name][0]

    def node_names(self, kind):
        return list(NODES) if kind == "geometry" else []

    def sockets(self, kind, spec, props):
        self.calls += 1
        _spec, inputs, outputs = NODES[spec.name]
        if spec.name == "Math":
            # Like Blender: a unary operation leaves one Value available
            op = props.get("operation", "ADD")
            inputs = VALUES[:1] if op in UNARY else VALUES[:2]
        if spec.name == "VectorMath":
            op = props.get("operation", "ADD")
            if op == "SCALE":
                inputs = [VECTORS[0], S("Scale", "Float")]
            else:
                inputs = VECTORS[:1] if op in VECTOR_UNARY else VECTORS[:2]
            outputs = [S("Value", "Float")] if op in VECTOR_TO_FLOAT else [S("Vector", "Vector")]
        return list(inputs), list(outputs)
