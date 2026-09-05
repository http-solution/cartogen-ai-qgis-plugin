# -*- coding: utf-8 -*-
"""
Export & Reporting Tools for Cartogen AI.
"""

import os
import json
import tempfile
from .registry import register_tool
from ._qgis_enum_compat import resolve_qgis_enum

try:
    from qgis.core import (
        QgsProject, QgsVectorFileWriter, QgsCoordinateTransformContext,
        QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    )
    from qgis.utils import iface
    QGIS_AVAILABLE = True
    # QGIS 4.x/Qt6 scopes this under QgsVectorFileWriter.WriterError.NoError;
    # QGIS 3.x/Qt5 exposes it flat as QgsVectorFileWriter.NoError. Resolved
    # once at import time rather than assuming one form -- see
    # _qgis_enum_compat.py.
    _VFW_NO_ERROR = resolve_qgis_enum(QgsVectorFileWriter, "WriterError", "NoError")
except ImportError:
    QGIS_AVAILABLE = False
    iface = None
    _VFW_NO_ERROR = None


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _write_vector(layer, output_path, driver_name, layer_options=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver_name
        options.fileEncoding = "UTF-8"
        if layer_options:
            options.layerOptions = layer_options

        error, message = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer,
            output_path,
            QgsCoordinateTransformContext(),
            options,
        )
        if error != _VFW_NO_ERROR:
            return {"error": f"Export failed: {message} (code {error})"}
        return {"success": True, "output_path": output_path}
    except Exception as e:
        return {"error": f"_write_vector failed: {e}"}


@register_tool("export_layer", "Export vector layer to file format (ESRI Shapefile, GeoJSON, GPKG, KML).", {"type": "object", "properties": {"layer_name": {"type": "string"}, "output_path": {"type": "string"}, "format": {"type": "string"}}, "required": ["layer_name", "output_path", "format"]})
def export_layer(layer_name, output_path, format):
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    fmt_map = {
        "shp": "ESRI Shapefile",
        "shapefile": "ESRI Shapefile",
        "geojson": "GeoJSON",
        "gpkg": "GPKG",
        "geopackage": "GPKG",
        "kml": "KML",
    }
    driver = fmt_map.get(format.lower(), format)
    return _write_vector(layer, output_path, driver)


@register_tool("export_to_csv", "Export layer attribute table to CSV file.", {"type": "object", "properties": {"layer_name": {"type": "string"}, "output_path": {"type": "string"}}, "required": ["layer_name", "output_path"]})
def export_to_csv(layer_name, output_path):
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    return _write_vector(
        layer,
        output_path,
        "CSV",
        layer_options=["GEOMETRY=AS_WKT", "SEPARATOR=COMMA"],
    )


@register_tool("print_map", "Export current QGIS map canvas view to PNG image.", {"type": "object", "properties": {"output_path": {"type": "string"}}, "required": ["output_path"]})
def print_map(output_path):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if iface is None:
        return {"error": "QGIS interface not available"}
    try:
        iface.mapCanvas().saveAsImage(output_path)
        return {"success": True, "output_path": output_path}
    except Exception as e:
        return {"error": f"print_map failed: {e}"}


def _layer_provenance_entries(source_layers):
    """For each named layer, returns lineage.py's tracked history (if any) --
    what tool created/modified it, with what parameters and source layers,
    and when (see agent/lineage.py and agent.py's automatic tag_layer_lineage
    calls on every successful layer-producing tool). Powers the optional
    provenance section on generate_report/generate_spatial_report.

    A layer that isn't found, or has no tracked history (loaded directly
    rather than created/modified by an agent tool), is reported as such
    rather than silently omitted -- a report implying full provenance when a
    layer's actual origin is unknown would be worse than no provenance
    section at all."""
    if not source_layers:
        return []
    from ..lineage import get_layer_lineage
    entries = []
    for name in source_layers:
        layer = _find_layer_by_name(name)
        if layer is None:
            entries.append({"layer": name, "found": False, "history": []})
            continue
        entries.append({"layer": name, "found": True, "history": get_layer_lineage(layer)})
    return entries


