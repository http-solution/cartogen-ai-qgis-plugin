"""M1 (roadmap 2026-10-14): create layers from nothing and add web map layers.

Why this exists: the coverage audit (docs/qgis_coverage/actions_matrix.csv) found that the chat could not create an empty layer
with chosen fields, could not give the project a basemap, and could not add a WMS/WMTS/XYZ/WFS/ArcGIS service. Before 1.16.0-rc4
a script could do all three; the script route was closed for security, so each ability is a checked tool here.

Everything that builds a QGIS source string or validates user text is a pure function (no QGIS import), so it is tested offline.
The layer-creating tools need QGIS and are exercised by tests/test_data_source_tools_live.py, whose first CI run is its first
execution (written without a QGIS install).

Web layers: QGIS itself fetches the tiles/features, straight from the service to this machine; the plugin sends no project data.
Only https is accepted, not local/private addresses and not URLs with embedded credentials."""
import ipaddress
import os
import re
from urllib.parse import quote, urlparse

from ._paths import resolve_output_path
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# name -> (xyz url template, zmin, zmax, attribution). A fixed, vetted list: a basemap name is never turned into a URL by the model.
BASEMAPS = {
    "openstreetmap": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", 0, 19, "OpenStreetMap contributors (ODbL)"),
    "opentopomap": ("https://tile.opentopomap.org/{z}/{x}/{y}.png", 0, 17, "OpenTopoMap (CC-BY-SA), data OpenStreetMap contributors"),
    "esri satellite": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", 0, 19,
                       "Esri World Imagery"),
    "esri streets": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", 0, 19,
                     "Esri World Street Map"),
    "carto light": ("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png", 0, 20, "CARTO, data OpenStreetMap contributors"),
    "carto dark": ("https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", 0, 20, "CARTO, data OpenStreetMap contributors"),
}
_BASEMAP_WORDS = {
    "osm": "openstreetmap", "openstreetmap": "openstreetmap", "open street map": "openstreetmap", "street": "openstreetmap",
    "topo": "opentopomap", "topographic": "opentopomap", "opentopomap": "opentopomap", "terrain": "opentopomap",
    "satellite": "esri satellite", "imagery": "esri satellite", "aerial": "esri satellite", "esri satellite": "esri satellite",
    "esri streets": "esri streets", "esri street": "esri streets",
    "light": "carto light", "positron": "carto light", "carto light": "carto light",
    "dark": "carto dark", "carto dark": "carto dark",
}

_FIELD_TYPES = {
    "string": "string", "text": "string", "str": "string", "varchar": "string",
    "int": "integer", "integer": "integer", "number": "double", "long": "int8", "bigint": "int8", "int8": "int8",
    "double": "double", "float": "double", "real": "double", "decimal": "double",
    "date": "date", "datetime": "datetime", "timestamp": "datetime",
}
_GEOMETRY_TYPES = {
    "point": "Point", "points": "Point", "multipoint": "MultiPoint",
    "line": "LineString", "linestring": "LineString", "lines": "LineString", "multiline": "MultiLineString",
    "multilinestring": "MultiLineString",
    "polygon": "Polygon", "polygons": "Polygon", "multipolygon": "MultiPolygon",
    "none": "NoGeometry", "table": "NoGeometry", "nogeometry": "NoGeometry",
}
_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$")
_MAX_FIELDS = 100
_FILE_DRIVERS = {".gpkg": "GPKG", ".shp": "ESRI Shapefile", ".geojson": "GeoJSON"}


def normalise_geometry_type(text):
    """QGIS memory-layer geometry keyword for a user's word, or None."""
    return _GEOMETRY_TYPES.get(str(text or "").strip().lower().replace(" ", "").replace("-", "").replace("_", ""))


