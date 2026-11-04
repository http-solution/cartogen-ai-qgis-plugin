"""PLAN-058 (DEF-25, row A1): in the 2026-11-04 live run every exported page of the layout script had a Legend box with only its heading, while the check
table said 7 layers were listed. _style_legend puts every layer in the legend when none lies on the map ("never an empty legend"), and then switched on
QGIS's filter-by-map-content for the same legend: at render QGIS drops the layers the map does not show, which is all of them. Offline (mocks); the rendered
result is checked in tests/test_legend_when_map_shows_nothing_live.py (CI live job)."""
import unittest
from unittest.mock import MagicMock, patch

from cartogen_ai.core.agent.tools import layout_style as ls


def _run(template, on_map, ids=("a", "b"), crs_valid=True):
    leg, map_item = MagicMock(name="legend"), MagicMock(name="map")
    map_item.crs.return_value.isValid.return_value = crs_valid
    layout = MagicMock()
    layout.itemById.side_effect = {"LEGEND": leg, "MAP_MAIN": map_item}.get
    by_id = {i: MagicMock(name=i) for i in ids}
    chosen = {"ids": list(ids)}
    with patch.object(ls, "legend_layers_on_map", return_value=[(i, by_id[i]) for i in on_map]), patch.object(ls, "_panel"):
        ls._style_legend(layout, "mm", list(ids), by_id, template, chosen)
    return leg, chosen


class TestLegendFilterFollowsWhatTheLegendHolds(unittest.TestCase):
    def test_when_no_layer_is_on_the_map_the_legend_lists_them_all_and_is_not_filtered_away(self):
        leg, chosen = _run("standard", on_map=[])
        self.assertEqual(chosen["ids"], ["a", "b"])
        leg.setLegendFilterByMapEnabled.assert_called_once_with(False)
        self.assertTrue(chosen["map_shows_none"])

    def test_when_some_layers_are_on_the_map_the_filter_stays_on(self):
        leg, chosen = _run("standard", on_map=["a"])
        self.assertEqual(chosen["ids"], ["a"])
        leg.setLegendFilterByMapEnabled.assert_called_once_with(True)
        self.assertFalse(chosen["map_shows_none"])

    def test_the_access_map_template_is_never_filtered(self):
        leg, chosen = _run("access_map", on_map=[])
        leg.setLegendFilterByMapEnabled.assert_called_once_with(False)
        self.assertFalse(chosen["map_shows_none"])           # nothing was tested for that template, so nothing is claimed

    def test_a_layout_with_no_layers_at_all_claims_nothing(self):
        _leg, chosen = _run("standard", on_map=[], ids=())
        self.assertFalse(chosen["map_shows_none"])


class TestAnUnknownMapCrs(unittest.TestCase):
    """The live run's pages read 'CRS unknown': a project cleared by a script has no coordinate system. QGIS's filter-by-map cannot transform a layer's extent into
    an unknown CRS, so the legend filter is the step that can drop everything; the plugin's own extent test keeps layers it cannot test."""

    def test_the_filter_is_off_when_the_map_has_no_crs_even_if_layers_are_on_the_map(self):
        leg, chosen = _run("standard", on_map=["a", "b"], crs_valid=False)
        self.assertEqual(chosen["ids"], ["a", "b"])
        leg.setLegendFilterByMapEnabled.assert_called_once_with(False)
        self.assertTrue(chosen["map_crs_unknown"])
        self.assertFalse(chosen["map_shows_none"])

    def test_a_valid_crs_keeps_the_filter_on(self):
        leg, chosen = _run("standard", on_map=["a"], crs_valid=True)
        leg.setLegendFilterByMapEnabled.assert_called_once_with(True)
        self.assertFalse(chosen["map_crs_unknown"])

    def test_the_warning_says_how_to_set_the_crs(self):
        text = ls.map_crs_unknown_warning()
        self.assertIn("coordinate system", text)
        self.assertIn("Project Properties", text)


class TestTheReplyWarnsWhenTheMapShowsNoneOfTheLayers(unittest.TestCase):
    def test_the_warning_names_the_cause_and_the_remedy(self):
        text = ls.map_shows_none_warning()
        self.assertIn("none of the layers", text)
        self.assertIn("Zoom", text)


class TestWhichWarningsAreRaised(unittest.TestCase):
    """CI live run (2026-11-04): two existing live tests build a layout with no map view at all (no canvas), where no map is ever framed on anything, so 'the
    view is not on the data' says nothing; only the no-CRS warning applies there."""

    def test_both_are_raised_when_there_is_a_map_view(self):
        out = ls.view_warnings({"map_shows_none": True, "map_crs_unknown": True}, view_known=True)
        self.assertEqual(out, [ls.map_shows_none_warning(), ls.map_crs_unknown_warning()])

    def test_the_view_warning_is_dropped_when_there_is_no_map_view(self):
        out = ls.view_warnings({"map_shows_none": True, "map_crs_unknown": True}, view_known=False)
        self.assertEqual(out, [ls.map_crs_unknown_warning()])

    def test_nothing_is_raised_when_nothing_is_wrong(self):
        self.assertEqual(ls.view_warnings({"map_shows_none": False, "map_crs_unknown": False}), [])
        self.assertEqual(ls.view_warnings({}), [])


if __name__ == "__main__":
    unittest.main()
