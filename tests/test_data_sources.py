"""PLAN-023 R1-8: the data-source catalogue (core/agent/data_sources.json) and its loader. Offline, no QGIS. The catalogue is a RECORD: tests keep it equal to the persona files, the registered tools and the guards the code really has, and show the checker
able to fail on each kind of fault (on synthetic sources, so a checker that accepts everything cannot pass)."""
import copy
import unittest

from cartogen_ai.core import personas as pp
from cartogen_ai.core.agent import data_sources as ds
from cartogen_ai.core.agent.agent_orchestrator import NETWORK_ONLY_TOOLS, TWO_PHASE_TOOLS
from cartogen_ai.core.agent.tools import TOOL_REGISTRY, TOOLS_SCHEMA
from cartogen_ai.core.personas import panel


def _persona_sources():
    return {pid: pp.get(pid)["data_sources"] for pid in pp.ids()}


def _good():
    return {"id": "x", "label": "X", "personas": ["general"], "kind": "API", "access": "open", "licence": "l", "size_class": "small", "size_guard": None, "egress_class": "none",
            "egress_note": "n", "hosts": ["example.org"], "cache_folder": None, "tools": ["get_layers"]}


def _problems(source, **kw):
    return ds.validate([source], tool_names=set(TOOL_REGISTRY), persona_ids=set(pp.ids()), **kw)


class TestTheShippedCatalogue(unittest.TestCase):
    def test_it_passes_the_checker_against_the_real_tools_personas_and_persona_files(self):
        problems = ds.validate(ds.load(), tool_names=set(TOOL_REGISTRY), persona_ids=set(pp.ids()), persona_sources=_persona_sources())
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_every_source_id_the_persona_files_use_is_in_the_catalogue_and_none_is_unused(self):
        used = {s for ids in _persona_sources().values() for s in ids}
        self.assertEqual(used, {s["id"] for s in ds.load()})

    def test_the_fourteen_sources_the_plan_names_are_there(self):
        self.assertEqual({s["id"] for s in ds.load()}, {"hdx", "geoboundaries", "osm", "footprints", "worldpop", "gdacs", "eonet", "firms", "fts", "usgs", "ucdp", "stac_search", "geocoding", "web_search"})

    def test_a_tool_belongs_to_one_source_only(self):
        names = [t for s in ds.load() for t in s["tools"]]
        self.assertEqual(len(names), len(set(names)))

    def test_every_catalogued_tool_is_a_network_tool_the_orchestrator_already_knows(self):
        known = set(NETWORK_ONLY_TOOLS) | set(TWO_PHASE_TOOLS)
        self.assertEqual(sorted(t for s in ds.load() for t in s["tools"] if t not in known), [])

    def test_the_only_source_that_needs_a_key_names_the_credential_the_tool_asks_for(self):
        keyed = [s for s in ds.load() if s["access"] == "free key"]
        self.assertEqual([(s["id"], s["credential"]) for s in keyed], [("firms", "firms")])
        import inspect

        from cartogen_ai.core.agent.tools import hazard_monitoring_tools
        self.assertIn('get_credential("firms")', inspect.getsource(hazard_monitoring_tools))

    def test_the_size_guard_record_matches_the_code(self):
        by_flag = {"allow_large_download": "content_length", "allow_whole_country": "whole_country_flag"}
        for item in TOOLS_SCHEMA:
            fn = item["function"]
            for flag, guard in by_flag.items():
                if flag in fn["parameters"].get("properties", {}):
                    self.assertEqual(ds.for_tool(fn["name"])["size_guard"], guard, fn["name"])
        for guard in ("content_length", "whole_country_flag"):
            self.assertTrue([s for s in ds.load() if s["size_guard"] == guard], guard)
        from cartogen_ai.core.agent import local_data_loader
        self.assertTrue(callable(local_data_loader.should_ask_before_download))
        self.assertEqual([s["id"] for s in ds.load() if s["size_guard"] == "extract_ask"], ["osm"])

    def test_the_sources_that_send_nothing_of_the_request_are_the_ones_whose_code_sends_nothing(self):
        self.assertEqual(sorted(s["id"] for s in ds.load() if s["egress_class"] == "none"), ["gdacs", "ucdp"])
        self.assertEqual(sorted(s["id"] for s in ds.load() if s["egress_class"] == "text"), ["geocoding", "hdx", "web_search"])

    def test_the_cache_folders_are_the_ones_the_loaders_use(self):
        self.assertEqual({s["id"]: s["cache_folder"] for s in ds.load() if s["cache_folder"]}, {"osm": "osm", "worldpop": "worldpop"})


