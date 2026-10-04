# -*- coding: utf-8 -*-
"""A failing layout re-run keeps the old layout; duplicate atlas values give distinct files (audit F28, #164).

Written without a QGIS install here: CI's first run is its first execution."""
import os
import shutil
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _districts(names):
    layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=name:string", "districts", "memory")
    feats = []
    for i, name in enumerate(names):
        f = QgsFeature(layer.fields())
        x = 44.0 + i * 0.1
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({x} 15, {x + 0.09} 15, {x + 0.09} 15.09, {x} 15.09, {x} 15))"))
        f.setAttributes([name])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestLayoutSwapAndAtlas(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cg_layout_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        QgsProject.instance().addMapLayer(_districts(["Sanaa", "Sanaa", "Aden"]))

    def _names(self):
        return sorted(layout.name() for layout in QgsProject.instance().layoutManager().printLayouts())

    def test_a_failing_rerun_keeps_the_old_layout_and_leaves_no_temporary_one(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        first = create_print_layout("Report", body_text="first version")
        self.assertTrue(first.get("success"), first)
        manager = QgsProject.instance().layoutManager()
        old = manager.layoutByName(first["layout_name"])
        self.assertIsNotNone(old)
        old_body = old.itemById("BODY_TEXT").text() if old.itemById("BODY_TEXT") else None

        bad = create_print_layout("Report", body_text="second version", output_path=os.path.join(self.tmp, "x.docx"))

        self.assertIn("error", bad)
        self.assertEqual(self._names(), [first["layout_name"]])               # no "__building" leftover
        kept = manager.layoutByName(first["layout_name"])
        self.assertIsNotNone(kept)
        if old_body is not None:
            self.assertEqual(kept.itemById("BODY_TEXT").text(), old_body)     # still the first version

    def test_a_good_rerun_replaces_it(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        first = create_print_layout("Report", body_text="first version")
        second = create_print_layout("Report", body_text="second version")
        self.assertTrue(second.get("success"), second)
        self.assertEqual(self._names(), [first["layout_name"]])               # still exactly one
        layout = QgsProject.instance().layoutManager().layoutByName(first["layout_name"])
        if layout.itemById("BODY_TEXT"):
            self.assertIn("second", layout.itemById("BODY_TEXT").text())

    def test_duplicate_atlas_values_write_distinct_files(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout, export_layout_atlas
        made = create_print_layout("Atlas")
        self.assertTrue(made.get("success"), made)
        out = os.path.join(self.tmp, "pages")
        res = export_layout_atlas(made["layout_name"], "districts", out, "name", output_format="png", dpi=40)
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["feature_count"], 3)
        names = sorted(os.path.basename(p) for p in res["output_files"])
        self.assertEqual(len(set(n.lower() for n in names)), 3, names)
        self.assertEqual(sorted(os.listdir(out)), names)
        self.assertTrue(res["atlas_settings_restored"])
        atlas = QgsProject.instance().layoutManager().layoutByName(made["layout_name"]).atlas()
        self.assertFalse(atlas.enabled())                                     # put back as it was


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestSitrepTemplate(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.mkdtemp(prefix="cg_sitrep_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        QgsProject.instance().addMapLayer(_districts(["Sanaa", "Aden"]))

    def test_sitrep_text_panel_holds_the_supplied_sections_and_exports(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        out = os.path.join(self.tmp, "sitrep.png")
        res = create_print_layout(
            "Situation report", template="sitrep", body_text="Flooding along the southern coast.", output_path=out, dpi=60,
            key_figures=[{"label": "People in need", "value": "412,000 (estimate)", "source": "calculate_population_in_need"}],
            sources=["OCHA COD-AB", "WorldPop 2020"])
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["template"], "sitrep")
        self.assertNotIn("sitrep_warning", res)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        text = layout.itemById("BODY_TEXT").text()
        for part in ("SITUATION", "KEY FIGURES", "412,000 (estimate)", "SOURCES", "WorldPop 2020", "HANDLING"):
            self.assertIn(part, text)
        self.assertGreater(os.path.getsize(out), 1000)

    def test_an_empty_sitrep_warns_instead_of_inventing_content(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Empty report", template="sitrep")
        self.assertTrue(res.get("success"), res)
        self.assertIn("sitrep_warning", res)
        layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
        text = layout.itemById("BODY_TEXT").text()
        self.assertTrue(text.startswith("HANDLING"))
        self.assertNotIn("KEY FIGURES", text)


if __name__ == "__main__":
    unittest.main()
