"""Scope-bewust hernoemen van identifiers (B299, fase 2)."""
import ast, json, pathlib, sys

def offsets(bron):
    uit, pos = [0], 0
    for r in bron.splitlines(keepends=True):
        pos += len(r); uit.append(pos)
    return uit

def punten_voor(bron, mapping):
    boom = ast.parse(bron)
    off = offsets(bron)
    punten = []
    for node in ast.walk(boom):
        name = col = lineno = None
        if isinstance(node, ast.Name):
            name, lineno, col = node.id, node.lineno, node.col_offset
        elif isinstance(node, ast.arg):
            name, lineno, col = node.arg, node.lineno, node.col_offset
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in mapping:
                # the name follows 'def '/'class ' on the def line
                line = bron[off[node.lineno-1]:off[node.lineno]]
                idx = line.find(node.name)
                if idx >= 0:
                    punten.append((off[node.lineno-1]+idx,
                                   off[node.lineno-1]+idx+len(node.name), node.name))
            continue
        elif isinstance(node, ast.Attribute):
            # the attribute name follows the last dot within this node
            if node.attr in mapping:
                start_search = (off[node.value.end_lineno-1]
                                + node.value.end_col_offset)
                end_search = off[node.end_lineno-1] + node.end_col_offset
                stuk = bron[start_search:end_search]
                idx = stuk.rfind(node.attr)
                if idx >= 0:
                    punten.append((start_search+idx,
                                   start_search+idx+len(node.attr),
                                   node.attr))
            continue
        if name and name in mapping:
            s = off[lineno-1] + col
            punten.append((s, s+len(name), name))
    return sorted(set(punten), reverse=True)

def main():
    wortel = pathlib.Path(sys.argv[1])
    mapping = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
    n_best = n_verv = 0
    for pad in sorted(wortel.rglob("*.py")):
        if "__pycache__" in str(pad): continue
        bron = pad.read_text(encoding="utf-8")
        try: punten = punten_voor(bron, mapping)
        except SyntaxError as e:
            print(f"  !! {pad}: {e}"); continue
        if not punten: continue
        for s, e, oud in punten:
            if bron[s:e] != oud: continue          # veiligheidscheck
            bron = bron[:s] + mapping[oud] + bron[e:]
            n_verv += 1
        pad.write_text(bron, encoding="utf-8"); n_best += 1
    print(f"bestanden: {n_best}, vervangingen: {n_verv}")

main()
