"""PLAN-033 item 4 (LEAD-4): a NEW tool can be registered without a hand-written schema; the schema is then built from its signature and type hints.

Why: three arguments were dropped in two days because the function and its schema are two places that can disagree. Built from one place they cannot. Rules pinned
here: every offered argument has a type hint and a description; arg_docs may not name a missing argument; no *args/**kwargs; `confirmed` and `hidden` names stay out of
the schema (the dispatcher strips what the schema does not offer, which is what stops a model injecting confirmed=True); an unsupported type raises at registration
instead of being guessed. Existing tools keep their hand-written schemas (nothing is converted), and register_tool's old call forms are unchanged. These tests use a
private registry so no test tool leaks into the real one."""
import inspect
import unittest
from typing import Literal
from unittest.mock import patch

from cartogen_ai.core.agent.tools import registry
from cartogen_ai.core.agent.tools.registry import UNADVERTISED_ARGUMENTS, schema_from_signature


def sample(layer_name: str, distance: float, steps: int = 3, tags: list[str] | None = None, mode: Literal["fast", "slow"] = "fast",
           keep: bool = True, extra: dict | None = None, confirmed: bool = False):
    return {"ok": True}


DOCS = {"layer_name": "Layer to use.", "distance": "Metres.", "steps": "How many steps.", "tags": "Labels.", "mode": "Speed.", "keep": "Keep it.",
        "extra": "Free-form options."}


class TestDerivedSchema(unittest.TestCase):
    def setUp(self):
        self.schema = schema_from_signature(sample, DOCS)
        self.props = self.schema["properties"]

    def test_types_come_from_the_hints(self):
        self.assertEqual(self.props["layer_name"]["type"], "string")
        self.assertEqual(self.props["distance"]["type"], "number")
        self.assertEqual(self.props["steps"]["type"], "integer")
        self.assertEqual(self.props["keep"]["type"], "boolean")
        self.assertEqual(self.props["extra"]["type"], "object")
        self.assertEqual(self.props["tags"], {"type": "array", "items": {"type": "string"}, "description": "Labels."})
        self.assertEqual(self.props["mode"]["enum"], ["fast", "slow"])

    def test_required_are_the_arguments_without_a_default_and_defaults_are_recorded(self):
        self.assertEqual(self.schema["required"], ["layer_name", "distance"])
        self.assertEqual(self.props["steps"]["default"], 3)
        self.assertIs(self.props["keep"]["default"], True)
        self.assertNotIn("default", self.props["tags"])      # a None default is not advertised

    def test_confirmed_is_never_advertised(self):
        self.assertIn("confirmed", inspect.signature(sample).parameters)
        self.assertNotIn("confirmed", self.props)
        self.assertIn("confirmed", UNADVERTISED_ARGUMENTS)

    def test_hidden_arguments_stay_out_too(self):
        schema = schema_from_signature(sample, {k: v for k, v in DOCS.items() if k != "extra"}, hidden=("extra",))
        self.assertNotIn("extra", schema["properties"])

    def test_every_description_is_carried_over(self):
        for name, text in DOCS.items():
            self.assertEqual(self.props[name]["description"], text)


class TestTheDerivationRefusesToGuess(unittest.TestCase):
    def test_a_missing_description_is_refused(self):
        with self.assertRaisesRegex(TypeError, "missing: \\['distance'\\]"):
            schema_from_signature(sample, {k: v for k, v in DOCS.items() if k != "distance"})

    def test_a_description_for_an_argument_that_is_not_there_is_refused(self):
        with self.assertRaisesRegex(TypeError, "does not offer"):
            schema_from_signature(sample, {**DOCS, "ghost": "x"})

    def test_a_missing_type_hint_is_refused(self):
        def unhinted(layer_name, count: int = 1):
            return {}
        with self.assertRaisesRegex(TypeError, "no type hint"):
            schema_from_signature(unhinted, {"layer_name": "x", "count": "y"})

    def test_an_unsupported_type_is_refused(self):
        def odd(value: set):
            return {}
        with self.assertRaisesRegex(TypeError, "cannot be turned into a tool schema"):
            schema_from_signature(odd, {"value": "x"})

    def test_var_args_are_refused(self):
        def loose(a: str, **kwargs):
            return {}
        with self.assertRaisesRegex(TypeError, "cannot be described"):
            schema_from_signature(loose, {"a": "x"})


class TestRegisterToolUsesIt(unittest.TestCase):
    def _register(self, **kw):
        with patch.object(registry, "TOOL_REGISTRY", {}) as reg, patch.object(registry, "TOOLS_SCHEMA", []) as schemas, patch.object(registry, "TOOL_KEYWORDS", {}):
            registry.register_tool("sample_tool", "Does a sample thing.", **kw)(sample)
            return reg, schemas

    def test_no_schema_means_derived(self):
        reg, schemas = self._register(arg_docs=DOCS)
        self.assertEqual(schemas[0]["function"]["parameters"], schema_from_signature(sample, DOCS))
        self.assertIn("sample_tool", reg)

    def test_a_hand_written_schema_is_used_as_it_is(self):
        hand = {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]}
        _, schemas = self._register(parameters=hand)
        self.assertIs(schemas[0]["function"]["parameters"], hand)

    def test_the_derived_schema_passes_the_registry_signature_rule(self):
        _, schemas = self._register(arg_docs=DOCS)
        advertised = set(schemas[0]["function"]["parameters"]["properties"])
        params = inspect.signature(sample).parameters
        self.assertEqual(sorted(advertised - set(params)), [])
        required = set(schemas[0]["function"]["parameters"]["required"])
        self.assertEqual(sorted(n for n, p in params.items() if p.default is inspect.Parameter.empty and n not in required and n not in advertised), [])


class TestNothingExistingChanged(unittest.TestCase):
    def test_the_real_registry_still_has_every_tool_with_a_schema(self):
        import cartogen_ai.core.agent.tools  # noqa: F401  (runs every @register_tool)
        self.assertEqual(len(registry.TOOLS_SCHEMA), len(registry.TOOL_REGISTRY))
        self.assertGreater(len(registry.TOOLS_SCHEMA), 300)
        self.assertNotIn("sample_tool", registry.TOOL_REGISTRY)


if __name__ == "__main__":
    unittest.main()
