"""Calls every registered tool once in real QGIS with plausible arguments built from its own schema, and fails if a tool raises.

Why: the signature test (test_tool_registry_signatures.py) proves a tool ACCEPTS its arguments; nothing proved that each of the 296 tools
can be CALLED in a QGIS session without an uncaught exception (the dispatcher turns an exception into a vague "Execution failed", which
is what a user sees as "it does not work"). A tool may return an error dict for arguments that mean nothing (that is correct behaviour and
counts as a pass); it may not raise, and it may not return None.

Not proved by this test: that the tool does the right thing. Dedicated tests do that. This is the net under them: a new tool, or a
change to an old one, cannot start crashing on ordinary input without this failing.

Skipped by name pattern, with the reason printed: tools that reach the network or a hosted model (a CI run must not depend on them; the
service-reach job covers those), tools that start long background work, and tools that open dialogs. KNOWN_CRASHES is a ratchet: a tool
listed there is a defect to fix, and the list may only shrink (test_known_crashes_are_still_crashing fails when one is fixed so the entry
is removed). Written without a local QGIS: the first CI run is its first execution."""
import faulthandler
import json
import os
import tempfile
import time
import unittest

try:
    from qgis.core import (QgsFeature, QgsGeometry, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsCoordinateReferenceSystem)
    LIVE = True
except ImportError:
    LIVE = False

NETWORK_PREFIXES = ("fetch_", "search_", "download_", "geocode", "load_stac", "web_", "find_incident", "ask_model", "check_fact")
NETWORK_NAMES = {"find_incident_reports", "generate_situation_dashboard", "extract_features_from_imagery", "evaluate_forecast_trigger"}
# Tools that deliberately run the user's code or a long background job; their own live tests cover them.
OTHER_SKIPS = {"execute_pyqgis_script": "runs model-written code in a worker process",
               "execute_read_only_sql": "needs a database connection",
               "run_monitoring_workflow": "starts a recurring background job",
               "schedule_workflow": "starts a recurring background job"}

# Tools that read through GDAL /vsicurl or the hosted model, which the Python-level network stub cannot intercept.
NO_STUB_SKIPS = {"fetch_dem": "reads through GDAL /vsicurl", "fetch_worldpop_population": "reads through GDAL /vsicurl",
                 "ask_model": "calls the hosted model", "extract_features_from_imagery": "downloads a model checkpoint"}
KNOWN_HOSTILE_CRASHES = {}      # "mode:tool" -> error, same ratchet rule as KNOWN_CRASHES

# name -> first line of the error, filled after the first CI run and only ever shortened.
KNOWN_CRASHES = {}


def _layers():
    pts = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer&field=val:double", "pts", "memory")
    for i in range(6):
        f = QgsFeature(pts.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POINT({35 + i * 0.01} {31 + i * 0.01})"))
        f.setAttributes([f"p{i}", 10 * (i + 1), float(i)])
        pts.dataProvider().addFeatures([f])
    zones = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string&field=pop:integer", "zones", "memory")
    for i in range(2):
        f = QgsFeature(zones.fields())
        x = 35 + i * 0.03
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 31,{x + 0.03} 31,{x + 0.03} 31.06,{x} 31.06,{x} 31))"))
        f.setAttributes([f"z{i}", 100 * (i + 1)])
        zones.dataProvider().addFeatures([f])
    roads = QgsVectorLayer("LineString?crs=EPSG:4326&field=name:string&field=highway:string&field=maxspeed:integer", "roads", "memory")
    for i in range(3):
        f = QgsFeature(roads.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"LINESTRING({35} {31 + i * 0.02},{35.06} {31 + i * 0.02})"))
        f.setAttributes([f"r{i}", "primary", 50])
        roads.dataProvider().addFeatures([f])
    return [pts, zones, roads]


def _dem(folder):
    from osgeo import gdal
    import numpy as np
    path = os.path.join(folder, "dem.tif")
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, 20, 20, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((35.0, 0.003, 0, 31.06, 0, -0.003))
    srs = QgsCoordinateReferenceSystem("EPSG:4326")
    ds.SetProjection(srs.toWkt())
    yy, xx = np.mgrid[0:20, 0:20]
    ds.GetRasterBand(1).WriteArray((100 + xx * 3 + yy * 2).astype("float32"))
    ds.FlushCache()
    ds = None
    return path


