"""Formulas: `a * 2 + sin(t)`, `p.x`, `n ⋅ up`, `h > 0.5 and not edge xor flip`, written as Math,
Vector Math, Compare and Boolean Math nodes.

`choose` decides which node and props a formula means from the types of
its operands. The checker uses it to build, the reader to check that a
node reads back as the same formula.
"""

SCALAR = {"Float", "Int", "Bool"}
VECTOR = {"Vector", "Color"}  # Blender converts a color to a vector for Vector Math

BINOPS = {"+": "ADD", "-": "SUBTRACT", "*": "MULTIPLY", "/": "DIVIDE"}

# Products of two vectors. AZERTY has neither sign: `dot` and `cross` are
# written in their place (the editor swaps them as you type), `·` too
PRODUCTS = {"⋅": "DOT_PRODUCT", "×": "CROSS_PRODUCT"}
WORDS = {"dot": "⋅", "cross": "×", "·": "⋅"}

COMPARE = {"<": "LESS_THAN", "<=": "LESS_EQUAL", ">": "GREATER_THAN", ">=": "GREATER_EQUAL",
           "==": "EQUAL", "!=": "NOT_EQUAL"}

LOGIC = {"and": "AND", "or": "OR", "xor": "XOR", "not": "NOT"}
BOOL_FUNCS = {"xor": "XOR", "xnor": "XNOR", "nand": "NAND", "nor": "NOR", "imply": "IMPLY", "nimply": "NIMPLY"}

# Nodes whose formula fills only their first inputs; the others must keep
# their default (Compare's Epsilon for ==)
OPERANDS = {"Compare": 2}

MATH_FUNCS = {
    "sin": "SINE", "cos": "COSINE", "tan": "TANGENT",
    "asin": "ARCSINE", "acos": "ARCCOSINE", "atan": "ARCTANGENT", "atan2": "ARCTAN2",
    "sinh": "SINH", "cosh": "COSH", "tanh": "TANH",
    "sqrt": "SQRT", "abs": "ABSOLUTE", "exp": "EXPONENT", "log": "LOGARITHM", "pow": "POWER",
    "min": "MINIMUM", "max": "MAXIMUM", "floor": "FLOOR", "ceil": "CEIL", "fract": "FRACT",
    "round": "ROUND", "trunc": "TRUNC", "sign": "SIGN", "mod": "MODULO",
    "radians": "RADIANS", "degrees": "DEGREES",
}

VECTOR_FUNCS = {
    "sin": "SINE", "cos": "COSINE", "tan": "TANGENT",
    "abs": "ABSOLUTE", "min": "MINIMUM", "max": "MAXIMUM", "floor": "FLOOR", "ceil": "CEIL",
    "fract": "FRACTION", "sign": "SIGN", "mod": "MODULO",
    "length": "LENGTH", "normalize": "NORMALIZE", "dot": "DOT_PRODUCT", "cross": "CROSS_PRODUCT",
    "distance": "DISTANCE",
}

FUNCS = set(MATH_FUNCS) | set(VECTOR_FUNCS) | set(BOOL_FUNCS)
COMPONENTS = ("x", "y", "z")


def kind(t):
    return "scalar" if t in SCALAR else "vector" if t in VECTOR else None


def choose(op, types):
    """(node, props, operand order) meant by `op` on operands of `types`.

    `op` is a binary operator, a comparison, "neg", or a function name.
    Raises ValueError with the message to show when the formula has no node.
    """
    if op in COMPARE:
        return "Compare", compare(op, types), (0, 1)
    if op in PRODUCTS:
        for t in types:
            if kind(t) != "vector":
                raise ValueError(f"« {op} » attend deux Vector, pas {t}")
        return "VectorMath", {"operation": PRODUCTS[op]}, (0, 1)
    if op in LOGIC or op in BOOL_FUNCS:
        for t in types:
            if kind(t) != "scalar":
                raise ValueError(f"« {op} » attend des Bool, pas {t}")
        return "BooleanMath", {"operation": LOGIC.get(op) or BOOL_FUNCS[op]}, tuple(range(len(types)))
    node, operation, order = math(op, types)
    return node, {"operation": operation}, order


def compare(op, types):
    """Compare's props for a comparison: its data type follows the operands."""
    equality = op in ("==", "!=")
    if "String" in types:
        if set(types) != {"String"} or not equality:
            raise ValueError(f"« {op} » : une String ne se compare qu'à une String, par == ou !=")
        data = "STRING"
    elif set(types) == {"Color"}:
        if not equality:
            raise ValueError(f"« {op} » : deux couleurs se comparent par == ou !=")
        data = "RGBA"
    else:
        kinds = [kind(t) for t in types]
        for t, k in zip(types, kinds):
            if k is None:
                raise ValueError(f"« {op} » ne s'applique pas à {t}")
        data = "VECTOR" if "vector" in kinds else "INT" if set(types) == {"Int"} else "FLOAT"
    return {"data_type": data, "operation": COMPARE[op]}


def math(op, types):
    kinds = [kind(t) for t in types]
    for t, k in zip(types, kinds):
        if k is None:
            raise ValueError(f"« {op} » ne s'applique pas à {t}")
    order = tuple(range(len(types)))
    vector = "vector" in kinds
    if op == "neg":
        return ("VectorMath", "SCALE", order) if vector else ("Math", "MULTIPLY", order)
    if op in BINOPS:
        if not vector:
            return "Math", BINOPS[op], order
        if op == "*" and kinds[0] != kinds[1]:
            # A vector times a number scales it; Vector Math takes the vector first
            return "VectorMath", "SCALE", order if kinds[0] == "vector" else (1, 0)
        return "VectorMath", BINOPS[op], order
    if vector:
        if op not in VECTOR_FUNCS:
            raise ValueError(f"{op} n'existe pas pour Vector")
        return "VectorMath", VECTOR_FUNCS[op], order
    if op not in MATH_FUNCS:
        raise ValueError(f"{op} attend des vecteurs")
    return "Math", MATH_FUNCS[op], order


def spellings(node, operation):
    """Every way of writing (node, operation) as a formula: operators first."""
    if node == "Compare":
        return [s for s, o in COMPARE.items() if o == operation]
    if node == "BooleanMath":
        return [s for s, o in {**LOGIC, **BOOL_FUNCS}.items() if o == operation]
    ops = [s for s, o in BINOPS.items() if o == operation]
    if node == "VectorMath":
        ops += [s for s, o in PRODUCTS.items() if o == operation]
    if node == "VectorMath" and operation == "SCALE":
        ops = ["*"]
    funcs = MATH_FUNCS if node == "Math" else VECTOR_FUNCS
    return ops + sorted(f for f, o in funcs.items() if o == operation)
