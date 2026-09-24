# -*- coding: utf-8 -*-
"""Tests for core/models/egress_gate.py -- the pure half of the cloud-provider egress gate
(docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md). Wiring into the agent is tested separately in
test_agent_runner.py; the sensitivity tool's downgrade lock in test_sensitivity_egress_lock.py."""
import unittest

from cartogen_ai.core.models import egress_gate as g


class TestIsLocalEndpoint(unittest.TestCase):
    def test_loopback_and_localhost_are_local(self):
        for url in ("http://localhost:11434/v1/chat/completions", "http://127.0.0.1:11434",
                    "http://127.5.5.5/x", "http://[::1]:11434/v1", "localhost:11434", "LOCALHOST"):
            self.assertTrue(g.is_local_endpoint(url), url)

    def test_private_lan_addresses_are_local(self):
        for url in ("http://192.168.1.20:11434", "http://10.0.0.5", "http://172.16.4.4:8080",
                    "http://169.254.1.1", "http://[fd00::1]:11434"):
            self.assertTrue(g.is_local_endpoint(url), url)

    def test_public_addresses_and_hostnames_are_not_local(self):
        for url in ("https://api.openai.com/v1/chat/completions", "https://openrouter.ai/api",
                    "https://generativelanguage.googleapis.com", "http://8.8.8.8:11434",
                    "http://1.1.1.1", "http://my-ollama-server:11434", "http://box.local"):
            self.assertFalse(g.is_local_endpoint(url), url)

    def test_reserved_non_routable_ranges_count_as_local(self):
        # Python's ipaddress calls documentation/benchmark ranges "private". They cannot reach a
        # real public server, so treating them as local is safe (and not worth special-casing).
        self.assertTrue(g.is_local_endpoint("http://203.0.113.9"))

    def test_trick_urls_are_not_local(self):
        # userinfo trick: the real host is what follows the @
        self.assertFalse(g.is_local_endpoint("http://localhost@evil.example/"))
        self.assertFalse(g.is_local_endpoint("http://127.0.0.1@evil.example/"))
        # a hostname that merely starts like an IP is a hostname, not an IP literal
        self.assertFalse(g.is_local_endpoint("http://127.0.0.1.evil.example/"))
        # an IPv4-mapped IPv6 address must be judged by its embedded IPv4 address
        self.assertFalse(g.is_local_endpoint("http://[::ffff:8.8.8.8]/"))
        self.assertTrue(g.is_local_endpoint("http://[::ffff:127.0.0.1]/"))

    def test_garbage_is_not_local(self):
        for url in (None, "", "   ", 123, "http://", "://", "http://[bad"):
            self.assertFalse(g.is_local_endpoint(url), repr(url))


class TestProtectionRules(unittest.TestCase):
    def test_restricted_and_sensitive_always_protected(self):
        for strict in (False, True):
            self.assertTrue(g.is_protected("RESTRICTED", strict))
            self.assertTrue(g.is_protected("SENSITIVE", strict))

    def test_open_levels_never_protected(self):
        for strict in (False, True):
            self.assertFalse(g.is_protected("PUBLIC", strict))
            self.assertFalse(g.is_protected("INTERNAL", strict))

    def test_untagged_is_protected_only_in_strict_mode(self):
        self.assertFalse(g.is_protected(None, False))
        self.assertTrue(g.is_protected(None, True))

    def test_loosening_is_protected_to_open_only(self):
        self.assertTrue(g.is_loosening("SENSITIVE", "PUBLIC", False))
        self.assertTrue(g.is_loosening("RESTRICTED", "INTERNAL", False))
        self.assertFalse(g.is_loosening("PUBLIC", "SENSITIVE", False))       # tightening
        self.assertFalse(g.is_loosening("SENSITIVE", "RESTRICTED", False))   # still protected
        self.assertFalse(g.is_loosening("PUBLIC", "INTERNAL", False))        # open -> open

    def test_tagging_an_untagged_layer_open_is_loosening_only_in_strict_mode(self):
        self.assertFalse(g.is_loosening(None, "PUBLIC", False))  # nothing was protecting it
        self.assertTrue(g.is_loosening(None, "PUBLIC", True))    # strict mode was blocking it


class TestCollectLayerNames(unittest.TestCase):
    KNOWN = {"roads", "clinics", "beneficiaries"}

    def test_finds_top_level_strings(self):
        self.assertEqual(g.collect_layer_names({"layer_name": "roads", "distance": 5}, self.KNOWN),
                         {"roads"})

    def test_finds_names_nested_in_dicts_and_lists(self):
        args = {"alg_id": "native:buffer", "params": {"INPUT": "beneficiaries", "X": [1, "clinics"]}}
        self.assertEqual(g.collect_layer_names(args, self.KNOWN), {"beneficiaries", "clinics"})

    def test_ignores_strings_that_are_not_layer_names(self):
        self.assertEqual(g.collect_layer_names({"a": "hello", "b": "roads2"}, self.KNOWN), set())

    def test_depth_is_bounded(self):
        nested = "beneficiaries"
        for _ in range(20):
            nested = [nested]
        self.assertEqual(g.collect_layer_names(nested, self.KNOWN), set())


