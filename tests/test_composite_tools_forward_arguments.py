"""PLAN-033 item 3 (LEAD-4): a registered tool that calls another registered tool must say, for every argument of the called tool it does not pass, why.

Why: three arguments were dropped in two days (GDACS `country`, `population_access_gap`'s speed field, `add_layer_from_path`'s `sublayer`). Item 2 covers the
orchestrator's own branches; this covers tools that call other tools. It reads the source (no QGIS): for each direct call from one @register_tool function to
another, it lists the called tool's parameters that the call neither passes nor leaves to `**kwargs`, and fails when one is not in INTENTIONALLY_FIXED (a cosmetic
or default choice, with the reason) or KNOWN_GAPS (an argument that CHANGES THE ANSWER and is fixed by the composite, listed so it is a visible open defect, not a
silent one; empty today). It also fails when a composite offers an argument of its own that has the called tool's name but does not pass it on (the drop this plan is about),
and when an allow-list entry is stale. Limit: direct calls by name only; a call through a variable, a lambda or `getattr` is not seen."""
import ast
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai" / "core" / "agent" / "tools"

COSMETIC = "styling or output naming only; the callee's default is the intended look"
# (composite, called tool, parameter) -> why the composite does not pass it on. Nothing here changes a number in the answer.
INTENTIONALLY_FIXED = {
    ("calculate_population_in_need", "estimate_population_exposure", "output_layer_name"): "the exposure result is read, not kept as a layer",
    ("population_access_gap", "estimate_population_exposure", "output_layer_name"): "the exposure result is read, not kept as a layer",
    ("calculate_damage_exposure_severity", "calculate_raster_change_detection", "align_to_first"): "the callee's default alignment is the intended one for a before/after pair",
    ("calculate_damage_exposure_severity", "calculate_raster_change_detection", "resampling"): "the callee's default (bilinear) is the intended one for a before/after pair",
    ("create_shaded_relief", "apply_raster_stretch", "band"): "a hillshade has one band",
    ("create_shaded_relief", "apply_raster_stretch", "min_value"): "the stretch is computed from the raster",
    ("create_shaded_relief", "apply_raster_stretch", "max_value"): "the stretch is computed from the raster",
    ("create_shaded_relief", "apply_raster_stretch", "keep_population_ramp"): "not a population raster",
    ("generate_sector_coverage_report", "generate_chart", "color_palette"): COSMETIC,
    ("generate_sector_coverage_report", "generate_chart", "dpi"): COSMETIC,
    ("chart_field_by_category", "generate_chart", "color_palette"): COSMETIC,
    ("chart_field_by_category", "generate_chart", "dpi"): COSMETIC,
    ("classify_facilities_by_access", "calculate_service_area", "style_by_cost"): "the composite styles the result itself",
    ("population_access_gap", "calculate_service_area", "style_by_cost"): "the composite styles the result itself",
    ("classify_facilities_by_access", "apply_categorized_style", "opacity"): COSMETIC,
    ("classify_facilities_by_access", "apply_categorized_style", "palette"): COSMETIC,
    ("export_temporal_animation_frames", "apply_categorized_style", "opacity"): COSMETIC,
    ("export_temporal_animation_frames", "apply_categorized_style", "palette"): COSMETIC,
    ("score_route_incident_risk", "buffer_analysis", "only_selected"): "the whole incident layer is intended",
    ("score_route_incident_risk", "buffer_analysis", "output_name"): "the buffer is an intermediate layer",
}
# Arguments that CHANGE THE ANSWER and that a composite fixes without offering them. Empty since 2026-11-22: the eight the first run found (raster_unit in
# calculate_population_in_need and population_access_gap; value_forward, value_backward and value_both in classify_facilities_by_access and
# population_access_gap) are now offered by those tools and passed on. A new entry here is an open defect, not a record.
KNOWN_GAPS: dict = {}


def _registered():
    """{function name: FunctionDef} for every @register_tool function, and {file: tree}."""
    found = {}
    for path in sorted(TOOLS.glob("*.py")):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and any(
                    isinstance(d, ast.Call) and getattr(d.func, "id", "") == "register_tool" for d in node.decorator_list):
                found.setdefault(node.name, node)
    return found


def _params(fn):
    return [a.arg for a in fn.args.args + fn.args.kwonlyargs]


def composite_calls():
    """[(composite, called, not_passed, offered_but_not_passed)] for every direct call of one registered tool by another. Pure."""
    reg = _registered()
    rows = []
    for fn in reg.values():
        own = set(_params(fn))
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in reg and call.func.id != fn.name):
                continue
            if any(k.arg is None for k in call.keywords):   # **kwargs forwards the rest
                continue
            callee = _params(reg[call.func.id])
            passed = {k.arg for k in call.keywords} | set(callee[:len(call.args)])
            missing = [p for p in callee if p not in passed]
            rows.append((fn.name, call.func.id, missing, [p for p in missing if p in own]))
    return rows


class TestCompositeToolsForwardArguments(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = composite_calls()

    def test_the_scan_sees_the_known_composites(self):
        names = {(c, k) for c, k, _, _ in self.rows}
        for pair in (("population_access_gap", "calculate_service_area"), ("chart_field_by_category", "generate_chart"),
                     ("score_route_incident_risk", "buffer_analysis")):
            self.assertIn(pair, names)

    def test_no_composite_offers_an_argument_it_then_drops(self):
        dropped = [(c, k, p) for c, k, _, offered in self.rows for p in offered]
        self.assertEqual(dropped, [], "a tool offers an argument with the called tool's name but does not pass it on")

    def test_every_argument_a_composite_does_not_pass_is_listed_with_a_reason(self):
        unlisted = [(c, k, p) for c, k, missing, _ in self.rows for p in missing
                    if (c, k, p) not in INTENTIONALLY_FIXED and (c, k, p) not in KNOWN_GAPS]
        self.assertEqual(unlisted, [], "add the argument to INTENTIONALLY_FIXED (with why) or KNOWN_GAPS, or pass it on")

    def test_the_lists_hold_no_stale_entries_and_do_not_overlap(self):
        live = {(c, k, p) for c, k, missing, _ in self.rows for p in missing}
        self.assertEqual(sorted(set(INTENTIONALLY_FIXED) - live), [])
        self.assertEqual(sorted(set(KNOWN_GAPS) - live), [])
        self.assertEqual(set(INTENTIONALLY_FIXED) & set(KNOWN_GAPS), set())

    def test_every_listed_entry_has_a_reason(self):
        for table in (INTENTIONALLY_FIXED, KNOWN_GAPS):
            for key, why in table.items():
                self.assertTrue(why.strip(), key)


if __name__ == "__main__":
    unittest.main()
