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
