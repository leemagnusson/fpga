"""Minimal KiCad s-expression reader/writer."""
import re
_tok = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+')
class Sym(str):
    """bare token (not a quoted string)"""
def parse(text):
    toks = _tok.findall(text)
    pos = 0
    def rd():
        nonlocal pos
        t = toks[pos]; pos += 1
        if t == '(':
            lst = []
            while toks[pos] != ')':
                lst.append(rd())
            pos += 1
            return lst
        if t.startswith('"'):
            return t[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        return Sym(t)
    return rd()
def dumps(node, indent=0):
    pad = '\t' * indent
    if isinstance(node, list):
        if not node:
            return pad + '()'
        head = node[0]
        simple = all(not isinstance(c, list) for c in node)
        if simple:
            return pad + '(' + ' '.join(dumps(c) for c in node) + ')'
        out = pad + '(' + dumps(head)
        i = 1
        while i < len(node) and not isinstance(node[i], list):
            out += ' ' + dumps(node[i]); i += 1
        out += '\n'
        for c in node[i:]:
            out += dumps(c, indent + 1) + '\n'
        out += pad + ')'
        return out
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return '"' + node.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return str(node)
def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]
def find1(node, key):
    r = find(node, key); return r[0] if r else None
def load_symbol(lib_path, name):
    with open(lib_path) as f:
        root = parse(f.read())
    for s in find(root, 'symbol'):
        if s[1] == name:
            return s, root
    raise KeyError(name)
