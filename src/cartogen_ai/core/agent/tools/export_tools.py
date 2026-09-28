# -*- coding: utf-8 -*-
"""
Export & Reporting Tools for Cartogen AI.
"""

import os
import json
import tempfile
import datetime
from .registry import register_tool
from ._qgis_enum_compat import resolve_qgis_enum
from ...models import sensitivity as _sens
from .analysis_tools import _parse_date
from .styling_tools import apply_categorized_style
from ....infrastructure.settings_keys import PROJECT_PROPERTY_FETCHED_AT

try:
    from qgis.core import (
        QgsProject, QgsVectorFileWriter, QgsCoordinateTransformContext,
        QgsCoordinateReferenceSystem, QgsCoordinateTransform,
        QgsVectorLayer, QgsFeature, QgsWkbTypes, QgsApplication,
    )
    from qgis.PyQt.QtCore import QVariant
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


def _check_shapefile_field_names(layer):
    """Preflight check for ESRI Shapefile export replicating OGR/DBF laundering.
    ESRI Shapefile (DBF) limits field names to 10 characters and is case-insensitive.
    OGR truncates names to 10 characters and resolves case-insensitive collisions
    by laundering conflicting names with numeric suffixes (e.g. 'populati_1', 'populati_2').
    Returns (warning_message_or_None, field_mapping_dict).
    """
    if layer is None or not hasattr(layer, "fields"):
        return None, {}

    long_fields = []
    truncated_map = {}  # original_name -> laundered_name
    used_lower = set()  # set of all allocated laundered names (lowercase)

    field_names = []
    for field in layer.fields():
        name = field.name() if hasattr(field, "name") else str(field)
        field_names.append(name)

    for name in field_names:
        if len(name) > 10:
            long_fields.append(name)
            base = name[:10]
        else:
            base = name

        base_lower = base.lower()
        if base_lower not in used_lower:
            laundered = base
            used_lower.add(base_lower)
        else:
            idx = 1
            while True:
                suffix = f"_{idx}"
                prefix_len = 10 - len(suffix)
                cand = f"{base[:prefix_len]}{suffix}"
                cand_lower = cand.lower()
                if cand_lower not in used_lower:
                    laundered = cand
                    used_lower.add(cand_lower)
                    break
                idx += 1

        truncated_map[name] = laundered

    # Collisions occurred if any field received a disambiguation suffix or changed from its base prefix
    has_collisions = any(
        truncated_map[name].lower() != (name[:10].lower() if len(name) > 10 else name.lower())
        for name in field_names
    )

    if not long_fields and not has_collisions:
        return None, truncated_map

    warning_parts = []
    if long_fields:
        warning_parts.append(
            f"ESRI Shapefile (DBF) limits field names to 10 characters. {len(long_fields)} field(s) will be truncated: "
            + ", ".join(f"'{f}' -> '{truncated_map[f]}'" for f in long_fields[:5])
            + (f" (and {len(long_fields) - 5} more)" if len(long_fields) > 5 else "")
        )
    if has_collisions:
        collision_examples = [
            f"'{f}' -> '{truncated_map[f]}'"
            for f in field_names
            if truncated_map[f] != (f[:10] if len(f) > 10 else f)
        ]
        warning_parts.append(
            "Case-insensitive collision(s) detected after truncation. OGR disambiguation will rename: "
            + ", ".join(collision_examples[:5])
            + ". Consider exporting to GeoPackage (GPKG) or GeoJSON to preserve full, distinct field names."
        )

    return " ".join(warning_parts), truncated_map



def _write_vector(layer, output_path, driver_name, layer_options=None, only_selected=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        shp_warning = None
        shp_mapping = None
        if driver_name == "ESRI Shapefile":
            shp_warning, shp_mapping = _check_shapefile_field_names(layer)

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = driver_name
        options.fileEncoding = "UTF-8"
        has_selection = False
        if hasattr(layer, "selectedFeatureCount"):
            try:
                cnt = layer.selectedFeatureCount()
                if isinstance(cnt, (int, float)) and cnt > 0:
                    has_selection = True
            except Exception:
                has_selection = False

        # Real bug found in a code-review pass (2026-09-20): only_selected=True with
        # has_selection=False used to silently fall through to a full-layer export --
        # `use_selection and has_selection` is False either way, so the caller's explicit
        # "just the selected records" request was downgraded with no warning at all. Fail
        # loudly instead: an export tool silently returning MORE data than asked for is a
        # real risk for humanitarian/sensitive layers, not just a minor UX surprise.
        if only_selected and not has_selection:
            return {
                "error": "only_selected=True was requested, but the layer has no features "
                "currently selected. Select features first, or omit only_selected to export "
                "the full layer intentionally."
            }
        use_selection = only_selected if only_selected is not None else has_selection
        if use_selection and has_selection:
            options.onlySelectedFeatures = True

        if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
            res = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                output_path,
                QgsCoordinateTransformContext(),
                options,
            )
            error, message = res[0], res[1]
        else:
            error, message = QgsVectorFileWriter.writeAsVectorFormatV2(
                layer,
                output_path,
                QgsCoordinateTransformContext(),
                options,
            )
        if _VFW_NO_ERROR is None:
            return {"error": "Could not resolve QgsVectorFileWriter.WriterError.NoError in this QGIS version -- export result cannot be verified."}
        if error != _VFW_NO_ERROR:
            return {"error": f"Export failed: {message} (code {error})"}

        exported_count = 0
        try:
            cnt = layer.selectedFeatureCount() if (use_selection and has_selection) else layer.featureCount()
            if isinstance(cnt, (int, float)):
                exported_count = cnt
        except Exception:
            exported_count = 0

        result = {
            "success": True,
            "output_path": output_path,
            "feature_count": exported_count,
            "only_selected_features": bool(use_selection and has_selection),
        }
        if shp_warning:
            result["shapefile_truncation_warning"] = shp_warning
            result["field_name_mapping"] = shp_mapping
        warning = _sens.export_warning_for(layer)
        if warning:
            result["warning"] = warning
        return result
    except Exception as e:
        return {"error": f"_write_vector failed: {e}"}



@register_tool("export_layer", "Export vector layer to file format (ESRI Shapefile, GeoJSON, GPKG, KML).", {"type": "object", "properties": {"layer_name": {"type": "string"}, "format": {"type": "string"}, "output_path": {"type": "string"}, "only_selected": {"type": "boolean"}}, "required": ["layer_name", "format"]})
def export_layer(layer_name, format, output_path=None, only_selected=None):
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}

    fmt_map = {
        "shp": ("ESRI Shapefile", ".shp", "ESRI Shapefile (*.shp)"),
        "shapefile": ("ESRI Shapefile", ".shp", "ESRI Shapefile (*.shp)"),
        "geojson": ("GeoJSON", ".geojson", "GeoJSON (*.geojson)"),
        "gpkg": ("GPKG", ".gpkg", "GeoPackage (*.gpkg)"),
        "geopackage": ("GPKG", ".gpkg", "GeoPackage (*.gpkg)"),
        "kml": ("KML", ".kml", "KML (*.kml)"),
    }
    fmt_key = format.lower()
    driver, ext, filter_str = fmt_map.get(fmt_key, (format, f".{format.lower()}", f"{format} (*.*)"))

    # No blocking QFileDialog here -- this tool is called by the LLM agent's unattended
    # tool-calling loop (agent/agent_orchestrator.py), not only from direct human UI interaction. A
    # code-review pass (2026-09-20) found a prior version of this function DID pop a modal
    # Save As dialog when output_path was omitted, reintroducing exactly the stall risk a
    # headless-safe default was previously added to fix: an agent turn with no output_path
    # would block on the QGIS main thread waiting for a human click that might never come.
    # Explicit output_path always wins; otherwise this always derives a project/profile-folder
    # path with no prompt (2026-09-28: moved off Desktop, see _default_export_dir's own
    # docstring -- same "keep generated files under the project/profile folder, not scattered
    # across the OS" fix _derive_csv_path got the same day), matching export_to_csv's/
    # _derive_csv_path's own headless-safe convention.
    if not output_path:
        base = _default_export_dir("exports/geospatial")
        output_path = os.path.join(base, f"{_sanitize_filename(layer.name())}{ext}")

    return _write_vector(layer, output_path, driver, only_selected=only_selected)


# SEC-002, 2026-09-13 audit: a value beginning with one of these characters is interpreted
# as a formula by Excel/LibreOffice/Google Sheets when the CSV is opened there -- a classic
# CSV/"formula" injection vector (OWASP). A layer's string attribute fields can come from
# unvetted external data (OSM tags, humanitarian datasets, a user's own free-text entry) and
# are exactly the kind of content that could carry e.g. "=HYPERLINK(...)" or "=cmd|'/calc'!A1".
# Numeric/date/bool fields are left untouched -- QGIS writes those as plain numbers/dates,
# never a string that could start with one of these characters, and quoting a negative number
# (a very common case: longitude, elevation change, etc.) would wrongly turn it into text.
_CSV_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_formula_injection(csv_path, string_field_names):
    """Post-processes a CSV file _write_vector already wrote successfully: any cell in a
    STRING-typed column whose value starts with a formula-trigger character gets a leading
    single quote, the standard mitigation (OWASP) -- spreadsheet apps display the quote as
    part of a plain-text cell rather than evaluating what follows as a formula. Only string
    columns are touched (see _CSV_FORMULA_TRIGGER_CHARS above); the WKT geometry column
    QgsVectorFileWriter adds (GEOMETRY=AS_WKT) is never in string_field_names, so it's left
    alone unconditionally. Runs after the real export already succeeded -- a failure here is
    reported as its own error rather than silently leaving unsanitized output in place."""
    import csv
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if not rows:
            return None
        header = rows[0]
        string_col_indices = {i for i, name in enumerate(header) if name in string_field_names}
        if not string_col_indices:
            return None
        changed = False
        for row in rows[1:]:
            for i in string_col_indices:
                if i < len(row) and row[i] and row[i][0] in _CSV_FORMULA_TRIGGER_CHARS:
                    row[i] = "'" + row[i]
                    changed = True
        if changed:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
        return None
    except Exception as e:
        return f"Export succeeded but CSV formula-injection sanitization failed: {e}"


