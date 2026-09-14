# -*- coding: utf-8 -*-
"""Tests for the 2026-09-04 dual controlled-vocabulary incident-coding
addition to agent/tools/humanitarian_tools.py (ACLED-style event_type/
sub_event_type + IMSMA/IMAS-style hazard_type/contamination_status), layered
on top of the pre-existing freeform severity/category fields per Baron's
decision to support both vocabularies rather than pick one. Follows the
QGIS_AVAILABLE=False degrade-path convention used throughout the suite;
QGIS-touching paths are exercised with MagicMock layers, same technique as
tests/test_logistics_tools.py."""
import unittest
from unittest.mock import patch, MagicMock
from cartogen_ai.core.agent.tools.humanitarian_tools import (
    _validate_incident_coding, _validate_incident_temporal, ACLED_EVENT_TAXONOMY, IMSMA_HAZARD_TYPES,
    IMSMA_CONTAMINATION_STATUSES, add_incident_point, add_point_layer,
)


class TestValidateIncidentCodingPureLogic(unittest.TestCase):
    """No QGIS needed -- pure validation logic."""

    def test_no_values_given_returns_no_warnings(self):
        self.assertEqual(_validate_incident_coding(), [])

    def test_valid_event_type_alone_is_clean(self):
        self.assertEqual(_validate_incident_coding(event_type="Battles"), [])

    def test_valid_event_and_sub_event_pair_is_clean(self):
        self.assertEqual(
            _validate_incident_coding(event_type="Battles", sub_event_type="Armed clash"), []
        )

    def test_unknown_event_type_warns(self):
        warnings = _validate_incident_coding(event_type="Frobnication")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Frobnication", warnings[0])
        self.assertIn("ACLED", warnings[0])

    def test_sub_event_type_not_valid_for_given_event_type_warns(self):
        # "Sexual violence" is a real ACLED sub-event, but only under
        # "Violence against civilians", not "Battles".
        warnings = _validate_incident_coding(event_type="Battles", sub_event_type="Sexual violence")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Sexual violence", warnings[0])
        self.assertIn("Battles", warnings[0])

    def test_valid_hazard_type_alone_is_clean(self):
        self.assertEqual(_validate_incident_coding(hazard_type="Improvised Explosive Device (IED)"), [])

    def test_unknown_hazard_type_warns(self):
        warnings = _validate_incident_coding(hazard_type="Sea Mine")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Sea Mine", warnings[0])
        self.assertIn("IMSMA", warnings[0])

    def test_unknown_contamination_status_warns(self):
        warnings = _validate_incident_coding(contamination_status="Definitely Fine")
        self.assertEqual(len(warnings), 1)
        self.assertIn("Definitely Fine", warnings[0])

    def test_can_combine_acled_and_imsma_fields_independently(self):
        # Both vocabularies at once -- one invalid on each side -- both flagged.
        warnings = _validate_incident_coding(
            event_type="NotReal", hazard_type="NotReal",
        )
        self.assertEqual(len(warnings), 2)

    def test_every_taxonomy_event_and_sub_event_pair_validates_clean(self):
        for event_type, sub_events in ACLED_EVENT_TAXONOMY.items():
            for sub_event_type in sub_events:
                self.assertEqual(
                    _validate_incident_coding(event_type=event_type, sub_event_type=sub_event_type), [],
                )

    def test_every_imsma_hazard_type_and_status_validates_clean(self):
        for hazard_type in IMSMA_HAZARD_TYPES:
            for status in IMSMA_CONTAMINATION_STATUSES:
                self.assertEqual(
                    _validate_incident_coding(hazard_type=hazard_type, contamination_status=status), [],
                )


class TestValidateIncidentTemporalPureLogic(unittest.TestCase):
    """Point 7 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md -- optional
    event_start/event_end/last_verified fields, additive alongside the pre-existing
    freeform `date`. No QGIS needed -- pure validation logic, same shape as
    _validate_incident_coding above."""

    def test_no_values_given_returns_no_warnings(self):
        self.assertEqual(_validate_incident_temporal(), [])

    def test_only_start_given_returns_no_warnings(self):
        self.assertEqual(_validate_incident_temporal(event_start="2026-03-14"), [])

    def test_only_end_given_returns_no_warnings(self):
        self.assertEqual(_validate_incident_temporal(event_end="2026-03-14"), [])

    def test_start_before_end_is_clean(self):
        self.assertEqual(_validate_incident_temporal("2026-03-10", "2026-03-14"), [])

    def test_start_equals_end_is_clean(self):
        # A single-day event given as both start and end is not an inversion.
        self.assertEqual(_validate_incident_temporal("2026-03-14", "2026-03-14"), [])

    def test_end_before_start_warns(self):
        warnings = _validate_incident_temporal("2026-03-14", "2026-03-10")
        self.assertEqual(len(warnings), 1)
        self.assertIn("2026-03-14", warnings[0])
        self.assertIn("2026-03-10", warnings[0])
        self.assertIn("before", warnings[0])

    def test_unparsable_dates_are_silently_skipped_not_flagged(self):
        # Freeform source dates that don't parse as ISO 8601 can't be ordered
        # -- must not raise, and must not be a false-positive warning either.
        self.assertEqual(_validate_incident_temporal("sometime in March", "later"), [])
        self.assertEqual(_validate_incident_temporal("March 14, 2026", "March 10, 2026"), [])

    def test_datetime_style_values_still_compare_on_the_date_portion(self):
        # A source giving full ISO datetimes, not just dates -- only the
        # first 10 chars (YYYY-MM-DD) are parsed.
        warnings = _validate_incident_temporal("2026-03-14T08:00:00", "2026-03-10T20:00:00")
        self.assertEqual(len(warnings), 1)


