# -*- coding: utf-8 -*-
import unittest
from agent.qgis_compat import get_project_custom_property, set_project_custom_property


class _FakeProjectOldApi:
    """Simulates QGIS 3.x QgsProject: has customProperty/setCustomProperty."""
    def __init__(self):
        self._props = {}

    def customProperty(self, key, default=""):
        return self._props.get(key, default)

    def setCustomProperty(self, key, value):
        self._props[key] = value


class _FakeProjectNewApi:
    """Simulates QGIS 4.x QgsProject: customProperty/setCustomProperty removed,
    only customVariables()/setCustomVariables() (bulk QVariantMap) remain."""
    def __init__(self):
        self._variables = {}

    def customVariables(self):
        return dict(self._variables)

    def setCustomVariables(self, variables):
        self._variables = dict(variables)


class TestQgisCompat(unittest.TestCase):
    def test_get_set_roundtrip_on_old_api(self):
        project = _FakeProjectOldApi()
        self.assertTrue(set_project_custom_property(project, "k", "v"))
        self.assertEqual(get_project_custom_property(project, "k", ""), "v")

    def test_get_set_roundtrip_on_new_api_without_custom_property(self):
        project = _FakeProjectNewApi()
        self.assertTrue(set_project_custom_property(project, "k", "v"))
        self.assertEqual(get_project_custom_property(project, "k", ""), "v")
        # setCustomVariables replaces the whole map -- must be read-modify-write,
        # not clobber other keys already stored.
        set_project_custom_property(project, "other", "x")
        self.assertEqual(get_project_custom_property(project, "k", ""), "v")
        self.assertEqual(get_project_custom_property(project, "other", ""), "x")

    def test_get_returns_default_when_key_missing_on_new_api(self):
        project = _FakeProjectNewApi()
        self.assertEqual(get_project_custom_property(project, "missing", "fallback"), "fallback")

    def test_get_returns_default_when_neither_api_available(self):
        class _Nothing:
            pass
        self.assertEqual(get_project_custom_property(_Nothing(), "k", "fallback"), "fallback")

    def test_set_returns_false_when_neither_api_available(self):
        class _Nothing:
            pass
        self.assertFalse(set_project_custom_property(_Nothing(), "k", "v"))


if __name__ == "__main__":
    unittest.main()
