"""Tiny helpers for writing KiCad S-expression files."""
import uuid as _uuid

_ns = _uuid.UUID("6c0f2b4e-7c2a-4d1b-9a3e-5e1f0c9d2a10")

def uid(*parts):
    """Deterministic UUID so regenerated files diff cleanly."""
    return str(_uuid.uuid5(_ns, "/".join(str(p) for p in parts)))

def q(s):
    """Quote a string for S-expressions."""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'

def num(x):
    """Format a number compactly (KiCad writes up to 6 decimals)."""
    if isinstance(x, int):
        return str(x)
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s

class W:
    """Indented S-expression writer."""
    def __init__(self):
        self.lines = []
        self.depth = 0
    def line(self, s):
        self.lines.append("\t" * self.depth + s)
    def open(self, s):
        self.line("(" + s)
        self.depth += 1
    def close(self):
        self.depth -= 1
        self.line(")")
    def text(self):
        return "\n".join(self.lines) + "\n"