def _sanitize_filename(name):
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in str(name)).strip()
    return safe or "layer"


def _default_export_dir(subdir="exports"):
    """A stable, reusable location for tool-generated files -- the project's own
    data/20_processed (matching create_project_folder_structure's own "Analysis outputs"
    folder, project_tools.py) when the project is saved, else a per-profile folder under the
    QGIS profile (the same pattern local_data_loader.py's data_dir() already established for
    downloaded OSM data, so this plugin never scatters files across arbitrary OS locations).
    Directory is created if missing -- callers never have to check first."""
    home = ""
    try:
        if QGIS_AVAILABLE:
            home = QgsProject.instance().homePath()
    except Exception:
        home = ""
    if home:
        base = os.path.join(home, "data", "20_processed")
    else:
        try:
            profile_dir = QgsApplication.qgisSettingsDirPath() if QGIS_AVAILABLE else os.path.expanduser("~")
        except Exception:
            profile_dir = os.path.expanduser("~")
        # subdir may be a "/"-joined caller convenience (e.g. "exports/geospatial") --
        # split it into separate os.path.join() components rather than passing it through
        # as one argument, which would embed a literal "/" in the path on Windows and mix
        # separators (CI failure on windows-latest, 2026-09-28: the resulting path had
        # "...\\cartogen_ai\\exports/geospatial\\..." and no longer matched an
        # os.path.join()-built expected path in the test).
        base = os.path.join(profile_dir, "cartogen_ai", *subdir.split("/"))
    try:
        os.makedirs(base, exist_ok=True)
    except OSError:
        base = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(base, exist_ok=True)
    return base


def _derive_csv_path(layer, output_path):
    """Returns (path, used_fallback) for export_to_csv. explicit output_path always wins;
    otherwise the .csv is written under _default_export_dir() (project folder or QGIS
    profile), never prompts -- this tool is called by the LLM agent's unattended
    tool-calling loop (agent/agent_orchestrator.py), not only from direct human UI
    interaction.

    Live-reported, 2026-09-28: an earlier version of this function sat the CSV beside the
    layer's own on-disk source file when one existed. For a layer that is itself a Processing
    algorithm's intermediate output (a common case for an analysis result like "Health
    Facilities Beyond 1 Hour"), that source is an auto-generated, QGIS-managed temp file --
    reusing its exact ugly basename produced an unreadable, unfindable filename (e.g.
    "out_Health_Facilities_Beyond_1_Hour_278d9021_6333_4b63_808c_957ff81df274.csv") sitting in
    a temp directory QGIS can clean up at any time, which the user could not open. Always
    using a clean, sanitized name under a stable project/profile folder instead closes both
    problems: the requested "local directories should be limited to project folder / profile
    folder for more reusable data sets" is exactly this change.

    A prior version of this function briefly reintroduced a blocking QFileDialog.
    getSaveFileName() call here when output_path was omitted -- found and reverted in a
    code-review pass (2026-09-20): that's exactly the interactive-stall risk this headless-
    safe design was originally built to avoid (a live-reported bug where an agent turn ran
    out of tool-call budget ending in "please specify a destination file path" -- a modal
    dialog on an unattended turn is the same failure mode, just silent instead of loud)."""
    if output_path:
        return output_path, False
    base = _default_export_dir("exports/geospatial")
    return os.path.join(base, f"{_sanitize_filename(layer.name())}.csv"), True


@register_tool("export_to_csv", "Export layer attribute table to CSV file. output_path is optional -- "
               "omit it to save under the project's data/20_processed folder (or the QGIS profile "
               "folder if the project isn't saved yet), under a clean, sanitized file name derived "
               "from the layer's own name. Never prompts interactively. "
               "If features are selected on the layer, only selected features are exported by default.",
               {"type": "object", "properties": {"layer_name": {"type": "string"}, "output_path": {"type": "string"}, "only_selected": {"type": "boolean"}}, "required": ["layer_name"]})
def export_to_csv(layer_name, output_path=None, only_selected=None):
    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    path, used_fallback = _derive_csv_path(layer, output_path)
    result = _write_vector(
        layer,
        path,
        "CSV",
        layer_options=["GEOMETRY=AS_WKT", "SEPARATOR=COMMA"],
        only_selected=only_selected,
    )
    if result.get("success"):
        string_field_names = {f.name() for f in layer.fields() if f.type() == QVariant.String}
        sanitize_error = _sanitize_csv_formula_injection(path, string_field_names)
        if sanitize_error:
            return {"error": sanitize_error}
        if used_fallback:
            result["note"] = f"No output_path given -- saved under {os.path.dirname(path)}."
    return result


@register_tool(
    "print_map",
    "Export current QGIS map canvas view to a PDF document or PNG/JPG image. output_path is optional -- if omitted, saves a PNG to Desktop without prompting.",
    {
        "type": "object",
        "properties": {
            "output_path": {
                "type": "string",
                "description": "Optional file path with .pdf, .png, or .jpg extension. If omitted, saves a PNG to Desktop.",
            }
        },
    },
)
def print_map(output_path=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if iface is None or iface.mapCanvas() is None:
        return {"error": "QGIS interface or map canvas not available"}

    canvas = iface.mapCanvas()

    # No blocking QFileDialog here -- see export_layer's own comment on this same fix
    # (code-review pass, 2026-09-20): this tool runs from the LLM agent's unattended
    # tool-calling loop, so a modal Save As dialog on a missing output_path risks stalling
    # a turn indefinitely instead of just picking a sane headless default.
    if not output_path:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        output_path = os.path.join(desktop, "qgis_map_export.png")

    out_ext = os.path.splitext(output_path)[1].lower()

    try:
        if out_ext == ".pdf":
            from qgis.PyQt.QtGui import QPainter, QPdfWriter, QPageSize
            from qgis.PyQt.QtCore import QSizeF
            from qgis.core import QgsMapSettings, QgsMapRendererCustomPainterJob

            # Size writer to canvas aspect ratio or standard A4 landscape
            c_size = canvas.size()
            c_w = max(100, c_size.width())
            c_h = max(100, c_size.height())

            # Convert canvas dimensions to mm at 96 DPI
            w_mm = max(100.0, (c_w / 96.0) * 25.4)
            h_mm = max(100.0, (c_h / 96.0) * 25.4)

            writer = QPdfWriter(output_path)
            writer.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Millimeter))
            writer.setResolution(300)

            painter = QPainter(writer)
            try:
                settings = QgsMapSettings(canvas.mapSettings())
                paint_rect = writer.layout().paintRectPixels(300)
                settings.setOutputSize(paint_rect.size())
                settings.setOutputDpi(300)

                job = QgsMapRendererCustomPainterJob(settings, painter)
                job.start()
                job.waitForFinished()
            finally:
                painter.end()

            return {"success": True, "output_path": output_path, "format": "pdf"}

        # Raster format (PNG, JPG)
        canvas.saveAsImage(output_path)
        return {"success": True, "output_path": output_path, "format": out_ext.lstrip(".")}

    except Exception as e:
        return {"error": f"print_map failed: {e}"}


