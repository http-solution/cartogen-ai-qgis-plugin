"""Live run of every geometry-family algorithm on the allow-list (M6a), built from each algorithm's OWN parameter definitions: a source
parameter gets a suitable test layer, numbers / enums / booleans their default, fields a matching field, extents and points a fixed
value. The call goes through run_allowlisted_processing_algorithm, so the wrapper (unknown-parameter check, memory-only sinks, layer
resolution) is exercised too. A failure names the algorithm and the error; fix the call here only if the call is wrong, otherwise the
algorithm leaves the allow-list and goes into GEOMETRY_NOT_YET with the reason. Written without a QGIS install: CI's first run is
its first execution."""
import unittest

try:
    from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False

from cartogen_ai.core.agent.tools._processing_allowlist import GEOMETRY_FAMILY
from tests._processing_live_rows import GEOMETRY_NOT_YET

_LAYERS = {
    "polys": ("Polygon", ["POLYGON((0 0,2 0,2 2,0 2,0 0),(0.5 0.5,1 0.5,1 1,0.5 1,0.5 0.5))", "POLYGON((2 0,4 0,4 2,2 2,2 0))"]),
    "lines": ("LineString", ["LINESTRING(0 0,1 1,2 0,3 1)", "LINESTRING(0 1,3 0)"]),
    "pts": ("Point", ["POINT(0.2 0.2)", "POINT(1.5 0.4)", "POINT(0.9 1.7)", "POINT(2.5 1.5)", "POINT(3.1 0.2)"]),
}
_ORDER_BY_TYPE = {"polygon": ["polys", "lines", "pts"], "line": ["lines", "polys", "pts"], "point": ["pts", "lines", "polys"]}


def _add_layers():
    for name, (kind, wkts) in _LAYERS.items():
        layer = QgsVectorLayer(f"{kind}?crs=EPSG:4326&field=name:string&field=val:double", name, "memory")
        feats = []
        for i, wkt in enumerate(wkts):
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(wkt))
            f.setAttributes([f"{name}{i}", float(i + 1)])
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)


def _is_optional(parameter):
    from qgis.core import Qgis
    flag = getattr(getattr(Qgis, "ProcessingParameterFlag", None), "Optional", None)
    if flag is None:
        flag = parameter.FlagOptional                      # QGIS 3 spelling
    return bool(parameter.flags() & flag)


def _params_for(algorithm, layer_name):
    params = {}
    for p in algorithm.parameterDefinitions():
        if p.isDestination():
            continue
        kind = p.type()
        if kind in ("source", "vector"):
            params[p.name()] = layer_name
        elif kind in ("number", "distance", "area", "angle"):
            default = p.defaultValue()
            params[p.name()] = default if isinstance(default, (int, float)) and default > 0 else 1
        elif kind == "enum":
            params[p.name()] = p.defaultValue() if p.defaultValue() is not None else 0
        elif kind == "boolean":
            params[p.name()] = bool(p.defaultValue())
        elif kind == "field":
            params[p.name()] = "val" if getattr(p, "dataType", lambda: 0)() == 0 and "numeric" in p.name().lower() else "name"
        elif kind == "extent":
            params[p.name()] = "0.5,3.5,0.2,1.8 [EPSG:4326]"
        elif kind == "point":
            params[p.name()] = "1,1 [EPSG:4326]"
        elif not _is_optional(p):
            params[p.name()] = p.defaultValue()
    return params


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestGeometryFamilyRuns(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        _add_layers()

    def test_every_algorithm_runs_on_at_least_one_geometry_type(self):
        from cartogen_ai.core.agent.tools.processing_allowlist_tools import run_allowlisted_processing_algorithm
        registry = QgsApplication.processingRegistry()
        failures = {}
        for alg_id in sorted(set(GEOMETRY_FAMILY) - set(GEOMETRY_NOT_YET)):
            algorithm = registry.algorithmById(alg_id)
            if algorithm is None:
                failures[alg_id] = "not in the QGIS registry"
                continue
            errors = []
            for layer_name in ("polys", "lines", "pts"):
                result = run_allowlisted_processing_algorithm(alg_id, _params_for(algorithm, layer_name), new_layer_name="out")
                if result.get("success"):
                    break
                errors.append(f"{layer_name}: {str(result.get('error'))[:160]}")
            else:
                failures[alg_id] = " | ".join(errors)
        self.assertEqual(failures, {}, "\n" + "\n".join(f"{k}: {v}" for k, v in sorted(failures.items())))


if __name__ == "__main__":
    unittest.main()
