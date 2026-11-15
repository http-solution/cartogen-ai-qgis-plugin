"""PLAN-058 (DEF-24, issue 362, row V4): the 2026-11-04 live run (and the 2026-11-03 one) asked 'animate the layer over time' after the layer was made temporal,
and the model gave a how-to instead of calling export_temporal_animation_frames. The router and find_tools both offer the tool; what the plugin can fix is the tool
itself: start_field was required even though set_layer_temporal had already recorded it, and the description promised only 'start/end period' layers, which does not
read as a fit for an events layer with one date column. Offline; no QGIS."""
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import cartogen_ai.core.agent.tools.export_tools as et
from cartogen_ai.core.agent.tools import TOOLS_SCHEMA


def _field(name, type_name):
    f = MagicMock()
    f.name.return_value = name
    f.typeName.return_value = type_name
    return f


def _layer(fields, temporal=None):
    layer = MagicMock()
    layer.fields.return_value = fields
    props = MagicMock()
    start, end = temporal if temporal else ("", "")
    props.isActive.return_value = bool(temporal)
    props.startField.return_value = start
    props.endField.return_value = end
    layer.temporalProperties.return_value = props
    return layer


EVENTS = [_field("id", "Integer"), _field("date", "Date"), _field("lon", "Real")]


class TestResolveFields(unittest.TestCase):
    def test_explicit_fields_are_kept_untouched(self):
        self.assertEqual(et._resolve_animation_fields(_layer(EVENTS), "date", "end"), ("date", "end", None))

    def test_a_missing_start_field_comes_from_the_layers_temporal_settings(self):
        self.assertEqual(et._resolve_animation_fields(_layer(EVENTS, ("date", "")), None, None), ("date", None, None))

    def test_a_start_and_end_pair_from_the_settings_is_used_whole(self):
        fields = [_field("from", "Date"), _field("to", "Date")]
        self.assertEqual(et._resolve_animation_fields(_layer(fields, ("from", "to")), None, None), ("from", "to", None))

    def test_an_explicit_end_field_wins_over_the_settings(self):
        fields = [_field("from", "Date"), _field("to", "Date"), _field("until", "Date")]
        self.assertEqual(et._resolve_animation_fields(_layer(fields, ("from", "to")), None, "until"), ("from", "until", None))

    def test_a_layer_that_is_not_temporal_gets_an_error_naming_its_date_fields(self):
        start, _end, error = et._resolve_animation_fields(_layer(EVENTS), None, None)
        self.assertIsNone(start)
        self.assertIn("'date'", error)
        self.assertIn("set_layer_temporal", error)
        self.assertNotIn("'lon'", error)

    def test_a_layer_with_no_date_field_says_so_and_lists_what_it_has(self):
        _s, _e, error = et._resolve_animation_fields(_layer([_field("id", "Integer"), _field("name", "String")]), None, None)
        self.assertIn("no date or date-time field", error)
        self.assertIn("id", error)

    def test_a_layer_without_temporal_properties_does_not_crash(self):
        layer = _layer(EVENTS)
        layer.temporalProperties.side_effect = RuntimeError("not a vector layer")
        self.assertIsNone(et._resolve_animation_fields(layer, None, None)[0])


class TestTheToolUsesIt(unittest.TestCase):
    def _run(self, layer, **kwargs):
        feature = MagicMock()
        feature.__getitem__ = lambda self, key: "2026-01-05"
        layer.getFeatures.return_value = [feature]
        layer.subsetString.return_value = ""
        with patch.object(et, "QGIS_AVAILABLE", True), patch.object(et, "iface", MagicMock()), patch.object(et, "_find_layer_by_name", return_value=layer):
            return et.export_temporal_animation_frames("smoke_events", output_dir=tempfile.mkdtemp(), **kwargs)

    def test_the_animation_runs_without_a_start_field_when_the_layer_is_temporal(self):
        """The V4 flow: step 1 made smoke_events temporal on 'date'; step 2 says 'animate the layer over time'."""
        res = self._run(_layer(EVENTS, ("date", "")))
        self.assertTrue(res.get("success"), res)

    def test_without_a_start_field_on_a_plain_layer_the_error_is_actionable(self):
        res = self._run(_layer(EVENTS))
        self.assertIn("error", res)
        self.assertIn("'date'", res["error"])

    def test_an_explicit_start_field_still_works_as_before(self):
        self.assertTrue(self._run(_layer(EVENTS), start_field="date").get("success"))


class TestTheSchemaAndDescription(unittest.TestCase):
    def setUp(self):
        self.tool = next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "export_temporal_animation_frames")

    def test_only_the_layer_is_required(self):
        self.assertEqual(self.tool["parameters"]["required"], ["layer_name"])

    def test_the_description_says_an_events_layer_with_one_date_field_fits_and_that_temporal_settings_are_used(self):
        text = self.tool["description"]
        self.assertIn("single date field", text)
        self.assertIn("set_layer_temporal", text)
        self.assertIn("start_field", text)


if __name__ == "__main__":
    unittest.main()