def _value(name, spec, mode="ok"):
    """A plausible argument for one schema property. `mode` makes the LAYER arguments hostile: 'missing' names a layer that does not exist,
    'wrong_type' swaps raster and vector, 'empty' names layers with no features."""
    if spec.get("enum"):
        return spec["enum"][0]
    for key in ("anyOf", "oneOf"):
        if spec.get(key):
            return _value(name, spec[key][0], mode)
    kind = spec.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), None)
    low = name.lower()
    if kind == "string":
        layerish = ("raster" in low or "dem" in low or "layer" in low
                    or low in ("source", "target", "input", "boundary", "mask", "facilities", "origin", "destination", "roads"))
        if layerish and "field" not in low and mode == "missing":
            return "no_such_layer_xyz"
        if layerish and "field" not in low and mode == "empty":
            return "empty_zones" if ("zone" in low or "admin" in low or "polygon" in low) else "empty_pts"
        if "raster" in low or "dem" in low:
            return "pts" if mode == "wrong_type" else "dem"
        if "field" in low and "layer" not in low:
            return "pop"
        if "layer" in low or low in ("source", "target", "input", "boundary", "mask", "facilities", "origin", "destination", "roads"):
            if mode == "wrong_type":
                return "dem"
            return "zones" if "zone" in low or "admin" in low or "polygon" in low else "pts"
        if "path" in low or "file" in low or "folder" in low:
            return os.path.join(tempfile.gettempdir(), "cartogen_every_tool", "out")
        if "wkt" in low:
            return "POINT(35.02 31.02)"
        if "crs" in low:
            return "EPSG:4326"
        if "expression" in low or "filter" in low:
            return '"pop" > 10'
        if "iso3" in low:
            return "YEM"
        return "x"
    if kind in ("integer", "number"):
        return spec.get("minimum", 1) if spec.get("minimum", 1) > 0 else 1
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "x"      # a property with no usable type: a short text is the most common thing a tool can take


def _args_for(schema, mode="ok"):
    props = schema.get("properties", {})
    return {n: _value(n, props.get(n, {}), mode) for n in schema.get("required", [])}


def _is_skipped(name, network_stubbed=False):
    if name in OTHER_SKIPS:
        return OTHER_SKIPS[name]
    if name in NO_STUB_SKIPS:
        return NO_STUB_SKIPS[name]
    if not network_stubbed and (name in NETWORK_NAMES or name.startswith(NETWORK_PREFIXES)):
        return "reaches the network or a hosted model"
    return None


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEveryToolLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_network_units_live import _boot
        cls.why = _boot()

    def setUp(self):
        if self.why:
            self.skipTest(self.why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp()
        for layer in _layers():
            QgsProject.instance().addMapLayer(layer)
        self.dem_path = _dem(self.tmp)
        QgsProject.instance().addMapLayer(QgsRasterLayer(self.dem_path, "dem"))
        QgsProject.instance().setFileName(os.path.join(self.tmp, "t.qgz"))

    def _run_all(self, mode="ok", network=None):
        import importlib
        importlib.import_module("cartogen_ai.core.agent.tools")
        from cartogen_ai.core.agent.tools import registry
        schemas = {s["function"]["name"]: s["function"]["parameters"] for s in registry.TOOLS_SCHEMA}
        crashed, none_result, skipped, passed, slow = {}, [], {}, [], []
        for name in sorted(registry.TOOL_REGISTRY):
            why = _is_skipped(name, network_stubbed=network is not None)
            if why:
                skipped[name] = why
                continue
            args = _args_for(schemas.get(name, {}), mode)
            t0 = time.time()
            # A tool that never returns would hold the whole CI job for hours (first run of the hostile passes, 2026-10-26: 90 minutes with no
            # output). Print where we are, and have the interpreter dump every thread's stack and exit if one call takes over 120 seconds,
            # so the log names the tool and the line it is stuck on.
            print(f"EVERY_TOOL_CALL mode={mode} network={'stub' if network is not None else 'none'} tool={name}", flush=True)
            faulthandler.dump_traceback_later(120, exit=True)
            try:
                result = registry.TOOL_REGISTRY[name](**args)
            except Exception as e:
                crashed[name] = f"{type(e).__name__}: {str(e).splitlines()[0][:160] if str(e) else ''}"
                continue
            finally:
                faulthandler.cancel_dump_traceback_later()
                if time.time() - t0 > 20:
                    slow.append((name, round(time.time() - t0, 1)))
            if result is None:
                none_result.append(name)
            else:
                passed.append(name)
        report = {"tools": len(registry.TOOL_REGISTRY), "passed": len(passed), "skipped": skipped, "crashed": crashed,
                  "returned_none": none_result, "slow_over_20s": slow}
        print("EVERY_TOOL_REPORT " + json.dumps(report, sort_keys=True))
        return report

    def test_no_tool_raises_or_returns_nothing_on_plausible_arguments(self):
        report = self._run_all()
        new_crashes = {n: m for n, m in report["crashed"].items() if n not in KNOWN_CRASHES}
        self.assertEqual(new_crashes, {}, "tools that raised on plausible arguments (fix the tool, or add to KNOWN_CRASHES with a ticket)")
        self.assertEqual(report["returned_none"], [])

    def test_known_crashes_are_still_crashing(self):
        if not KNOWN_CRASHES:
            self.skipTest("no known crashes")
        report = self._run_all()
        fixed = sorted(n for n in KNOWN_CRASHES if n not in report["crashed"])
        self.assertEqual(fixed, [], "these tools no longer crash: remove them from KNOWN_CRASHES")


class _FakeResponse:
    """What a data service could answer instead of what a tool expects: the shape of a urlopen response."""
    status = 200

    def __init__(self, body):
        self._body = body
        self.headers = {}

    def read(self, n=-1):
        data, self._body = (self._body, b"") if n is None or n < 0 else (self._body[:n], self._body[n:])
        return data

    def getcode(self):
        return 200

    def geturl(self):
        return "https://example.invalid/"

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._body.splitlines(True))