class TestAccessors(unittest.TestCase):
    def test_for_tool_and_for_persona(self):
        self.assertEqual(ds.for_tool("geocode_batch")["id"], "geocoding")
        self.assertIsNone(ds.for_tool("get_layers"))
        self.assertIn("firms", [s["id"] for s in ds.for_persona("disaster_risk")])
        self.assertEqual(ds.for_persona("nonsense"), [])

    def test_access_text_is_plain_words(self):
        self.assertEqual(ds.access_text(ds.get("hdx")), "open")
        self.assertEqual(ds.access_text(ds.get("firms")), "needs a free key")
        self.assertIn("bring your own", ds.access_text({"access": "licensed"}))

    def test_lines_for_persona_name_the_source_and_how_to_get_it(self):
        lines = ds.lines_for_persona("disaster_risk")
        self.assertIn("NASA FIRMS active fires (needs a free key)", lines)
        self.assertTrue(all(line.endswith(")") for line in lines))


class TestStacHostsComeFromTheCatalogue(unittest.TestCase):
    def test_the_allowed_host_is_what_it_was_before_the_catalogue(self):
        from cartogen_ai.core.agent.tools import stac_ops
        self.assertEqual(stac_ops.ALLOWED_HOSTS, frozenset({"sentinel-cogs.s3.us-west-2.amazonaws.com"}))

    def test_an_unreadable_catalogue_leaves_no_host_allowed(self):
        real_path, real_cache = ds._data_path, dict(ds._cache)
        ds._cache.update({"data": None, "by_id": None})
        ds._data_path = lambda: "/nonexistent/data_sources.json"
        try:
            self.assertEqual(ds.load(), [])
            self.assertEqual(ds.asset_hosts("stac_search"), frozenset())
        finally:
            ds._data_path = real_path
            ds._cache.update(real_cache)
        self.assertTrue(ds.asset_hosts("stac_search"))

    def test_an_unknown_source_has_no_asset_hosts(self):
        self.assertEqual(ds.asset_hosts("nope"), frozenset())


class TestTheCheckerCatchesEachFault(unittest.TestCase):
    def test_a_good_source_has_no_problems(self):
        self.assertEqual(_problems(_good()), [])

    def test_each_fault_is_reported_with_the_source_and_the_cause(self):
        faults = {
            "missing": (lambda s: s.pop("licence"), "missing 'licence'"),
            "kind": (lambda s: s.update(kind="ftp"), "kind 'ftp'"),
            "access": (lambda s: s.update(access="free"), "access 'free'"),
            "size_class": (lambda s: s.update(size_class="huge"), "size_class 'huge'"),
            "size_guard": (lambda s: s.update(size_guard="magic"), "size_guard 'magic'"),
            "egress": (lambda s: s.update(egress_class="all"), "egress_class 'all'"),
            "key_without_credential": (lambda s: s.update(access="free key"), "names its credential"),
            "credential_without_key": (lambda s: s.update(credential="x"), "names its credential"),
            "empty_text": (lambda s: s.update(licence="  "), "'licence' is empty"),
            "no_hosts": (lambda s: s.update(hosts=[]), "hosts is empty"),
            "host_with_scheme": (lambda s: s.update(hosts=["https://example.org"]), "bare lower-case host name"),
            "host_upper_case": (lambda s: s.update(hosts=["Example.org"]), "bare lower-case host name"),
            "asset_host_not_listed": (lambda s: s.update(asset_hosts=["other.org"]), "not in hosts"),
            "no_tools": (lambda s: s.update(tools=[]), "tools is empty"),
            "unregistered_tool": (lambda s: s.update(tools=["no_such_tool"]), "not a registered tool"),
            "unknown_persona": (lambda s: s.update(personas=["nobody"]), "does not exist"),
        }
        for name, (change, expected) in faults.items():
            source = copy.deepcopy(_good())
            change(source)
            problems = _problems(source)
            self.assertTrue(any(expected in p and p.startswith("x:") for p in problems), f"{name}: {problems}")

    def test_a_duplicate_id_is_reported(self):
        problems = ds.validate([_good(), _good()])
        self.assertTrue(any("appears twice" in p for p in problems))

    def test_personas_that_differ_from_the_persona_files_are_reported(self):
        problems = _problems(_good(), persona_sources={"general": [], "research": ["x"]})
        self.assertTrue(any("differ from the persona files" in p for p in problems))
        self.assertEqual(_problems(_good(), persona_sources={"general": ["x"]}), [])

    def test_the_persona_checker_flags_an_unknown_data_source(self):
        persona = dict(pp.get("general"), data_sources=["hdx", "not_a_source"])
        problems = pp.validate(persona, data_source_ids={s["id"] for s in ds.load()})
        self.assertEqual(len(problems), 1)
        self.assertIn("not_a_source", problems[0])


class TestPanelShowsTheSources(unittest.TestCase):
    def test_the_panel_lists_each_persons_sources_when_given_the_lines(self):
        text = panel.panel_text("disaster_risk", "", ds.lines_for_persona)
        self.assertIn("Data it can read:", text)
        self.assertIn("NASA FIRMS active fires (needs a free key)", text)

    def test_the_panel_without_lines_is_unchanged(self):
        self.assertNotIn("Data it can read:", panel.panel_text("disaster_risk"))

    def test_a_persona_with_no_sources_gets_no_data_section(self):
        self.assertNotIn("Data it can read:", panel.panel_text("logistics", "", lambda _p: []))


if __name__ == "__main__":
    unittest.main()
