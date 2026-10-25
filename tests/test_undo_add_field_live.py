"""PLAN-021 WP-E (#425), real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution): add_field, then undo,
on a real layer, through the same snapshot and restore the agent uses."""
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestUndoOfAddField(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string", "towns", "memory")
        feats = []
        for n in range(3):
            f = QgsFeature(self.layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({44 + n} 15)"))
            f.setAttributes([f"town {n}"])
            feats.append(f)
        self.layer.dataProvider().addFeatures(feats)
        QgsProject.instance().addMapLayer(self.layer)
        from cartogen_ai.core.agent.tools import _snapshot_registry as reg
        from cartogen_ai.core.agent.tools.attribute_edit_tools import add_field
        self.reg, self.add_field = reg, add_field

    def _add(self):
        args = {"layer_name": "towns", "field_name": "notes", "field_type": "string"}
        snap = self.reg.get_snapshot_fn("add_field")(args)
        self.assertIsNotNone(snap)
        self.assertTrue(self.add_field(**args).get("success"))
        self.assertGreaterEqual(self.layer.fields().indexOf("notes"), 0)
        return snap

    def test_an_empty_new_field_is_taken_away_by_undo(self):
        snap = self._add()
        self.assertTrue(self.reg.get_restore_fn("restore_added_field", "add_field")(snap), snap)
        self.assertEqual(self.layer.fields().indexOf("notes"), -1)
        self.assertEqual([f["name"] for f in self.layer.getFeatures()], ["town 0", "town 1", "town 2"])      # the other data is untouched

    def test_a_field_that_was_filled_after_it_was_added_is_kept(self):
        snap = self._add()
        idx = self.layer.fields().indexOf("notes")
        if not self.layer.isEditable():
            self.layer.startEditing()
        fid = next(iter(self.layer.getFeatures())).id()
        self.assertTrue(self.layer.changeAttributeValue(fid, idx, "important"))
        self.assertTrue(self.layer.commitChanges())
        self.assertFalse(self.reg.get_restore_fn("restore_added_field", "add_field")(snap))
        self.assertGreaterEqual(self.layer.fields().indexOf("notes"), 0)
        self.assertIn("now holds values", snap["refusal"])
        self.assertIn("important", [f["notes"] for f in self.layer.getFeatures()])

    def test_adding_a_field_that_exists_records_nothing_to_undo(self):
        self._add()
        self.assertIsNone(self.reg.get_snapshot_fn("add_field")({"layer_name": "towns", "field_name": "notes"}))


if __name__ == "__main__":
    unittest.main()
