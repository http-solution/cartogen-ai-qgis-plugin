"""GitHub #128, rc48 hand test OI-128 (2026-10-24): "Style the raster yem_ppp_2020 with a population colour ramp." The reply said a singleband
pseudocolor population ramp with transparent NoData was applied, but the canvas and legend showed a plain grey gradient. Reply and rendering
disagreed. Existing tests read the renderer back; none renders the layer and looks at the pixels. This renders the layer to an image after the
tools run and asserts the pixels are COLOURED (red, green and blue clearly different), so a grey gradient fails.
Written without a QGIS install: CI's first run is its first execution; a failure is the finding, not a test slip."""
import os
import unittest

from tests.test_network_units_live import QGIS_LIVE_AVAILABLE, _boot

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsMapRendererSequentialJob, QgsMapSettings, QgsProject, QgsRasterLayer
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor

DEM = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "release_smoke_assets", "inputs", "smoke_dem.tif")


def coloured_fraction(layer, size=96):
    """Share of rendered pixels whose channels differ clearly (a grey ramp has r == g == b). Renders the layer alone on white."""
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setExtent(layer.extent())
    settings.setOutputSize(QSize(size, size))
    settings.setBackgroundColor(QColor(255, 255, 255))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    coloured = total = 0
    for y in range(image.height()):
        for x in range(image.width()):
            c = QColor(image.pixel(x, y))
            r, g, b = c.red(), c.green(), c.blue()
            if (r, g, b) == (255, 255, 255):
                continue                      # background / transparent cell
            total += 1
            if max(r, g, b) - min(r, g, b) >= 25:
                coloured += 1
    return (coloured / total) if total else 0.0, total


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestPopulationRampRenders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        why = _boot()
        if why:
            raise unittest.SkipTest(why)

    def setUp(self):
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        # the hand test loaded the same file twice and renamed one copy, so a plain DEM sits beside the population-named layer
        self.dem = QgsRasterLayer(DEM, "smoke_dem")
        self.ppp = QgsRasterLayer(DEM, "yem_ppp_2020")
        self.assertTrue(self.dem.isValid() and self.ppp.isValid())
        QgsProject.instance().addMapLayer(self.dem)
        QgsProject.instance().addMapLayer(self.ppp)

    def test_apply_raster_stretch_on_a_population_named_raster_renders_in_colour(self):
        from cartogen_ai.core.agent.tools.raster_tools import apply_raster_stretch
        result = apply_raster_stretch("yem_ppp_2020")
        print(f"PPPRENDER tool result {result}")
        self.assertTrue(result.get("success"), result)
        share, total = coloured_fraction(self.ppp)
        print(f"PPPRENDER coloured share {share:.2f} of {total} pixels, renderer {self.ppp.renderer().type()}")
        self.assertGreater(total, 100)
        self.assertGreater(share, 0.5, "the population raster renders grey even though the tool reported a ramp")

    def test_the_renderer_the_tool_reports_is_the_one_on_the_layer(self):
        from cartogen_ai.core.agent.tools.raster_tools import apply_raster_stretch
        apply_raster_stretch("yem_ppp_2020")
        self.assertEqual(self.ppp.renderer().type(), "singlebandpseudocolor")

    def test_the_plain_dem_next_to_it_is_left_alone(self):
        from cartogen_ai.core.agent.tools.raster_tools import apply_raster_stretch
        before = self.dem.renderer().type()
        apply_raster_stretch("yem_ppp_2020")
        self.assertEqual(self.dem.renderer().type(), before)


if __name__ == "__main__":
    unittest.main()
