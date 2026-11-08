from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    file: str
    line: int
    col: int
    message: str

    def __str__(self):
        return f"{self.file}:{self.line}:{self.col}  {self.message}"


class BnError(Exception):
    """One or more diagnostics, sorted by position."""

    def __init__(self, diagnostics):
        self.diagnostics = sorted(diagnostics, key=lambda d: (d.line, d.col))
        super().__init__("\n".join(str(d) for d in self.diagnostics))
