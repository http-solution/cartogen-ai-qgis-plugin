"""TEMPORARY probe (DEF-27): prints what each way of measuring a legend returns on real QGIS, so the fix rests on numbers. Removed once the measurement is chosen."""
import unittest

from tests.test_layout_fit_live import QGIS_LIVE_AVAILABLE, TestLayoutFitsItsFrames

if QGIS_LIVE_AVAILABLE:
    from qgis.core import QgsProject, QgsLayoutSize, QgsUnitTypes


def say(label, call):
    try:
        print(f"LEGENDPROBE {label}: {call()}", flush=True)
    except Exception as exc:
        print(f"LEGENDPROBE {label}: EXC {type(exc).__name__}: {exc}", flush=True)


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "needs real qgis.core bindings")
class TestProbe(TestLayoutFitsItsFrames):
    def test_probe(self):
        for count, classes in ((1, 3), (7, 14)):
            QgsProject.instance().clear()
            self._layers(count, classes)
            res = self._make(page_size="A3", page_orientation="Portrait")
            layout = QgsProject.instance().layoutManager().layoutByName(res["layout_name"])
            self._probe(res, layout, f"{count}x{classes}")

    def _probe(self, res, layout, tag):
        if True:
            leg = layout.itemById("LEGEND")
            say(f"{tag} check", lambda: res["legend_check"])
            say(f"{tag} rect", lambda: (leg.rect().width(), leg.rect().height()))
            say(f"{tag} resizeToContents", leg.resizeToContents)
            say(f"{tag} sizeWithUnits", lambda: (leg.sizeWithUnits().width(), leg.sizeWithUnits().height(), leg.sizeWithUnits().units()))
            say(f"{tag} minimumSize", lambda: (leg.minimumSize().width(), leg.minimumSize().height()))
            say(f"{tag} fixedSize", lambda: (leg.fixedSize().width(), leg.fixedSize().height()))
            say(f"{tag} layers in model", lambda: [layer.name() for layer in leg.model().rootGroup().findLayers()])

            def after_adjust():
                leg.setResizeToContents(True)
                leg.adjustBoxSize()
                return (leg.rect().width(), leg.rect().height())
            say(f"{tag} after setResizeToContents(True)+adjustBoxSize", after_adjust)

            def after_small():
                leg.attemptResize(QgsLayoutSize(20, 10, QgsUnitTypes.LayoutUnit.LayoutMillimeters))
                leg.adjustBoxSize()
                return (leg.rect().width(), leg.rect().height())
            say(f"{tag} after shrink to 20x10 then adjustBoxSize", after_small)

            def renderer_min():
                from qgis.core import QgsLegendRenderer, QgsLayoutUtils
                context = QgsLayoutUtils.createRenderContextForLayout(layout, None)
                size = QgsLegendRenderer(leg.model(), leg.legendSettings()).minimumSize(context)
                return (size.width(), size.height())
            say(f"{tag} QgsLegendRenderer.minimumSize", renderer_min)

            def refreshed():
                leg.refresh()
                return (leg.rect().width(), leg.rect().height())
            say(f"{tag} after refresh()", refreshed)
            say(f"{tag} filterByMap", leg.legendFilterByMapEnabled)


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromName("test_probe", TestProbe))
    return suite


if __name__ == "__main__":
    unittest.main()