def _format_lineage_entry(h):
    sources = f" (from: {', '.join(h['sources'])})" if h.get("sources") else ""
    params = h.get("params") or {}
    params_str = f" [{', '.join(f'{k}={v}' for k, v in params.items())}]" if params else ""
    return f"{h.get('timestamp', 'unknown time')} -- {h.get('tool', 'unknown tool')}{sources}{params_str}"


@register_tool(
    "generate_report",
    "Generate a Word (.docx) report document saved on Desktop. Optionally pass source_layers to "
    "append a 'Data Sources & Provenance' section -- what tool created/modified each layer, with "
    "what parameters and source layers, and when -- pulled from tracked lineage. Gives a report's "
    "audience (often not QGIS users, e.g. a fund-allocation committee) something to check a "
    "spatial claim against instead of just asserting it.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"},
            "source_layers": {"type": "array", "items": {"type": "string"}, "description": "Optional layer names to append a provenance/lineage section for."},
        },
        "required": ["title", "content"],
    },
)
def generate_report(title, content, source_layers=None):
    try:
        from docx import Document
        doc = Document()
        doc.add_heading(str(title), 0)
        for paragraph in str(content).split("\n\n"):
            doc.add_paragraph(paragraph)

        entries = _layer_provenance_entries(source_layers)
        if entries:
            doc.add_heading("Data Sources & Provenance", level=1)
            for entry in entries:
                doc.add_heading(entry["layer"], level=2)
                if not entry["found"]:
                    doc.add_paragraph("Layer not found in the current project.")
                elif not entry["history"]:
                    doc.add_paragraph("No tracked lineage -- loaded directly, not created/modified by an agent tool.")
                else:
                    for h in entry["history"]:
                        doc.add_paragraph(_format_lineage_entry(h), style="List Bullet")

        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in str(title)).strip() or "report"
        out_path = os.path.join(desktop, f"{safe_title}.docx")
        doc.save(out_path)
        return {"success": True, "path": out_path}
    except ImportError:
        return {
            "error": (
                "python-docx not installed. Run in OSGeo4W Shell: "
                "python -m pip install python-docx"
            )
        }
    except Exception as e:
        return {"error": f"Error: {e}"}


@register_tool(
    "generate_spatial_report",
    "Generate a markdown report to present insights in chat. Optionally pass source_layers to "
    "append a 'Data Sources & Provenance' section -- what tool created/modified each layer, with "
    "what parameters and source layers, and when -- pulled from tracked lineage. Gives a report's "
    "audience (often not QGIS users, e.g. a fund-allocation committee) something to check a "
    "spatial claim against instead of just asserting it.",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "insights": {"type": "string"},
            "source_layers": {"type": "array", "items": {"type": "string"}, "description": "Optional layer names to append a provenance/lineage section for."},
        },
        "required": ["title", "insights"],
    },
)
def generate_spatial_report(title, insights, source_layers=None):
    report = f"## 📊 Spatial Report: {title}\n\n{insights}"

    entries = _layer_provenance_entries(source_layers)
    if entries:
        lines = ["", "### Data Sources & Provenance"]
        for entry in entries:
            if not entry["found"]:
                lines.append(f"- **{entry['layer']}**: layer not found in the current project.")
            elif not entry["history"]:
                lines.append(f"- **{entry['layer']}**: no tracked lineage -- loaded directly, not created/modified by an agent tool.")
            else:
                lines.append(f"- **{entry['layer']}**:")
                for h in entry["history"]:
                    lines.append(f"  - {_format_lineage_entry(h)}")
        report += "\n\n" + "\n".join(lines)

    return {"message": "Report generated successfully.", "report": report}


