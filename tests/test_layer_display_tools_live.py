"""PLAN-023 R10-2 on real QGIS layers: conditional-formatting rules are read back (expression and colour) for a field and for rows and can be cleared; a map tip is read back and a
script tag, an event handler and a denied expression are refused; a command layer action is refused with the policy while an open_url action is added with its address. Written without
a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestLayerDisplayLive(unittest.TestCase):
    def setUp(self):
        from tests.test_network_units_live import _boot
        why = _boot()
        if why:
            self.skipTest(why)
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        self.layer = QgsVectorLayer("Point?crs=EPSG:32636&field=name:string&field=pop:integer", "pts", "memory")
        f = QgsFeature(self.layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        f.setAttributes(["a", 150])
        self.layer.dataProvider().addFeatures([f])
        QgsProject.instance().addMapLayer(self.layer)

    def test_conditional_formatting_for_a_field_is_read_back_and_can_be_cleared(self):
        from cartogen_ai.core.agent.tools.layer_display_tools import set_conditional_formatting
        out = set_conditional_formatting("pts", rules=[{"condition": "@value > 100", "background_color": "#ffcccc", "text_color": "red", "name": "big"}], field="pop")
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["rules_before"], out["rules_now"]), (0, 1))
        style = self.layer.conditionalStyles().fieldStyles("pop")[0]
        self.assertEqual(style.rule(), "@value > 100")
        self.assertEqual(style.backgroundColor().name(), "#ffcccc")
        self.assertEqual(style.name(), "big")
        cleared = set_conditional_formatting("pts", field="pop", clear=True)
        self.assertEqual(cleared["rules_now"], 0)

    def test_row_rules_and_refusals(self):
        from cartogen_ai.core.agent.tools.layer_display_tools import set_conditional_formatting
        out = set_conditional_formatting("pts", rules=[{"condition": '"pop" is null', "text_color": "#888888"}])
        self.assertEqual(out["rules_now"], 1)
        self.assertEqual(len(self.layer.conditionalStyles().rowStyles()), 1)
        self.assertIn("error", set_conditional_formatting("pts", rules=[{"condition": "eval('1')", "text_color": "red"}], field="pop"))
        self.assertIn("error", set_conditional_formatting("pts", rules=[{"condition": "1", "text_color": "notacolour"}], field="pop"))
        self.assertIn("not found", set_conditional_formatting("pts", rules=[{"condition": "1", "text_color": "red"}], field="zzz")["error"])
        self.assertIn("error", set_conditional_formatting("pts"))

    def test_a_map_tip_is_read_back_and_unsafe_ones_are_refused(self):
        from cartogen_ai.core.agent.tools.layer_display_tools import set_map_tip
        template = '<b>[% "name" %]</b><br>Population [% "pop" * 2 %]'
        out = set_map_tip("pts", template)
        self.assertTrue(out.get("success"), out)
        self.assertEqual((out["map_tip_now"], out["expressions"]), (template, 2))
        self.assertEqual(self.layer.mapTipTemplate(), template)
        self.assertIn("error", set_map_tip("pts", "<script>alert(1)</script>"))
        self.assertIn("error", set_map_tip("pts", '<img src=x onerror="a()">'))
        self.assertIn("error", set_map_tip("pts", "[% eval('1') %]"))
        self.assertEqual(self.layer.mapTipTemplate(), template)                      # refusals changed nothing
        removed = set_map_tip("pts", "")
        self.assertTrue(removed["had_a_map_tip_before"])
        self.assertEqual(self.layer.mapTipTemplate(), "")

    def test_a_command_action_is_refused_and_an_open_url_action_is_added(self):
        from cartogen_ai.core.agent.tools.layer_display_tools import add_feature_action
        for kind in ("python", "shell", "windows"):
            refused = add_feature_action("pts", "Run", kind, url="notepad.exe")
            self.assertIn("policy", refused["error"])
        self.assertEqual(len(self.layer.actions().actions()), 0)
        url = 'https://en.wikipedia.org/wiki/[% "name" %]'
        out = add_feature_action("pts", "Wikipedia", "open_url", url=url)
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["actions_now"], ["Wikipedia"])
        self.assertEqual(self.layer.actions().actions()[0].command(), url)
        self.assertIn("error", add_feature_action("pts", "Bad", "open_url", url="file:///etc/passwd"))
        self.assertIn("error", add_feature_action("pts", "Bad", "open_url", url='https://x/[% eval(1) %]'))
        self.assertEqual(len(self.layer.actions().actions()), 1)


if __name__ == "__main__":
    unittest.main()