def _mock_incident_layer(existing_field_names):
    """A MagicMock standing in for the shared 'Incidents' QgsVectorLayer,
    reporting the given field names as present (indexFromName >= 0) and
    everything else as absent (-1), matching the real
    QgsFields.indexFromName contract closely enough for these tests."""
    layer = MagicMock()

    def index_from_name(name):
        return 0 if name in existing_field_names else -1
    layer.fields.return_value.indexFromName.side_effect = index_from_name
    layer.addFeature.return_value = True
    return layer


ALL_INCIDENT_FIELDS = {
    "date", "description", "severity", "event_type", "sub_event_type", "hazard_type", "contamination_status",
    "event_start", "event_end", "last_verified",
}


class TestAddIncidentPointCodingFields(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_valid_coding_fields_are_set_with_no_warnings(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = _mock_incident_layer(ALL_INCIDENT_FIELDS)
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]
        feat = mock_feature_cls.return_value

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident", severity="High",
            event_type="Battles", sub_event_type="Armed clash",
        )

        self.assertTrue(res["success"])
        self.assertNotIn("coding_warnings", res)
        feat.setAttribute.assert_any_call("event_type", "Battles")
        feat.setAttribute.assert_any_call("sub_event_type", "Armed clash")

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_invalid_hazard_type_still_inserts_but_warns(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = _mock_incident_layer(ALL_INCIDENT_FIELDS)
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident", hazard_type="Sea Mine",
        )

        self.assertTrue(res["success"])
        self.assertIn("coding_warnings", res)
        self.assertIn("Sea Mine", res["coding_warnings"][0])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_older_layer_missing_new_fields_skips_them_without_error(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        # Simulates a pre-existing "Incidents" layer created before this
        # session's fields were added -- must degrade gracefully, same as the
        # pre-existing severity-field handling this pattern is copied from.
        layer = _mock_incident_layer({"date", "description", "severity"})
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]
        feat = mock_feature_cls.return_value

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident", event_type="Battles",
        )

        self.assertTrue(res["success"])
        for call in feat.setAttribute.call_args_list:
            self.assertNotEqual(call.args[0], "event_type")

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_valid_temporal_fields_are_set_with_no_warnings(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = _mock_incident_layer(ALL_INCIDENT_FIELDS)
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]
        feat = mock_feature_cls.return_value

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident",
            event_start="2026-03-10", event_end="2026-03-14", last_verified="2026-03-15",
        )

        self.assertTrue(res["success"])
        self.assertNotIn("temporal_warnings", res)
        feat.setAttribute.assert_any_call("event_start", "2026-03-10")
        feat.setAttribute.assert_any_call("event_end", "2026-03-14")
        feat.setAttribute.assert_any_call("last_verified", "2026-03-15")

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_inverted_temporal_range_still_inserts_but_warns(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = _mock_incident_layer(ALL_INCIDENT_FIELDS)
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident",
            event_start="2026-03-14", event_end="2026-03-10",
        )

        self.assertTrue(res["success"])
        self.assertIn("temporal_warnings", res)
        self.assertIn("before", res["temporal_warnings"][0])
        # Distinct key from coding_warnings -- an unrelated validation concern.
        self.assertNotIn("coding_warnings", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_older_layer_missing_temporal_fields_skips_them_without_error(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = _mock_incident_layer({"date", "description", "severity"})
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]
        feat = mock_feature_cls.return_value

        res = add_incident_point(
            31.95, 35.93, "2026-03-14", "Test incident", event_start="2026-03-10",
        )

        self.assertTrue(res["success"])
        for call in feat.setAttribute.call_args_list:
            self.assertNotEqual(call.args[0], "event_start")


class TestAddPointLayerCodingFields(unittest.TestCase):
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_per_point_coding_warnings_are_collected_with_point_index(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        layer = MagicMock()
        layer.fields.return_value = [
            MagicMock(name=lambda: n) for n in
            ("name", "description", "category", "event_type", "sub_event_type", "hazard_type", "contamination_status")
        ]
        for f, n in zip(layer.fields.return_value, ("name", "description", "category", "event_type", "sub_event_type", "hazard_type", "contamination_status")):
            f.name.return_value = n
        layer.addFeature.return_value = True
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        res = add_point_layer("Incidents2", [
            {"lat": 1.0, "lon": 2.0, "name": "a", "event_type": "Battles"},
            {"lat": 3.0, "lon": 4.0, "name": "b", "event_type": "NotReal"},
        ])

        self.assertTrue(res["success"])
        self.assertEqual(res["added"], 2)
        self.assertIn("coding_warnings", res)
        self.assertEqual(len(res["coding_warnings"]), 1)
        self.assertIn("Point 1", res["coding_warnings"][0])
        self.assertIn("NotReal", res["coding_warnings"][0])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    def test_per_point_temporal_warnings_are_collected_with_point_index(self, mock_project, mock_feature_cls, mock_geom, mock_point):
        field_names = (
            "name", "description", "category", "event_type", "sub_event_type",
            "hazard_type", "contamination_status", "event_start", "event_end", "last_verified",
        )
        layer = MagicMock()
        layer.fields.return_value = [MagicMock(name=lambda: n) for n in field_names]
        for f, n in zip(layer.fields.return_value, field_names):
            f.name.return_value = n
        layer.addFeature.return_value = True
        mock_project.instance.return_value.mapLayersByName.return_value = [layer]

        res = add_point_layer("Incidents3", [
            {"lat": 1.0, "lon": 2.0, "name": "a", "event_start": "2026-01-01", "event_end": "2026-01-05"},
            {"lat": 3.0, "lon": 4.0, "name": "b", "event_start": "2026-02-05", "event_end": "2026-02-01"},
        ])

        self.assertTrue(res["success"])
        self.assertEqual(res["added"], 2)
        self.assertIn("coding_warnings", res)
        self.assertEqual(len(res["coding_warnings"]), 1)
        self.assertIn("Point 1", res["coding_warnings"][0])
        self.assertIn("before", res["coding_warnings"][0])


class TestStylingFailureDoesNotBlockNewLayerCreation(unittest.TestCase):
    """QGIS-009, 2026-09-14 audit: _style_incident_layer/_style_named_point_layer used to run
    unguarded right after a brand-new shared layer was added to the project -- a styling
    failure (e.g. an unresolved QGIS enum, same class as QGIS-004/005) would raise past that
    point, so the point/feature the caller actually asked for never got added, even though the
    layer now exists in the project (already added a line earlier) -- and since styling only
    ever runs on first creation, every later call reusing that same layer would never retry it
    either. Styling is cosmetic; a failure there must not block the tool's actual job."""

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._style_incident_layer")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    def test_add_incident_point_still_succeeds_when_styling_raises(
        self, mock_project, mock_vector_layer_cls, mock_feature_cls, mock_geom, mock_point, mock_style
    ):
        new_layer = _mock_incident_layer(ALL_INCIDENT_FIELDS)
        new_layer.isValid.return_value = True
        mock_vector_layer_cls.return_value = new_layer
        mock_project.instance.return_value.mapLayersByName.return_value = []  # no existing layer
        mock_style.side_effect = RuntimeError("Could not resolve ShapeType enum in this QGIS version.")

        res = add_incident_point(31.95, 35.93, "2026-03-14", "Test incident")

        self.assertTrue(res.get("success"), res)
        mock_project.instance.return_value.addMapLayer.assert_called_once_with(new_layer)
        mock_style.assert_called_once_with(new_layer)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._style_named_point_layer")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsPointXY", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsGeometry", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsFeature", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsVectorLayer", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QgsProject", create=True)
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.QGIS_AVAILABLE", True)
    def test_add_point_layer_still_succeeds_when_styling_raises(
        self, mock_project, mock_vector_layer_cls, mock_feature_cls, mock_geom, mock_point, mock_style
    ):
        field_names = ("name", "description", "category")
        new_layer = MagicMock()
        new_layer.isValid.return_value = True
        new_layer.addFeature.return_value = True
        new_layer.fields.return_value = [MagicMock(name=lambda: n) for n in field_names]
        for f, n in zip(new_layer.fields.return_value, field_names):
            f.name.return_value = n
        mock_vector_layer_cls.return_value = new_layer
        mock_project.instance.return_value.mapLayersByName.return_value = []  # no existing layer
        mock_style.side_effect = RuntimeError("Could not resolve ShapeType enum in this QGIS version.")

        res = add_point_layer("Embassies", [{"lat": 31.95, "lon": 35.93, "name": "Embassy"}])

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res.get("added"), 1)
        mock_style.assert_called_once_with(new_layer)


if __name__ == "__main__":
    unittest.main()