def _ctx(levels, sources=None):
    sources = sources or {}
    return (lambda n: levels.get(n), lambda n: sources.get(n, []))


class TestFindProtected(unittest.TestCase):
    def test_tagged_layers(self):
        gl, gs = _ctx({"a": "SENSITIVE", "b": "PUBLIC", "c": None})
        self.assertEqual(set(g.find_protected({"a", "b", "c"}, gl, gs, False)), {"a"})
        self.assertEqual(set(g.find_protected({"a", "b", "c"}, gl, gs, True)), {"a", "c"})

    def test_untagged_derived_layer_inherits_from_a_protected_source(self):
        gl, gs = _ctx({"src": "SENSITIVE"}, {"buf": ["src"]})
        res = g.find_protected({"buf"}, gl, gs, False)
        self.assertIn("derived from 'src'", res["buf"])

    def test_explicit_open_tag_on_a_derived_layer_overrides_inheritance(self):
        # An aggregated/anonymized output the owner has released must not stay blocked forever.
        gl, gs = _ctx({"src": "SENSITIVE", "agg": "PUBLIC"}, {"agg": ["src"]})
        self.assertEqual(g.find_protected({"agg"}, gl, gs, False), {})

    def test_inheritance_is_transitive(self):
        gl, gs = _ctx({"src": "RESTRICTED"}, {"b": ["a"], "a": ["src"]})
        self.assertIn("b", g.find_protected({"b"}, gl, gs, False))

    def test_lineage_cycles_terminate(self):
        gl, gs = _ctx({}, {"a": ["b"], "b": ["a"]})
        self.assertEqual(g.find_protected({"a"}, gl, gs, False), {})


class TestEvaluate(unittest.TestCase):
    LEVELS = {"beneficiaries": "SENSITIVE", "boundary": "PUBLIC"}

    def _eval(self, **over):
        gl, gs = _ctx(over.pop("levels", self.LEVELS), over.pop("sources", None))
        kw = dict(mode=g.MODE_ENFORCE, provider_is_local=False, tool_name="buffer_analysis",
                  arguments={"layer_name": "beneficiaries", "distance": 100},
                  project_layer_names=["beneficiaries", "boundary"],
                  get_level=gl, get_sources=gs, strict=False)
        kw.update(over)
        return g.evaluate(**kw)

    def test_enforce_blocks_a_protected_layer_on_a_cloud_provider(self):
        res = self._eval()
        self.assertEqual(res["action"], "block")
        self.assertEqual(res["result"]["status"], "EGRESS_BLOCKED")
        self.assertEqual(res["result"]["layers"], ["beneficiaries"])
        self.assertIn("Do not retry", res["result"]["message"])

    def test_off_never_blocks(self):
        self.assertIsNone(self._eval(mode=g.MODE_OFF))

    def test_unknown_mode_never_blocks(self):
        self.assertIsNone(self._eval(mode="banana"))

    def test_local_provider_is_never_blocked(self):
        self.assertIsNone(self._eval(provider_is_local=True))

    def test_warn_allows_but_reports(self):
        res = self._eval(mode=g.MODE_WARN)
        self.assertEqual(res["action"], "warn")
        self.assertIsNone(res["result"])
        self.assertIn("beneficiaries", res["warning"])

    def test_a_public_layer_is_allowed(self):
        self.assertIsNone(self._eval(arguments={"layer_name": "boundary"}))

    def test_no_layer_named_means_nothing_to_block(self):
        self.assertIsNone(self._eval(arguments={"query": "hello"}))

    def test_nested_processing_params_are_seen(self):
        res = self._eval(tool_name="run_allowlisted_processing_algorithm",
                         arguments={"alg_id": "native:buffer", "params": {"INPUT": "beneficiaries"}})
        self.assertEqual(res["action"], "block")

    def test_sensitivity_tools_are_exempt_so_a_layer_can_still_be_classified(self):
        for tool in ("set_layer_sensitivity", "get_layer_sensitivity"):
            self.assertIsNone(self._eval(tool_name=tool, arguments={"layer_name": "beneficiaries"}))

    def test_execute_pyqgis_script_is_judged_on_the_whole_project(self):
        # The script names its layers inside its own source, not in arguments -- so a project with
        # any protected layer blocks it even though "layer" appears nowhere in the arguments.
        res = self._eval(tool_name="execute_pyqgis_script", arguments={"script": "def run(): pass"})
        self.assertEqual(res["action"], "block")

    def test_execute_pyqgis_script_is_allowed_when_the_whole_project_is_open(self):
        self.assertIsNone(self._eval(tool_name="execute_pyqgis_script",
                                     arguments={"script": "def run(): pass"},
                                     levels={"beneficiaries": "PUBLIC", "boundary": "PUBLIC"}))

    def test_strict_mode_blocks_untagged_layers(self):
        self.assertIsNone(self._eval(arguments={"layer_name": "new_layer"},
                                     project_layer_names=["new_layer"], levels={}))
        res = self._eval(arguments={"layer_name": "new_layer"},
                         project_layer_names=["new_layer"], levels={}, strict=True)
        self.assertEqual(res["action"], "block")


if __name__ == "__main__":
    unittest.main()
