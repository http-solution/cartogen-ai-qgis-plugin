"""PLAN-011 gaps 4 and 5 from the self-audit, real QGIS (CI live job; written without a QGIS install, so CI's first run is its first execution).

4. The footer's sources line read a layer's organisation and publication date from its own metadata, but only the 'source not recorded' path had run.
   This sets real metadata (and a file-backed layer) and checks the footer.
5. The two Settings controls for the footer disclaimer had no test: default state, and what Save writes."""
import os
import tempfile
import unittest

try:
    from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsLayerMetadata, QgsProject, QgsSettings, QgsVectorLayer
    from qgis.PyQt.QtCore import QDate, QDateTime, QTime
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    return _boot_qgis()


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestFooterSourceMetadata(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _memory_layer(self, name):
        layer = QgsVectorLayer("Point?crs=EPSG:4326&field=id:integer", name, "memory")
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt("POINT(44 15)"))
        feature.setAttributes([1])
        layer.dataProvider().addFeatures([feature])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        return layer

    def _footer(self):
        from cartogen_ai.core.agent.tools.layout_tools import create_print_layout
        res = create_print_layout("Source check", confirmed=True)
        self.assertTrue(res.get("success"), res)
        return QgsProject.instance().layoutManager().layoutByName(res["layout_name"]).itemById("FOOTER").text()

    def test_organisation_and_publication_date_come_from_the_layer_metadata(self):
        layer = self._memory_layer("roads")
        metadata = QgsLayerMetadata()
        contact = QgsLayerMetadata.Contact()
        contact.organization = "OCHA"
        metadata.setContacts([contact])
        metadata.setDateTime(Qgis.MetadataDateType.Published, QDateTime(QDate(2024, 5, 1), QTime(0, 0)))
        layer.setMetadata(metadata)
        self.assertIn("Sources: roads (OCHA; 2024-05-01)", self._footer())

    def test_a_file_backed_layer_without_metadata_names_its_file(self):
        path = os.path.join(self.tmp.name, "clinics.geojson")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":1},'
                         '"geometry":{"type":"Point","coordinates":[44,15]}}]}')
        layer = QgsVectorLayer(path, "clinics", "ogr")
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        self.assertIn("Sources: clinics (file clinics.geojson)", self._footer())


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestDisclaimerSettingsControls(unittest.TestCase):
    PREFIX = "cartogen_ai/"

    def setUp(self):
        why = _boot()
        if why:
            self.skipTest(why)
        settings = QgsSettings()
        saved = {key: settings.value(key) for key in settings.allKeys() if key.startswith(self.PREFIX)}

        def restore():
            for key in [k for k in settings.allKeys() if k.startswith(self.PREFIX)]:
                settings.remove(key)
            for key, value in saved.items():
                settings.setValue(key, value)
        self.addCleanup(restore)
        for key in saved:
            settings.remove(key)

    def test_default_is_on_with_empty_wording_and_save_writes_both(self):
        from cartogen_ai.core.ui.settings_dialog import CartogenAiSettingsDialog
        from cartogen_ai.infrastructure.settings_keys import SETTINGS_LAYOUT_DISCLAIMER_ENABLED, SETTINGS_LAYOUT_DISCLAIMER_TEXT
        dialog = CartogenAiSettingsDialog()
        self.assertTrue(dialog.layout_disclaimer_checkbox.isChecked())
        self.assertEqual(dialog.layout_disclaimer_edit.text(), "")
        dialog.layout_disclaimer_checkbox.setChecked(False)
        dialog.layout_disclaimer_edit.setText("  Our boundary wording.  ")
        dialog.accept()
        settings = QgsSettings()
        self.assertFalse(settings.value(SETTINGS_LAYOUT_DISCLAIMER_ENABLED, True, type=bool))
        self.assertEqual(settings.value(SETTINGS_LAYOUT_DISCLAIMER_TEXT, ""), "Our boundary wording.")
        again = CartogenAiSettingsDialog()
        self.assertFalse(again.layout_disclaimer_checkbox.isChecked())
        self.assertEqual(again.layout_disclaimer_edit.text(), "Our boundary wording.")


if __name__ == "__main__":
    unittest.main()
