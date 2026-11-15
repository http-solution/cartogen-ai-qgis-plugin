"""M1 (roadmap completion plan, package C): data sources the chat could not open or produce before.

add_postgis_layer       a table or view from a PostGIS connection already saved in QGIS, as a layer
create_virtual_layer    a SQL (SQLite) query over the layers in the project, as a live virtual layer
load_layer_definition   .qlr file (layers with their styles) into the project
save_layer_definition   chosen layers to a .qlr file
package_layers_offline  chosen vector layers into one GeoPackage (native:package), styles included

Rules as elsewhere: nothing here writes outside the file the user named, an existing file is only replaced after a preview, model-written
SQL goes through data_layer_options.py, credentials of a saved connection are read by QGIS and never returned or logged. Written without
a QGIS install: tests/test_data_layer_tools_live.py reads everything back from real layers (CI's first run is its first execution;
add_postgis_layer needs the PostGIS service of the live job)."""
import os

from ._paths import resolve_output_path
from .data_layer_options import (identifier_violation, layer_definition_path_violation, package_path_violation, virtual_sql_violation)
from .registry import register_tool

try:
    from qgis.core import (QgsDataSourceUri, QgsLayerDefinition, QgsProject, QgsSettings, QgsVectorLayer,
                           QgsVirtualLayerDefinition)
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _vector_layers(names):
    layers, missing = [], []
    for name in names or []:
        found = [layer for layer in QgsProject.instance().mapLayersByName(name) if isinstance(layer, QgsVectorLayer)]
        (layers if found else missing).append(found[0] if found else name)
    return layers, missing