def build_field_specs(fields):
    """[{name, type}] -> ([uri parts 'field=name:type'], error). Names are checked because a name containing '&' or ':' would
    inject further parameters into the memory-layer source string."""
    if not fields:
        return [], None
    if not isinstance(fields, list) or len(fields) > _MAX_FIELDS:
        return None, f"fields must be a list of at most {_MAX_FIELDS} items like {{\"name\": \"id\", \"type\": \"integer\"}}."
    parts, seen = [], set()
    for item in fields:
        if not isinstance(item, dict) or "name" not in item:
            return None, "Each field needs a name, for example {\"name\": \"id\", \"type\": \"integer\"}."
        name = str(item["name"]).strip()
        if not _FIELD_NAME.match(name):
            return None, (f"Field name '{name[:40]}' is not allowed: use letters, digits, underscore and spaces, "
                          "starting with a letter or underscore.")
        if name.lower() in seen:
            return None, f"Field name '{name}' is repeated."
        seen.add(name.lower())
        kind = _FIELD_TYPES.get(str(item.get("type", "string")).strip().lower())
        if kind is None:
            return None, (f"Field type '{item.get('type')}' is not supported. Use one of: "
                          f"{', '.join(sorted(set(_FIELD_TYPES.values())))}.")
        parts.append(f"field={quote(name, safe='')}:{kind}")
    return parts, None


def memory_layer_uri(geometry, crs, field_parts):
    return "&".join([f"{geometry}?crs={quote(crs, safe=':')}", *field_parts]) if geometry != "NoGeometry" \
        else "&".join(["None?", *field_parts]).replace("None?&", "None?")


def resolve_basemap(name):
    """(key, (url, zmin, zmax, attribution)) for a user's basemap word, or (None, None)."""
    key = str(name or "").strip().lower()
    key = _BASEMAP_WORDS.get(key, key)
    return (key, BASEMAPS[key]) if key in BASEMAPS else (None, None)


def xyz_uri(url, zmin=0, zmax=19):
    return f"type=xyz&url={quote(url, safe=':/{}')}&zmax={int(zmax)}&zmin={int(zmin)}"


def validate_service_url(url):
    """None when the URL may be handed to QGIS, else the reason it may not."""
    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return "The URL could not be read."
    if parsed.scheme != "https":
        return "Only https:// service URLs are accepted."
    host = (parsed.hostname or "").lower()
    if not host:
        return "The URL has no host."
    if parsed.username or parsed.password:
        return "A URL with a user name or password inside it is not accepted; add credentials through QGIS Auth Manager instead."
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return "Local addresses are not accepted."
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified):
        return "Private and local IP addresses are not accepted."
    return None


_SERVICE_KINDS = ("xyz", "wms", "wmts", "wfs", "arcgis_feature")


