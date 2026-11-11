"""PLAN-023 R3-2 in real QGIS, with the real network (non-blocking: a test SKIPS, it does not fail, when the catalogue or the image store cannot be reached from the CI runner): a small window of
one Sentinel-2 scene is searched, previewed (size shown, nothing downloaded), confirmed and loaded; the file's coordinate system, band count and size are read back and the provenance record sits
beside it. Refusals that need no network (an unsupported band, a layer extent, an invalid area) run always. Written without a QGIS install: CI's first run is its first execution."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from qgis.core import QgsProject, QgsRasterLayer
    LIVE = True
except ImportError:
    LIVE = False

BBOX = [36.80, -1.35, 36.83, -1.32]          # about 3.3 x 3.3 km near Nairobi: roughly 330 x 330 cells at 10 m, under 1 MB


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLoadStacAssetsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        QgsProject.instance().setFileName(os.path.join(self.home, "p.qgz"))

    def _run(self, **kw):
        from cartogen_ai.core.agent.tools.stac_load_tool import load_stac_assets
        return load_stac_assets(**kw)

    def test_refusals_that_need_no_network(self):
        base = {"start_date": "2026-10-01", "end_date": "2026-11-10", "bbox": BBOX}
        self.assertIn("Unknown band", self._run(**base, assets=["landsat_red"])["error"])
        self.assertIn("1 to 6", self._run(**base, assets=["blue"] * 7)["error"])
        self.assertIn("not found", self._run(start_date="2026-10-01", end_date="2026-11-10", assets=["red"], layer_name="nope")["error"])
        self.assertIn("valid WGS84", self._run(start_date="2026-10-01", end_date="2026-11-10", assets=["red"], bbox=[10, 0, 5, 1])["error"])

    def test_preview_then_confirmed_load_of_one_small_window(self):
        args = {"start_date": "2026-08-01", "end_date": "2026-11-10", "bbox": BBOX, "assets": ["red", "nir"], "max_cloud": 100, "limit": 1}
        card = self._run(**args)
        print(f"STACPREVIEW {str(card)[:500]}")
        if "error" in card and ("STAC API query failed" in card["error"] or "no Sentinel-2 scenes" in card["error"]):
            self.skipTest(f"the catalogue could not be reached from this runner: {card['error'][:160]}")
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        self.assertEqual(len(card["scenes"]), 1)
        self.assertEqual(QgsProject.instance().mapLayers(), {})                         # the preview downloaded nothing and added nothing
        self.assertLess(card["estimate_bytes"], 5 * 1024 * 1024)
        out = self._run(**card["arguments"])
        print(f"STACLOADED {str(out)[:600]}")
        if "error" in out and out["error"].startswith("No band could be downloaded"):
            self.skipTest(f"the image store could not be reached from this runner: {out['error'][:200]}")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(len(out["layers"]), 2)
        for entry in out["layers"]:
            layer = QgsRasterLayer(entry["file"], "check")
            self.assertTrue(layer.isValid(), entry)
            self.assertEqual(layer.bandCount(), 1)
            self.assertTrue(layer.crs().authid().startswith("EPSG:327"), layer.crs().authid())      # the scene's own UTM zone, not reprojected
            self.assertTrue(0 < layer.width() < 600 and 0 < layer.height() < 600, (layer.width(), layer.height()))
            record = json.loads(Path(entry["file"].replace(".tif", ".provenance.json")).read_text(encoding="utf-8"))
            self.assertIn("Copernicus Sentinel", record["licence_notice"])
            self.assertEqual(record["band"], entry["layer"].rsplit("_", 1)[1])
        self.assertEqual(len(QgsProject.instance().mapLayers()), 2)
        again = self._run(**card["arguments"])                                         # the same window of the same scene is reused, never downloaded twice
        self.assertTrue(all(e.get("reused") for e in again["layers"]), again)


if __name__ == "__main__":
    unittest.main()
