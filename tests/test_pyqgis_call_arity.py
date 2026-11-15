"""Argument-count ratchet (PLAN-023 R11-6): a call into the QGIS Python API whose number of arguments fits no overload of the 4.2 reference fails the build, listed with file and line.

Why: tests/test_pyqgis_call_names.py catches a method name that does not exist; this catches the next commonest slip, a name that exists called with the wrong number of arguments (an
overload added or dropped between QGIS versions, a typo of one argument). CI has no map canvas and most tools have no live test, so such a call can sit unexecuted for months.

What it checks, from tests/fixtures/pyqgis_4_2_signatures.json (argument counts only, built by tools/build_pyqgis_signatures.py from the QGIS 4.2 developer reference):
  * `QgsX(...)` for a class the file imports from qgis.core / qgis.gui / qgis.analysis: the constructor overloads;
  * `QgsX.member(...)`: the member's overloads;
  * `obj.member(...)` on an object of unknown type: only for camelCase names that are a member of some QGIS class in the fixture and not also a known Qt method; the call fails only if it fits NO
    overload of ANY class that has that member (so it cannot prove a call is right, only that it is wrong everywhere).
Calls with *args or **kwargs are skipped. It does not check argument types or return types (the reference's types are not stored). A call that is right but fails here goes into
REVIEWED_OK with the reason, as for the name ratchet. Offline: reads src/ and the fixture only."""
import ast
import json
import os
import unittest

from tests.test_pyqgis_call_names import QT_AND_OTHER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (path relative to the repo, line, member) -> why the call is right although it fits no overload of the reference. Empty until a failure has been reviewed.
REVIEWED_OK = {}


# Member names that a QGIS class has AND a Qt class has with other argument lists (QFormLayout.addRow(label, field), QBoxLayout.addWidget(w, stretch), QWidget.setFixedSize(w, h) ...). On an object of
# unknown type such a call is far more likely the Qt one, so these names are not judged on an unknown object (a call on a named QGIS class is still checked). Reviewed 2026-11-11 from the first run.
QT_NAME_COLLISIONS = frozenset({"deleteLater", "addRow", "addItem", "addWidget", "addButton", "setFixedSize", "setMinimumSize", "openUrl", "setGeometry", "setPosition", "setItem",
                                "boundingRect", "setRect", "createConnection"})


def _is_camel_case(name):
    """True for QGIS-style member names (setGeometry, mapSettings). A lowercase single word (run, get, count, format, color, accept) is also a Python or Qt name, and with the object's type
    unknown such a call cannot be judged, so only camelCase names are checked on an object of unknown type. Pure."""
    return any(c.isupper() for c in name[1:]) and name[0].islower()


def _snapshot():
    with open(os.path.join(ROOT, "tests", "fixtures", "pyqgis_4_2_signatures.json"), encoding="utf-8") as fh:
        return json.load(fh)["classes"]


def fits(overload, positional, keywords):
    """True when a call with `positional` positional arguments and the given keyword names fits one overload [fewest, most (-1 = *args), parameter names]. Pure."""
    fewest, most, names = overload[0], overload[1], overload[2]
    if most != -1 and positional > most:
        return False
    if any(k not in names for k in keywords):
        return False
    return positional + len(keywords) >= fewest and (most == -1 or positional + len(keywords) <= most)


def _call_shape(node):
    """(positional count, keyword names) or None when the call uses *args or **kwargs. Pure."""
    if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
        return None
    return len(node.args), [k.arg for k in node.keywords]


def problems():
    classes = _snapshot()
    by_member = {}
    for _cls, members in classes.items():
        for member, overloads in members.items():
            if member != "__init__":
                by_member.setdefault(member, []).extend(overloads)
    found = []
    for folder, _dirs, files in os.walk(os.path.join(ROOT, "src")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module in ("qgis.core", "qgis.gui", "qgis.analysis") for a in n.names}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                shape = _call_shape(node)
                if shape is None:
                    continue
                positional, keywords = shape
                func = node.func
                if isinstance(func, ast.Name) and func.id in imported and func.id in classes and "__init__" in classes[func.id]:
                    overloads, label = classes[func.id]["__init__"], func.id
                elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in imported and func.value.id in classes and func.attr in classes[func.value.id]:
                    overloads, label = classes[func.value.id][func.attr], f"{func.value.id}.{func.attr}"
                    # QgsX.method(obj, ...) is an unbound call of an instance method: one argument more is allowed, but never for a static member
                    if not any(fits(o, positional, keywords) or (not o[3] and fits(o, positional - 1, keywords)) for o in overloads):
                        found.append((rel, node.lineno, func.attr, f"{label}({positional} positional, keywords {keywords}) fits none of {overloads}"))
                    continue
                elif isinstance(func, ast.Attribute) and func.attr in by_member and func.attr not in QT_AND_OTHER and func.attr not in QT_NAME_COLLISIONS and _is_camel_case(func.attr):
                    overloads, label = by_member[func.attr], f"<object>.{func.attr}"
                else:
                    continue
                if not any(fits(o, positional, keywords) for o in overloads) and (rel, node.lineno, func.attr if isinstance(func, ast.Attribute) else func.id) not in REVIEWED_OK:
                    found.append((rel, node.lineno, func.attr if isinstance(func, ast.Attribute) else func.id,
                                  f"{label}({positional} positional, keywords {keywords}) fits no overload: {sorted(set(map(str, overloads)))[:4]}"))
    return [f for f in found if (f[0], f[1], f[2]) not in REVIEWED_OK]


class TestFits(unittest.TestCase):
    def test_known_answers(self):
        point = [[2, 2, ["x", "y"], 0], [1, 1, ["point"], 0]]
        self.assertTrue(any(fits(o, 2, []) for o in point))
        self.assertTrue(any(fits(o, 0, ["x", "y"]) for o in point))
        self.assertFalse(any(fits(o, 3, []) for o in point))
        self.assertFalse(any(fits(o, 0, []) for o in point))
        self.assertFalse(any(fits(o, 1, ["z"]) for o in point))
        self.assertTrue(fits([1, -1, [], 0], 7, []))

    def test_call_shape_skips_star_arguments(self):
        self.assertIsNone(_call_shape(ast.parse("f(*a)").body[0].value))
        self.assertIsNone(_call_shape(ast.parse("f(**k)").body[0].value))
        self.assertEqual(_call_shape(ast.parse("f(1, 2, a=3)").body[0].value), (2, ["a"]))


class TestArity(unittest.TestCase):
    def test_the_fixture_is_not_empty_and_knows_the_common_classes(self):
        classes = _snapshot()
        self.assertGreater(len(classes), 100)
        self.assertIn("QgsGeometry", classes)
        self.assertIn("__init__", classes["QgsPointXY"])

    def test_no_call_fits_no_overload_of_the_reference(self):
        found = problems()
        self.assertEqual(found, [], "\n" + "\n".join(f"{p}:{n}: {why}" for p, n, _m, why in sorted(found)))


if __name__ == "__main__":
    unittest.main()
