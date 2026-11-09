"""Recursive descent parser.

Precedence, loosest first: `|>`, then `+ -`, then `* /`, then unary `-`,
then `.socket`. Statements need no separator: an expression ends where
the next token cannot continue it.
"""

from . import ast
from .errors import BnError, Diagnostic
from .lexer import tokenize


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
        while not self.at("EOF"):
            f.graphs.append(self.graph())
        if not f.graphs:
            self.fail("fichier vide : aucun graph")
        return f

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
        body = []
        while not self.accept("}"):
            if self.at("EOF"):
                self.fail("« } » attendu avant la fin du fichier")
            body.append(self.statement())
        return ast.Graph(kind.text, name.text, params, outputs, single, body, kind.line, kind.col)

    def typed_list(self, close):
        """`name: Type, ...` up to `close`, which is consumed."""
        items = []
        while not self.accept(close):
            name = self.accept("STRING") or self.expect("IDENT", what="nom")
            self.expect(":")
            t = self.expect("IDENT", what="type")
            items.append(ast.Param(name.text, t.text, name.line, name.col))
            if not self.accept(","):
                self.expect(close)
                break
        return items

    def statement(self):
        t = self.tok
        if self.accept("KEYWORD", "return"):
            if self.at("(") and (self.peek().kind == ")" or
                                 self.peek().kind in ("IDENT", "STRING") and self.peek(2).kind == ":"):
                self.advance()
                fields = self.args(named_only=True)
                return ast.Return(ast.Record(fields, t.line, t.col), t.line, t.col)
            return ast.Return(self.expr(), t.line, t.col)
        if self.at("IDENT") and self.peek().kind == "=":
            self.advance()
            self.advance()
            return ast.Assign(t.text, self.expr(), t.line, t.col)
        self.fail(f"instruction attendue (nom = …, ou return), trouvé {describe(t)}")

    def expr(self):
        left = self.additive()
        while self.at("|>"):
            op = self.advance()
            rhs = self.postfix()
            call = rhs.target if isinstance(rhs, ast.Member) else rhs
            if not isinstance(call, ast.Call):
                self.fail("un appel de nœud est attendu après |>", op)
            left = ast.Pipe(left, rhs, op.line, op.col)
        return left

    def additive(self):
        left = self.multiplicative()
        while self.at("+") or self.at("-"):
            op = self.advance()
            left = ast.BinOp(op.text, left, self.multiplicative(), op.line, op.col)
        return left

    def multiplicative(self):
        left = self.unary()
        while self.at("*") or self.at("/"):
            op = self.advance()
            left = ast.BinOp(op.text, left, self.unary(), op.line, op.col)
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
                args.append(ast.Arg(t.text, self.expr(), t.line, t.col))
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


def describe(tok):
    if tok.kind == "EOF":
        return "la fin du fichier"
    return f"« {tok.text} »"