def _layer_provenance_entries(source_layers):
    """For each named layer, returns lineage.py's tracked history (if any) --
    what tool created/modified it, with what parameters and source layers,
    and when (see agent/lineage.py and agent_orchestrator.py's automatic tag_layer_lineage
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


_CATEGORICAL_PALETTE = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3",
    "#a6d854", "#ffd92f", "#e5c494", "#b3b3b3",
]  # ColorBrewer "Set2" qualitative ramp -- the same one apply_categorized_style
   # (styling_tools.py) uses via QgsStyle.defaultStyle().colorRamp("Set2"),
   # hardcoded here as plain hex so this module's pure HTML-generation core
   # stays usable/testable without a live QGIS session (same reasoning as
   # _build_dashboard_html's own docstring on why it's split out that way).


def _categorical_color_map(values):
    """Assigns each distinct value (in first-seen order, so the same input
    always gets the same colors -- reproducible, not re-shuffled per call) a
    color from _CATEGORICAL_PALETTE, cycling it if there are more distinct
    values than colors (e.g. more than 8 controlling factions). Returns
    {value: hex_color}."""
    color_map = {}
    for v in values:
        if v not in color_map:
            color_map[v] = _CATEGORICAL_PALETTE[len(color_map) % len(_CATEGORICAL_PALETTE)]
    return color_map


_FETCHED_AT_PROPERTY_KEY = PROJECT_PROPERTY_FETCHED_AT

_FRESHNESS_FRESH_MAX_SECONDS = 3600    # < 1h old -> fresh
_FRESHNESS_STALE_MAX_SECONDS = 86400   # < 24h old -> stale; >= 24h -> very stale

# (text color, background color) per status -- same green/amber/red convention this codebase's
# own choropleth colormap already uses (_build_dashboard_html's color_field styling above), not
# an arbitrary new palette.
_FRESHNESS_COLORS = {
    "fresh": ("#1a9850", "#eafaf0"),
    "stale": ("#b8860b", "#fff8e1"),
    "very_stale": ("#d73027", "#fdecea"),
}
_FRESHNESS_LABELS = {"fresh": "Fresh", "stale": "Stale", "very_stale": "Very stale"}


def _humanize_age(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def _classify_freshness(fetched_at_iso):
    """Classifies a layer's cartogen_ai/fetched_at ISO-8601 timestamp (set by
    hazard_monitoring_tools.py's fetch tools) into (status, age_label) for a dashboard freshness
    pill. Returns None for a missing/unparseable timestamp -- most layers were never fetched
    from a live source and should render with no badge at all, not a fake 'unknown' one."""
    if not fetched_at_iso:
        return None
    try:
        fetched_dt = datetime.datetime.fromisoformat(fetched_at_iso)
    except (TypeError, ValueError):
        return None
    if fetched_dt.tzinfo is None:
        fetched_dt = fetched_dt.replace(tzinfo=datetime.timezone.utc)
    age_seconds = max(0, (datetime.datetime.now(datetime.timezone.utc) - fetched_dt).total_seconds())
    if age_seconds < _FRESHNESS_FRESH_MAX_SECONDS:
        status = "fresh"
    elif age_seconds < _FRESHNESS_STALE_MAX_SECONDS:
        status = "stale"
    else:
        status = "very_stale"
    return status, _humanize_age(age_seconds)


def _freshness_legend_html(layers):
    """Small floating panel listing each layer's data-freshness pill (green 'Fresh 2m', amber
    'Stale 3h', red 'Very stale 2d') -- WorldMonitor's exact visual pattern (a color-coded pill
    plus a tooltip with the precise fetch time), reproduced in plain inline HTML/CSS, no JS
    framework or new dependency. Only rendered for layers that were actually stamped with a
    fetched_at time; a layer never fetched from a live source (the overwhelming majority of
    layers this tool has ever been called with) gets no badge, correctly. This is a
    computed-once-at-export-time snapshot from a static HTML file, not a live ticking clock --
    the tool's own description says so, so it isn't misread as a live dashboard."""
    import html as html_module
    rows = []
    for layer in layers:
        classified = _classify_freshness(layer.get("fetched_at"))
        if classified is None:
            continue
        status, age = classified
        text_color, bg_color = _FRESHNESS_COLORS[status]
        label = _FRESHNESS_LABELS[status]
        name = html_module.escape(str(layer["name"]))
        tooltip = html_module.escape(f"As of {layer.get('fetched_at')} (UTC)")
        rows.append(
            f'<div style="margin:2px 0;white-space:nowrap;" title="{tooltip}">'
            f'<span style="display:inline-block;padding:1px 8px;border-radius:10px;'
            f'background:{bg_color};color:{text_color};font-size:11px;font-weight:600;">'
            f'{label} {age}</span> '
            f'<span style="font-size:12px;">{name}</span>'
            f'</div>'
        )
    if not rows:
        return ""
    return (
        '<div style="position:fixed;top:60px;left:10px;z-index:9999;background:white;'
        'padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px rgba(0,0,0,0.3);'
        'max-width:300px;">'
        '<div style="font-size:11px;font-weight:700;margin-bottom:4px;color:#333;">Data freshness</div>'
        + "".join(rows) + '</div>'
    )


def _title_overlay_html(title):
    """Shared fixed-position title-heading overlay markup for both
    _build_dashboard_html and _build_temporal_dashboard_html. Escaped so a
    title containing '<'/'&' can't break the page."""
    import html as html_module
    return (
        '<h3 style="position:fixed;top:10px;left:60px;z-index:9999;background:white;'
        f'padding:4px 10px;border-radius:4px;">{html_module.escape(str(title))}</h3>'
    )


def _resolve_popup_kwargs(folium_module, name, features, popup_fields, popup_labels, warnings):
    """Shared popup-field resolution, used by both _build_dashboard_html and
    _build_temporal_dashboard_html so the "which fields, how many, what
    label" logic exists in exactly one place rather than duplicated between
    them. Internal bookkeeping fields this module bakes into a feature's own
    properties itself (prefixed __cartogen_ -- see the temporal builder's
    start/end/color) are never offered as a default popup field, whether or
    not popup_fields was passed explicitly: they're plumbing for the map,
    not something a user asked to see in a popup.

    Returns a folium.GeoJsonPopup ready to pass as GeoJson(popup=...), or
    None if there's nothing to show. Mutates `warnings` in place -- same
    convention every other warning collected while building the map
    already uses."""
    if popup_fields:
        popup_fields = [f for f in popup_fields if not str(f).startswith("__cartogen_")]
    if not popup_fields and features:
        popup_fields = [
            k for k in features[0].get("properties", {}).keys()
            if not str(k).startswith("__cartogen_")
        ]
    if popup_fields and len(popup_fields) > _MAX_DASHBOARD_POPUP_FIELDS:
        warnings.append(
            f"'{name}': popup_fields truncated to the first {_MAX_DASHBOARD_POPUP_FIELDS} of "
            f"{len(popup_fields)} -- pass popup_fields explicitly to control which show."
        )
        popup_fields = popup_fields[:_MAX_DASHBOARD_POPUP_FIELDS]
    if popup_fields and features:
        # A field missing from a feature's properties would raise inside
        # GeoJsonPopup and break the whole layer's rendering, not just that
        # one popup -- so only fields present on the first feature (assumed
        # representative of the layer's schema) are kept.
        present = set(features[0].get("properties", {}).keys())
        popup_fields = [f for f in popup_fields if f in present]
    if not popup_fields:
        return None
    popup_labels = popup_labels or {}
    aliases = [popup_labels.get(f, _humanize_field_name(f)) for f in popup_fields]
    return folium_module.GeoJsonPopup(fields=popup_fields, aliases=aliases)


# Every entry here is a free, no-API-key tile service with a documented usage policy that
# permits exactly this "embed in a generated standalone HTML page" pattern (the same reason
# cartodbpositron -- "positron" below -- was chosen as the original default over OSM's own
# tiles, which explicitly prohibit unattributed bulk/embedded-app use -- see
# _build_dashboard_html's comment). "satellite" and "hot" answer the "no satellite imagery
# or Humanitarian OSM toggle" gap directly; folium requires an explicit attr= string for any
# tiles= value that isn't one of its own small set of built-in named presets.
_DASHBOARD_BASEMAPS = {
    "positron": {"tiles": "cartodbpositron", "attr": None},
    "dark_matter": {"tiles": "cartodbdark_matter", "attr": None},
    "satellite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    },
    "hot": {
        "tiles": "https://tile-{s}.openstreetmap.fr/hot/{z}/{x}/{y}.png",
        "attr": "&copy; OpenStreetMap contributors, Tiles style by Humanitarian OpenStreetMap Team",
    },
}
_DEFAULT_DASHBOARD_BASEMAP = "positron"


def _resolve_basemap_kwargs(basemap):
    """Returns (folium.Map kwargs dict, warning_or_None). Falls back to the default basemap
    (with a warning, not a hard error) for an unrecognized key, rather than failing the whole
    dashboard over a caller typo in an otherwise-optional cosmetic parameter."""
    key = (basemap or _DEFAULT_DASHBOARD_BASEMAP).lower()
    entry = _DASHBOARD_BASEMAPS.get(key)
    if entry is None:
        return _DASHBOARD_BASEMAPS[_DEFAULT_DASHBOARD_BASEMAP], f"Unknown basemap '{basemap}' -- used the default ('{_DEFAULT_DASHBOARD_BASEMAP}') instead. Valid options: {', '.join(_DASHBOARD_BASEMAPS)}."
    return entry, None


def _build_dashboard_html(layers, title=None, basemap=None):
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

    # folium's own default tiles="OpenStreetMap" points straight at
    # tile.openstreetmap.org with no custom User-Agent and no caching --
    # every open/reload of the exported HTML hits OSM's production tile
    # servers directly from the viewer's browser. OSM's own tile usage
    # policy explicitly prohibits exactly this pattern (bulk/embedded-app
    # use with no distinguishing User-Agent or local caching) and their
    # servers block misbehaving clients -- reported live as the dashboard's
    # basemap showing a blocked/unavailable tile message instead of real
    # map tiles. CartoDB Positron remains the default (permissively-licensed,
    # built for exactly this "embed a basemap in your own generated page"
    # case, light/unobtrusive under thematic overlays) -- basemap= (see
    # _DASHBOARD_BASEMAPS) lets a caller opt into satellite imagery or a
    # Humanitarian OSM Team style instead when that's more useful.
    basemap_kwargs, basemap_warning = _resolve_basemap_kwargs(basemap)
    m = folium.Map(**basemap_kwargs)
    if all_lats and all_lons:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])
    else:
        m.location, m.zoom_start = [0, 0], 2

    warnings = []
    if basemap_warning:
        warnings.append(basemap_warning)
    for layer in layers:
        name = layer["name"]
        geojson = layer.get("geojson", {})
        features = geojson.get("features", [])

        popup = _resolve_popup_kwargs(
            folium, name, features, layer.get("popup_fields"), layer.get("popup_labels"), warnings,
        )

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
        if popup is not None:
            gj_kwargs["popup"] = popup
        if style_function:
            gj_kwargs["style_function"] = style_function
        folium.GeoJson(geojson, **gj_kwargs).add_to(m)

        if colormap is not None:
            colormap.caption = color_field
            colormap.add_to(m)

    folium.LayerControl().add_to(m)

    if title:
        m.get_root().html.add_child(folium.Element(_title_overlay_html(title)))

    freshness_html = _freshness_legend_html(layers)
    if freshness_html:
        m.get_root().html.add_child(folium.Element(freshness_html))

    return {"html": m.get_root().render(), "warnings": warnings}


