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
    "raster calculator: dem minus dem_old": {"raster_calculator"},
    "make the outline of smoke_zones thinner and dashed": {"set_layer_symbol"},
    "add a logo to the layout": {"add_layout_item"},
    "change the page size of the layout to A3": {"set_layout_page"},
    "set the layout map scale to 1:250000": {"set_layout_map"},
    "save the layout as a template": {"save_layout_template"},
    "export the layout as SVG": {"export_layout"},
    "give the smoke_points labels a white halo": {"set_label_style"},
    "show the land cover raster with one colour per value": {"set_raster_style"},
    "make a mask of the cells above 100 in the dem": {"raster_calculator"},
    "set a definition query on smoke_points": {"set_layer_filter"},
    "move the selected features 100 m east": {"transform_features"},
    "merge the selected features into one": {"merge_features"},
    "split the polygon with a line": {"split_features_by_line"},
    "undo my last edit on smoke_zones": {"undo_manual_edit"},
    "change the field type of pop to integer": {"change_field_type"},
    "save the edits on smoke_points": {"set_layer_editing"},
    "add the postgis table roads to the map": {"add_postgis_layer"},
    "create a virtual layer joining smoke_points and smoke_zones with sql": {"create_virtual_layer"},
    "load the qlr file styles.qlr": {"load_layer_definition"},
    "save smoke_points as a qlr file": {"save_layer_definition"},
    "package the project layers into one geopackage for offline use": {"package_layers_offline"},
    "rename the group Transport to Roads": {"rename_layer_group"},
    "zoom to the previous extent": {"zoom_history"},
    "set the abstract and license of smoke_zones": {"set_layer_metadata"},
    "turn on snapping to vertices": {"set_snapping_options"},
    "create a relation between districts and schools": {"create_relation"},
    "make the layer temporal using the date field": {"set_layer_temporal"},
    "add a text annotation on the map": {"add_text_annotation"},
    "label the big camps in bold and the small ones only when zoomed in": {"set_rule_based_labels"},
    "add callouts to the labels": {"set_label_callout"},
    "use an svg icon for the camps": {"set_point_marker"},
    "draw a pie chart on each district with male and female": {"set_layer_diagram"},
    "show the dem as a hillshade": {"set_raster_relief"},
    "save this symbol to my library": {"save_symbol_to_library"},
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
    "create an empty polygon layer with fields name and population": {"create_empty_layer"},
    "add an openstreetmap basemap": {"add_basemap"},
    "add the wms layer from this url": {"add_web_layer"},
    "look at the map": {"inspect_canvas_visually"},
    "find the information from the internet and provide the source": {"web_research"},
    "check the internet for major incidents from the news in Jordan this week and put them on the map": {"find_incident_reports"},
}


