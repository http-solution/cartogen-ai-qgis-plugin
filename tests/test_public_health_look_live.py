"""Live run of apply_public_health_look (PLAN-023 R2-5): every renderer setting is read back from real QGIS layers. Known answers: the rate look on figures 1 to 100 with 5 classes breaks at 1, 20.8, 40.6, 60.4, 80.2, 100
in the Blues ramp with a grey hatch rule for suppressed (empty) figures, labelled 'Suppressed (n < 5)'; the cluster look is a black 1.2 mm line under a white 0.5 mm line with no fill and no red; the lisa and hotspot looks
colour exactly the class tables of the pure module. Written without a QGIS install: CI's first run is its first execution."""
import unittest

try:
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    LIVE = True
except ImportError:
    LIVE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()


def _layer(name, rows, fields="field=value_shown:double&field=lisa_class:string&field=gi_class:string"):
    layer = QgsVectorLayer(f"Polygon?crs=EPSG:3857&{fields}", name, "memory")
    feats = []
    for i, row in enumerate(rows):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromWkt(f"POLYGON(({i} 0,{i + 1} 0,{i + 1} 1,{i} 1,{i} 0))"))
        f.setAttributes(list(row))
        feats.append(f)
    layer.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayer(layer)
    return layer


@unittest.skipUnless(LIVE, "requires real QGIS")
class TestPublicHealthLook(unittest.TestCase):
    def setUp(self):
        _boot()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)

    def _run(self, *args, **kwargs):
        from cartogen_ai.core.agent.tools.public_health_look_tool import apply_public_health_look
        return apply_public_health_look(*args, **kwargs)

    def test_rate_look_has_five_blue_rules_a_hatch_rule_and_the_legend_sentence(self):
        from cartogen_ai.core.representation import epi_look
        rows = [(float(v), None, None) for v in range(1, 101)] + [(None, None, None)] * 3
        layer = _layer("rates", rows)
        result = self._run("rates", "rate")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result["legend_title"], "Rate per 100,000; suppressed where n < 5")
        self.assertEqual(layer.customProperty("cartogen/legend_title"), "Rate per 100,000; suppressed where n < 5")
        self.assertEqual(result["suppressed"], 3)
        self.assertEqual(result["shown"], 100)
        renderer = layer.renderer()
        self.assertEqual(renderer.type(), "RuleRenderer")      # QGIS names the rule-based renderer "RuleRenderer" (CI run 43091162738)
        rules = renderer.rootRule().children()
        self.assertEqual(len(rules), 6)
        plan = epi_look.rate_classes(range(1, 101))["classes"]
        for rule, c in zip(rules[:5], plan, strict=True):
            self.assertEqual(rule.symbol().color().name().upper(), c["colour"].upper())
            self.assertEqual(rule.label(), c["label"])
        self.assertEqual(rules[5].label(), "Suppressed (n < 5)")
        self.assertIn("IS NULL", rules[5].filterExpression())
        hatch = rules[5].symbol().symbolLayer(0)
        self.assertEqual(hatch.color().name().upper(), epi_look.SUPPRESSED_COLOUR.upper())
        self.assertNotEqual(str(hatch.brushStyle()), "NoBrush")

    def test_the_rate_rules_put_every_feature_in_exactly_one_rule(self):
        rows = [(float(v), None, None) for v in (2, 5, 9, 14, 20, 33, 47, 60, 75, 91, 100)] + [(None, None, None)] * 2
        layer = _layer("rates", rows)
        self.assertTrue(self._run("rates", "rate").get("success"))
        from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
        rules = layer.renderer().rootRule().children()
        for f in layer.getFeatures():
            context = QgsExpressionContext()
            context.appendScope(QgsExpressionContextUtils.layerScope(layer))
            context.setFeature(f)
            hits = [r for r in rules if QgsExpression(r.filterExpression()).evaluate(context)]
            self.assertEqual(len(hits), 1, f.attributes())

    def test_repeated_figures_drop_classes_and_say_so(self):
        _layer("rates", [(1.0, None, None)] * 4 + [(5.0, None, None)])
        result = self._run("rates", "rate")
        self.assertTrue(result.get("success"), result)
        self.assertEqual(len(result["classes"]), 2)
        self.assertEqual(result["classes_dropped"], 3)

    def test_a_custom_field_and_class_count(self):
        layer = _layer("rates", [(float(v), None, None) for v in range(1, 41)], fields="field=my_rate:double&field=lisa_class:string&field=gi_class:string")
        result = self._run("rates", "rate", field="my_rate", classes=3)
        self.assertTrue(result.get("success"), result)
        self.assertEqual(len(layer.renderer().rootRule().children()), 4)

    def test_cluster_look_is_a_black_line_under_a_white_line_with_no_fill_and_no_red(self):
        layer = _layer("circles", [(None, None, None)])
        result = self._run("circles", "cluster")
        self.assertTrue(result.get("success"), result)
        symbol = layer.renderer().symbol()
        self.assertEqual(symbol.symbolLayerCount(), 2)
        black, white = symbol.symbolLayer(0), symbol.symbolLayer(1)
        self.assertEqual(black.strokeColor().name().upper(), "#000000")
        self.assertEqual(white.strokeColor().name().upper(), "#FFFFFF")
        self.assertAlmostEqual(black.strokeWidth(), 1.2)
        self.assertAlmostEqual(white.strokeWidth(), 0.5)
        for part in (black, white):
            self.assertEqual(str(part.brushStyle()).split(".")[-1], "NoBrush")
        from cartogen_ai.core.representation import colour_rules
        self.assertFalse(any(colour_rules.is_red(c.strokeColor().name()) for c in (black, white)))

    def test_lisa_and_hotspot_looks_colour_exactly_the_class_tables(self):
        from cartogen_ai.core.representation import epi_look
        rows = [(None, c, None) for c in ("HH", "LL", "HL", "LH", "not significant", "no neighbours")]
        lisa = _layer("lisa", rows)
        result = self._run("lisa", "lisa")
        self.assertTrue(result.get("success"), result)
        cats = {c.value(): c.symbol().color().name().upper() for c in lisa.renderer().categories()}
        for value, colour, _label in epi_look.LISA_CLASSES:
            self.assertEqual(cats[value], colour.upper(), value)
        hot = _layer("hot", [(None, None, c) for c in ("Hot spot 99%", "Cold spot 95%", "Not significant")])
        self.assertTrue(self._run("hot", "hotspot").get("success"))
        cats = {c.value(): c.symbol().color().name().upper() for c in hot.renderer().categories()}
        self.assertEqual(cats["Hot spot 99%"], "#B35806")
        self.assertEqual(cats["Cold spot 95%"], "#998EC3")

    def test_values_that_are_not_a_class_are_named_and_a_layer_with_none_is_refused(self):
        _layer("mixed", [(None, "HH", None), (None, "weird", None)])
        result = self._run("mixed", "lisa")
        self.assertEqual(result["values_not_in_the_look"], ["weird"])
        _layer("none", [(None, "x", None)])
        self.assertIn("nothing was restyled", self._run("none", "lisa")["error"])

    def test_refusals_name_the_cause(self):
        _layer("rates", [(1.0, "HH", None), (2.0, "HH", None)])
        self.assertIn("not found", self._run("nope", "rate")["error"])
        self.assertIn("Unknown look", self._run("rates", "pie")["error"])
        self.assertIn("Field 'zzz' not found", self._run("rates", "rate", field="zzz")["error"])
        self.assertIn("not numeric", self._run("rates", "rate", field="lisa_class")["error"])
        self.assertIn("min_cases", self._run("rates", "rate", min_cases=-1)["error"])
        self.assertIn("per", self._run("rates", "rate", per=0)["error"])
        self.assertIn("2 to 5", self._run("rates", "rate", classes=9)["error"])


if __name__ == "__main__":
    unittest.main()
