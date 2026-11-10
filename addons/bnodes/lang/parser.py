"""Recursive descent parser.

Precedence, loosest first: `|>`, `or xor`, `and`, `not`, comparisons, `+ -`,
`* / ⋅ ×`, unary `-`, then `.socket`. Statements need no separator: an
expression ends where the next token cannot continue it.
"""

from . import ast
from .errors import BnError, Diagnostic
from .lexer import tokenize
from .sugar import COMPARE, WORDS


def parse(source, filename="<text>"):
    return Parser(tokenize(source, filename), filename).file()


class Parser:
    def __init__(self, tokens, filename):
        self.tokens = tokens
        self.filename = filename
        self.i = 0

    # Token helpers

    @property
    def tok(self):
        return self.tokens[self.i]

    def peek(self, offset=1):
        return self.tokens[min(self.i + offset, len(self.tokens) - 1)]

    def at(self, kind, text=None):
        t = self.tok
        return t.kind == kind and (text is None or t.text == text)

    def advance(self):
        t = self.tok
        self.i += 1
        return t

    def accept(self, kind, text=None):
        if self.at(kind, text):
            return self.advance()
        return None

    def expect(self, kind, text=None, what=None):
        if self.at(kind, text):
            return self.advance()
        self.fail(f"{what or text or kind} attendu, trouvé {describe(self.tok)}")

    def fail(self, message, tok=None):
        tok = tok or self.tok
        raise BnError([Diagnostic(self.filename, tok.line, tok.col, message)])

    # Grammar

    def file(self):
        f = ast.File()
        while self.at_use():
            f.uses.append(self.use())
        while not self.at("EOF"):
            if self.at_use():
                self.fail("les use vont en tête du fichier, avant le premier graph")
            f.graphs.append(self.graph())
        if not f.graphs:
            self.fail("fichier vide : aucun graph")
        return f

    def at_use(self):
        # `use` is a keyword only here, so that a socket or a name may still be called use
        return self.at("IDENT", "use") and self.peek().kind == "IDENT"

    def use(self):
        t = self.advance()
        name = self.advance()
        names = None
        if self.accept("("):
            names = []
            while not self.accept(")"):
                names.append(self.expect("IDENT", what="nom de graph").text)
                if not self.accept(","):
                    self.expect(")")
                    break
            if not names:
                self.fail("liste vide : écrire use " + name.text + " pour tout le module", t)
        source = None
        if self.accept("IDENT", "from"):
            source = self.expect("STRING", what="source entre guillemets").text
        return ast.Use(name.text, names, source, t.line, t.col)

    def graph(self):
        kind = self.expect("IDENT", what="type d'arbre (geometry, shader, compositor)")
        self.expect("KEYWORD", "graph")
        name = self.accept("STRING") or self.expect("IDENT", what="nom du graph")
        self.expect("(")
        params = self.typed_list(")")
        self.expect("->")
        if self.accept("("):
            outputs, single = self.typed_list(")"), False
        else:
            t = self.expect("IDENT", what="type de retour")
            outputs, single = [ast.Param(t.text, t.text, t.line, t.col)], True
        self.expect("{")
        description = None
        if self.at_description():
            description = self.advance()
        body = []
        while not self.at("}"):
            if self.at("EOF"):
                self.fail("« } » attendu avant la fin du fichier")
            if self.at_description():
                self.fail("la description d'un graph va en première ligne de son corps")
            body.append(self.statement())
        end = self.advance()
        g = ast.Graph(kind.text, name.text, params, outputs, single, body, kind.line, kind.col, end.line)
        if description is not None:
            g.description, g.description_line = description.text, description.line
        return g

    def at_description(self):
        # A string alone: `"Titre" {` and `"Titre" #couleur {` are frames
        return self.at("STRING") and self.peek().kind not in ("{", "COLOR")

    def typed_list(self, close):
        """`name: Type = default in lo..hi, ...` up to `close`, which is consumed."""
        items = []
        while not self.accept(close):
            name = self.accept("STRING") or self.expect("IDENT", what="nom")
            self.expect(":")
            t = self.expect("IDENT", what="type")
            p = ast.Param(name.text, t.text, name.line, name.col)
            if self.accept("("):
                p.options = self.args(named_only=True)
            if self.accept("="):
                p.default = self.unary()
            if self.at("IDENT", "in") and self.peek().kind != ":":
                # Either side may be left open: `in 0.0..`, `in ..1.0`
                self.advance()
                lo = None if self.at("..") else self.unary()
                self.expect("..", what="« .. » entre le min et le max")
                hi = self.unary() if self.tok.kind in ("NUMBER", "-") else None
                if lo is None and hi is None:
                    self.fail("bornes vides : écrire au moins le min ou le max")
                p.range = (lo, hi)
            items.append(p)
            if not self.accept(","):
                self.expect(close)
                break
        return items

    def statement(self):
        t = self.tok
        if self.at("{") or self.at("COLOR") or self.at("STRING") and self.peek().kind in ("{", "COLOR"):
            return self.frame()
        if self.accept("KEYWORD", "return"):
            if self.at("(") and (self.peek().kind == ")" or
                                 self.peek().kind in ("IDENT", "STRING") and self.peek(2).kind == ":"):
                self.advance()
                fields = self.args(named_only=True)
                return ast.Return(ast.Record(fields, t.line, t.col), t.line, t.col)
            return ast.Return(self.expr(), t.line, t.col)
        if self.at("IDENT") and self.peek().kind == "=":
            if t.text in WORDS:
                self.fail(f"« {t.text} » est réservé au produit {'scalaire' if t.text == 'dot' else 'vectoriel'} : "
                          "choisir un autre nom")
            self.advance()
            self.advance()
            if self.at("KEYWORD", "repeat"):
                value = self.repeat()
            elif self.at_closure():
                value = self.closure()
            else:
                value = self.expr()
            return ast.Assign(t.text, value, t.line, t.col)
        self.fail(f"instruction attendue (nom = …, return, ou un frame \"titre\" {{ … }}), trouvé {describe(t)}")

    def frame(self):
        t = self.tok
        label = self.accept("STRING")
        color = self.accept("COLOR")
        self.expect("{")
        body = []
        while not self.at("}"):
            if self.at("EOF"):
                self.fail("« } » attendu avant la fin du fichier")
            body.append(self.statement())
        end = self.advance()
        return ast.Frame(label and label.text, color and color.text, body, t.line, t.col, end.line)

    def repeat(self):
        t = self.advance()
        self.expect("(", what="« ( » après repeat")
        args = self.args()
        if not args or args[0].name is not None:
            self.fail("repeat attend d'abord le nombre de tours : repeat(10, état: départ, …)", t)
        if len(args) < 2:
            self.fail("repeat attend au moins un état : repeat(10, état: départ)", t)
        self.expect("{", what="« { » après repeat(…)")
        body = []
        while not self.at("}"):
            if self.at("EOF"):
                self.fail("« } » attendu avant la fin du fichier")
            body.append(self.statement())
        end = self.advance()
        return ast.Repeat(args[0].value, args[1:], body, t.line, t.col, end.line)

    def at_closure(self):
        # `closure` is a keyword only as `closure(…) -> … {`, so that a name, a socket
        # or a graph may still be called closure
        if not (self.at("IDENT", "closure") and self.peek().kind == "("):
            return False
        i = self.matching(self.i + 1)
        if i is None or self.tokens[i + 1].kind != "->":
            return False
        i += 2
        if self.tokens[i].kind == "(":
            i = self.matching(i)
            if i is None:
                return False
        return self.tokens[i + 1].kind == "{"

    def matching(self, i):
        """Index of the `)` closing the `(` at token i, or None."""
        depth = 0
        for j in range(i, len(self.tokens)):
            kind = self.tokens[j].kind
            if kind == "(":
                depth += 1
            elif kind == ")":
                depth -= 1
                if depth == 0:
                    return j
            elif kind == "EOF":
                return None
        return None

    def closure(self):
        t = self.advance()
        self.expect("(")
        params = self.typed_list(")")
        self.expect("->")
        outputs, single = self.outputs()
        self.expect("{", what="« { » après closure(…) -> …")
        body = []
        while not self.at("}"):
            if self.at("EOF"):
                self.fail("« } » attendu avant la fin du fichier")
            body.append(self.statement())
        end = self.advance()
        return ast.Closure(params, outputs, single, body, t.line, t.col, end.line)

    def outputs(self):
        """After `->`: `(name: Type, …)`, or one Type named as itself."""
        if self.accept("("):
            return self.typed_list(")"), False
        t = self.expect("IDENT", what="type de retour")
        return [ast.Param(t.text, t.text, t.line, t.col)], True

    def expr(self):
        left = self.disjunction()
        while self.at("|>"):
            op = self.advance()
            rhs = self.postfix()
            call = rhs.target if isinstance(rhs, ast.Member) else rhs
            if not isinstance(call, ast.Call):
                self.fail("un appel de nœud est attendu après |>", op)
            left = ast.Pipe(left, rhs, op.line, op.col)
        return left

    def disjunction(self):
        left = self.conjunction()
        while self.at("KEYWORD", "or") or self.at("KEYWORD", "xor"):
            op = self.advance()
            left = ast.BinOp(op.text, left, self.conjunction(), op.line, op.col)
        return left

    def conjunction(self):
        left = self.negation()
        while self.at("KEYWORD", "and"):
            op = self.advance()
            left = ast.BinOp("and", left, self.negation(), op.line, op.col)
        return left

    def negation(self):
        if self.at("KEYWORD", "not"):
            op = self.advance()
            return ast.Not(self.negation(), op.line, op.col)
        return self.comparison()

    def comparison(self):
        left = self.additive()
        if self.tok.kind in COMPARE:
            op = self.advance()
            left = ast.BinOp(op.text, left, self.additive(), op.line, op.col)
            if self.tok.kind in COMPARE:
                self.fail("une seule comparaison à la fois ; pour deux, passer par un nom")
        return left

    def additive(self):
        left = self.multiplicative()
        while self.at("+") or self.at("-"):
            op = self.advance()
            left = ast.BinOp(op.text, left, self.multiplicative(), op.line, op.col)
        return left

    def multiplicative(self):
        left = self.unary()
        # After an operand, `dot` and `cross` can only be products: they are reserved names
        while self.tok.kind in ("*", "/", "⋅", "·", "×") or \
                self.at("IDENT") and self.tok.text in WORDS and self.peek().kind != "=":
            op = self.advance()
            left = ast.BinOp(WORDS.get(op.text, op.text), left, self.unary(), op.line, op.col)
        return left

    def unary(self):
        if self.at("-"):
            op = self.advance()
            value = self.unary()
            if isinstance(value, ast.Number):
                return ast.Number(-value.value, value.is_int, op.line, op.col)
            return ast.Neg(value, op.line, op.col)
        return self.postfix()

    def postfix(self):
        node = self.primary()
        if isinstance(node, ast.Call) and self.at("->"):
            # The outputs a node declares end it: `(… -> (a: Float)).a` takes parentheses
            self.advance()
            node.outputs, node.single_output = self.outputs()
            return node
        while self.at("."):
            dot = self.advance()
            if self.at("IDENT") or self.at("STRING"):
                node = ast.Member(node, self.advance().text, dot.line, dot.col)
            else:
                self.fail("nom de sortie attendu après « . »")
        return node

    def primary(self):
        t = self.tok
        if self.accept("NUMBER"):
            is_int = not any(c in t.text for c in ".eE")
            return ast.Number(int(t.text) if is_int else float(t.text), is_int, t.line, t.col)
        if self.accept("STRING"):
            return ast.String(t.text, t.line, t.col)
        if self.accept("KEYWORD", "true") or self.accept("KEYWORD", "false"):
            return ast.Bool(t.text == "true", t.line, t.col)
        if self.at("KEYWORD", "repeat"):
            self.fail("repeat s'écrit seul, en valeur d'un nom : r = repeat(10, état: départ) { … }")
        if self.at("KEYWORD", "xor") and self.peek().kind == "(":
            # The function form, kept from before `xor` was an operator
            self.advance()
            self.advance()
            return ast.Call("xor", self.args(), t.line, t.col)
        if self.accept("IDENT"):
            if self.accept("("):
                return ast.Call(t.text, self.args(), t.line, t.col)
            return ast.Ref(t.text, t.line, t.col)
        if self.accept("("):
            items = [self.expr()]
            while self.accept(","):
                if self.at(")"):
                    break
                items.append(self.expr())
            self.expect(")")
            return items[0] if len(items) == 1 else ast.Tuple(items, t.line, t.col)
        self.fail(f"expression attendue, trouvé {describe(t)}")

    def args(self, named_only=False):
        """Arguments up to `)`, which is consumed."""
        args = []
        while not self.accept(")"):
            t = self.tok
            if t.kind in ("IDENT", "STRING") and self.peek().kind == ":":
                self.advance()
                self.advance()
                value = self.expr()
                arg = ast.Arg(t.text, value, t.line, t.col)
                if self.at("="):
                    # `name: Type(options) = value`: an item given its type
                    eq = self.advance()
                    arg.type = self.item_type(t.text, value, eq)
                    arg.value = self.expr()
                args.append(arg)
            elif named_only:
                self.fail("champ nommé attendu (nom: valeur)")
            else:
                if any(a.name for a in args):
                    self.fail("argument positionnel après un argument nommé")
                args.append(ast.Arg(None, self.expr(), t.line, t.col))
            if not self.accept(","):
                self.expect(")")
                break
        return args


    def item_type(self, name, e, at):
        """The type written before `=`: `Float`, or `Float(structure_type: SINGLE)`."""
        if isinstance(e, ast.Ref):
            return ast.Param(name, e.name, e.line, e.col)
        if isinstance(e, ast.Call) and e.outputs is None and all(a.name and a.type is None for a in e.args):
            return ast.Param(name, e.name, e.line, e.col, options=e.args)
        self.fail("un type est attendu avant « = » : nom: Type = valeur", at)


def describe(tok):
    if tok.kind == "EOF":
        return "la fin du fichier"
    return f"« {tok.text} »"