_MAX_DASHBOARD_POPUP_FIELDS = 15


def _iter_geojson_coords(geometry):
    """Yields (lon, lat) pairs from any GeoJSON geometry, including Multi*
    and GeometryCollection, for map-bounds computation. Coordinates nest at
    different depths per geometry type (Point=[x,y], Polygon=[[[x,y],...]],
    etc.), so this recurses on nesting depth instead of hardcoding a level
    per type."""
    if not geometry:
        return
    if geometry.get("type") == "GeometryCollection":
        for g in geometry.get("geometries", []):
            yield from _iter_geojson_coords(g)
        return
    yield from _iter_geojson_coord_pairs(geometry.get("coordinates"))


def _iter_geojson_coord_pairs(coords):
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield coords[0], coords[1]
        return
    for c in coords:
        yield from _iter_geojson_coord_pairs(c)


def _humanize_field_name(name):
    """Mechanical, no-semantic-guessing fallback label for a popup field that
    wasn't given an explicit alias: snake_case/kebab-case -> Title Case With
    Spaces (e.g. 'food_insec_pct' -> 'Food Insec Pct'). Doesn't expand
    abbreviations or infer meaning -- a caller that knows the domain (the
    agent, not this tool) should pass popup_labels explicitly for a genuinely
    readable label (e.g. 'Food Insecurity (IPC 3+) %'); this is only the
    floor, not a substitute for that."""
    words = [w for w in str(name).replace("-", "_").split("_") if w]
    return " ".join(w.capitalize() for w in words) if words else str(name)


def _build_dashboard_html(layers, title=None):
    """Pure HTML-generation core, no QGIS needed -- takes already-extracted
    GeoJSON per layer and builds a Folium/Leaflet dashboard: one togglable
    overlay per layer, popups on the requested fields, and an optional
    branca choropleth color scale driven by color_field (e.g. a severity
    score). Split out from generate_html_dashboard so this can be tested with
    synthetic GeoJSON, without needing a live QGIS session to produce it --
    same split as _compute_severity_index vs. calculate_severity_index.

    layers: list of {"name": str, "geojson": dict, "popup_fields": list[str]|None,
    "popup_labels": dict[str,str]|None, "color_field": str|None}. popup_labels
    maps a raw field name to the label shown in the popup; any popup field
    without an explicit entry falls back to _humanize_field_name.
    Returns {"html": <str>, "warnings": [...]} or {"error": <str>}."""
    try:
        import folium
        import branca.colormap as branca_cm
    except ImportError:
        return {
            "error": (
                "folium is required for generate_html_dashboard. Install via qpip, or in the "
                "OSGeo4W Shell: python -m pip install folium"
            )
        }

    if not layers:
        return {"error": "layers must not be empty."}

    all_lats, all_lons = [], []
    for layer in layers:
        for feat in layer.get("geojson", {}).get("features", []):
            for lon, lat in _iter_geojson_coords(feat.get("geometry")):
                all_lats.append(lat)
                all_lons.append(lon)

    m = folium.Map()
    if all_lats and all_lons:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])
    else:
        m.location, m.zoom_start = [0, 0], 2

    warnings = []
    for layer in layers:
        name = layer["name"]
        geojson = layer.get("geojson", {})
        features = geojson.get("features", [])

        popup_fields = layer.get("popup_fields")
        if not popup_fields and features:
            popup_fields = list(features[0].get("properties", {}).keys())
        if popup_fields and len(popup_fields) > _MAX_DASHBOARD_POPUP_FIELDS:
            warnings.append(
                f"'{name}': popup_fields truncated to the first {_MAX_DASHBOARD_POPUP_FIELDS} of "
                f"{len(popup_fields)} -- pass popup_fields explicitly to control which show."
            )
            popup_fields = popup_fields[:_MAX_DASHBOARD_POPUP_FIELDS]
        if popup_fields and features:
            # A field missing from a feature's properties would raise inside
            # GeoJsonPopup and break the whole layer's rendering, not just
            # that one popup -- so only fields present on the first feature
            # (assumed representative of the layer's schema) are kept.
            present = set(features[0].get("properties", {}).keys())
            popup_fields = [f for f in popup_fields if f in present]

        color_field = layer.get("color_field")
        style_function = None
        colormap = None
        if color_field and features:
            values = [
                f["properties"][color_field] for f in features
                if isinstance(f.get("properties", {}).get(color_field), (int, float))
            ]
            if values:
                colormap = branca_cm.LinearColormap(
                    ["#1a9850", "#fee08b", "#d73027"], vmin=min(values), vmax=max(values),
                )

                def style_function(feat, _cmap=colormap, _field=color_field):
                    val = feat["properties"].get(_field)
                    return {
                        "fillColor": _cmap(val) if isinstance(val, (int, float)) else "#999999",
                        "color": "black",
                        "weight": 1,
                        "fillOpacity": 0.6,
                    }
            else:
                warnings.append(f"'{name}': color_field '{color_field}' has no numeric values -- rendered without choropleth coloring.")

        gj_kwargs = {"name": name}
        if popup_fields:
            popup_labels = layer.get("popup_labels") or {}
            aliases = [popup_labels.get(f, _humanize_field_name(f)) for f in popup_fields]
            gj_kwargs["popup"] = folium.GeoJsonPopup(fields=popup_fields, aliases=aliases)
        if style_function:
            gj_kwargs["style_function"] = style_function
        folium.GeoJson(geojson, **gj_kwargs).add_to(m)

        if colormap is not None:
            colormap.caption = color_field
            colormap.add_to(m)

    folium.LayerControl().add_to(m)

    if title:
        import html as html_module
        title_html = (
            '<h3 style="position:fixed;top:10px;left:60px;z-index:9999;background:white;'
            f'padding:4px 10px;border-radius:4px;">{html_module.escape(str(title))}</h3>'
        )
        m.get_root().html.add_child(folium.Element(title_html))

    return {"html": m.get_root().render(), "warnings": warnings}