def web_layer_source(kind, url, layer=None, crs=None, image_format=None, tile_matrix_set=None, style=None):
    """(provider, uri, is_raster, error) for a web service. Pure; see tests for the exact strings.

    Unverified against live services: the strings follow the QGIS 4.2 cookbook / data-provider conventions and are checked live
    only against what CI can reach (tests/test_data_source_tools_live.py checks that QGIS accepts the syntax, not that a service
    answers)."""
    kind = str(kind or "").strip().lower().replace(" ", "_")
    if kind == "arcgis" or kind == "arcgis_rest":
        kind = "arcgis_feature"
    if kind not in _SERVICE_KINDS:
        return None, None, None, f"service type must be one of {', '.join(_SERVICE_KINDS)}."
    problem = validate_service_url(url)
    if problem:
        return None, None, None, problem
    url = str(url).strip()
    if kind == "xyz":
        return "wms", xyz_uri(url), True, None
    if kind in ("wms", "wmts"):
        if not layer:
            return None, None, None, "A WMS/WMTS layer needs the service layer name (from its GetCapabilities)."
        if kind == "wmts" and not tile_matrix_set:
            return None, None, None, "A WMTS layer needs tile_matrix_set (for example EPSG:3857)."
        crs = crs or "EPSG:3857"
        fmt = image_format or "image/png"
        parts = ["contextualWMSLegend=0", f"crs={quote(crs, safe=':')}", "dpiMode=7", f"format={quote(fmt, safe='/')}",
                 f"layers={quote(str(layer), safe='')}", f"styles={quote(str(style or ''), safe='')}"]
        if kind == "wmts":
            parts.append(f"tileMatrixSet={quote(str(tile_matrix_set), safe=':')}")
        parts.append(f"url={quote(url, safe=':/')}")
        return "wms", "&".join(parts), True, None
    if kind in ("wfs", "arcgis_feature") and any("'" in str(v or "") for v in (url, layer, crs)):
        # These two source strings are single-quoted; a quote would end the value and let text add its own url='...' parameter.
        return None, None, None, "A quote character (') is not allowed in the URL, layer name or CRS of this service type."
    if kind == "wfs":
        if not layer:
            return None, None, None, "A WFS layer needs the feature type name (typename)."
        return "WFS", (f"pagingEnabled='true' restrictToRequestBBOX='1' srsname='{crs or 'EPSG:4326'}' "
                       f"typename='{layer}' url='{url}' version='auto'"), False, None
    return "arcgisfeatureserver", f"crs='{crs or 'EPSG:4326'}' url='{url}'", False, None


@register_tool(
    "create_empty_layer",
    "Create a new EMPTY vector layer (or a table with no geometry) with the fields you choose, ready for digitising. geometry_type: point, "
    "line, polygon, multipoint, multiline, multipolygon or none. fields: list of {name, type} with type string, integer, long, double, "
    "date or datetime. By default a scratch (in-memory) layer is added; give file_path ending .gpkg, .shp or .geojson to create a file.",
    {"type": "object", "properties": {
        "layer_name": {"type": "string"}, "geometry_type": {"type": "string"},
        "fields": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}}}},
        "crs": {"type": "string", "description": "e.g. EPSG:4326 (default)"},
        "file_path": {"type": "string", "description": "optional .gpkg/.shp/.geojson to create on disk"}},
     "required": ["layer_name", "geometry_type"]})
