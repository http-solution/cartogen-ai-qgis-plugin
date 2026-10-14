"""Golden basics: everyday short requests must be offered the tools that do them, in every release.

Why this exists (owner report 2026-10-14: "this was working in the previous version ... every release breaks previous work"): the rc23
cost work discounted generic words ("layer", "add", "export", "create") for EVERY request instead of only long ones. From then on
"create layer for Jordan ADM1", "zoom to the layer X", "remove the layer X" and "export X to CSV" were offered alphabetical filler
(apply_*, calculate_*) instead of add_layer_from_path, zoom_to_layer, remove_layer, export_layer. Nothing failed: the model simply
never saw the tool. The check was found by replaying 40 plain requests against all 43 releases from rc12 to 1.16.2 and diffing what
was offered. Add a row here for every plain request a user has ever relied on; a router change that drops one must fail the build."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

# request -> tools that must be among those offered
GOLDEN = {
    "create layer for Jordan ADM1": {"fetch_geoboundaries", "fetch_hdx_admin_boundaries", "add_layer_from_path"},
    "Jordan ADM2 districts": {"fetch_geoboundaries", "fetch_hdx_admin_boundaries"},
    "load the administrative boundaries for Yemen": {"fetch_geoboundaries", "fetch_hdx_admin_boundaries"},
    "zoom to the layer smoke_zones": {"zoom_to_layer", "get_layer_extent"},
    "remove the layer smoke_zones": {"remove_layer"},
    "rename the layer smoke_zones to zones": {"rename_layer"},
    "export smoke_points to CSV": {"export_layer"},
    "reproject smoke_points to EPSG:4326": {"reproject_layer"},
    "clip smoke_points to smoke_boundary": {"clip_layer"},
    "merge smoke_points and smoke_hubs": {"merge_layers"},
    "dissolve smoke_admin by name": {"dissolve_layer"},
    "union of smoke_zones": {"union_layers"},
    "add a point at 15.3694, 44.1910": {"add_point_layer"},
    "buffer smoke_points by 500 m": {"buffer_analysis"},
    "label smoke_points by name": {"apply_labels"},
    "change the colour of smoke_zones": {"change_layer_color"},
    "make the layer smoke_zones 50 percent transparent": {"set_layer_transparency"},
    "save the style of the layer smoke_zones": {"save_layer_style"},
    "what layers are in this project": {"get_layers"},
    "load this csv as a layer": {"load_tabular_data_as_layer"},
    "add the shapefile roads.shp to the map": {"add_layer_from_path"},
    "move the layer smoke_zones above smoke_points": {"set_layer_order"},
    "calculate a 1500 m service area around Hub_A on smoke_roads": {"calculate_service_area"},
    "make a print layout with the title Test and export a PDF": {"create_print_layout"},
    "make an HTML dashboard of smoke_facilities": {"generate_html_dashboard"},
    "slope of smoke_dem": {"slope_analysis"},
    "earthquakes in Turkey in the last 14 days": {"fetch_usgs_earthquakes"},
    "has this claim been fact-checked": {"search_fact_checks"},
}


class TestPlainRequestsAreOfferedTheirTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ToolRouter(TOOLS_SCHEMA)

    def test_golden_requests(self):
        problems = []
        for query, needed in GOLDEN.items():
            offered = {t["function"]["name"] for t in self.router.filter_relevant_tools(query)}
            missing = sorted(needed - offered)
            if missing:
                problems.append(f"{query!r}: not offered {missing}")
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_golden_tool_is_a_registered_tool(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        for query, needed in GOLDEN.items():
            self.assertTrue(needed <= registered, f"{query!r} names an unknown tool: {sorted(needed - registered)}")

    def test_a_short_layer_request_is_not_filled_with_alphabetical_noise(self):
        offered = [t["function"]["name"] for t in self.router.filter_relevant_tools("remove the layer smoke_zones")]
        layer_tools = [n for n in offered if "layer" in n]
        self.assertGreaterEqual(len(layer_tools), 8, offered)


if __name__ == "__main__":
    unittest.main()
