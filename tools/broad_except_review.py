#!/usr/bin/env python3
"""Classify every broad exception handler in src/ (DEF-8). Standard library only.

    python tools/broad_except_review.py            counts per class, and the silent handlers with file:line
    python tools/broad_except_review.py --json     the same as JSON

A "broad" handler catches `Exception`, `BaseException` or nothing at all (bare `except:`). Each is put in one class by what its body does:

  reraises   the body raises (a bare `raise`, or a new exception built from it)
  uses_error the body reads the caught exception by name (message, logging, returning it in a result)
  logs       the body calls something that records (log_event, log_error, log_warning, logger.*, print, _err) without reading the exception
  returns    the body returns a value or sets state but neither logs nor reads the exception
  silent     the body is only `pass`, `continue`, `break` or `...` : the failure disappears with no trace

`contextlib.suppress(Exception)` blocks are counted separately: they are silent by construction and are the project's chosen form for best-effort work.
`silent` is what a person should review; tests/test_broad_except_review.py pins its count so it can only shrink."""
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LOG_NAMES = {"log_event", "log_error", "log_warning", "log_info", "_err", "print", "warn", "warning", "error", "exception", "debug", "info"}


def _is_broad(handler):
    if handler.type is None:
        return True
    names = [handler.type] if not isinstance(handler.type, ast.Tuple) else list(handler.type.elts)
    return any(isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names)


def _calls_logger(body):
    for node in (n for stmt in body for n in ast.walk(stmt)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in LOG_NAMES:
                return True
    return False


def classify(handler):
    """The class name of one `ast.ExceptHandler`. Pure."""
    body = handler.body
    if any(isinstance(n, ast.Raise) for stmt in body for n in ast.walk(stmt)):
        return "reraises"
    if handler.name and any(isinstance(n, ast.Name) and n.id == handler.name for stmt in body for n in ast.walk(stmt)):
        return "uses_error"
    if _calls_logger(body):
        return "logs"
    if all(isinstance(stmt, (ast.Pass, ast.Continue, ast.Break)) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)) for stmt in body):
        return "silent"
    return "returns"


def scan(root=SRC):
    """({class: count}, [(class, 'relative/path.py:line')], suppress_count) for every .py file under root."""
    counts, found, suppress = {}, [], 0
    for path in sorted(Path(root).rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix() if ROOT in path.parents else path.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and _is_broad(node):
                kind = classify(node)
                counts[kind] = counts.get(kind, 0) + 1
                found.append((kind, f"{rel}:{node.lineno}"))
            elif isinstance(node, ast.Call):
                func = node.func
                is_suppress = (isinstance(func, ast.Attribute) and func.attr == "suppress") or (isinstance(func, ast.Name) and func.id == "suppress")
                if is_suppress and any(isinstance(a, ast.Name) and a.id in ("Exception", "BaseException") for a in node.args):
                    suppress += 1
    return counts, found, suppress


def main(argv):
    counts, found, suppress = scan()
    if "--json" in argv:
        print(json.dumps({"counts": counts, "total": sum(counts.values()), "suppress_blocks": suppress, "silent": [w for k, w in found if k == "silent"]}, indent=1))
        return 0
    print(f"broad handlers: {sum(counts.values())}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) + f"  | contextlib.suppress(Exception) blocks: {suppress}")
    for kind, where in found:
        if kind == "silent":
            print("  silent:", where)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
