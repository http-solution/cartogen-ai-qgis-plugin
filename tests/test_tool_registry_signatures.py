"""Every registered tool's function must accept the arguments its schema advertises.

Why (hand test 2026-10-13, row RC37-F4): PR #249 put a helper between the @register_tool decorator and run_allowlisted_processing_algorithm,
so the registry held the helper and every model call failed with "unexpected keyword argument 'params'". Tests that import the function
directly never see that, so this checks the registry itself."""
import importlib
import inspect
import unittest

from cartogen_ai.core.agent.tools import registry


class TestRegisteredSignaturesMatchSchemas(unittest.TestCase):
    def test_every_tool_function_accepts_its_schema_arguments(self):
        importlib.import_module("cartogen_ai.core.agent.tools")          # runs every tool module's @register_tool
        schemas = {s["function"]["name"]: s["function"]["parameters"] for s in registry.TOOLS_SCHEMA}
        self.assertGreater(len(registry.TOOL_REGISTRY), 150)
        bad = []
        for name, func in registry.TOOL_REGISTRY.items():
            params = inspect.signature(func).parameters
            if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
                continue
            schema = schemas.get(name, {})
            advertised = set(schema.get("properties", {}))
            missing = sorted(advertised - set(params))
            unneeded_required = sorted(
                n for n, p in params.items()
                if p.default is inspect.Parameter.empty and n not in set(schema.get("required", [])) and n not in advertised)
            if missing or unneeded_required:
                bad.append((name, func.__name__, {"schema_args_the_function_lacks": missing, "function_args_the_schema_never_offers": unneeded_required}))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
