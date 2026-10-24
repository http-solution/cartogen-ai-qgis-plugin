"""PLAN-016 item 2, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): a layer made from a
SENSITIVE layer (even renamed, with its source renamed too) makes a layout export ask for confirmation, and the QA checklist and the
Sensitivity wording say where the protection comes from."""
import os
import tempfile
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

    from cartogen_ai.core.agent.lineage import tag_layer_lineage
    from cartogen_ai.core.models.sensitivity import set_layer_sensitivity


def _layer(name, x):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=val:double", name, "memory")
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromWkt(f"POINT({x} 15)"))
    f.setAttributes([1.0])
    layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestExportFollowsLineage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = _layer("smoke_points", 44)
        set_layer_sensitivity(self.source, "SENSITIVE", "test")
        self.derived = _layer("merged_test", 45)
        tag_layer_lineage(self.derived, "native:mergevectorlayers", {}, source_layers=["smoke_points"], source_ids=[self.source.id()])
        self.derived.setName("harmless_name")                 # the rename of the hand-test row
        self.source.setName("renamed_source")                 # and the source renamed too: the recorded id still resolves
        node = QgsProject.instance().layerTreeRoot().findLayer(self.source.id())
        node.setItemVisibilityChecked(False)                  # the map draws only the derived layer

    def _layout(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Lineage test", confirmed=True)
        self.assertTrue(res.get("success"), res)
        return res["layout_name"]

    def test_the_derived_layer_has_no_tag_of_its_own(self):
        from cartogen_ai.core.models.sensitivity import get_layer_sensitivity
        self.assertIsNone(get_layer_sensitivity(self.derived).get("level"))

    def test_exporting_a_map_that_draws_the_derived_layer_asks_first(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        name = self._layout()
        path = os.path.join(self.tmp.name, "a.png")
        card = export_layout(name, path)
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)
        self.assertIn("derived from 'renamed_source'", card["rationale"])
        self.assertFalse(os.path.exists(path))
        done = export_layout(name, path, confirmed=True)
        self.assertTrue(done.get("success"), done)
        self.assertEqual(done["protected_layers"][0]["layer"], "harmless_name")

    def test_building_a_layout_that_writes_a_file_asks_first(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        card = create_print_layout("Lineage build", output_path=os.path.join(self.tmp.name, "b.pdf"))
        self.assertEqual(card.get("status"), "PREVIEW_REQUIRED", card)

    def test_a_publication_export_lists_it_as_a_problem(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        name = self._layout()
        refused = export_layout(name, os.path.join(self.tmp.name, "c.png"), purpose="publication")
        self.assertIn("error", refused, refused)
        self.assertTrue(any("derived from" in p for p in refused["problems"]), refused)

    def test_an_explicit_public_tag_on_the_derived_layer_releases_it(self):
        from cartogen_ai.core.agent.tools.layout_item_tools import export_layout
        set_layer_sensitivity(self.derived, "PUBLIC", "aggregated")
        name = self._layout()
        self.assertTrue(export_layout(name, os.path.join(self.tmp.name, "d.png")).get("success"))

    def test_the_qa_checklist_names_the_source(self):
        from cartogen_ai.core.agent.tools.qa_checklist_tools import generate_map_product_qa_checklist
        disclosure = generate_map_product_qa_checklist("harmless_name")["categories"]["disclosure"]
        self.assertEqual((disclosure["level"], disclosure["derived_from"]), ("SENSITIVE", "renamed_source"))

    def test_the_sensitivity_dialog_label_says_protected_through_lineage(self):
        from cartogen_ai.core.agent.protection import effective_sensitivity, sensitivity_label
        record = effective_sensitivity(self.derived, list(QgsProject.instance().mapLayers().values()))
        self.assertEqual(sensitivity_label(record["level"], None, record["derived_from"]),
                         "Current: untagged, protected through lineage from 'renamed_source' (SENSITIVE)")


if __name__ == "__main__":
    unittest.main()
