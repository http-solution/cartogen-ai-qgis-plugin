"""The registry turns "this layer is the wrong kind" AttributeErrors into an error result, and nothing else."""
import unittest

from cartogen_ai.core.agent.tools import registry


class TestWrongLayerKindGuard(unittest.TestCase):
    def _guard(self, exc):
        def tool(layer):
            raise exc
        return registry._refuse_wrong_layer_kind("demo_tool", tool)

    def test_a_raster_given_where_features_are_needed_becomes_an_error_result(self):
        res = self._guard(AttributeError("'QgsRasterLayer' object has no attribute 'fields'"))("dem")
        self.assertIn("raster", res["error"])
        self.assertIn("fields", res["error"])
        self.assertIn("demo_tool", res["error"])

    def test_other_attribute_errors_still_raise(self):
        with self.assertRaises(AttributeError):
            self._guard(AttributeError("'NoneType' object has no attribute 'name'"))("x")

    def test_other_exceptions_still_raise(self):
        with self.assertRaises(ValueError):
            self._guard(ValueError("bad"))("x")

    def test_a_normal_result_and_the_signature_are_unchanged(self):
        import inspect

        def tool(layer, flag=False):
            return {"ok": layer, "flag": flag}
        guarded = registry._refuse_wrong_layer_kind("t", tool)
        self.assertEqual(guarded("a", flag=True), {"ok": "a", "flag": True})
        self.assertEqual(list(inspect.signature(guarded).parameters), ["layer", "flag"])

    def test_the_registered_tools_are_guarded(self):
        import importlib
        importlib.import_module("cartogen_ai.core.agent.tools")
        self.assertTrue(all(hasattr(f, "__wrapped__") for f in registry.TOOL_REGISTRY.values()))


if __name__ == "__main__":
    unittest.main()
