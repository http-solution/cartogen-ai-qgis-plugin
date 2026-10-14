"""QGIS everyday vocabulary: a plain, menu-style phrase must be offered the tool that does it, or an honest fallback when none exists.

Written 2026-10-14 after the owner asked whether basic QGIS actions and the Processing tools are covered. 91 phrases taken from the
QGIS Vector / Raster / Processing menus and the attribute-table, layer-tree, symbology and layout actions. Measured before the fixes: 71 of 78
phrases that have a tool reached it (91 percent) and none of the 13 phrases without a tool was offered a fallback. A phrase maps to the tools
that do it (any one is enough), or to "GAP" when no dedicated tool and no allow-listed Processing algorithm exists; a GAP phrase must at
least be offered execute_pyqgis_script or find_tools so the model can try and say honestly what it did. Add a phrase here whenever a user
reports one that failed. This checks what is OFFERED, not what the model then does."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.services.tool_router import ToolRouter

P = "run_allowlisted_processing_algorithm"
VOCAB = {
 # --- Vector > Geoprocessing
 "buffer the roads by 200 m": ["buffer_analysis"],
 "clip the roads to the district": ["clip_layer"],
 "intersect the flood zone with the districts": ["intersect_layers"],
 "union the two polygon layers": ["union_layers"],
 "difference of the districts and the flood zone": ["difference_layers"],
 "symmetrical difference of the two layers": [P],
 "dissolve the districts by governorate": ["dissolve_layer"],
 "convex hull of the points": ["convex_hull"],
 "get the centroids of the polygons": ["centroid"],
 # --- Geometry tools
 "simplify the geometry of the coastline": ["simplify_geometry"],
 "convert multipart to single parts": ["convert_to_singlepart"],
 "fix invalid geometries": ["fix_geometries"],
 "make voronoi polygons from the points": ["voronoi_polygons"],
 "delaunay triangulation of the points": ["delaunay_triangulation"],
 "extract the vertices of the roads": "GAP",
 "densify the lines": "GAP",
 "polygons to lines": "GAP",
 "minimum bounding box of each polygon": "GAP",
 # --- Analysis
 "count points in each polygon": [P, "spatial_join", "aggregate_data"],
 "statistics of the population field": ["field_statistics"],
 "nearest neighbour of each point": ["find_nearest_features", P],
 "join each school to the nearest road": [P, "find_nearest_features"],
 "sum the road length per district": ["aggregate_data", P, "calculate_length"],
 "k-means clustering of the points": [P],
 "dbscan clusters of the incidents": [P, "hotspot_analysis"],
 "hotspot analysis of the incidents": ["hotspot_analysis"],
 # --- Research tools / data management
 "create a 1 km grid over the district": [P, "generate_mapping_task_grid"],
 "select the points inside the polygon": ["select_by_location"],
 "select the districts where population is over 1000": ["select_by_attribute"],
 "invert the selection": ["invert_selection"],
 "merge the two road layers": ["merge_layers"],
 "join the table to the layer by the pcode field": ["join_by_attribute"],
 "spatial join the schools to the districts": ["spatial_join"],
 "reproject the layer to UTM 36N": ["reproject_layer"],
 "what is the crs of this layer": ["get_crs"],
 "check that the layers have the same crs": ["verify_crs_compatibility"],
 "find topology errors in the polygons": ["diagnose_topology"],
 "random points inside the polygon": "GAP",
 "split the layer by attribute": "GAP",
 "delete duplicate geometries": "GAP",
 # --- Table / attributes
 "open the attribute table": ["open_attribute_table"],
 "show the fields of the layer": ["get_attributes"],
 "how many features are in the layer": ["get_feature_count"],
 "add a field with the area in square kilometres": ["calculate_area", "field_calculator"],
 "calculate a new field from an expression": ["field_calculator"],
 "calculate the length of each road": ["calculate_length"],
 "undo the last change": ["undo_last_operation"],
 "highlight the selected features": ["highlight_features"],
 "zoom to the selected feature": ["zoom_to_feature"],
 # --- Raster
 "make a hillshade from the dem": ["hillshade", "create_shaded_relief"],
 "calculate the slope": ["slope_analysis"],
 "calculate the aspect": ["aspect_analysis"],
 "generate contour lines from the dem": ["generate_contours"],
 "clip the raster by the boundary layer": ["raster_clip"],
 "mosaic the raster tiles": ["mosaic_rasters"],
 "reclassify the raster into three classes": [P],
 "zonal statistics of the raster for each district": ["zonal_statistics", P],
 "sample the raster values at the points": [P],
 "interpolate a surface from the points": ["interpolate_surface", P],
 "make a heatmap of the points": ["apply_heatmap_style", P],
 "calculate ndvi": ["calculate_ndvi"],
 "supervised classification of the image": ["supervised_classification"],
 "raster calculator A minus B": "GAP",
 "polygonize the raster": "GAP",
 "rasterize the polygons": "GAP",
 "viewshed analysis": "GAP",
 # --- Styling / labels / layout / project
 "style the layer by the population field with graduated colours": ["apply_graduated_style"],
 "categorize the layer by type": ["apply_categorized_style"],
 "label the layer with the name field": ["apply_labels"],
 "change the layer colour to red": ["change_layer_color"],
 "set the layer transparency to 50 percent": ["set_layer_transparency"],
 "save the layer style": ["save_layer_style"],
 "load the style file onto the layer": ["load_layer_style"],
 "move the layer to the top": ["set_layer_order"],
 "hide the layer": ["toggle_visibility"],
 "rename the layer": ["rename_layer"],
 "remove the layer": ["remove_layer"],
 "zoom to the layer": ["zoom_to_layer"],
 "export the layer to a shapefile": ["export_layer"],
 "export the table to csv": ["export_to_csv", "export_layer"],
 "add a shapefile to the map": ["add_layer_from_path"],
 "load a csv with x and y columns as points": ["load_tabular_data_as_layer"],
 "add a point at these coordinates": ["add_point_layer"],
 "make a print layout and export a pdf": ["create_print_layout", "print_map"],
 "export an atlas of the districts": ["export_layout_atlas"],
 "save the project": ["save_project"],
 "open the project file": ["load_project"],
 "create a map theme": ["create_map_theme"],
 "add an openstreetmap basemap": "GAP",
 "georeference this scanned map": ["georeference_image"],
 "measure the distance between two points": "GAP",
}


class TestQgisVocabulary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = ToolRouter(TOOLS_SCHEMA)
        cls.registered = {t["function"]["name"] for t in TOOLS_SCHEMA}

    def _offered(self, phrase):
        return {t["function"]["name"] for t in self.router.filter_relevant_tools(phrase)}

    def test_every_named_tool_exists(self):
        for phrase, need in VOCAB.items():
            if need != "GAP":
                self.assertTrue(set(need) <= self.registered, f"{phrase!r}: {sorted(set(need) - self.registered)}")

    def test_phrases_with_a_tool_are_offered_it(self):
        missing = [f"{p!r} -> {n}" for p, n in VOCAB.items() if n != "GAP" and not (set(n) & self._offered(p))]
        self.assertEqual(missing, [], chr(10).join(missing))

    def test_phrases_without_a_tool_are_offered_a_fallback(self):
        missing = [p for p, n in VOCAB.items() if n == "GAP" and not ({"execute_pyqgis_script", "find_tools"} & self._offered(p))]
        self.assertEqual(missing, [], chr(10).join(missing))


if __name__ == "__main__":
    unittest.main()
