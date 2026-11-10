from dataclasses import dataclass

from .errors import BnError, Diagnostic

KEYWORDS = {"graph", "return", "true", "false", "and", "or", "xor", "not", "repeat"}

# Longest first, so "->" wins over "-", "==" over "=" and ".." over "."
PUNCT = ("|>", "->", "<=", ">=", "==", "!=", "<", ">", "(", ")", "{", "}", ",", ":", "..", ".", "=", "+", "-", "*", "/",
         "⋅", "·", "×", "@")


@dataclass(frozen=True)
class Token:
    kind: str  # IDENT, NUMBER, STRING, KEYWORD, COLOR, COMMENT, a PUNCT string, or EOF
    text: str
    line: int
    col: int


def tokenize(source, filename="<text>", strict=True):
    """Tokens of the source. Not strict, for the editor: half-typed text never
    fails, comments are kept as tokens and an unclosed string runs to the line's end."""
    tokens = []
    i, line, col = 0, 1, 1
    n = len(source)

    def fail(message):
        raise BnError([Diagnostic(filename, line, col, message)])

    while i < n:
        c = source[i]
        if c == "\n":
            i, line, col = i + 1, line + 1, 1
            continue
        if c in " \t\r":
            i, col = i + 1, col + 1
            continue
        if source.startswith("//", i):
            start = i
            while i < n and source[i] != "\n":
                i += 1
            if not strict:
                tokens.append(Token("COMMENT", source[start:i], line, col))
                col += i - start
            continue

        start = i
        if c.isalpha() or c == "_":
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text = source[start:i]
            kind = "KEYWORD" if text in KEYWORDS else "IDENT"
        elif c.isdigit():
            while i < n and source[i].isdigit():
                i += 1
            if i + 1 < n and source[i] == "." and source[i + 1].isdigit():
                i += 1
                while i < n and source[i].isdigit():
                    i += 1
            if i < n and source[i] in "eE":
                j = i + 1
                if j < n and source[j] in "+-":
                    j += 1
                if j < n and source[j].isdigit():
                    i = j
                    while i < n and source[i].isdigit():
                        i += 1
            text, kind = source[start:i], "NUMBER"
        elif c == "#":
            # A frame color, its text with the `#`: checked later, so `#nope` gets a clear error
            i += 1
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1
            text, kind = source[start:i], "COLOR"
        elif c == '"':
            i += 1
            while i < n and source[i] not in '"\n':
                i += 1
            if i < n and source[i] == '"':
                i += 1
                text, kind = source[start + 1:i - 1], "STRING"
            elif strict:
                fail("chaîne non fermée")
            else:
                text, kind = source[start + 1:i], "OPEN_STRING"
        else:
            for p in PUNCT:
                if source.startswith(p, i):
                    i += len(p)
                    text = kind = p
                    break
            else:
                if strict:
                    fail(f"caractère inattendu « {c} »")
                i, col = i + 1, col + 1
                continue

        tokens.append(Token(kind, text, line, col))
        col += i - start

    tokens.append(Token("EOF", "", line, col))
    return tokens
