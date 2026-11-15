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
    from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize
    from qgis.PyQt.QtGui import QColor
    LIVE = True
except ImportError:
    LIVE = False

PX_PER_MM = 5

from cartogen_ai.core.agent.tools.layout_chart_profile_tools import is_data_ink  # noqa: E402  (pure; same rule as the tool's own render check)


def _keep(name, image):
    """Save the picture for the CI artifact (master list DEF-1); never lets a save problem fail a test."""
    try:
        from tests._render_artifacts import save_png
        return save_png(name, image)
    except Exception:                        # keeping a picture is a diagnostic, not part of what the test asserts
        return None


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
                if is_data_ink(c.red(), c.green(), c.blue()):      # DEF-38: one rule for the tool and this test; a fixed spread of 40 missed a muted random colour
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

    def test_a_crowded_page_gets_smaller_items_not_overlapping_ones(self):
        """DEF-37 (round-3 smoke row E3): a header band and a map filling most of the page left no spot for a 120 x 80 chart or a 180 mm profile, so
        both went to (10, 10) on top of them. Now they shrink into what is free, and the result says so."""
        from qgis.core import QgsLayoutItemLabel, QgsLayoutItemMap
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_chart, add_layout_elevation_profile
        page = self.layout.pageCollection().page(0).pageSize()
        # setUp's layout comes from initializeDefaults(): a page and nothing else, so there is nothing to clear. (Clearing through items() raised a
        # TypeError on a plain Qt item in CI run 42561173584, and QgsPrintLayout has no layoutItems() in 4.2.2, run 42561940478.)
        header = QgsLayoutItemLabel(self.layout)
        header.setId("header_band")
        self.layout.addLayoutItem(header)
        header.attemptSetSceneRect(QRectF(0, 0, page.width(), 25))
        frame = QgsLayoutItemMap(self.layout)
        frame.setId("main_map")
        self.layout.addLayoutItem(frame)
        frame.attemptSetSceneRect(QRectF(10, 30, page.width() - 20, page.height() - 90))
        chart = add_layout_chart("render", "towns", "name", "pop", chart_type="bar", item_id="crowded_chart")
        self.assertTrue(chart.get("success"), chart)
        self.assertTrue(set_layer_elevation("dem", enabled=True, mode="surface", band=1).get("success"))
        profile = add_layout_elevation_profile("render", ["dem"], 0.2, 0.2, 3.8, 3.8, item_id="crowded_profile", width_mm=180, height_mm=80)
        self.assertTrue(profile.get("success"), profile)
        print(f"LAYOUTRENDER crowded chart {chart.get('placement_note')} | profile {profile.get('placement_note')}")
        rects = {k: self.layout.itemById(k).sceneBoundingRect() for k in ("header_band", "main_map", "crowded_chart", "crowded_profile")}
        for new in ("crowded_chart", "crowded_profile"):
            for old in ("header_band", "main_map"):
                self.assertFalse(rects[new].intersects(rects[old]), f"{new} {rects[new]} overlaps {old} {rects[old]} (notes: {chart.get('placement_note')} / {profile.get('placement_note')})")
        self.assertFalse(rects["crowded_chart"].intersects(rects["crowded_profile"]))

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
            _keep(f"items_{k}", crop)
            data = QByteArray()
            buf = QBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            crop.save(buf, "PNG")
            print(f"LAYOUTPNG {k} {bytes(data.toBase64()).decode()}")
        empty = [k for k, (c, _n, t) in stats.items() if c * t < 100]   # a thin line or curve is a few hundred pixels at 5 px/mm; an empty plot is none
        self.assertEqual(empty, [], f"these items drew no colour (measured: {report})")

    def test_every_tool_says_whether_its_item_drew_data(self):
        """#379: a chart or profile that drew nothing used to be reported as added with no hint; the result now carries render_check."""
        from cartogen_ai.core.agent.tools.layout_chart_profile_tools import add_layout_chart, add_layout_elevation_profile
        from cartogen_ai.core.agent.tools.elevation_tools import set_layer_elevation
        for kind in ("bar", "pie", "line"):
            res = add_layout_chart("render", "towns", "name", "pop", chart_type=kind, item_id=f"chart_{kind}")
            self.assertTrue(res["render_check"]["drew"], (kind, res))
            self.assertNotIn("render_warning", res)
        self.assertTrue(set_layer_elevation("dem", enabled=True, mode="surface", band=1).get("success"))
        res = add_layout_elevation_profile("render", ["dem"], 0.2, 0.2, 3.8, 3.8, item_id="profile_dem", width_mm=120, height_mm=60)
        self.assertTrue(res["render_check"]["drew"], res)

    def test_the_profile_curve_is_there_every_time_it_is_rendered(self):
        """#379 said the elevation-profile render was intermittently empty in CI. Rendering the same layout five times must give a curve each
        time, with ink counts that agree to within a third of each other; a flaky render fails here with the five numbers."""
        ids = self._build()
        rect = self.layout.itemById(ids["profile"]).sceneBoundingRect()
        counts = []
        for n in range(5):
            image = QgsLayoutExporter(self.layout).renderRegionToImage(rect, QSize(int(rect.width() * PX_PER_MM), int(rect.height() * PX_PER_MM)))
            _keep(f"profile_render_{n + 1}", image)
            counts.append(sum(1 for x in range(0, image.width(), 2) for y in range(0, image.height(), 2) if is_data_ink(QColor(image.pixel(x, y)).red(), QColor(image.pixel(x, y)).green(), QColor(image.pixel(x, y)).blue())) * 4)
        print(f"LAYOUTRENDER profile five renders: {counts}")
        self.assertTrue(all(c >= 100 for c in counts), counts)
        self.assertLessEqual(max(counts) - min(counts), max(counts) / 3, counts)


if __name__ == "__main__":
    unittest.main()