def _date_to_epoch_ms(date_obj):
    """Converts a datetime.date to epoch milliseconds at UTC midnight -- the
    unit the temporal dashboard's JS slider works in (JS epoch-ms, not a
    QGIS/Python date type), and the unit _compute_animation_frame_epochs
    uses for the QGIS-native frame-export path below. Returns None if
    date_obj is None (the caller's cue that a feature's date couldn't be
    parsed / wasn't given -- see _resolve_temporal_bounds for what that
    means for a feature's visibility)."""
    if date_obj is None:
        return None
    return int(
        datetime.datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=datetime.timezone.utc)
        .timestamp() * 1000
    )


def _month_bucket_label(date_obj):
    """'YYYY-MM' calendar-month bucket label for a datetime.date, used to
    group features by month for generate_temporal_dashboard's trend chart
    (_build_trend_chart_data below). Returns None for None -- the caller's
    cue to skip that feature (its start_field couldn't be parsed at all)."""
    if date_obj is None:
        return None
    return f"{date_obj.year:04d}-{date_obj.month:02d}"


def _resolve_feature_locations(features, location_field):
    """Per-feature raw location value (whatever field the caller points
    location_field at -- e.g. a governorate/admin1 name) for the dashboard's
    location-filter checkbox panel. None (not the two-character string
    "None") for a feature missing the field, or for every feature when
    location_field itself wasn't given at all -- those features are never
    affected by the location filter, whether or not a panel ends up being
    shown for other layers (see _build_temporal_dashboard_html)."""
    if not location_field:
        return [None] * len(features)
    return [f.get("properties", {}).get(location_field) for f in features]


def _resolve_temporal_colors(name, features, category_field, color_field, warnings):
    """Per-feature hex colors for one temporal layer, baked into each
    feature's own properties (as __cartogen_color) so the client-side
    slider JS can restyle a feature on every frame without recomputing a
    ColorBrewer/branca scale in JavaScript. category_field (e.g. a
    controlling faction/group name) takes priority when given, since
    categorizing "who/what has this status" is the expected default use for
    an animated control/status layer; color_field (a numeric field, e.g. an
    intensity score) is a choropleth fallback for a caller that wants that
    instead; with neither, every feature gets the same default color.

    Category-to-color assignment is done in SORTED (not first-seen) order
    so that, for the common case of one temporal layer, the colors used
    here line up with generate_temporal_dashboard's trend-chart legend
    below, which also assigns colors to sorted category names -- with
    multiple temporal layers whose category sets differ, this alignment is
    only best-effort (each layer's own sort is independent), not a
    guarantee across layers."""
    if category_field:
        values = [f.get("properties", {}).get(category_field) for f in features]
        distinct_sorted = sorted({str(v) for v in values if v is not None})
        color_map = _categorical_color_map(distinct_sorted)
        return [color_map.get(str(v), "#999999") if v is not None else "#999999" for v in values]

    if color_field:
        numeric_vals = [
            f["properties"][color_field] for f in features
            if isinstance(f.get("properties", {}).get(color_field), (int, float))
        ]
        if numeric_vals:
            import branca.colormap as branca_cm
            cmap = branca_cm.LinearColormap(
                ["#1a9850", "#fee08b", "#d73027"], vmin=min(numeric_vals), vmax=max(numeric_vals),
            )
            colors = []
            for f in features:
                val = f.get("properties", {}).get(color_field)
                colors.append(cmap(val) if isinstance(val, (int, float)) else "#999999")
            return colors
        warnings.append(
            f"'{name}': color_field '{color_field}' has no numeric values -- rendered with a "
            "single default color."
        )

    return ["#3388ff"] * len(features)  # Leaflet's own default path/marker blue


def _resolve_temporal_bounds(features, start_field, end_field, name, warnings):
    """Parses start_field/end_field on every feature into epoch-ms bounds
    for the slider's per-feature toggling logic.

    A feature missing/unparseable on start_field is treated as
    always-visible (both bounds None) rather than dropped -- an
    unparseable date is a data-quality issue worth surfacing (see the
    warning below), not a reason to silently hide a feature from the whole
    animation. A feature with no end_field value is open-ended: visible
    from its start through the last frame, which is the ordinary "still in
    effect" case (e.g. a faction that still holds an area as of the latest
    available data), not an error.

    Returns a list of (start_ms_or_None, end_ms_or_None) pairs, aligned 1:1
    with features."""
    bounds = []
    unparseable_start = 0
    unparseable_end = 0
    for feat in features:
        props = feat.get("properties", {})
        start_raw = props.get(start_field) if start_field else None
        end_raw = props.get(end_field) if end_field else None

        start_date = _parse_date(start_raw) if start_raw is not None else None
        if start_field and start_raw is not None and start_date is None:
            unparseable_start += 1
        end_date = _parse_date(end_raw) if end_raw is not None else None
        if end_field and end_raw is not None and end_date is None:
            unparseable_end += 1

        bounds.append((_date_to_epoch_ms(start_date), _date_to_epoch_ms(end_date)))

    if unparseable_start:
        warnings.append(
            f"'{name}': {unparseable_start} feature(s) had a start_field value that couldn't be "
            "parsed as a date -- shown for the entire animation instead of being hidden."
        )
    if unparseable_end:
        warnings.append(
            f"'{name}': {unparseable_end} feature(s) had an end_field value that couldn't be "
            "parsed as a date -- treated as open-ended (visible through the last frame)."
        )
    return bounds


def _build_trend_chart_data(layer_chart_inputs):
    """Aggregates every temporal layer's features into a
    month -> category -> count cube, split per location value (plus a
    "__none__" bucket for features with no location), so
    generate_temporal_dashboard's client-side trend chart can recompute its
    visible bars instantly as the location-filter checkboxes change,
    without re-walking every feature in JavaScript.

    layer_chart_inputs: list of (features, category_field, location_values,
    start_ms_list) tuples, one per temporal layer -- location_values and
    start_ms_list are each aligned 1:1 with that layer's own features
    (see _resolve_feature_locations/_resolve_temporal_bounds). A layer
    with no category_field is skipped entirely (nothing to chart it by).

    A feature contributes to the bucket for the CALENDAR MONTH its own
    start_field falls in, not every month it's active through -- this
    counts "how many status/control changes began in month X", the natural
    reading for event-style records (one row per change), and matches what
    the reference dashboard the project owner shared (a per-month count of records by
    'Controlled By') is doing. It is NOT a running tally of how many
    features were active at any given moment -- a caller wanting that
    instead would need a different aggregation, not built here.

    Returns {"months": [sorted 'YYYY-MM' labels], "categories": [sorted
    distinct category values seen, as strings], "by_location": {loc_key:
    {month: {category: count}}}}, or None if no layer had a category_field
    (nothing to chart -- the caller skips rendering the chart panel
    entirely rather than showing an empty one)."""
    months_seen = set()
    categories_seen = set()
    by_location = {}
    any_category_field = False

    for features, category_field, location_values, start_ms_list in layer_chart_inputs:
        if not category_field:
            continue
        any_category_field = True
        for feat, location_value, start_ms in zip(features, location_values, start_ms_list):
            if start_ms is None:
                continue
            category = feat.get("properties", {}).get(category_field)
            if category is None:
                continue
            month = _month_bucket_label(
                datetime.datetime.fromtimestamp(start_ms / 1000, tz=datetime.timezone.utc).date()
            )
            months_seen.add(month)
            categories_seen.add(str(category))
            loc_key = "__none__" if location_value is None else str(location_value)
            month_bucket = by_location.setdefault(loc_key, {}).setdefault(month, {})
            month_bucket[str(category)] = month_bucket.get(str(category), 0) + 1

    if not any_category_field:
        return None

    return {
        "months": sorted(months_seen),
        "categories": sorted(categories_seen),
        "by_location": by_location,
    }


def _json_for_inline_script(value):
    """Serializes a value as JSON for embedding directly inside a <script>
    block as a JS literal (e.g. `var x = {...};`), not via JSON.parse.
    A literal '</' sequence in the JSON text could otherwise prematurely
    close the surrounding <script> tag if it happens to spell '</script'
    -- e.g. a caller-supplied location or category name of
    '</script><script>alert(1)</script>' -- so it is escaped to '<\\/'
    (a JS string still reads '\\/' as a plain '/'), the standard defense
    for exactly this "JSON dropped into a <script> tag" pattern. (json
    .dumps' own default ensure_ascii=True already \\uXXXX-escapes the
    U+2028/U+2029 JS line-terminator characters that are the other classic
    gotcha here, so nothing extra is needed for those.)"""
    return json.dumps(value).replace("</", "<\\/")


