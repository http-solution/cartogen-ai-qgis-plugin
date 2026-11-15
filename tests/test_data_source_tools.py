"""Pure logic of the M1 data-source tools (tools/data_source_tools.py): field specs, memory-layer and web-service source strings, URL
screening, basemap names, and that the new tools are offered for the plain requests that need them. No QGIS."""
import unittest

from cartogen_ai.core.agent.tools import TOOLS_SCHEMA
from cartogen_ai.core.agent.tools import data_source_tools as ds
from cartogen_ai.core.services.tool_router import ToolRouter


class TestFieldSpecs(unittest.TestCase):
    def test_types_are_normalised(self):
        parts, err = ds.build_field_specs([{"name": "id", "type": "int"}, {"name": "Name", "type": "text"},
                                           {"name": "pop", "type": "bigint"}, {"name": "when", "type": "timestamp"}])
        self.assertIsNone(err)
        self.assertEqual(parts, ["field=id:integer", "field=Name:string", "field=pop:int8", "field=when:datetime"])

    def test_missing_type_defaults_to_string(self):
        self.assertEqual(ds.build_field_specs([{"name": "note"}])[0], ["field=note:string"])

    def test_a_name_that_would_inject_a_parameter_is_refused(self):
        for bad in ("a&crs=EPSG:3857", "x:integer", "1abc", "", "a" * 80):
            parts, err = ds.build_field_specs([{"name": bad, "type": "string"}])
            self.assertIsNone(parts, bad)
            self.assertTrue(err, bad)

    def test_duplicates_unknown_types_and_oversize_lists_are_refused(self):
        self.assertIsNotNone(ds.build_field_specs([{"name": "a"}, {"name": "A"}])[1])
        self.assertIsNotNone(ds.build_field_specs([{"name": "a", "type": "blob"}])[1])
        self.assertIsNotNone(ds.build_field_specs([{"name": f"f{i}"} for i in range(101)])[1])

    def test_no_fields_is_fine(self):
        self.assertEqual(ds.build_field_specs(None), ([], None))


class TestGeometryAndMemoryUri(unittest.TestCase):
    def test_words(self):
        for word, expected in [("polygon", "Polygon"), ("Polygons", "Polygon"), ("line", "LineString"), ("multi-polygon", "MultiPolygon"),
                               ("point", "Point"), ("table", "NoGeometry"), ("none", "NoGeometry")]:
            self.assertEqual(ds.normalise_geometry_type(word), expected, word)
        self.assertIsNone(ds.normalise_geometry_type("blob"))

    def test_memory_uri(self):
        self.assertEqual(ds.memory_layer_uri("Polygon", "EPSG:4326", ["field=a:string"]), "Polygon?crs=EPSG:4326&field=a:string")
        self.assertEqual(ds.memory_layer_uri("NoGeometry", "EPSG:4326", ["field=a:string"]), "None?field=a:string")


