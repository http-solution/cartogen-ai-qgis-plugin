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
    _validate_incident_coding, ACLED_EVENT_TAXONOMY, IMSMA_HAZARD_TYPES,
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


ALL_INCIDENT_FIELDS = {"date", "description", "severity", "event_type", "sub_event_type", "hazard_type", "contamination_status"}


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


if __name__ == "__main__":
    unittest.main()