def _build_temporal_dashboard_html(layers, title=None, step_days=30, basemap=None):
    """Pure HTML-generation core for generate_temporal_dashboard -- same
    QGIS-independent split as _build_dashboard_html (takes already-extracted
    GeoJSON, so this is directly unit-testable with synthetic data, no live
    QGIS session needed). Builds a Folium/Leaflet map where every layer that
    sets start_field gets a period baked onto each of its features
    (start_field/end_field -> a [start, end] window; category_field, e.g. a
    controlling faction, colors it), plus:

    - A play/pause + single-point-in-time slider that shows/hides each
      temporal feature according to whether the slider's current date falls
      inside that feature's own window -- deliberately per-FEATURE, not
      per-layer, because two polygons in the same layer (e.g. two factions'
      areas) can each have their own distinct period. That per-feature
      independence is exactly the shape folium.plugins.TimestampedGeoJson
      does NOT support (its `duration` is one global value for the whole
      GeoJSON, not per-feature), which is why this hand-rolled control
      exists instead of that plugin.
    - A separate from/to date-RANGE control (two plain <input type=range>
      sliders, not a fancier dual-handle widget -- simpler and more robust
      to get right without an extra JS dependency) that narrows what the
      play slider ever shows: a feature only ever displays when the current
      playhead is both inside its own window AND inside the selected range,
      and the play button loops within the selected range rather than the
      whole dataset once one is chosen.
    - An optional location-filter checkbox panel (only rendered when at
      least one layer sets location_field), unchecking a value hides every
      feature carrying it, in every layer, independent of date.
    - An optional stacked bar trend chart (Chart.js, via CDN -- only
      rendered when at least one layer sets category_field) showing counts
      per category per calendar month, live-recomputed as the location
      filter or date range change. This is the one part of this function
      that needs internet access to actually render (see the registered
      tool's connectivity_note) -- everything else here is Leaflet/folium,
      already covered by that same note.

    Point-geometry features render as colored circle markers (Leaflet
    CircleMarker via folium's `marker=` option), not folium/Leaflet's
    default plain-icon Marker -- confirmed empirically (folium's own
    generated pointToLayer function Object.assign()s this function's
    style_function output onto the marker's options) that this correctly
    colors point layers by category exactly like polygon layers do, and
    that a CircleMarker supports the same .setStyle() this function's
    slider JS already uses to toggle a polygon's visibility, so one
    toggling code path covers both geometry shapes.

    A layer without start_field is rendered as an ordinary always-visible
    overlay alongside the animated ones (e.g. a fixed country outline
    behind moving control-areas) -- reuses the same popup/color-field logic
    _build_dashboard_html uses for its layers, via _resolve_popup_kwargs.

    layers: list of {"name", "geojson", "popup_fields", "popup_labels",
    "start_field": str|None, "end_field": str|None, "category_field": str|None,
    "color_field": str|None, "location_field": str|None,
    "marker_radius": number|None}. At least one layer must set start_field
    -- this tool exists specifically to add a time dimension; a dashboard
    with none belongs in generate_html_dashboard instead.

    step_days: the slider's step size in days, and the play button's
    per-tick advance. Does not change which features are considered "in
    range" at a given frame -- only how coarse the sliding/auto-play motion
    is.

    Returns {"html": str, "warnings": [...]} or {"error": str}."""
    try:
        import folium
    except ImportError:
        return {
            "error": (
                "folium is required for generate_temporal_dashboard. Install via qpip, or in the "
                "OSGeo4W Shell: python -m pip install folium"
            )
        }

    if not layers:
        return {"error": "layers must not be empty."}
    if not any(layer.get("start_field") for layer in layers):
        return {
            "error": (
                "generate_temporal_dashboard needs at least one layer with start_field set -- for "
                "a multi-layer dashboard with no time dimension, use generate_html_dashboard instead."
            )
        }

    warnings = []
    all_lats, all_lons = [], []
    for layer in layers:
        for feat in layer.get("geojson", {}).get("features", []):
            for lon, lat in _iter_geojson_coords(feat.get("geometry")):
                all_lats.append(lat)
                all_lons.append(lon)

    # See _build_dashboard_html's identical fix, same file: folium's default
    # tiles="OpenStreetMap" hits tile.openstreetmap.org directly with no
    # User-Agent/caching, which OSM's own tile usage policy blocks for
    # exactly this bulk/embedded-app pattern -- reported live as the
    # dashboard's basemap showing a blocked tile message. basemap= (see
    # _DASHBOARD_BASEMAPS) opts into satellite/HOT imagery instead of the
    # CartoDB Positron default, same mechanism as _build_dashboard_html.
    basemap_kwargs, basemap_warning = _resolve_basemap_kwargs(basemap)
    m = folium.Map(**basemap_kwargs)
    if all_lats and all_lons:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])
    else:
        m.location, m.zoom_start = [0, 0], 2
    if basemap_warning:
        warnings.append(basemap_warning)

    temporal_js_vars = []
    all_start_ms, all_end_ms = [], []
    all_locations = set()
    chart_inputs = []

    for layer in layers:
        name = layer["name"]
        geojson = layer.get("geojson", {})
        features = geojson.get("features", [])
        start_field = layer.get("start_field")

        popup = _resolve_popup_kwargs(
            folium, name, features, layer.get("popup_fields"), layer.get("popup_labels"), warnings,
        )

        if not start_field:
            # Static reference layer -- same choropleth-or-plain rendering
            # _build_dashboard_html uses, inlined here since this is its
            # only other caller.
            color_field = layer.get("color_field")
            style_function = None
            if color_field and features:
                values = [
                    f["properties"][color_field] for f in features
                    if isinstance(f.get("properties", {}).get(color_field), (int, float))
                ]
                if values:
                    import branca.colormap as branca_cm
                    cmap = branca_cm.LinearColormap(
                        ["#1a9850", "#fee08b", "#d73027"], vmin=min(values), vmax=max(values),
                    )

                    def style_function(feat, _cmap=cmap, _field=color_field):
                        val = feat["properties"].get(_field)
                        return {
                            "fillColor": _cmap(val) if isinstance(val, (int, float)) else "#999999",
                            "color": "black", "weight": 1, "fillOpacity": 0.6,
                        }
            gj_kwargs = {"name": name}
            if popup is not None:
                gj_kwargs["popup"] = popup
            if style_function:
                gj_kwargs["style_function"] = style_function
            folium.GeoJson(geojson, **gj_kwargs).add_to(m)
            continue

        # Temporal layer: bake each feature's window + color + location into
        # its own properties so the client-side slider JS can restyle/
        # toggle/filter it without recomputing anything (see module
        # docstring above on why colors are baked in Python rather than
        # recolored live in JS).
        location_field = layer.get("location_field")
        colors = _resolve_temporal_colors(
            name, features, layer.get("category_field"), layer.get("color_field"), warnings,
        )
        bounds = _resolve_temporal_bounds(features, start_field, layer.get("end_field"), name, warnings)
        location_values = _resolve_feature_locations(features, location_field)

        new_features = []
        for feat, color, (start_ms, end_ms), location_value in zip(features, colors, bounds, location_values):
            props = dict(feat.get("properties", {}))
            props["__cartogen_start_ms"] = start_ms
            props["__cartogen_end_ms"] = end_ms
            props["__cartogen_color"] = color
            props["__cartogen_location"] = None if location_value is None else str(location_value)
            new_features.append({**feat, "properties": props})
            if start_ms is not None:
                all_start_ms.append(start_ms)
            if end_ms is not None:
                all_end_ms.append(end_ms)
            if location_value is not None:
                all_locations.add(str(location_value))
        temporal_geojson = {**geojson, "features": new_features}

        chart_inputs.append((features, layer.get("category_field"), location_values, [s for s, _e in bounds]))

        def _cartogen_temporal_style(feat):
            return {
                "fillColor": feat["properties"].get("__cartogen_color", "#3388ff"),
                "color": "#333333", "weight": 1, "fillOpacity": 0.6, "opacity": 1,
            }

        gj_kwargs = {
            "name": name, "style_function": _cartogen_temporal_style,
            "marker": folium.CircleMarker(radius=layer.get("marker_radius") or 6, fill=True),
        }
        if popup is not None:
            gj_kwargs["popup"] = popup
        gj = folium.GeoJson(temporal_geojson, **gj_kwargs)
        gj.add_to(m)
        temporal_js_vars.append(gj.get_name())

    folium.LayerControl().add_to(m)

    if title:
        m.get_root().html.add_child(folium.Element(_title_overlay_html(title)))

    if not temporal_js_vars:
        # Every start_field-bearing layer's features were entirely
        # unparseable -- caught here (rather than earlier) so the specific
        # per-layer warnings above are still returned, explaining why.
        return {
            "error": "No usable temporal layers -- see warnings for why every feature's dates failed to parse.",
            "warnings": warnings,
        }

    all_ms = all_start_ms + all_end_ms
    if not all_ms:
        return {
            "error": "No parseable start_field/end_field dates found across the temporal layer(s).",
            "warnings": warnings,
        }
    min_ms, max_ms = min(all_ms), max(all_ms)
    if min_ms == max_ms:
        max_ms = min_ms + 1  # avoid a zero-width/unusable <input type=range>

    step_ms = max(int(step_days), 1) * 86400000
    layers_js_array = "[" + ",".join(temporal_js_vars) + "]"

    location_list = sorted(all_locations)
    chart_data = _build_trend_chart_data(chart_inputs)
    # Same sorted-order _categorical_color_map call _resolve_temporal_colors
    # makes above -- for the common single-temporal-layer case this lines
    # the chart's legend colors up exactly with the map's feature colors.
    chart_category_colors = _categorical_color_map(chart_data["categories"]) if chart_data else {}

    location_panel_html = ""
    if location_list:
        import html as html_module
        rows = "\n".join(
            f'<label style="display:block;white-space:nowrap;">'
            f'<input type="checkbox" class="cartogen-location-checkbox" value="{html_module.escape(loc)}" checked> '
            f'{html_module.escape(loc)}</label>'
            for loc in location_list
        )
        location_panel_html = f"""
<div id="cartogen-location-panel" style="position:fixed;top:10px;right:10px;z-index:9999;background:white;
padding:8px 12px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,0.4);font-family:sans-serif;font-size:12px;
max-height:220px;overflow-y:auto;min-width:160px;">
  <div style="font-weight:bold;margin-bottom:4px;">Filter by location</div>
  {rows}
</div>
"""

    chart_panel_html = ""
    chart_js = ""
    if chart_data:
        chart_panel_html = """
<div id="cartogen-chart-panel" style="position:fixed;bottom:20px;right:10px;z-index:9999;background:white;
padding:8px 12px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,0.4);width:340px;">
  <canvas id="cartogen-trend-chart" height="160"></canvas>
</div>
"""
        chart_js = f"""
  var __cartogenChartData = {_json_for_inline_script(chart_data)};
  var __cartogenCategoryColors = {_json_for_inline_script(chart_category_colors)};
  var __cartogenChart = null;

  function __cartogenAggregateChartData() {{
    var months = __cartogenChartData.months;
    var categories = __cartogenChartData.categories;
    var byLocation = __cartogenChartData.by_location;
    var activeLocKeys = Object.keys(byLocation).filter(function(k) {{
      if (__cartogenCheckedLocations === null) return true;
      if (k === "__none__") return true;
      return __cartogenCheckedLocations.has(k);
    }});
    var visibleMonths = months.filter(function(mo) {{
      var d = Date.parse(mo + "-01T00:00:00Z");
      return d >= __cartogenRangeFrom && d <= __cartogenRangeTo;
    }});
    var datasets = categories.map(function(cat) {{
      return {{
        label: cat,
        backgroundColor: __cartogenCategoryColors[cat] || "#999999",
        data: visibleMonths.map(function(mo) {{
          var total = 0;
          activeLocKeys.forEach(function(k) {{
            var monthData = byLocation[k][mo];
            if (monthData && monthData[cat]) total += monthData[cat];
          }});
          return total;
        }}),
      }};
    }});
    return {{labels: visibleMonths, datasets: datasets}};
  }}

  function __cartogenRedrawChart() {{
    if (typeof Chart === "undefined") return;
    var data = __cartogenAggregateChartData();
    if (__cartogenChart) {{
      __cartogenChart.data = data;
      __cartogenChart.update();
      return;
    }}
    var canvas = document.getElementById("cartogen-trend-chart");
    if (!canvas) return;
    __cartogenChart = new Chart(canvas.getContext("2d"), {{
      type: "bar",
      data: data,
      options: {{
        responsive: true,
        plugins: {{title: {{display: true, text: "Status changes per month by category (sample counts)"}}}},
        scales: {{x: {{stacked: true}}, y: {{stacked: true, beginAtZero: true}}}},
      }},
    }});
  }}
"""
    else:
        chart_js = """
  function __cartogenRedrawChart() {}
"""

    slider_html = f"""
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.1/chart.umd.min.js"></script>
<div id="cartogen-temporal-control" style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
z-index:9999;background:white;padding:10px 16px;border-radius:6px;box-shadow:0 1px 6px rgba(0,0,0,0.4);
font-family:sans-serif;min-width:360px;">
  <div style="display:flex;align-items:center;gap:10px;">
    <button id="cartogen-play-btn" type="button" style="cursor:pointer;">Play</button>
    <input id="cartogen-slider" type="range" min="{min_ms}" max="{max_ms}" step="{step_ms}" value="{min_ms}"
      style="flex:1;">
    <span id="cartogen-date-label" style="min-width:90px;text-align:right;font-weight:bold;"></span>
  </div>
  <div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:12px;">
    <span>Range:</span>
    <span id="cartogen-range-from-label" style="min-width:80px;"></span>
    <input id="cartogen-range-from" type="range" min="{min_ms}" max="{max_ms}" step="{step_ms}" value="{min_ms}"
      style="flex:1;">
    <input id="cartogen-range-to" type="range" min="{min_ms}" max="{max_ms}" step="{step_ms}" value="{max_ms}"
      style="flex:1;">
    <span id="cartogen-range-to-label" style="min-width:80px;"></span>
  </div>
</div>
{location_panel_html}
{chart_panel_html}
<script>
(function() {{
  var __cartogenLayers = {layers_js_array};
  var __cartogenMin = {min_ms}, __cartogenMax = {max_ms}, __cartogenStep = {step_ms};
  var __cartogenRangeFrom = {min_ms}, __cartogenRangeTo = {max_ms};
  var __cartogenCheckedLocations = null;
  var __cartogenTimer = null;
{chart_js}
  function __cartogenIsActive(p, ms) {{
    var start = p.__cartogen_start_ms, end = p.__cartogen_end_ms;
    var inWindow = (start === null || start === undefined || ms >= start) &&
                   (end === null || end === undefined || ms <= end);
    if (!inWindow) return false;
    if (ms < __cartogenRangeFrom || ms > __cartogenRangeTo) return false;
    if (__cartogenCheckedLocations !== null) {{
      var loc = p.__cartogen_location;
      if (loc !== null && loc !== undefined && !__cartogenCheckedLocations.has(String(loc))) return false;
    }}
    return true;
  }}

  function __cartogenUpdateFrame(ms) {{
    __cartogenLayers.forEach(function(layerGroup) {{
      if (!layerGroup || typeof layerGroup.eachLayer !== "function") return;
      layerGroup.eachLayer(function(sub) {{
        var p = (sub.feature && sub.feature.properties) || {{}};
        var active = __cartogenIsActive(p, ms);
        if (typeof sub.setStyle === "function") {{
          sub.setStyle({{opacity: active ? 1 : 0, fillOpacity: active ? 0.6 : 0}});
        }} else if (typeof sub.setOpacity === "function") {{
          sub.setOpacity(active ? 1 : 0);
        }}
      }});
    }});
    var label = document.getElementById("cartogen-date-label");
    if (label) label.textContent = new Date(ms).toISOString().slice(0, 10);
  }}

  function __cartogenUpdateRangeLabels() {{
    var fromLabel = document.getElementById("cartogen-range-from-label");
    var toLabel = document.getElementById("cartogen-range-to-label");
    if (fromLabel) fromLabel.textContent = new Date(__cartogenRangeFrom).toISOString().slice(0, 10);
    if (toLabel) toLabel.textContent = new Date(__cartogenRangeTo).toISOString().slice(0, 10);
  }}

  function __cartogenOnRangeChange() {{
    var fromEl = document.getElementById("cartogen-range-from");
    var toEl = document.getElementById("cartogen-range-to");
    var from = parseInt(fromEl.value, 10);
    var to = parseInt(toEl.value, 10);
    if (from > to) {{ to = from; toEl.value = to; }}
    __cartogenRangeFrom = from;
    __cartogenRangeTo = to;
    __cartogenUpdateRangeLabels();
    var slider = document.getElementById("cartogen-slider");
    var current = parseInt(slider.value, 10);
    var clamped = Math.min(Math.max(current, from), to);
    slider.value = clamped;
    __cartogenUpdateFrame(clamped);
    __cartogenRedrawChart();
  }}

  function __cartogenInitLocationFilter() {{
    var boxes = document.querySelectorAll(".cartogen-location-checkbox");
    if (!boxes.length) return;
    __cartogenCheckedLocations = new Set();
    boxes.forEach(function(b) {{ if (b.checked) __cartogenCheckedLocations.add(b.value); }});
    boxes.forEach(function(b) {{
      b.addEventListener("change", function() {{
        __cartogenCheckedLocations = new Set();
        boxes.forEach(function(bb) {{ if (bb.checked) __cartogenCheckedLocations.add(bb.value); }});
        var slider = document.getElementById("cartogen-slider");
        __cartogenUpdateFrame(parseInt(slider.value, 10));
        __cartogenRedrawChart();
      }});
    }});
  }}

  function __cartogenInit() {{
    var slider = document.getElementById("cartogen-slider");
    var playBtn = document.getElementById("cartogen-play-btn");
    if (!slider || !playBtn) return;
    slider.addEventListener("input", function() {{ __cartogenUpdateFrame(parseInt(slider.value, 10)); }});
    playBtn.addEventListener("click", function() {{
      if (__cartogenTimer) {{
        clearInterval(__cartogenTimer);
        __cartogenTimer = null;
        playBtn.textContent = "Play";
        return;
      }}
      playBtn.textContent = "Pause";
      __cartogenTimer = setInterval(function() {{
        var next = parseInt(slider.value, 10) + __cartogenStep;
        if (next > __cartogenRangeTo) next = __cartogenRangeFrom;
        slider.value = next;
        __cartogenUpdateFrame(next);
      }}, 700);
    }});

    var rangeFrom = document.getElementById("cartogen-range-from");
    var rangeTo = document.getElementById("cartogen-range-to");
    if (rangeFrom) rangeFrom.addEventListener("input", __cartogenOnRangeChange);
    if (rangeTo) rangeTo.addEventListener("input", __cartogenOnRangeChange);
    __cartogenUpdateRangeLabels();

    __cartogenInitLocationFilter();
    __cartogenRedrawChart();
    __cartogenUpdateFrame(__cartogenMin);
  }}

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", __cartogenInit);
  }} else {{
    __cartogenInit();
  }}
}})();
</script>
"""
    m.get_root().html.add_child(folium.Element(slider_html))

    freshness_html = _freshness_legend_html(layers)
    if freshness_html:
        m.get_root().html.add_child(folium.Element(freshness_html))

    return {"html": m.get_root().render(), "warnings": warnings}