class TestBasemaps(unittest.TestCase):
    def test_everyday_words_resolve_to_the_fixed_list(self):
        for word, key in [("osm", "openstreetmap"), ("OpenStreetMap", "openstreetmap"), ("satellite", "esri satellite"),
                          ("topo", "opentopomap"), ("dark", "carto dark")]:
            self.assertEqual(ds.resolve_basemap(word)[0], key, word)
        self.assertEqual(ds.resolve_basemap("a url https://evil.example/{z}")[0], None)

    def test_every_basemap_is_https_with_xyz_placeholders(self):
        for key, (url, zmin, zmax, attribution) in ds.BASEMAPS.items():
            self.assertIsNone(ds.validate_service_url(url), key)
            self.assertTrue(all(token in url for token in ("{z}", "{x}", "{y}")), key)
            self.assertLessEqual(zmin, zmax)
            self.assertTrue(attribution)

    def test_xyz_uri_keeps_the_placeholders_unescaped(self):
        self.assertEqual(ds.xyz_uri("https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
                         "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0")


class TestServiceUrlScreening(unittest.TestCase):
    def test_accepts_public_https(self):
        self.assertIsNone(ds.validate_service_url("https://example.org/wms?map=a"))

    def test_refuses_everything_else(self):
        for url in ("http://example.org/wms", "ftp://example.org", "file:///etc/passwd", "https://localhost/wms", "https://127.0.0.1/x",
                    "https://192.168.1.5/x", "https://10.0.0.2/x", "https://169.254.169.254/latest", "https://user:pw@example.org/x",
                    "https://printer.local/x", "https:///nohost", "", None):
            self.assertIsNotNone(ds.validate_service_url(url), url)


class TestWebLayerSource(unittest.TestCase):
    def test_wms(self):
        provider, uri, raster, err = ds.web_layer_source("wms", "https://x.org/wms?map=a", "roads")
        self.assertEqual((provider, raster, err), ("wms", True, None))
        self.assertIn("layers=roads", uri)
        self.assertIn("url=https://x.org/wms%3Fmap%3Da", uri)
        self.assertIn("crs=EPSG:3857", uri)

    def test_wmts_needs_a_matrix_set_and_wms_needs_a_layer(self):
        self.assertIsNotNone(ds.web_layer_source("wmts", "https://x.org/w", "l")[3])
        self.assertIsNotNone(ds.web_layer_source("wms", "https://x.org/w")[3])
        self.assertIn("tileMatrixSet=EPSG:3857", ds.web_layer_source("wmts", "https://x.org/w", "l", tile_matrix_set="EPSG:3857")[1])

    def test_wfs_and_arcgis(self):
        provider, uri, raster, err = ds.web_layer_source("wfs", "https://x.org/wfs", "ns:roads")
        self.assertEqual((provider, raster, err), ("WFS", False, None))
        self.assertIn("typename='ns:roads'", uri)
        self.assertEqual(ds.web_layer_source("arcgis", "https://x.org/arcgis/rest/services/a/FeatureServer/0")[0], "arcgisfeatureserver")

    def test_unknown_type_and_bad_url(self):
        self.assertIsNotNone(ds.web_layer_source("ftp", "https://x.org")[3])
        self.assertIsNotNone(ds.web_layer_source("xyz", "http://x.org/{z}/{x}/{y}.png")[3])

    def test_a_quote_cannot_break_out_of_the_single_quoted_source_string(self):
        self.assertIsNotNone(ds.web_layer_source("wfs", "https://x.org/wfs", "a' url='https://evil.example")[3])
        self.assertIsNotNone(ds.web_layer_source("arcgis", "https://x.org/a'b")[3])
        self.assertIsNotNone(ds.web_layer_source("wfs", "https://x.org/wfs", "l", crs="EPSG:4326' x='")[3])


class TestOfferedForPlainRequests(unittest.TestCase):
    ROWS = {  # noqa: RUF012
        "create an empty polygon layer with fields name and population": "create_empty_layer",
        "create a new geopackage layer for polygons": "create_empty_layer",
        "make a scratch layer for points": "create_empty_layer",
        "add an openstreetmap basemap": "add_basemap",
        "add a satellite background": "add_basemap",
        "add the wms layer from this url": "add_web_layer",
        "add a wfs layer": "add_web_layer",
        "add an xyz tile layer": "add_web_layer",
        "load the roads table from the geopackage": "add_layer_from_path",
        "look at the map": "inspect_canvas_visually",
    }

    def test_each_phrase_is_offered_its_tool(self):
        router = ToolRouter(TOOLS_SCHEMA)
        missing = {q: t for q, t in self.ROWS.items() if t not in {x["function"]["name"] for x in router.filter_relevant_tools(q)}}
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()


class TestBrokenLayerRepairHelpers(unittest.TestCase):
    def test_source_file_path(self):
        self.assertEqual(ds.source_file_path("/data/a.gpkg|layername=roads"), "/data/a.gpkg")
        self.assertEqual(ds.source_file_path("C:/d/roads.shp"), "C:/d/roads.shp")
        for not_a_file in ("https://x.org/a.geojson", "dbname='x' host=y table=\"t\"", "memory?geometry=Point", "/vsizip/a.zip",
                           "type=xyz&url=https://a/{z}", "", None):
            self.assertIsNone(ds.source_file_path(not_a_file), not_a_file)

    def test_replacement_source_keeps_the_suffix(self):
        self.assertEqual(ds.replacement_source("/old/a.gpkg|layername=roads", "/new/a.gpkg"), "/new/a.gpkg|layername=roads")
        self.assertEqual(ds.replacement_source("/old/a.shp", "/new/a.shp"), "/new/a.shp")

    def test_candidates_are_found_case_insensitively_and_bounded(self):
        import os
        import tempfile
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "a", "b"))
        for rel in ("a/Roads.SHP", "a/b/roads.shp", "other.txt"):
            open(os.path.join(root, rel), "w").close()
        found = ds.find_file_candidates("roads.shp", [root])
        self.assertEqual([os.path.relpath(p, root) for p in found], sorted([os.path.join("a", "Roads.SHP"), os.path.join("a", "b", "roads.shp")]))
        self.assertEqual([os.path.relpath(p, root) for p in ds.find_file_candidates("roads.shp", [root], max_depth=1)],
                         [os.path.join("a", "Roads.SHP")])   # depth 1 reaches a/ but not a/b/
        self.assertEqual(ds.find_file_candidates("roads.shp", [os.path.join(root, "missing"), None]), [])
        self.assertLessEqual(len(ds.find_file_candidates("roads.shp", [root], max_files=1)), 1)


class TestSaveAsPlan(unittest.TestCase):
    def test_all_fields_by_default_and_case_insensitive_subset(self):
        self.assertEqual(ds.save_as_plan(None, ["a", "b", "c"]), ([0, 1, 2], []))
        self.assertEqual(ds.save_as_plan(["C", "a"], ["a", "b", "c"]), ([2, 0], []))

    def test_unknown_fields_are_reported(self):
        self.assertEqual(ds.save_as_plan(["a", "zz"], ["a", "b"]), ([0], ["zz"]))


class TestArchiveSource(unittest.TestCase):
    def test_zip_is_read_in_place_and_other_files_are_unchanged(self):
        from cartogen_ai.core.agent.tools.vector_tools import archive_source
        self.assertEqual(archive_source("/t/x.zip", ".zip"), "/vsizip//t/x.zip")
        self.assertEqual(archive_source("C:\\d\\x.zip", ".zip"), "/vsizip/C:/d/x.zip")
        self.assertEqual(archive_source("/t/x.kmz", ".kmz"), "/t/x.kmz")
        self.assertEqual(archive_source("/t/x.shp", ".shp"), "/t/x.shp")
        self.assertEqual(archive_source("/vsizip//t/x.zip", ".zip"), "/vsizip//t/x.zip")


class TestOfferedForRepairAndSaveAs(unittest.TestCase):
    def test_phrases(self):
        router = ToolRouter(TOOLS_SCHEMA)
        rows = {"which layers are broken": "find_broken_layers", "fix the broken layer paths": "repair_layer_source",
                "relink the layer to the new folder": "repair_layer_source",
                "save the layer as geopackage in epsg 4326 with only the name field": "save_layer_as",
                "open the zipped shapefile": "add_layer_from_path"}
        offered = {q: {x["function"]["name"] for x in router.filter_relevant_tools(q)} for q in rows}
        self.assertEqual({q: t for q, t in rows.items() if t not in offered[q]}, {})
