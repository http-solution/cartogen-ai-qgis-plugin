"""GitHub #379, rc48 hand test rows A12 and A6 (2026-10-24): three layout charts added without a position sat on top of one another, the bar and pie
items drew empty grids, and the elevation profile drew axes but no curve. Existing tests read the items back; none renders the layout.

This adds three charts and a profile through the real tools, with NO positions, then (1) checks no two items overlap and (2) renders page 1 to an
image and measures how much of each item's rectangle is coloured (a drawn bar, slice, line or profile curve is coloured; axes, grid and text are
grey or black). The measured numbers are printed and included in the failure message, because the first run is a diagnosis: a failure in (2) says
whether the items really draw empty or whether the colour threshold is wrong. Written without a QGIS install: CI's first run is its first execution."""
import tempfile
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsLayoutExporter, QgsPrintLayout, QgsProject, QgsRasterLayer, QgsVectorLayer
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QSize
    from qgis.PyQt.QtGui import QColor
    LIVE = True
except ImportError:
    LIVE = False

PX_PER_MM = 5


def colour_stats(image, rect_mm):
    """(share of pixels clearly coloured, share not white, pixel count) inside a rectangle given in millimetres."""
    x0, y0 = int(rect_mm.x() * PX_PER_MM), int(rect_mm.y() * PX_PER_MM)
    x1, y1 = int((rect_mm.x() + rect_mm.width()) * PX_PER_MM), int((rect_mm.y() + rect_mm.height()) * PX_PER_MM)
    coloured = not_white = total = 0
    for y in range(max(0, y0), min(image.height(), y1)):
        for x in range(max(0, x0), min(image.width(), x1)):
            c = QColor(image.pixel(x, y))
            total += 1
            if c.alpha() and (c.red(), c.green(), c.blue()) != (255, 255, 255):
                not_white += 1
                if max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) >= 40:
                    coloured += 1
    return (coloured / total if total else 0.0), (not_white / total if total else 0.0), total


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLayoutItemsRender(unittest.TestCase):
    def setUp(self):
        from tests._geometry_probe import _make_rasters
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.dem = QgsRasterLayer(_make_rasters(tempfile.mkdtemp())["dem"], "dem")
        QgsProject.instance().addMapLayer(self.dem)
        towns = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string&field=pop:integer", "towns", "memory")
        for i, (n, pop) in enumerate((("a", 5), ("b", 50), ("c", 500), ("d", 120))):
            f = QgsFeature(towns.fields())
            f.setGeometry(QgsGeometry.fromWkt(f"POINT({i} {i})"))
            f.setAttributes([n, pop])
            towns.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(towns)
        self.layout = QgsPrintLayout(QgsProject.instance())
        self.layout.initializeDefaults()
        self.layout.setName("render")
        QgsProject.instance().layoutManager().addLayout(self.layout)

    def _build(self):
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_chart, add_layout_elevation_profile
        ids = {}
        for kind in ("bar", "pie", "line"):
            res = add_layout_chart("render", "towns", "name", "pop", chart_type=kind, item_id=f"chart_{kind}")
            self.assertTrue(res.get("success"), res)
            print(f"LAYOUTRENDER {kind} placed at {res.get('x_mm')}, {res.get('y_mm')} {res.get('placement_note', '')}")
            ids[kind] = f"chart_{kind}"
        self.assertTrue(set_layer_elevation("dem", enabled=True, mode="surface", band=1).get("success"))
        res = add_layout_elevation_profile("render", ["dem"], 0.2, 0.2, 3.8, 3.8, item_id="profile_dem", width_mm=120, height_mm=60)
        self.assertTrue(res.get("success"), res)
        print(f"LAYOUTRENDER profile placed at {res.get('x_mm')}, {res.get('y_mm')} {res.get('placement_note', '')}")
        ids["profile"] = "profile_dem"
        return ids

    def test_items_added_without_a_position_do_not_overlap(self):
        ids = self._build()
        rects = {k: self.layout.itemById(v).sceneBoundingRect() for k, v in ids.items()}   # Qt rectangles in mm, enough for a test
        names = list(rects)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertFalse(rects[a].intersects(rects[b]), f"{a} {rects[a]} overlaps {b} {rects[b]}")

    def test_the_rendered_items_are_not_empty(self):
        ids = self._build()
        page = self.layout.pageCollection().page(0).pageSize()
        size = QSize(int(page.width() * PX_PER_MM), int(page.height() * PX_PER_MM))
        image = QgsLayoutExporter(self.layout).renderPageToImage(0, size)
        self.assertFalse(image.isNull())
        stats = {k: colour_stats(image, self.layout.itemById(v).sceneBoundingRect()) for k, v in ids.items()}
        report = "; ".join(f"{k}: coloured {c:.3f}, not-white {n:.3f}, {t} px" for k, (c, n, t) in stats.items())
        print(f"LAYOUTRENDER {report}")
        for k in ("line", "profile"):   # rc48 A12/A6: the colour share cannot tell "thin dark line" from "nothing", so print the picture itself
            rect = self.layout.itemById(ids[k]).sceneBoundingRect()
            crop = image.copy(int(rect.x() * PX_PER_MM), int(rect.y() * PX_PER_MM), int(rect.width() * PX_PER_MM), int(rect.height() * PX_PER_MM))
            data = QByteArray()
            buf = QBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            crop.save(buf, "PNG")
            print(f"LAYOUTPNG {k} {bytes(data.toBase64()).decode()}")
        empty = [k for k, (c, _n, t) in stats.items() if c * t < 100]   # a thin line or curve is a few hundred pixels at 5 px/mm; an empty plot is none
        self.assertEqual(empty, [], f"these items drew no colour (measured: {report})")


if __name__ == "__main__":
    unittest.main()
