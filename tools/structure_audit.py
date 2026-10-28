"""Measures the shape of src/cartogen_ai so a reorganisation is argued from numbers (PLAN-040). Stdlib only; read-only.

Run: python tools/structure_audit.py [--json]
Reports: size by package, largest files, import edges (module level vs inside functions), import cycles at import time, layer-to-layer
import counts, modules nothing imports, helper functions defined in several modules, and how many tests and ledger entries name tool
module paths (the cost of moving a file). Nothing here changes behaviour; the numbers are only as good as `ast` can see: dynamic imports
and importlib are invisible to it."""
import ast
import collections
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")


def _read(path):
    with open(path, encoding="utf-8", errors="ignore") as handle:
        return handle.read()


def _modules():
    mods = {}
    for dirpath, _dirs, files in os.walk(SRC):
        if "__pycache__" in dirpath:
            continue
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                mod = os.path.relpath(path, SRC)[:-3].replace(os.sep, ".")
                mods[mod[:-9] if mod.endswith(".__init__") else mod] = path
    return mods


def _resolve(mods, packages, current, node):
    found = set()
    package = current if current in packages else current.rsplit(".", 1)[0]
    if isinstance(node, ast.ImportFrom):
        if node.level:
            parts = package.split(".")
            base = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
            basemod = ".".join(base + ([node.module] if node.module else []))
        else:
            basemod = node.module or ""
        if basemod in mods:
            found.add(basemod)
        for alias in node.names:
            if f"{basemod}.{alias.name}" in mods:
                found.add(f"{basemod}.{alias.name}")
    else:
        for alias in node.names:
            if alias.name in mods:
                found.add(alias.name)
    return found


def _collect(mods, packages, mod, node, in_function, top, lazy):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for target in _resolve(mods, packages, mod, child):
                if target != mod:
                    (lazy if in_function else top)[mod].add(target)
        else:
            nested = in_function or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            _collect(mods, packages, mod, child, nested, top, lazy)


def _edges(mods):
    packages = {m for m, p in mods.items() if p.endswith("__init__.py")}
    top, lazy = collections.defaultdict(set), collections.defaultdict(set)
    for mod, path in mods.items():
        _collect(mods, packages, mod, ast.parse(_read(path)), False, top, lazy)
    return top, lazy


def _cycles(mods, edges):
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]
    sys.setrecursionlimit(10000)

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in edges.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                found.append(sorted(comp))

    for v in mods:
        if v not in index:
            visit(v)
    return found


def _layer(mod):
    if ".ui" in mod:
        return "ui"
    if ".agent.tools" in mod:
        return "tools"
    if ".agent" in mod:
        return "agent"
    if any(s in mod for s in (".services", ".models", ".validators", ".representation")):
        return "core-support"
    if "infrastructure" in mod:
        return "infrastructure"
    if "processing" in mod:
        return "processing"
    return "other"


def main():
    mods = _modules()
    top, lazy = _edges(mods)
    allk = collections.defaultdict(set)
    for d in (top, lazy):
        for k, v in d.items():
            allk[k] |= v
    lines = {m: len(_read(p).splitlines()) for m, p in mods.items()}
    pkg_lines = collections.Counter()
    for m, n in lines.items():
        pkg_lines[m.rsplit(".", 1)[0]] += n
    cross = collections.Counter((_layer(a), _layer(b)) for a, bs in allk.items() for b in bs)
    imported = {t for bs in allk.values() for t in bs}
    packages = {m for m, p in mods.items() if p.endswith("__init__.py")}
    unimported = sorted(m for m in mods if m not in imported and m not in packages)
    helpers = collections.defaultdict(list)
    for m, p in mods.items():
        for node in ast.parse(_read(p)).body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("_") and not node.name.startswith("__"):
                helpers[node.name].append(m)
    tests = [os.path.join(ROOT, "tests", f) for f in os.listdir(os.path.join(ROOT, "tests")) if f.endswith(".py")]
    pattern = re.compile(r"core\.agent\.tools\.[a-z_0-9]+")
    texts = [_read(t) for t in tests]
    test_files = sum(1 for text in texts if pattern.search(text))
    test_refs = sum(len(pattern.findall(text)) for text in texts)
    ledger = _read(os.path.join(ROOT, "docs", "FEATURE_LEDGER.json")).count("src/cartogen_ai/core/agent/tools/")
    report = {
        "files": len(mods), "lines": sum(lines.values()),
        "lines_by_package": dict(sorted(pkg_lines.items(), key=lambda x: -x[1])),
        "largest_files": sorted(((n, m) for m, n in lines.items()), reverse=True)[:12],
        "import_edges": {"module_level": sum(map(len, top.values())), "inside_functions": sum(map(len, lazy.values()))},
        "module_level_cycles": [len(c) for c in _cycles(mods, top)],
        "cycles_counting_deferred_imports": [len(c) for c in _cycles(mods, allk)],
        "layer_imports": {f"{a}->{b}": n for (a, b), n in sorted(cross.items(), key=lambda x: -x[1])},
        "modules_nothing_imports": unimported,
        "private_helpers_defined_in_2plus_modules": sum(1 for v in helpers.values() if len(v) >= 2),
        "most_duplicated_helpers": sorted(((len(v), k) for k, v in helpers.items() if len(v) >= 3), reverse=True)[:6],
        "cost_of_moving_a_tool_file": {"test_files_naming_tool_module_paths": test_files, "path_references_in_tests": test_refs,
                                       "ledger_source_paths_under_tools": ledger},
    }
    if "--json" in sys.argv:
        print(json.dumps(report, indent=1))
        return
    for key, value in report.items():
        print(f"\n## {key}")
        if isinstance(value, dict):
            for k, v in value.items():
                print(f"  {k}: {v}")
        elif isinstance(value, list) and value and isinstance(value[0], (tuple, list)):
            for item in value:
                print("  ", *item)
        else:
            print(" ", value)


if __name__ == "__main__":
    main()