def _write_layer_geojson_wgs84(layer, output_path):
    """Writes a vector layer to a GeoJSON file reprojected to EPSG:4326
    (WGS84) -- Leaflet/Folium expects lon/lat coordinates, and GeoJSON's own
    spec (RFC 7946) requires WGS84, so a layer in any other CRS (e.g. a UTM
    projection) must be reprojected, not just relabeled -- writing it out
    verbatim would place every feature at nonsensical coordinates on the
    dashboard's basemap. Kept separate from _write_vector above (which
    intentionally preserves a layer's native CRS for export_layer/
    export_to_csv) rather than changing that already-tested function's
    behavior."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GeoJSON"
        options.fileEncoding = "UTF-8"
        if layer.crs() != wgs84:
            options.ct = QgsCoordinateTransform(layer.crs(), wgs84, QgsProject.instance())

        error, message = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer, output_path, QgsCoordinateTransformContext(), options,
        )
        if error != _VFW_NO_ERROR:
            return {"error": f"GeoJSON export failed: {message} (code {error})"}
        return {"success": True}
    except Exception as e:
        return {"error": f"_write_layer_geojson_wgs84 failed: {e}"}


@register_tool(
    "generate_html_dashboard",
    "Generate an interactive HTML situation dashboard (Leaflet/Folium map with layer toggles and "
    "popups) from one or more vector layers already in the project -- e.g. a severity-index layer "
    "plus facility points plus admin boundaries, click-to-inspect the indicator values behind a "
    "severity score. This is the highest-visibility deliverable for a non-QGIS audience "
    "(fund-allocation committees, donors) -- prefer it over a static print layout/report when the "
    "audience will interact with the map themselves. The viewer needs internet access at view time "
    "(see the result's connectivity_note for the exact wording to relay). Each layer is reprojected "
    "to WGS84 automatically. Vector layers only -- not for raster layers. Optionally pass "
    "color_field per layer (e.g. a severity score field) to choropleth-color it. IMPORTANT: always "
    "pass popup_labels for any field whose raw name isn't already plain language (e.g. abbreviated or "
    "coded field names like 'food_insec_pct', 'wash_depriv_pct') -- give each one a real "
    "human-readable label (e.g. 'Food Insecurity (IPC 3+) %', 'WASH Service Deprivation %') using "
    "your own knowledge of what the field means. Fields left unlabeled fall back to a purely "
    "mechanical Title Case of the raw name (e.g. 'food_insec_pct' -> 'Food Insec Pct'), which is "
    "not real language and should not be relied on for a field whose meaning you actually know.",
    {
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "popup_fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to show in this layer's popup. Defaults to all fields (capped)."},
                        "popup_labels": {"type": "object", "description": "Optional {field: human-readable label} shown in the popup instead of the raw field name (e.g. {'food_insec_pct': 'Food Insecurity (IPC 3+) %'}). Strongly recommended for any non-plain-language field name."},
                        "color_field": {"type": "string", "description": "Optional numeric field to choropleth-color this layer by (e.g. a severity score)."},
                    },
                    "required": ["layer_name"],
                },
                "description": "One or more layers to include, each rendered as its own toggleable overlay.",
            },
            "title": {"type": "string", "description": "Optional dashboard title, shown as a heading overlay on the map."},
            "output_path": {"type": "string", "description": "Where to save the HTML file. Defaults to a temp file."},
        },
        "required": ["layers"],
    },
)
def generate_html_dashboard(layers, title=None, output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not layers:
        return {"error": "layers must not be empty."}

    prepared = []
    tmp_files = []
    try:
        for spec in layers:
            layer_name = spec.get("layer_name")
            layer = _find_layer_by_name(layer_name)
            if layer is None:
                return {"error": f"Layer '{layer_name}' not found"}
            if not layer.isSpatial():
                return {"error": f"Layer '{layer_name}' has no geometry -- generate_html_dashboard needs spatial vector layers."}

            fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
            os.close(fd)
            tmp_files.append(tmp_path)
            write_res = _write_layer_geojson_wgs84(layer, tmp_path)
            if "error" in write_res:
                return write_res

            with open(tmp_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)

            prepared.append({
                "name": layer_name,
                "geojson": geojson,
                "popup_fields": spec.get("popup_fields"),
                "popup_labels": spec.get("popup_labels"),
                "color_field": spec.get("color_field"),
            })

        result = _build_dashboard_html(prepared, title=title)
        if "error" in result:
            return result

        out_path = output_path or _temp_html_path()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result["html"])

        response = {
            "success": True,
            "output_path": out_path,
            "layer_count": len(prepared),
            # Moved here from the tool description (paid on every call where
            # ToolRouter merely selects this as a candidate, invoked or not)
            # -- this is presentation guidance only needed when the tool
            # actually runs. See also BASE_SYSTEM_PROMPT rule 27, which
            # already instructs relaying this when presenting the result;
            # this field keeps the same wording machine-locatable in the
            # tool's own output rather than relying on that rule alone.
            "connectivity_note": (
                "This HTML file is not fully offline: opening it loads the Leaflet/Bootstrap "
                "libraries and OpenStreetMap basemap tiles from public CDNs, so the viewer needs "
                "internet access at view time (generating the file itself needed no network)."
            ),
        }
        if result.get("warnings"):
            response["warnings"] = result["warnings"]
        return response
    except Exception as e:
        return {"error": f"generate_html_dashboard failed: {e}"}
    finally:
        for p in tmp_files:
            try:
                os.remove(p)
            except OSError:
                pass


def _temp_html_path():
    fd, path = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    return path