def create_empty_layer(layer_name, geometry_type, fields=None, crs=None, file_path=None, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from qgis.core import QgsCoordinateReferenceSystem
    geometry = normalise_geometry_type(geometry_type)
    if geometry is None:
        return {"error": f"Unknown geometry_type '{geometry_type}'. Use point, line, polygon, multipoint, multiline, multipolygon or none."}
    name = str(layer_name or "").strip()
    if not name:
        return {"error": "layer_name is required."}
    crs = (crs or "EPSG:4326").strip()
    if geometry != "NoGeometry" and not QgsCoordinateReferenceSystem(crs).isValid():
        return {"error": f"Unknown crs '{crs}'. Use a code such as EPSG:4326."}
    parts, problem = build_field_specs(fields)
    if problem:
        return {"error": problem}
    memory = QgsVectorLayer(memory_layer_uri(geometry, crs, parts), name, "memory")
    if not memory.isValid():
        return {"error": "QGIS could not create the layer from this specification."}
    result_layer, note = memory, "A scratch layer: it lives in the project only until it is saved elsewhere (ask to export it)."
    path = None
    if file_path:
        path = resolve_output_path(file_path)
        driver = _FILE_DRIVERS.get(os.path.splitext(path)[1].lower())
        if driver is None:
            return {"error": "file_path must end in .gpkg, .shp or .geojson."}
        from .export_tools import _write_vector, overwrite_preview, remember_written
        if not confirmed:
            preview = overwrite_preview("create_empty_layer", {"layer_name": layer_name, "geometry_type": geometry_type,
                                                               "fields": fields, "crs": crs, "file_path": file_path}, path)
            if preview:
                return preview
        written = _write_vector(memory, path, driver)
        if not (isinstance(written, dict) and written.get("success")):
            return written if isinstance(written, dict) else {"error": "The layer could not be written."}
        remember_written(path)
        result_layer = QgsVectorLayer(path, name, "ogr")
        if not result_layer.isValid():
            return {"error": f"The file was written but could not be opened: {path}"}
        note = f"Saved to {path}."
    QgsProject.instance().addMapLayer(result_layer)
    out = {"success": True, "layer_name": result_layer.name(), "geometry": geometry, "crs": crs if geometry != "NoGeometry" else None,
           "fields": [f.name() for f in result_layer.fields()], "feature_count": 0, "note": note}
    if path:
        out["output_path"] = path
    return out


@register_tool(
    "add_basemap",
    "Add a background map to the QGIS project from a fixed list: openstreetmap, opentopomap, satellite (Esri imagery), esri streets, "
    "carto light, carto dark. The layer is placed at the bottom of the layer tree. Tiles are loaded by QGIS directly from the provider.",
    {"type": "object", "properties": {"basemap": {"type": "string", "description": "openstreetmap, topo, satellite, esri streets, carto light, carto dark"}},
     "required": ["basemap"]})
def add_basemap(basemap):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    key, spec = resolve_basemap(basemap)
    if key is None:
        return {"error": f"Unknown basemap '{basemap}'. Available: {', '.join(sorted(BASEMAPS))}. For another tile service use add_web_layer."}
    url, zmin, zmax, attribution = spec
    title = key.title() if key != "openstreetmap" else "OpenStreetMap"
    existing = QgsProject.instance().mapLayersByName(title)
    if existing:
        return {"success": True, "layer_name": title, "reused_existing_layer": True,
                "message": f"The project already has a '{title}' layer; no duplicate was added."}
    layer = QgsRasterLayer(xyz_uri(url, zmin, zmax), title, "wms")
    if not layer.isValid():
        return {"error": f"QGIS could not open the {title} tile source."}
    project = QgsProject.instance()
    project.addMapLayer(layer, False)
    project.layerTreeRoot().insertLayer(-1, layer)   # -1 = last child = bottom of the tree, so data layers draw above it
    return {"success": True, "layer_name": title, "attribution": attribution,
            "note": "Tiles are fetched by QGIS from the provider when the map draws. Keep the attribution on published maps."}


@register_tool(
    "add_web_layer",
    "Add a web map or feature service to the project. service_type: xyz (tile URL with {z}/{x}/{y}), wms, wmts, wfs or arcgis_feature. "
    "Only https URLs are accepted. wms/wmts need layer (the service layer name), wmts also tile_matrix_set, wfs needs layer (typename).",
    {"type": "object", "properties": {
        "service_type": {"type": "string"}, "url": {"type": "string"}, "layer_name": {"type": "string"},
        "layer": {"type": "string", "description": "service layer / typename"}, "crs": {"type": "string"},
        "image_format": {"type": "string"}, "tile_matrix_set": {"type": "string"}, "style": {"type": "string"}},
     "required": ["service_type", "url"]})
def add_web_layer(service_type, url, layer_name=None, layer=None, crs=None, image_format=None, tile_matrix_set=None, style=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    provider, uri, is_raster, problem = web_layer_source(service_type, url, layer, crs, image_format, tile_matrix_set, style)
    if problem:
        return {"error": problem}
    name = layer_name or layer or urlparse(url).hostname or "web layer"
    web = QgsRasterLayer(uri, name, provider) if is_raster else QgsVectorLayer(uri, name, provider)
    if not web.isValid():
        return {"error": (f"QGIS could not open this {service_type} service. Check the URL and the layer name "
                          "(the service's GetCapabilities lists them).")}
    QgsProject.instance().addMapLayer(web)
    return {"success": True, "layer_name": web.name(), "service_type": service_type,
            "note": "QGIS fetches data from this service itself whenever the map draws; the service sees this computer's address."}