def _stub_network(answer):
    """Replace every reference to the plugin's HTTP entry points with `answer`: an exception class instance to raise, or bytes to return.
    Returns an undo function. Done by identity over all loaded cartogen_ai modules, so a tool that imported the function under another
    name is still covered."""
    import sys
    import urllib.error
    import urllib.request
    from cartogen_ai.core import net
    from cartogen_ai.core.agent.tools import _urllib_retry

    def fake(*args, **kwargs):
        if isinstance(answer, BaseException):
            raise answer
        return _FakeResponse(answer)

    targets = {id(net.urlopen), id(net.stream_following), id(_urllib_retry.urlopen_with_retry)}
    patched = []
    for mod_name, mod in list(sys.modules.items()):
        if not mod_name.startswith("cartogen_ai") or mod is None:
            continue
        for attr, value in list(vars(mod).items()):
            if id(value) in targets:
                patched.append((mod, attr, value))
                setattr(mod, attr, fake)
    original_urlopen = urllib.request.urlopen
    urllib.request.urlopen = fake
    from cartogen_ai.core.agent.tools import vector_tools
    original_safe_open = vector_tools._SafeOpener.open
    vector_tools._SafeOpener.open = lambda self, req, timeout=60: fake()

    def undo():
        for mod, attr, value in patched:
            setattr(mod, attr, value)
        urllib.request.urlopen = original_urlopen
        vector_tools._SafeOpener.open = original_safe_open
    return undo, urllib.error


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestEveryToolHostileInputsLive(TestEveryToolLive):
    """Second and third pass over every tool: hostile layer arguments (missing, wrong type, empty) and hostile network answers (host
    unreachable, an HTML error page, `[]`, `{}`, `null`). A tool may refuse with an error result; it may not raise. The network answers are
    the ones that crashed tools in the field before (a JSON body that is not an object, an error page served as 200)."""
    # the parent's two tests would run again here; they are not repeated
    test_no_tool_raises_or_returns_nothing_on_plausible_arguments = None
    test_known_crashes_are_still_crashing = None

    def setUp(self):
        super().setUp()
        for name, geom, fields in (("empty_pts", "Point", "name:string&field=pop:integer&field=val:double"),
                                   ("empty_zones", "Polygon", "name:string&field=pop:integer")):
            QgsProject.instance().addMapLayer(QgsVectorLayer(f"{geom}?crs=EPSG:4326&field={fields}", name, "memory"))

    def _check(self, mode, network=None):
        undo = None
        if network is not None:
            undo, _ = _stub_network(network)
        try:
            report = self._run_all(mode, network=network)
        finally:
            if undo:
                undo()
        label = mode if network is None else f"net:{mode}"
        new = {n: m for n, m in report["crashed"].items() if f"{label}:{n}" not in KNOWN_HOSTILE_CRASHES}
        listing = "\n".join(f"  {n}: {m}" for n, m in sorted(new.items()))     # the default diff is cut off in the CI log
        self.assertFalse(new, f"[{label}] {len(new)} tools raised (fix the tool, or add '{label}:<tool>' to KNOWN_HOSTILE_CRASHES):\n{listing}")

    def test_layer_that_does_not_exist(self):
        self._check("missing")

    def test_layer_of_the_wrong_type(self):
        self._check("wrong_type")

    def test_layer_with_no_features(self):
        self._check("empty")

    def test_host_unreachable(self):
        import urllib.error
        self._check("ok", network=urllib.error.URLError("host unreachable"))

    def test_http_error_page(self):
        self._check("ok", network=b"<html><body>502 Bad Gateway</body></html>")

    def test_json_that_is_a_list(self):
        self._check("ok", network=b"[]")

    def test_json_that_is_empty_object(self):
        self._check("ok", network=b"{}")

    def test_json_null(self):
        self._check("ok", network=b"null")


class TestEveryToolInputsOffline(unittest.TestCase):
    """The argument builder and the skip list are pure, so they are checked in the plain job too."""

    def _registry(self):
        import importlib
        importlib.import_module("cartogen_ai.core.agent.tools")
        from cartogen_ai.core.agent.tools import registry
        return registry

    def test_every_required_argument_gets_a_value(self):
        registry = self._registry()
        for schema in registry.TOOLS_SCHEMA:
            params = schema["function"]["parameters"]
            args = _args_for(params)
            self.assertEqual(sorted(args), sorted(params.get("required", [])), schema["function"]["name"])
            for n, v in args.items():
                self.assertIsNotNone(v, f"{schema['function']['name']}.{n}")

    def test_the_skip_list_is_small(self):
        # A skip is a tool nobody exercises here; keep that visible. Raise the ceiling only with a reason.
        registry = self._registry()
        skipped = [n for n in registry.TOOL_REGISTRY if _is_skipped(n)]
        self.assertLess(len(skipped), 60, skipped)


if __name__ == "__main__":
    unittest.main()