_DASHBOARD_MAX_FEATURES = 2500


def _prepare_dashboard_layer(layer, max_features=_DASHBOARD_MAX_FEATURES):
    """Caps feature count and simplifies geometry for a layer about to be exported into an
    HTML dashboard -- embedding a layer's full, unbounded GeoJSON directly into the page's
    JavaScript (generate_html_dashboard's approach) previously had no limit, and a >10,000-
    feature layer with detailed polygon boundaries could produce a 25MB+ HTML file that
    freezes the viewer's browser on open. Returns (layer_to_export, warning_or_None) --
    the ORIGINAL layer unchanged when it's already under the cap and simple enough that
    nothing needs doing (the common case), or a new in-memory layer with a feature subset
    and Douglas-Peucker-simplified geometries (QgsGeometry.simplify()) otherwise. Tolerance
    is derived from the layer's own extent (roughly 1/2000th of its diagonal) rather than a
    fixed constant, since a sensible simplification tolerance in degrees (a country-sized
    geographic-CRS layer) is a completely different number than in meters (a city-sized
    projected one). Best-effort: any failure determining whether capping/simplification is
    even needed (e.g. a degenerate extent) falls back to exporting the original layer
    unchanged rather than failing the whole dashboard over what is, at worst, a missed file-
    size optimization."""
    try:
        total = layer.featureCount()
        extent = layer.extent()
        diagonal = ((extent.width() ** 2) + (extent.height() ** 2)) ** 0.5
        tolerance = diagonal / 2000.0 if diagonal > 0 else 0
        needs_work = total > max_features or tolerance > 0
    except Exception:
        return layer, None
    if not needs_work:
        return layer, None

    try:
        return _build_capped_simplified_layer(layer, max_features, total, tolerance)
    except Exception:
        return layer, None


