# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.ui.canvas_highlight import find_mentioned_layers, zoom_to_layers


class _FakeLayer:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class TestFindMentionedLayers(unittest.TestCase):
    def test_matches_layer_name_in_text(self):
        layers = [_FakeLayer("Jordan_Governorates"), _FakeLayer("Flood_Zones")]
        matched = find_mentioned_layers("I've buffered the Jordan_Governorates layer by 500m.", layers)
        self.assertEqual([l.name() for l in matched], ["Jordan_Governorates"])

    def test_case_insensitive_match(self):
        layers = [_FakeLayer("Roads")]
        matched = find_mentioned_layers("The roads layer now has a new field.", layers)
        self.assertEqual(len(matched), 1)

    def test_no_match_returns_empty(self):
        layers = [_FakeLayer("Jordan_Governorates")]
        matched = find_mentioned_layers("Here is a general summary with no layer names.", layers)
        self.assertEqual(matched, [])

    def test_short_names_ignored_to_avoid_false_positives(self):
        # A 2-character layer name shouldn't match generic prose.
        layers = [_FakeLayer("ID")]
        matched = find_mentioned_layers("This identifies each feature.", layers)
        self.assertEqual(matched, [])

    def test_respects_max_matches(self):
        layers = [_FakeLayer("Alpha_Layer"), _FakeLayer("Beta_Layer"), _FakeLayer("Gamma_Layer")]
        text = "Alpha_Layer, Beta_Layer, and Gamma_Layer were all processed."
        matched = find_mentioned_layers(text, layers, max_matches=2)
        self.assertEqual(len(matched), 2)

    def test_longer_names_preferred_over_substrings(self):
        layers = [_FakeLayer("Zone"), _FakeLayer("Flood_Zone")]
        matched = find_mentioned_layers("The Flood_Zone layer was updated.", layers, max_matches=1)
        self.assertEqual(matched[0].name(), "Flood_Zone")


def _make_layer(extent_empty=False, extent_null=False):
    layer = MagicMock()
    extent = MagicMock()
    extent.isNull.return_value = extent_null
    extent.isEmpty.return_value = extent_empty
    layer.extent.return_value = extent
    layer.crs.return_value = MagicMock()
    return layer


class TestZoomToLayers(unittest.TestCase):
    """Real user report: after the agent creates/modifies layers, the
    canvas kept whatever extent it already had, so the result was never
    actually visible without the user manually zooming. zoom_to_layers
    moves the canvas view (distinct from flash_layer_extent, which only
    highlights without moving it)."""

    def test_degrades_gracefully_outside_qgis(self):
        # QGIS_AVAILABLE is False in this sandbox by default (no qgis
        # package importable) -- confirms the real degrade path, not a
        # patched one.
        self.assertFalse(zoom_to_layers(MagicMock(), [_make_layer()]))

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    def test_no_layers_returns_false(self):
        self.assertFalse(zoom_to_layers(MagicMock(), []))

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    def test_none_iface_returns_false(self):
        self.assertFalse(zoom_to_layers(None, [_make_layer()]))

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.ui.canvas_highlight.QgsRectangle", create=True)
    def test_single_layer_sets_extent_and_refreshes(self, mock_rect_cls):
        iface = MagicMock()
        canvas = iface.mapCanvas.return_value
        layer = _make_layer()
        # Same CRS as canvas -- _extent_to_canvas_crs returns the extent
        # unchanged, no QgsCoordinateTransform needed.
        canvas.mapSettings.return_value.destinationCrs.return_value = layer.crs.return_value
        layer.crs.return_value.isValid.return_value = True

        result = zoom_to_layers(iface, [layer])

        self.assertTrue(result)
        canvas.setExtent.assert_called_once()
        canvas.refresh.assert_called_once()

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.ui.canvas_highlight.QgsRectangle", create=True)
    def test_multiple_layers_combine_into_one_extent(self, mock_rect_cls):
        iface = MagicMock()
        canvas = iface.mapCanvas.return_value
        layer_a = _make_layer()
        layer_b = _make_layer()
        for layer in (layer_a, layer_b):
            canvas.mapSettings.return_value.destinationCrs.return_value = layer.crs.return_value
            layer.crs.return_value.isValid.return_value = True

        combined_instance = mock_rect_cls.return_value

        result = zoom_to_layers(iface, [layer_a, layer_b])

        self.assertTrue(result)
        # First layer seeds the combined rectangle; the second is merged in
        # via combineExtentWith, not a second setExtent() call.
        combined_instance.combineExtentWith.assert_called_once()
        canvas.setExtent.assert_called_once_with(combined_instance)
        canvas.refresh.assert_called_once()

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    def test_null_extent_layers_are_skipped(self):
        iface = MagicMock()
        canvas = iface.mapCanvas.return_value
        null_layer = _make_layer(extent_null=True)

        result = zoom_to_layers(iface, [null_layer])

        self.assertFalse(result)
        canvas.setExtent.assert_not_called()

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.ui.canvas_highlight.QgsRectangle", create=True)
    def test_empty_but_not_null_extent_is_NOT_skipped(self, mock_rect_cls):
        # Live-found bug: a single-point layer's extent() is a real,
        # non-null extent with isNull()=False but isEmpty()=True (zero
        # width/height -- a point has no area). An earlier version of
        # zoom_to_layers also skipped on isEmpty(), which silently dropped
        # every single-point layer -- one of the most common layer types
        # this plugin creates. Confirmed live against real QGIS 4.2.2
        # before this test was written.
        iface = MagicMock()
        canvas = iface.mapCanvas.return_value
        single_point_layer = _make_layer(extent_empty=True, extent_null=False)
        canvas.mapSettings.return_value.destinationCrs.return_value = single_point_layer.crs.return_value
        single_point_layer.crs.return_value.isValid.return_value = True

        result = zoom_to_layers(iface, [single_point_layer])

        self.assertTrue(result)
        canvas.setExtent.assert_called_once()

    @patch("cartogen_ai.core.ui.canvas_highlight.QGIS_AVAILABLE", True)
    def test_exception_returns_false_not_raises(self):
        iface = MagicMock()
        iface.mapCanvas.side_effect = RuntimeError("boom")
        result = zoom_to_layers(iface, [_make_layer()])
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