@register_tool(
    "add_postgis_layer",
    "Add a PostGIS table or view to the project as a layer, using a database connection already saved in QGIS (Browser panel > PostgreSQL). "
    "Give the connection name, schema and table; geometry_column and key_column are only needed when the table has several geometry "
    "columns or no primary key. Read-only data access: it adds a layer, it changes nothing in the database. Use execute_read_only_sql for "
    "a query instead of a whole table.",
    {"type": "object", "properties": {"connection_name": {"type": "string"}, "table": {"type": "string"}, "schema": {"type": "string"},
                                      "geometry_column": {"type": "string"}, "key_column": {"type": "string"}, "layer_name": {"type": "string"}},
     "required": ["connection_name", "table"]},
    keywords=[
        "postgis table", "postgis layer", "add the postgis", "load the postgis", "table from postgis", "postgresql table",
        "postgres table", "add the table from the database", "layer from the database", "from the postgis connection",
    ],
)
def add_postgis_layer(connection_name, table, schema="public", geometry_column=None, key_column=None, layer_name=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    checks = [("schema", schema or "public"), ("table", table)]
    checks += [(label, value) for label, value in (("geometry_column", geometry_column), ("key_column", key_column)) if value]
    for label, value in checks:
        problem = identifier_violation(label, value)
        if problem:
            return {"error": problem}
    if not connection_name or any(c in connection_name for c in "/\\"):
        return {"error": "connection_name must be the name of a saved PostgreSQL connection."}
    settings = QgsSettings()
    base = f"QGIS/connections-postgres/{connection_name}"
    host, database = settings.value(f"{base}/host", ""), settings.value(f"{base}/database", "")
    if not (host and database):
        known = sorted(_connection_names(settings))
        return {"error": f"PostGIS connection '{connection_name}' was not found in QGIS. Saved connections: {', '.join(known) or 'none'}."}
    uri = QgsDataSourceUri()
    authcfg = settings.value(f"{base}/authcfg", "")
    port = str(settings.value(f"{base}/port", "5432"))
    if authcfg:
        uri.setConnection(host, port, database, "", "", authConfigId=str(authcfg))
    else:
        uri.setConnection(host, port, database, settings.value(f"{base}/username", ""), settings.value(f"{base}/password", ""))
    uri.setDataSource(schema or "public", table, geometry_column or "", "", key_column or "")
    name = layer_name or f"{table}"
    layer = QgsVectorLayer(uri.uri(False), name, "postgres")
    if not layer.isValid():
        return {"error": f"QGIS could not open {schema or 'public'}.{table} on connection '{connection_name}' (wrong name, no permission, or "
                         "several geometry columns: then give geometry_column)."}
    QgsProject.instance().addMapLayer(layer)
    return {"success": True, "layer_name": layer.name(), "feature_count": layer.featureCount(), "crs": layer.crs().authid(),
            "editable_source": not layer.readOnly()}


def _connection_names(settings):
    settings.beginGroup("QGIS/connections-postgres")
    try:
        return settings.childGroups()
    finally:
        settings.endGroup()


@register_tool(
    "create_virtual_layer",
    "Create a virtual layer: a live SQL (SQLite/SpatiaLite) query over the layers in the project, for example SELECT a.name, count(b.id) AS "
    "n FROM districts a JOIN points b ON ST_Contains(a.geometry, b.geometry) GROUP BY a.name. Reference layers by their project layer name. "
    "Only a single SELECT is accepted; paths, URLs, comments, ATTACH and other statements are refused. The layer is not saved to disk and "
    "follows the source layers.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "sql": {"type": "string"},
                                      "geometry_column": {"type": "string", "description": "name of the geometry column in the result, if it is not detected"}},
     "required": ["layer_name", "sql"]},
    keywords=[
        "virtual layer", "create a virtual layer", "sql layer", "query layer", "spatialite query",
        "sqlite query over the layers", "join the layers with sql", "sql query over the layers", "live query layer",
    ],
)
def create_virtual_layer(layer_name, sql, geometry_column=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    problem = virtual_sql_violation(sql)
    if problem:
        return {"error": problem}
    if QgsProject.instance().mapLayersByName(layer_name):
        return {"error": f"A layer called '{layer_name}' already exists; choose another name."}
    definition = QgsVirtualLayerDefinition()
    definition.setQuery(sql.strip().rstrip(";"))
    if geometry_column:
        problem = identifier_violation("geometry_column", geometry_column)
        if problem:
            return {"error": problem}
        definition.setGeometryField(geometry_column)
    layer = QgsVectorLayer(definition.toString(), layer_name, "virtual")
    if not layer.isValid():
        detail = ""
        try:
            detail = f" ({layer.error().summary()})"
        except Exception:
            detail = ""
        return {"error": f"QGIS could not build the virtual layer{detail}. Check the layer names (they must match the project) and the SQL."}
    QgsProject.instance().addMapLayer(layer)
    return {"success": True, "layer_name": layer_name, "feature_count": layer.featureCount(),
            "fields": layer.fields().names(), "geometry": layer.isSpatial()}


@register_tool(
    "load_layer_definition",
    "Load a QGIS layer definition file (.qlr) into the project: the layers it holds come with their styles. The layers read their own data "
    "sources, so a .qlr is only as safe as the files and services it points to.",
    {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
    keywords=[
        "load the qlr", "open the qlr", "qlr file", "layer definition file", "load a layer definition",
        "import the layer definition",
    ],
)
def load_layer_definition(file_path):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    path = resolve_output_path(file_path)
    problem = layer_definition_path_violation(path, must_exist=True)
    if problem:
        return {"error": problem}
    project = QgsProject.instance()
    before = set(project.mapLayers())
    result = QgsLayerDefinition.loadLayerDefinition(path, project, project.layerTreeRoot())
    ok, message = (result[0], result[1]) if isinstance(result, (tuple, list)) else (bool(result), "")
    added = [project.mapLayer(i) for i in set(project.mapLayers()) - before]
    if not ok or not added:
        return {"error": f"The definition file could not be loaded{': ' + str(message) if message else ''}."}
    invalid = [layer.name() for layer in added if not layer.isValid()]
    out = {"success": True, "layers_added": sorted(layer.name() for layer in added)}
    if invalid:
        out["warning"] = f"These layers were added but their data source cannot be read: {', '.join(sorted(invalid))}."
    return out


@register_tool(
    "save_layer_definition",
    "Save chosen layers of the project, with their styles, to a QGIS layer definition file (.qlr) that can be loaded into other projects. "
    "layer_names is the list of layers. An existing file is only replaced after confirmation.",
    {"type": "object", "properties": {"layer_names": {"type": "array", "items": {"type": "string"}}, "file_path": {"type": "string"}},
     "required": ["layer_names", "file_path"]},
    keywords=[
        "save as qlr", "save the layer definition", "export the layer definition", "save layers as qlr", "layer definition for",
    ],
)
def save_layer_definition(layer_names, file_path, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    path = resolve_output_path(file_path)
    problem = layer_definition_path_violation(path, must_exist=False)
    if problem:
        return {"error": problem}
    if not layer_names:
        return {"error": "Give at least one layer name."}
    root = QgsProject.instance().layerTreeRoot()
    nodes, missing = [], []
    for name in layer_names:
        found = QgsProject.instance().mapLayersByName(name)
        node = root.findLayer(found[0].id()) if found else None
        (nodes if node else missing).append(node or name)
    if missing:
        return {"error": f"Layer(s) not found in the project: {', '.join(missing)}."}
    from .export_tools import overwrite_preview, remember_written
    if not confirmed:
        preview = overwrite_preview("save_layer_definition", {"layer_names": list(layer_names), "file_path": file_path}, path)
        if preview:
            return preview
    result = QgsLayerDefinition.exportLayerDefinition(path, nodes)
    ok, message = (result[0], result[1]) if isinstance(result, (tuple, list)) else (bool(result), "")
    if not ok or not os.path.isfile(path):
        return {"error": f"The definition file was not written{': ' + str(message) if message else ''}."}
    remember_written(path)
    return {"success": True, "file_path": path, "layers": list(layer_names)}


@register_tool(
    "package_layers_offline",
    "Package vector layers into ONE GeoPackage file for offline use or hand-over, keeping their styles and metadata (QGIS native:package). "
    "layer_names is the list of vector layers; file_path ends in .gpkg. only_selected packs just the selected features. An existing file "
    "is only replaced after confirmation. Raster layers are not packaged.",
    {"type": "object", "properties": {"layer_names": {"type": "array", "items": {"type": "string"}}, "file_path": {"type": "string"},
                                      "only_selected": {"type": "boolean"}}, "required": ["layer_names", "file_path"]},
    keywords=[
        "package the layers", "package the project layers", "package for offline", "offline package",
        "package into one geopackage", "pack the layers into a geopackage", "use offline", "take the layers offline",
        "package layers", "bundle the project", "bundle the layers", "bundle the data", "package the data",
        "package the project", "share the project data", "share the layers", "zip the layers", "zip the project data",
        "hand over the data", "send the project data",
    ],
)
def package_layers_offline(layer_names, file_path, only_selected=False, confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    path = resolve_output_path(file_path)
    problem = package_path_violation(path)
    if problem:
        return {"error": problem}
    layers, missing = _vector_layers(layer_names)
    if missing or not layers:
        return {"error": f"Vector layer(s) not found: {', '.join(missing) or 'none given'}. Raster layers cannot be packaged."}
    from .export_tools import overwrite_preview, remember_written
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    if exists and not confirmed:
        preview = overwrite_preview("package_layers_offline",
                                    {"layer_names": list(layer_names), "file_path": file_path, "only_selected": only_selected}, path)
        if preview:
            return preview
    from ... import _background_processing as _bg
    from .raster_tools import _run_in_background
    try:
        result = _run_in_background("native:package", {"LAYERS": layers, "OUTPUT": path, "OVERWRITE": exists, "SAVE_STYLES": True,
                                                       "SAVE_METADATA": True, "SELECTED_FEATURES_ONLY": bool(only_selected),
                                                       "EXPORT_RELATED_LAYERS": False})
    except _bg.AnalysisCancelledError:
        return {"error": "Stopped before the package was finished.", "cancelled": True}
    except Exception as e:
        return {"error": f"native:package failed: {e}"}
    if not os.path.isfile(path):
        return {"error": "The package was not written."}
    remember_written(path)
    packed = (result or {}).get("OUTPUT_LAYERS") or []
    from ._sensitivity_notes import protected_layer_notes
    out = {"success": True, "file_path": path, "layers_packaged": len(packed) or len(layers), "layers": [layer.name() for layer in layers]}
    notes = protected_layer_notes(layers, "its data is now in this package file; confirm sharing it is intended. Advisory only, nothing was blocked.")
    if notes:
        out["warning"] = " ".join(notes)
    return out

