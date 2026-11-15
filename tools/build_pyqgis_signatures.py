"""Build tests/fixtures/pyqgis_4_2_signatures.json: the argument counts of the QGIS 4.2 Python API for exactly the classes and members this plugin calls (PLAN-023 R11-6).

    python tools/build_pyqgis_signatures.py            # fetches https://qgis.org/pyqgis/4.2/ (needs network), rewrites the fixture

What is stored: for EVERY class of qgis.core / qgis.gui / qgis.analysis in the reference, each member name that src/ calls on SOMETHING (so a call on an object of unknown type can be judged against all
of them), and the constructor of each class imported anywhere under src/; for each, the list of
overloads as [fewest positional arguments, most positional arguments or -1 when the overload takes *args, [parameter names], 1 when the member is static]; `self` and `cls` are not counted. Nothing else of the reference is
kept (no descriptions, no types), so the file stays small and holds names and numbers only. tests/test_pyqgis_call_arity.py reads it and fails on a call whose argument count fits no overload.
The reference is the developer reference qgis.org/pyqgis/4.2 (QGIS 4.2.x; the pages carry no patch number, so the fixture records the date it was read). Re-run it after adding a call to a QGIS
class the fixture does not know, or when the CI QGIS image moves to a new minor version."""
import ast
import concurrent.futures
import datetime
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://qgis.org/pyqgis/4.2"
MODULES = ("core", "gui", "analysis")
OUT = ROOT / "tests" / "fixtures" / "pyqgis_4_2_signatures.json"


def source_usage():
    """(classes imported per module, member names called anywhere in src/) from the plugin's own code. Pure apart from reading files."""
    classes, members = {}, set()
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in ("qgis.core", "qgis.gui", "qgis.analysis"):
                classes.setdefault(node.module.split(".")[1], set()).update(a.name for a in node.names if a.name[:1] == "Q")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                members.add(node.func.attr)
    return classes, members


_DT = re.compile(r'<dt class="sig sig-object py" id="qgis\.(?:core|gui|analysis)\.(\w+)\.(\w+)">')
_TAGS = re.compile(r"<[^>]+>")


def _split_params(text):
    """The top-level comma-separated pieces of a parameter list, so a default such as Qgis.X(1, 2) or a type such as tuple[int, int] stays whole. Pure."""
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def _overload(params_text, static=False):
    """[fewest positional, most (-1 = *args), names, 1 when static else 0] of one parameter list as printed in the reference. Pure."""
    names, required, variadic = [], 0, False
    for piece in _split_params(params_text):
        name = re.split(r"[:=\s]", piece, maxsplit=1)[0]
        if name in ("self", "cls", ""):
            continue
        if name.startswith("*"):
            variadic = True
            continue
        names.append(name)
        if "=" not in re.sub(r"\[.*?\]|\(.*?\)", "", piece):
            required += 1
    return [required, -1 if variadic else len(names), names, 1 if static else 0]


def _bracketed(line, start):
    """The text between the bracket that opens just before `start` and its matching close bracket, or None when the line ends first. Pure."""
    depth = 1
    for i in range(start, len(line)):
        if line[i] in "([{":
            depth += 1
        elif line[i] in ")]}":
            depth -= 1
            if depth == 0:
                return line[start:i]
    return None


def parse_signatures(page, wanted):
    """{member: [[min, max, [names]], ...]} for the `wanted` member names plus __init__ on one class page. The first overload of a member is its heading and the others are lines in its
    description that start with the member name and a bracket, so every line of the member's section is read. Pure."""
    marks = [(m.start(), m.group(1), m.group(2)) for m in _DT.finditer(page)]
    out = {}
    for i, (start, _cls, member) in enumerate(marks):
        if member not in wanted and member != "__init__":
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else len(page)
        text = _TAGS.sub("", page[start:end])
        head = re.compile(r"^(?:\w+ )*" + re.escape(member) + r"\(")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            m = head.match(line)
            if not m:
                continue
            params = _bracketed(line, m.end())
            if params is None:
                continue
            tail = line[m.end() + len(params) + 1:].strip()
            if tail and not tail.startswith(("→", "->", "[source]", "¶")):
                continue                                 # a sentence of the description that happens to start with the name
            found = _overload(params, static="static" in line[:m.end()].split("(")[0].split())
            if found not in out.setdefault(member, []):
                out[member].append(found)
    return out


def all_classes():
    """{module: sorted class names} from each module's index page of the reference (names like QgsGeometry); every class is read so that a member name can be matched against ALL of them. Needs network."""
    found = {}
    for module in MODULES:
        with urllib.request.urlopen(f"{BASE}/{module}/index.html", timeout=60) as resp:  # noqa: S310 (BASE is a fixed https URL)
            page = resp.read().decode("utf-8")
        found[module] = sorted(set(re.findall(r'href="(Q\w+)\.html"', page)))
    return found


def fetch(module, cls):
    try:
        with urllib.request.urlopen(f"{BASE}/{module}/{cls}.html", timeout=60) as resp:  # noqa: S310 (BASE is a fixed https URL)
            return module, cls, html.unescape(resp.read().decode("utf-8"))
    except Exception:
        return module, cls, None


def main():
    imported, members = source_usage()
    everything = all_classes()
    jobs = [(m, c) for m, names in everything.items() for c in names]
    snapshot, missing = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for module, cls, page in pool.map(lambda j: fetch(*j), jobs):
            if page is None:
                missing.append(f"{module}.{cls}")      # not a class page (an enum, a function, a name that moved): the test treats an unknown class as unchecked
                continue
            sigs = parse_signatures(page, members)
            if cls not in imported.get(module, ()):
                sigs.pop("__init__", None)           # constructors are kept only for classes this plugin imports; a member is kept for every class
            if sigs:
                snapshot.setdefault(cls, {}).update(sigs)
    doc = {"_about": f"Argument counts of the QGIS 4.2 Python API for the classes and members src/ uses, read from {BASE}/ on {datetime.date.today().isoformat()} by tools/build_pyqgis_signatures.py. "
                     "Each overload is [fewest positional arguments, most (-1 = takes *args), parameter names, 1 if static]; self is not counted.",
           "classes": snapshot}
    OUT.write_text(json.dumps(doc, indent=0, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(snapshot)} classes, {OUT.stat().st_size} bytes); {len(missing)} names had no class page")
    if missing:
        print("no class page:", ", ".join(sorted(missing))[:400])


if __name__ == "__main__":
    sys.exit(main())