# Requests of more than 25 words. They use the stricter long-request rules (generic words discounted, a minimum score), so they are guarded separately.
GOLDEN_LONG = {
    'I have a layer of health facilities called smoke_facilities and a road network smoke_roads. Please work out which of the facilities can be reached within one hour of Hub_A by road, show the reachable ones in green and the others in red, and tell me how many are in each group.': {'classify_facilities_by_access'},
    'Create a map of Yemen ADM1 governorate boundaries with labels, download them if they are not already in the project, style them with a pale fill and a grey outline, and add a title and scale bar in a print layout I can export as a PDF.': {'apply_labels', 'create_print_layout', 'fetch_geoboundaries', 'fetch_hdx_admin_boundaries', ('change_layer_color', 'apply_categorized_style')},
    'Download the OpenStreetMap hospitals and clinics for the area covered by smoke_boundary, buffer them by two kilometres, dissolve the buffers into a single polygon and calculate the area of the result in square kilometres.': {'buffer_analysis', 'calculate_area', 'dissolve_layer', 'fetch_osm_features'},
    'Take the population raster yem_ppp_2020 and the 1500 m service area around Hub_A and estimate how many people live inside it, giving me the three labelled figures and saying which one is an upper bound.': {'estimate_population_exposure'},
    'Check the internet for recent incidents, disasters or conflict events reported near Amman in Jordan during the last thirty days from named reliable sources and put whatever you find on the map with the source and the date for each record.': {'find_incident_reports'},
    'Compute the slope of smoke_dem in degrees, classify it into five classes, style the result with a green to red colour ramp and make a print layout of it with a legend and a title that I can export.': {'apply_raster_stretch', 'create_print_layout', 'slope_analysis'},
    'Rank the three candidate hub locations in smoke_hubs by their average distance to the points in smoke_points and tell me which hub serves the points best and by how much it beats the other two candidates.': {'optimal_hub_siting'},
    'Remove the layer smoke_zones from the project, then rename the layer smoke_admin to districts, reproject it to EPSG:4326 and export it as a GeoPackage in the project folder under the name districts_4326.': {'export_layer', 'remove_layer', 'rename_layer', 'reproject_layer'},
    'Make an interactive HTML dashboard of the health facilities in smoke_facilities with a basemap, a layer control and a popup that shows the facility name, and save it in the project folder so that I can send it to the donors.': {'generate_html_dashboard'},
    'I need a delivery route that starts at Hub_A and visits each of the five points in smoke_points in the shortest order using the road network smoke_roads, and I want the route drawn as a line above the roads with the total distance reported.': {'optimize_delivery_route'},
    'Has the claim that a video of Houthi fighters in Dhale was filmed recently been fact-checked by any of the outlets, and if so what did they conclude, please answer in English and mention the outlet and the date.': {'search_fact_checks'},
    'Geocode this list of towns: Amman, Irbid, Zarqa, Aqaba, Madaba, Salt, Jerash, Karak, Tafilah and Maan, put them on the map as points labelled with the town names, and then zoom the map to the new layer.': {'apply_labels', 'geocode_batch', 'zoom_to_layer'},
    'Load the earthquakes with a magnitude of 4.5 or more from the last thirty days within a box around Turkey, classify the points by magnitude band, label the largest events and tell me how many events fall in each band.': {'fetch_usgs_earthquakes'},
    'Calculate a severity index for smoke_admin_dup from population and need using the name field admin_name, write the score to a field called sev and make a map where the worst affected districts stand out clearly.': {'calculate_severity_index'},
    'Clip smoke_points to the boundary smoke_boundary, merge the result with smoke_hubs, add a field with the distance to the nearest hub and export the final layer to CSV with the coordinates included.': {'clip_layer', 'export_layer', 'merge_layers'},
    'Find all schools within two kilometres of the flooded area in the GDACS alert layer, show them on the map, count how many there are in each district of smoke_admin and give me a table I can paste into a situation report.': {"fetch_gdacs_disaster_alerts", ("fetch_osm_features", "ingest_osm_features")},
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

    def test_golden_long_requests(self):
        """A tuple in the set means any one of its tools is enough."""
        problems = []
        for query, needed in GOLDEN_LONG.items():
            self.assertGreater(len(query.split()), 25, query)
            offered = {t["function"]["name"] for t in self.router.filter_relevant_tools(query)}
            missing = [n for n in needed if (not (set(n) & offered) if isinstance(n, tuple) else n not in offered)]
            if missing:
                problems.append(f"{query[:70]!r}: not offered {missing}")
        self.assertEqual(problems, [], chr(10).join(problems))

    def test_every_golden_tool_is_a_registered_tool(self):
        registered = {t["function"]["name"] for t in TOOLS_SCHEMA}
        for query, needed in list(GOLDEN.items()) + list(GOLDEN_LONG.items()):
            flat = {x for n in needed for x in (n if isinstance(n, tuple) else (n,))}
            self.assertTrue(flat <= registered, f"{query!r} names an unknown tool: {sorted(flat - registered)}")

    def test_a_short_layer_request_is_not_filled_with_alphabetical_noise(self):
        offered = [t["function"]["name"] for t in self.router.filter_relevant_tools("remove the layer smoke_zones")]
        layer_tools = [n for n in offered if "layer" in n]
        self.assertGreaterEqual(len(layer_tools), 8, offered)


if __name__ == "__main__":
    unittest.main()
