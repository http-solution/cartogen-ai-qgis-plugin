"""Live-QGIS test for tools/_chunked.py: a real layer, a real Qt event loop. Written without a local QGIS: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
    from qgis.PyQt.QtCore import QTimer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    return _boot_qgis()


def _layer(n):
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=i:integer", "pts", "memory")
    feats = []
    for i in range(n):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(44.0 + i * 1e-5, 15.0)))
        f.setAttributes([i])
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestChunkedLive(unittest.TestCase):
    def setUp(self):
        _boot()

    def test_every_feature_is_seen_and_qt_gets_a_turn_during_the_loop(self):
        from cartogen_ai.core.agent.tools import _chunked as ch
        layer = _layer(3000)
        fired = []
        QTimer.singleShot(0, lambda: fired.append(True))              # only runs if the loop hands control back to Qt
        seen = 0
        for _feat in ch.features(layer, "live test", slice_s=0.0, check_every=1):
            seen += 1
        self.assertEqual(seen, 3000)
        self.assertEqual(fired, [True])

    def test_stop_ends_the_loop_with_the_cancel_error(self):
        from cartogen_ai.core.agent.tools import _chunked as ch
        from cartogen_ai.core.agent.tools._background_processing import AnalysisCancelledError
        layer = _layer(3000)
        seen = 0
        with self.assertRaises(AnalysisCancelledError):
            for _feat in ch.features(layer, "live test", slice_s=0.0, check_every=1, cancelled=lambda: seen >= 100):
                seen += 1
        self.assertTrue(100 <= seen < 3000, seen)


if __name__ == "__main__":
    unittest.main()
