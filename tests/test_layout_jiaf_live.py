# -*- coding: utf-8 -*-
"""A real layout built while a JIAF-support result field is visible contains the statement (issue 229, J16)."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsLayoutItemLabel, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLayoutJiafLive(unittest.TestCase):
    def setUp(self):
        from tests.test_chat_widget_live import _boot_qgis
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _labels(self, field):
        import cartogen_ai.core.agent.tools  # noqa: F401
        from cartogen_ai.core.agent.tools.registry import TOOL_REGISTRY
        layer = QgsVectorLayer(f"Polygon?crs=EPSG:4326&field={field}:double", "adm", "memory")
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt("Polygon((44 15,44.2 15,44.2 15.2,44 15.2,44 15))"))
        f.setAttributes([3.0])
        layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(layer)
        result = TOOL_REGISTRY["create_print_layout"](title="Severity map")
        self.assertNotIn("error", result, result)
        layout = QgsProject.instance().layoutManager().layouts()[0]
        return " ".join(i.text() for i in layout.items() if isinstance(i, QgsLayoutItemLabel))

    def test_statement_present_for_a_jiaf_field(self):
        self.assertIn("not endorsed by OCHA or the IASC", self._labels("jf_pre_sev"))

    def test_statement_absent_otherwise(self):
        self.assertNotIn("OCHA", self._labels("pop"))


if __name__ == "__main__":
    unittest.main()
