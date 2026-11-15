#!/usr/bin/env python3
"""Static audit of what each registered tool can cost the QGIS GUI thread. Standard library only (reads source, imports nothing).

    python tools/audit_processing_cost.py            # ranked table on stdout
    python tools/audit_processing_cost.py --markdown # the same as a Markdown table

Why static: tools run on QGIS's GUI thread (agent/tools/_background_processing.py explains), so any tool that loops over features, reads a
raster, waits on the network or calls a Processing algorithm synchronously can freeze QGIS. Measuring needs real data and a real QGIS, which
this cannot do; what it CAN do is find the code shapes that cost time and say whether the tool is already guarded (runs in the background,
checks Stop, caps its input). It is a risk ranking, not a timing: every number is a count of code patterns found in the tool's own body
and in the module-level helpers it calls by name.
"""
import argparse
import ast
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "src" / "cartogen_ai" / "core" / "agent" / "tools"
BACKGROUND = {"run_algorithm", "run_callable", "_run_in_background"}
CANCEL = {"is_cancelled", "should_stop", "check_cancel", "raise_if_cancelled"}
NET = {"urlopen", "urlopen_with_retry", "urlopen_with_retry_", "_qgis_urlopen"}
RASTER = {"ReadAsArray", "bandStatistics", "readAsArray"}
CAPS = {"max_", "MAX_", "limit", "cap", "budget", "LIMIT", "CAP"}


def _name(node):
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _is_tool(fn):
    return any(isinstance(d, ast.Call) and _name(d.func) == "register_tool" for d in fn.decorator_list)


def _loop_depth_over_data(node, depth=0):
    """Deepest nesting of for-loops whose iterable looks like feature/pixel data (getFeatures, list(...) of them, range of a count)."""
    best = depth
    for child in ast.iter_child_nodes(node):
        d = depth
        if isinstance(child, (ast.For, ast.comprehension)):
            it = child.iter
            text = ast.unparse(it) if hasattr(ast, "unparse") else ""
            if "getFeatures" in text or "features" in text.lower() or "range(" in text or "pixels" in text or "rows" in text or "cells" in text:
                d = depth + 1
        best = max(best, _loop_depth_over_data(child, d))
    return best


def _scan(fn, helpers):
    calls = []
    sleeps = pr_calls = get_features = 0
    spatial_index = False
    caps = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            nm = _name(n.func)
            calls.append(nm)
            if nm == "sleep":
                sleeps += 1
            if nm == "run" and isinstance(n.func, ast.Attribute) and _name(n.func.value) == "processing":
                pr_calls += 1
            if nm == "getFeatures":
                get_features += 1
            if nm == "QgsSpatialIndex":
                spatial_index = True
        elif isinstance(n, ast.Name) and any(c in n.id for c in CAPS):
            caps += 1
    called_helpers = [h for h in set(calls) if h in helpers and helpers[h] is not fn]
    # one level of same-module helpers, so a tool that delegates its loop is not scored as empty
    for h in called_helpers:
        for n in ast.walk(helpers[h]):
            if isinstance(n, ast.Call):
                nm = _name(n.func)
                calls.append(nm)
                if nm == "run" and isinstance(n.func, ast.Attribute) and _name(n.func.value) == "processing":
                    pr_calls += 1
                if nm == "getFeatures":
                    get_features += 1
                if nm == "QgsSpatialIndex":
                    spatial_index = True
    depth = max([_loop_depth_over_data(fn)] + [_loop_depth_over_data(helpers[h]) for h in called_helpers])
    cs = set(calls)
    return {
        "loops": depth, "get_features": get_features, "processing_run": pr_calls, "sleep": sleeps,
        "raster_reads": len(cs & RASTER), "network": bool(cs & NET), "spatial_index": spatial_index,
        "background": bool(cs & BACKGROUND), "cancel": bool(cs & CANCEL), "caps": caps > 0,
    }


def score(m):
    """Higher = more likely to freeze QGIS. Guards subtract; nothing here is a measurement."""
    s = 0
    s += 3 * min(m["loops"], 3) + 2 * min(m["get_features"], 3)
    s += 4 * min(m["processing_run"], 2) + 3 * (m["raster_reads"] > 0) + 3 * m["network"] + 2 * min(m["sleep"], 2)
    if m["loops"] >= 2 and not m["spatial_index"]:
        s += 3
    if m["background"]:
        s -= 6
    if m["cancel"]:
        s -= 2
    if m["caps"]:
        s -= 2
    return max(s, 0)


def audit():
    rows = []
    for path in sorted(TOOLS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        helpers = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        for fn in helpers.values():
            if _is_tool(fn):
                m = _scan(fn, helpers)
                m.update(tool=fn.name, module=path.stem, score=score(m), lines=fn.end_lineno - fn.lineno + 1)
                rows.append(m)
    return sorted(rows, key=lambda r: (-r["score"], r["tool"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--top", type=int, default=0, help="only the highest-scoring N tools")
    args = ap.parse_args(argv)
    rows = audit()
    if args.top:
        rows = rows[:args.top]
    cols = ["score", "tool", "module", "loops", "get_features", "processing_run", "raster_reads", "network", "sleep", "spatial_index", "background", "cancel", "caps"]
    if args.markdown:
        print("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        for r in rows:
            print("| " + " | ".join(("yes" if r[c] is True else "" if r[c] is False else str(r[c])) for c in cols) + " |")
    else:
        print("  ".join(f"{c[:9]:>9}" for c in cols))
        for r in rows:
            print("  ".join(f"{str(r[c])[:30] if c in ('tool','module') else str(r[c]):>9}" for c in cols))
    return 0


if __name__ == "__main__":
    sys.exit(main())
