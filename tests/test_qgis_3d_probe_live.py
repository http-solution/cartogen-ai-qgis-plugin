"""PLAN-023 R10-6: does this QGIS build have the 3D module (qgis._3d)? A probe, not a feature test: it always passes and records the answer, because the answer decides what the coverage
row 'B project and canvas: 3D map view' says. If the module is present, a create_3d_view package is planned in R12 with its own plan; if it is absent, the row is set to declined (module
absent in the CI image). The answer is printed on one line starting '3D_PROBE' in the live job's log and written to $CARTOGEN_LIVE_ARTIFACTS/3d_probe.txt when that folder is set.
Written without a QGIS install: CI's first run is where the answer comes from."""
import json
import os
import unittest

try:
    import qgis.core  # noqa: F401
    LIVE = True
except ImportError:
    LIVE = False

NAMES = ("Qgs3DMapSettings", "Qgs3DMapScene", "Qgs3DMapCanvas", "QgsTerrainGenerator", "QgsFlatTerrainGenerator", "QgsDemTerrainGenerator", "Qgs3DRenderContext", "QgsVectorLayer3DRenderer")


def _probe():
    """{name: bool} of what the 3D module offers; 'importable' is False when `qgis._3d` cannot be imported. Needs QGIS."""
    result = {}
    try:
        from qgis import _3d
    except ImportError as e:
        return {"importable": False, "why": str(e)[:200]}
    result["importable"] = True
    for name in NAMES:
        result[name] = hasattr(_3d, name)
    try:
        result["settings_constructible"] = _3d.Qgs3DMapSettings() is not None
    except (AttributeError, RuntimeError, TypeError) as e:
        result["settings_constructible"] = False
        result["settings_why"] = f"{type(e).__name__}: {str(e)[:120]}"
    return result


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestThreeDProbe(unittest.TestCase):
    def test_record_whether_the_3d_module_is_present(self):
        from qgis.core import Qgis
        result = _probe()
        result["qgis_version"] = Qgis.version()
        line = "3D_PROBE " + json.dumps(result, sort_keys=True)
        print(line)
        folder = os.environ.get("CARTOGEN_LIVE_ARTIFACTS")
        if folder:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "3d_probe.txt"), "w", encoding="utf-8") as fh:
                fh.write(line + "\n")
        self.assertIn("importable", result)


if __name__ == "__main__":
    unittest.main()