def _build_capped_simplified_layer(layer, max_features, total, tolerance):
    mem_layer = QgsVectorLayer(
        f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}",
        layer.name(), "memory",
    )
    mem_provider = mem_layer.dataProvider()
    mem_provider.addAttributes(layer.fields())
    mem_layer.updateFields()

    # An earlier version used QgsFeatureRequest().setLimit(max_features) here -- "the first
    # N features in the source's storage order". For a country-wide layer whose features
    # happen to be grouped by region (a common real shape: an OSM/Geofabrik extract or a
    # paginated API ingest often loads one admin area at a time), that silently produced a
    # dashboard showing only one corner of the data, not a representative view -- the "poor
    # quality, incomplete" symptom this fix addresses. An even STRIDE sample (every Nth
    # feature across the whole layer, in whatever order getFeatures() returns) is a simple,
    # well-known systematic-sampling technique that spreads the kept features across the
    # entire dataset regardless of storage order, at no extra dependency cost.
    truncated = total > max_features
    stride = max(1, total // max_features) if truncated else 1

    out_feats = []
    kept = 0
    for i, feat in enumerate(layer.getFeatures()):
        if truncated:
            if i % stride != 0:
                continue
            if kept >= max_features:
                break
        new_feat = QgsFeature(mem_layer.fields())
        new_feat.setAttributes(feat.attributes())
        geom = feat.geometry()
        if tolerance > 0 and geom is not None and not geom.isEmpty():
            geom = geom.simplify(tolerance)
        new_feat.setGeometry(geom)
        out_feats.append(new_feat)
        kept += 1
    mem_provider.addFeatures(out_feats)
    mem_layer.updateExtents()

    warning = None
    if truncated or tolerance > 0:
        parts = []
        if truncated:
            parts.append(f"showing an evenly-sampled {kept:,} of {total:,} features")
        if tolerance > 0:
            parts.append("geometry simplified for file size")
        warning = f"'{layer.name()}': {', '.join(parts)} -- large layers are capped/simplified to keep the dashboard file a reasonable size."
    return mem_layer, warning


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

        if hasattr(QgsVectorFileWriter, "writeAsVectorFormatV3"):
            res = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, output_path, QgsCoordinateTransformContext(), options,
            )
            error, message = res[0], res[1]
        else:
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
            "basemap": {"type": "string", "description": "'positron' (default, light/unobtrusive), 'dark_matter', 'satellite' (Esri World Imagery), or 'hot' (Humanitarian OSM Team style)."},
        },
        "required": ["layers"],
    },
)
def generate_html_dashboard(layers, title=None, output_path=None, basemap=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not layers:
        return {"error": "layers must not be empty."}

    prepared = []
    tmp_files = []
    size_warnings = []
    try:
        for spec in layers:
            layer_name = spec.get("layer_name")
            layer = _find_layer_by_name(layer_name)
            if layer is None:
                return {"error": f"Layer '{layer_name}' not found"}
            if not layer.isSpatial():
                return {"error": f"Layer '{layer_name}' has no geometry -- generate_html_dashboard needs spatial vector layers."}

            export_layer, size_warning = _prepare_dashboard_layer(layer)
            if size_warning:
                size_warnings.append(size_warning)

            fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
            os.close(fd)
            tmp_files.append(tmp_path)
            write_res = _write_layer_geojson_wgs84(export_layer, tmp_path)
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
                # Set by hazard_monitoring_tools.py's fetch tools (and any future live-data
                # fetch tool that adopts the same convention) -- empty/absent for every other
                # layer, which is the correct, common case (most layers were never fetched
                # from a live source and should render with no freshness badge at all).
                "fetched_at": layer.customProperty(_FETCHED_AT_PROPERTY_KEY, "") or None,
            })

        result = _build_dashboard_html(prepared, title=title, basemap=basemap)
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
        all_warnings = size_warnings + result.get("warnings", [])
        if all_warnings:
            response["warnings"] = all_warnings
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


