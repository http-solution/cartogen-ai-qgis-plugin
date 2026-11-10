"""PLAN-023 R10-5 in real QGIS: the datum operations between two CRSs are listed and one chosen from the list is read back from the project's transform context (an id that is not on the list is
refused); a PROJ string is validated and an invalid one refused, and a custom CRS can become the project CRS; the project ellipsoid and units read back; a decoration's switch, placement and
text read back from the project properties. Decorations are not seen on a canvas. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsCoordinateReferenceSystem, QgsProject
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestProjectSettingsLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def test_the_operations_are_listed_and_a_chosen_one_is_read_back(self):
        from cartogen_ai.core.agent.tools.project_settings_tools import set_project_transform_context
        listing = set_project_transform_context("EPSG:4267", "EPSG:4326")                       # NAD27 to WGS 84 has several operations
        self.assertTrue(listing.get("success"), listing)
        usable = [o for o in listing["operations"] if o["available"]]
        if not usable:
            self.skipTest("no usable datum operation listed for NAD27 to WGS 84 in this image")
        chosen = usable[0]["id"]
        card = set_project_transform_context("EPSG:4267", "EPSG:4326", operation_id=chosen)
        self.assertEqual(card["status"], "PREVIEW_REQUIRED")
        self.assertFalse(QgsProject.instance().transformContext().coordinateOperations())       # the preview changed nothing
        out = set_project_transform_context(confirmed=True, **{k: v for k, v in card["arguments"].items() if k != "confirmed"})
        self.assertTrue(out.get("success"), out)
        source, dest = QgsCoordinateReferenceSystem("EPSG:4267"), QgsCoordinateReferenceSystem("EPSG:4326")
        self.assertTrue(QgsProject.instance().transformContext().coordinateOperations().get((source.authid(), dest.authid())))
        again = set_project_transform_context("EPSG:4267", "EPSG:4326")
        self.assertTrue(any(o["in_use"] for o in again["operations"]))

    def test_an_operation_that_is_not_listed_and_bad_requests_are_refused(self):
        from cartogen_ai.core.agent.tools.project_settings_tools import set_project_transform_context
        self.assertIn("not one of the operations", set_project_transform_context("EPSG:4267", "EPSG:4326", operation_id="+proj=pipeline +step +proj=noop")["error"])
        self.assertIn("same", set_project_transform_context("EPSG:4326", "EPSG:4326")["error"])
        self.assertIn("not a coordinate system", set_project_transform_context("EPSG:4326", "EPSG:notacode")["error"])

    def test_a_proj_string_is_validated_and_can_become_the_project_crs(self):
        from cartogen_ai.core.agent.tools.project_settings_tools import define_custom_crs
        out = define_custom_crs("Local TM", "+proj=tmerc +lat_0=0 +lon_0=35 +k=0.9996 +x_0=500000 +y_0=0 +datum=WGS84 +units=m +no_defs")
        self.assertTrue(out.get("valid"), out)
        self.assertFalse(out["geographic"])
        self.assertEqual(out["units"], "Meters")
        self.assertFalse(out["used_as_project_crs"])
        self.assertIn("error", define_custom_crs("Bad", "+proj=thisisnotaprojection +zone=1"))
        self.assertIn("error", define_custom_crs("Bad", "EPSG:4326"))
        used = define_custom_crs("Local TM", "+proj=tmerc +lat_0=0 +lon_0=35 +k=0.9996 +x_0=500000 +y_0=0 +datum=WGS84 +units=m +no_defs", use_as_project_crs=True)
        self.assertTrue(used["used_as_project_crs"])
        self.assertTrue(QgsProject.instance().crs().isValid())
        self.assertFalse(QgsProject.instance().crs().isGeographic())

    def test_ellipsoid_and_units_read_back(self):
        from cartogen_ai.core.agent.tools.project_settings_tools import set_project_measurement
        out = set_project_measurement(ellipsoid="WGS84", distance_units="kilometers", area_units="hectares")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["now"]["distance_units"], "Kilometers")
        self.assertEqual(out["now"]["area_units"], "Hectares")
        self.assertEqual(QgsProject.instance().distanceUnits().name, "Kilometers")
        self.assertEqual(QgsProject.instance().areaUnits().name, "Hectares")
        self.assertIn("WGS84", out["now"]["ellipsoid"].upper())
        self.assertIn("not an ellipsoid", set_project_measurement(ellipsoid="NOTANELLIPSOID")["error"])
        self.assertIn("error", set_project_measurement(distance_units="furlongs"))
        self.assertIn("error", set_project_measurement())

    def test_a_decoration_setting_reads_back_from_the_project(self):
        from cartogen_ai.core.agent.tools.project_settings_tools import set_canvas_decoration
        out = set_canvas_decoration("title", enabled=True, placement="top_center", text="Flood response")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["now"], {"enabled": True, "placement": 4, "text": "Flood response"})
        project = QgsProject.instance()
        self.assertTrue(project.readBoolEntry("TitleLabel", "/Enabled", False)[0])
        self.assertEqual(project.readEntry("TitleLabel", "/Label", "")[0], "Flood response")
        arrow = set_canvas_decoration("north_arrow", enabled=True, placement="top_right")
        self.assertEqual(arrow["now"], {"enabled": True, "placement": 2})
        self.assertIn("error", set_canvas_decoration("legend", enabled=True))
        self.assertIn("error", set_canvas_decoration("grid", enabled=True, text="x"))


if __name__ == "__main__":
    unittest.main()
