# -*- coding: utf-8 -*-
"""Live-QGIS check that the scoped enum names the plugin uses exist (plugins.qgis.org Qt6 compatibility check, 2026-10-10: 38 unscoped
enum uses such as QgsProcessing.TypeVectorPoint were flagged). A name that did not resolve would be an AttributeError the first time
its code path ran, and several of these paths only run in a real map session, so every one is resolved here."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import qgis.core as qc
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QPageSize
    LIVE = True
except ImportError:
    LIVE = False

# (owner, scoped path) as written in the plugin source.
NAMES = [
    ("QgsProcessing", "SourceType.TypeVectorPoint"), ("QgsProcessing", "SourceType.TypeVectorLine"),
    ("QgsProcessingParameterNumber", "Type.Double"), ("QgsFeatureSink", "Flag.FastInsert"),
    ("Qgis", "MessageLevel.Info"), ("Qgis", "MessageLevel.Warning"), ("Qgis", "MessageLevel.Critical"),
    ("QgsWkbTypes", "GeometryType.PointGeometry"), ("QgsWkbTypes", "GeometryType.LineGeometry"),
    ("QgsWkbTypes", "GeometryType.PolygonGeometry"), ("QgsUnitTypes", "RenderUnit.RenderMillimeters"),
    ("QgsPalLayerSettings", "Placement.OrderedPositionsAroundPoint"), ("QgsPalLayerSettings", "Placement.Curved"),
    ("QgsPalLayerSettings", "Placement.Horizontal"), ("QgsLabelObstacleSettings", "ObstacleType.PolygonBoundary"),
    ("QgsLayoutExporter", "ExportResult.Success"),
]


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestScopedEnumsResolve(unittest.TestCase):
    def test_qgis_core_names(self):
        for owner, path in NAMES:
            obj = getattr(qc, owner)
            for part in path.split("."):
                self.assertTrue(hasattr(obj, part), f"{owner}.{path}: no '{part}'")
                obj = getattr(obj, part)

    def test_flat_qvariant_field_types_still_exist(self):
        """28 call sites build QgsField(name, QVariant.Double/Int/String/...). The directory's checker did not flag them, but
        PyQt6 dropped QVariant.Type, so confirm QGIS 4.2's qgis.PyQt still provides them (they are not Qt6-clean if this fails)."""
        from qgis.PyQt.QtCore import QVariant
        for name in ("Double", "Int", "String", "LongLong", "Bool", "Date", "DateTime"):
            self.assertTrue(hasattr(QVariant, name), f"QVariant.{name} missing on this QGIS")
        qc.QgsField("x", QVariant.Double)

    def test_qt_names(self):
        self.assertTrue(hasattr(Qt.PenJoinStyle, "RoundJoin"))
        self.assertTrue(hasattr(QPageSize.Unit, "Millimeter"))


if __name__ == "__main__":
    unittest.main()