@register_tool(
    "generate_temporal_dashboard",
    "Generate an animated, time-sliding HTML dashboard (Leaflet/Folium) from one or more vector "
    "layers already in the project -- e.g. control-area polygons or incident points for several "
    "armed groups/factions over a multi-year period, each with its own period/date, plus a "
    "play/pause + date slider the viewer drags or plays through to watch status/control change over "
    "time. This is the temporal, reusable-for-any-multi-period-status-dataset sibling of "
    "generate_html_dashboard -- use THIS tool (not that one) whenever the data has a time dimension a "
    "viewer should be able to scrub through (e.g. 'from 2016 to 2026'), and generate_html_dashboard "
    "for a plain, non-animated situation map. At least one layer must set start_field. Give every "
    "temporal layer a category_field (e.g. the controlling faction/group name) so features are "
    "colored by category -- without it every feature in that layer gets the same color, which "
    "defeats the point of an animated status map. A layer with no start_field is rendered as an "
    "always-visible reference layer alongside the animated ones (e.g. a fixed country outline). "
    "Point-geometry layers (e.g. incidents) render as colored circle markers, not plain icons. "
    "Beyond the single-point-in-time slider, the dashboard also gets: a separate from/to date-range "
    "control that narrows what the slider ever shows and what the play button loops through; an "
    "automatic checkbox filter panel listing every distinct value of any layer's location_field (e.g. "
    "governorate/admin1 name), letting the viewer hide specific locations regardless of date; and, "
    "when any layer sets category_field, an automatic stacked bar chart (via Chart.js, from a CDN) "
    "showing how many status/control changes started in each calendar month, broken down by category "
    "and kept in sync with the location filter and date range -- modeled on a real reference dashboard "
    "the project owner shared (a Power BI conflict-monitoring report with a map, location filters, a date range, "
    "and a synced trend chart). Each layer is reprojected to WGS84 automatically. Vector layers only. "
    "The viewer needs internet access at view time (see the result's connectivity_note -- this is now "
    "true even for a dashboard with no chart, since Chart.js is always loaded). IMPORTANT: use your "
    "own knowledge of the data's field names to pass human-readable popup_labels for any coded/"
    "abbreviated field, exactly as for generate_html_dashboard. This tool never invents data of its "
    "own -- it only animates/charts whatever start_field/end_field/category_field/location_field "
    "values are actually present on the layer(s) you point it at.",
    {
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "start_field": {"type": "string", "description": "Date/text field holding when this feature's status/control period began. Omit for an always-visible reference layer."},
                        "end_field": {"type": "string", "description": "Optional date/text field holding when the period ended. Omitted/blank on a feature means it's still in effect through the latest frame."},
                        "category_field": {"type": "string", "description": "Field to color-code by category, e.g. the controlling faction/group name. Strongly recommended for any temporal layer -- also drives the automatic trend chart's legend when set."},
                        "color_field": {"type": "string", "description": "Alternative to category_field: a numeric field to choropleth-color by instead (e.g. an intensity score). Not charted (the trend chart needs a category, not a number)."},
                        "location_field": {"type": "string", "description": "Optional field to build the automatic location-filter checkbox panel from, e.g. a governorate/admin1 name. Unchecking a value hides every feature carrying it, in every layer, regardless of date."},
                        "marker_radius": {"type": "number", "description": "Circle-marker radius in pixels for a point-geometry layer. Defaults to 6. Ignored for polygon/line layers."},
                        "popup_fields": {"type": "array", "items": {"type": "string"}, "description": "Fields to show in this layer's popup. Defaults to all fields (capped)."},
                        "popup_labels": {"type": "object", "description": "Optional {field: human-readable label} shown in the popup instead of the raw field name."},
                    },
                    "required": ["layer_name"],
                },
                "description": "One or more layers. At least one must set start_field.",
            },
            "title": {"type": "string", "description": "Optional dashboard title, shown as a heading overlay on the map."},
            "output_path": {"type": "string", "description": "Where to save the HTML file. Defaults to a temp file."},
            "step_days": {"type": "integer", "description": "Slider step size / play-button advance, in days. Defaults to 30."},
            "basemap": {"type": "string", "description": "'positron' (default, light/unobtrusive), 'dark_matter', 'satellite' (Esri World Imagery), or 'hot' (Humanitarian OSM Team style)."},
        },
        "required": ["layers"],
    },
)
def generate_temporal_dashboard(layers, title=None, output_path=None, step_days=30, basemap=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if not layers:
        return {"error": "layers must not be empty."}

    prepared = []
    tmp_files = []
    size_warnings = []
    try:
        for spec in layers:
            layer_name = spec.get("layer_name")
            layer = _find_layer_by_name(layer_name)
            if layer is None:
                return {"error": f"Layer '{layer_name}' not found"}
            if not layer.isSpatial():
                return {"error": f"Layer '{layer_name}' has no geometry -- generate_temporal_dashboard needs spatial vector layers."}

            export_layer, size_warning = _prepare_dashboard_layer(layer)
            if size_warning:
                size_warnings.append(size_warning)

            fd, tmp_path = tempfile.mkstemp(suffix=".geojson")
            os.close(fd)
            tmp_files.append(tmp_path)
            write_res = _write_layer_geojson_wgs84(export_layer, tmp_path)
            if "error" in write_res:
                return write_res

            with open(tmp_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)

            prepared.append({
                "name": layer_name,
                "geojson": geojson,
                "popup_fields": spec.get("popup_fields"),
                "popup_labels": spec.get("popup_labels"),
                "start_field": spec.get("start_field"),
                "end_field": spec.get("end_field"),
                "category_field": spec.get("category_field"),
                "color_field": spec.get("color_field"),
                "location_field": spec.get("location_field"),
                "marker_radius": spec.get("marker_radius"),
                "fetched_at": layer.customProperty(_FETCHED_AT_PROPERTY_KEY, "") or None,
            })

        result = _build_temporal_dashboard_html(prepared, title=title, step_days=step_days, basemap=basemap)
        if "error" in result:
            return result

        out_path = output_path or _temp_html_path()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result["html"])

        response = {
            "success": True,
            "output_path": out_path,
            "layer_count": len(prepared),
            "connectivity_note": (
                "This HTML file is not fully offline: opening it loads the Leaflet/Bootstrap "
                "libraries and OpenStreetMap basemap tiles from public CDNs, so the viewer needs "
                "internet access at view time (generating the file itself needed no network)."
            ),
        }
        all_warnings = size_warnings + result.get("warnings", [])
        if all_warnings:
            response["warnings"] = all_warnings
        return response
    except Exception as e:
        return {"error": f"generate_temporal_dashboard failed: {e}"}
    finally:
        for p in tmp_files:
            try:
                os.remove(p)
            except OSError:
                pass


def _compute_animation_frame_epochs(min_ms, max_ms, step_days):
    """Evenly spaced frame timestamps (epoch ms) from min_ms to max_ms,
    stepping by step_days -- always includes both endpoints (the final
    frame is appended even if the last regular step overshoots or falls
    short of max_ms, so the animation's last frame always shows the true
    final state, not a truncated one). Returns [min_ms] alone if
    min_ms >= max_ms (nothing to step through -- a single-instant dataset)."""
    if min_ms >= max_ms:
        return [min_ms]
    step_ms = max(int(step_days), 1) * 86400000
    frames = list(range(min_ms, max_ms, step_ms))
    if not frames or frames[-1] != max_ms:
        frames.append(max_ms)
    return frames


def _temporal_subset_expression(start_field, end_field, frame_date_iso):
    """QGIS subset-string expression selecting features whose
    [start_field, end_field] period covers frame_date_iso (a 'YYYY-MM-DD'
    string) -- plain ISO-8601 string comparison (QGIS/most providers
    compare ISO date strings correctly, lexicographically), not a
    date-type cast, so this works the same whether the field is stored as
    a QGIS date type or plain text. A feature with no end_field value
    (NULL) is treated as open-ended/still in effect, matching
    _resolve_temporal_bounds' same choice for the HTML dashboard."""
    expr = f"\"{start_field}\" <= '{frame_date_iso}'"
    if end_field:
        expr += f" AND (\"{end_field}\" IS NULL OR \"{end_field}\" >= '{frame_date_iso}')"
    return expr


@register_tool(
    "export_temporal_animation_frames",
    "Render one PNG frame per time step from a layer with start/end period fields already in the "
    "project -- e.g. control-area polygons over 2016-2026 -- by filtering the layer to each frame's "
    "date and exporting the current map canvas view, so the frames can be assembled into a GIF/video "
    "outside QGIS (e.g. with ffmpeg) for a native, non-HTML animation. This is the QGIS-native "
    "sibling of generate_temporal_dashboard's HTML output -- use this one when a video/GIF file is "
    "wanted instead of (or in addition to) a shareable web page. The canvas view/extent is NOT "
    "changed between frames (so the animation doesn't visually jump) -- pan/zoom to the desired "
    "extent yourself before calling this. Optionally applies a categorized style once via "
    "category_field before rendering frames. The layer's filter is restored to what it was before "
    "the call once done, even on failure.",
    {
        "type": "object",
        "properties": {
            "layer_name": {"type": "string"},
            "start_field": {"type": "string", "description": "Date/text field holding when each feature's period began."},
            "end_field": {"type": "string", "description": "Optional date/text field holding when the period ended. A feature with no value here stays visible from its start onward."},
            "category_field": {"type": "string", "description": "Optional field to categorize/color the layer by (e.g. controlling faction) before rendering frames -- applied once via apply_categorized_style."},
            "output_dir": {"type": "string", "description": "Directory to write frame_0001.png, frame_0002.png, etc. Defaults to a new temp directory."},
            "step_days": {"type": "integer", "description": "Days between frames. Defaults to 30."},
        },
        "required": ["layer_name", "start_field"],
    },
)
def export_temporal_animation_frames(layer_name, start_field, end_field=None, category_field=None, output_dir=None, step_days=30):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if iface is None:
        return {"error": "QGIS interface not available"}

    layer = _find_layer_by_name(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found"}
    field_names = [f.name() for f in layer.fields()]
    if start_field not in field_names:
        return {"error": f"Field '{start_field}' not found in '{layer_name}'"}
    if end_field and end_field not in field_names:
        return {"error": f"Field '{end_field}' not found in '{layer_name}'"}

    dates = []
    for feat in layer.getFeatures():
        d = _parse_date(feat[start_field])
        if d is not None:
            dates.append(d)
        if end_field:
            d2 = _parse_date(feat[end_field])
            if d2 is not None:
                dates.append(d2)
    if not dates:
        suffix = f"/'{end_field}'" if end_field else ""
        return {"error": f"No parseable dates found in '{start_field}'{suffix} on '{layer_name}'."}

    min_ms = _date_to_epoch_ms(min(dates))
    max_ms = _date_to_epoch_ms(max(dates))
    frame_epochs = _compute_animation_frame_epochs(min_ms, max_ms, step_days)

    out_dir = output_dir or tempfile.mkdtemp(prefix="cartogen_temporal_frames_")
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        return {"error": f"Could not create output_dir '{out_dir}': {e}"}

    if category_field:
        style_result = apply_categorized_style(layer_name, category_field)
        if "error" in style_result:
            return style_result

    original_subset = layer.subsetString()
    canvas = iface.mapCanvas()
    frame_paths = []
    try:
        for i, epoch_ms in enumerate(frame_epochs, start=1):
            frame_date_iso = datetime.datetime.fromtimestamp(
                epoch_ms / 1000, tz=datetime.timezone.utc
            ).date().isoformat()
            expr = _temporal_subset_expression(start_field, end_field, frame_date_iso)
            if not layer.setSubsetString(expr):
                return {"error": f"Failed to apply frame filter on '{layer_name}': {expr}"}
            canvas.refresh()
            canvas.waitWhileRendering()
            frame_path = os.path.join(out_dir, f"frame_{i:04d}.png")
            canvas.saveAsImage(frame_path)
            frame_paths.append({"path": frame_path, "date": frame_date_iso})
        return {
            "success": True,
            "output_dir": out_dir,
            "frame_count": len(frame_paths),
            "frames": frame_paths,
            "note": (
                "QGIS itself doesn't encode video/GIF -- these are individual PNG frames. Assemble "
                "them yourself, e.g.: ffmpeg -framerate 4 -i frame_%04d.png -pix_fmt yuv420p "
                "animation.mp4 (run from output_dir)."
            ),
        }
    finally:
        layer.setSubsetString(original_subset)
