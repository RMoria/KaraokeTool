"""Scope-aware renaming of identifiers (B299, phase 2)."""
import ast, json, pathlib, sys

def offsets(source):
    out, pos = [0], 0
    for r in source.splitlines(keepends=True):
        pos += len(r); out.append(pos)
    return out

def points_for(source, mapping):
    tree = ast.parse(source)
    off = offsets(source)
    points = []
    for node in ast.walk(tree):
        name = col = lineno = None
        if isinstance(node, ast.Name):
            name, lineno, col = node.id, node.lineno, node.col_offset
        elif isinstance(node, ast.arg):
            name, lineno, col = node.arg, node.lineno, node.col_offset
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in mapping:
                # the name follows 'def '/'class ' on the def line
                line = source[off[node.lineno-1]:off[node.lineno]]
                idx = line.find(node.name)
                if idx >= 0:
                    points.append((off[node.lineno-1]+idx,
                                   off[node.lineno-1]+idx+len(node.name), node.name))
            continue
        elif isinstance(node, ast.Attribute):
            # the attribute name follows the last dot within this node
            if node.attr in mapping:
                start_search = (off[node.value.end_lineno-1]
                                + node.value.end_col_offset)
                end_search = off[node.end_lineno-1] + node.end_col_offset
                piece = source[start_search:end_search]
                idx = piece.rfind(node.attr)
                if idx >= 0:
                    points.append((start_search+idx,
                                   start_search+idx+len(node.attr),
                                   node.attr))
            continue
        if name and name in mapping:
            s = off[lineno-1] + col
            points.append((s, s+len(name), name))
    return sorted(set(points), reverse=True)

def main(argv=None):
    """B564: through argparse. It read sys.argv[1] and [2] blind, so
    running it without arguments gave an IndexError instead of a word
    about what it wants."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Rename identifiers in a tree, by an AST-safe map.")
    parser.add_argument("root", help="folder to walk")
    parser.add_argument("mapping", help="json file with old -> new")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.root)
    mapping = json.loads(
        pathlib.Path(arguments.mapping).read_text(encoding="utf-8"))
    n_files = n_replaced = 0
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in str(path): continue
        source = path.read_text(encoding="utf-8")
        try: points = points_for(source, mapping)
        except SyntaxError as e:
            print(f"  !! {path}: {e}"); continue
        if not points: continue
        for s, e, old in points:
            if source[s:e] != old: continue          # safety check
            source = source[:s] + mapping[old] + source[e:]
            n_replaced += 1
        path.write_text(source, encoding="utf-8"); n_files += 1
    print(f"files: {n_files}, replacements: {n_replaced}")


if __name__ == "__main__":
    main(sys.argv[1:])
