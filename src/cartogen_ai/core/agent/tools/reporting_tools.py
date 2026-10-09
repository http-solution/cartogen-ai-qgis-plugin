# -*- coding: utf-8 -*-
"""
Reporting & Document Analysis Tools for Cartogen AI.
Statistical charting, structured table extraction from PDF/Word documents,
3W/4W ("who does what where") operational-presence aggregation from CSV/Excel,
and a "beneficiaries reached vs. target" sector-coverage report preset --
complements the map-styling tools, which can't express non-spatial comparisons
(funding by cluster, incidents over time, casualties by district). None of
these touch qgis.core/Qt objects, so they run off the main thread like the
network-only tools (see NETWORK_ONLY_TOOLS in agent/agent_orchestrator.py).
"""

import os
import tempfile
from .registry import register_tool
from ._paths import resolve_output_path

_CHART_TYPES = {"bar", "pie", "line"}
_AGG_FUNCS = {"sum", "count", "mean", "min", "max"}

# Default categorical palette instead of matplotlib's raw default cycle (Tab10's blue/
# orange/green/...) -- a colorblind-safe qualitative set (Okabe-Ito, the standard
# accessible-palette reference for categorical data) so charts remain distinguishable to
# deuteranopia/protanopia viewers without the caller needing to think about it. Caller-
# supplied color_palette overrides this entirely.
_DEFAULT_CHART_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#CC79A7",
    "#D55E00", "#56B4E9", "#F0E442", "#999999",
]

# Cartographic/data-viz convention: a pie chart with too many slices becomes unreadable --
# beyond this many, the smallest slices are aggregated into a single "Other" wedge instead
# of drawing (or rejecting outright) an unreadable chart.
_PIE_MAX_SLICES = 8


def _apply_pie_slice_cap(labels, values, max_slices=_PIE_MAX_SLICES):
    """Returns (labels, values, note_or_None). Unchanged if already within max_slices;
    otherwise keeps the (max_slices - 1) largest values as-is and sums the rest into a
    single 'Other' slice, sorted so 'Other' doesn't visually dominate a chart where it's
    actually the smallest meaningful grouping. Pure Python, no matplotlib needed."""
    if len(labels) <= max_slices:
        return labels, values, None
    paired = sorted(zip(labels, values), key=lambda lv: lv[1], reverse=True)
    kept = paired[: max_slices - 1]
    rest = paired[max_slices - 1 :]
    other_total = sum(v for _, v in rest)
    new_labels = [label for label, _ in kept] + ["Other"]
    new_values = [v for _, v in kept] + [other_total]
    note = f"{len(rest)} smallest categories combined into 'Other' to keep the pie chart at {max_slices} slices or fewer (was {len(labels)})."
    return new_labels, new_values, note


def _temp_png_path():
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    return path


@register_tool(
    "generate_chart",
    "Generate a bar, pie, or line chart image from labeled numeric data -- for statistical "
    "comparisons a map can't show (funding by cluster, incidents over time, casualties by "
    "district). Not for spatial/geographic visualization -- use the styling tools "
    "(apply_categorized_style, apply_graduated_style, etc.) for that. Returns the PNG file path.",
    {
        "type": "object",
        "properties": {
            "chart_type": {"type": "string", "description": "'bar', 'pie', or 'line'."},
            "title": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}, "description": "Category names (bar/pie) or x-axis points (line)."},
            "values": {"type": "array", "items": {"type": "number"}, "description": "One numeric value per label."},
            "x_label": {"type": "string", "description": "X-axis label. Ignored for pie charts."},
            "y_label": {"type": "string", "description": "Y-axis label. Ignored for pie charts."},
            "output_path": {"type": "string", "description": "Where to save the PNG. Defaults to a temp file."},
            "color_palette": {"type": "array", "items": {"type": "string"}, "description": "Optional list of hex colors (e.g. ['#0072B2', '#E69F00']) to use instead of the default colorblind-safe palette -- cycled if there are more categories than colors."},
            "dpi": {"type": "integer", "description": "Export resolution in DPI. Defaults to 300 (print quality)."},
        },
        "required": ["chart_type", "title", "labels", "values"],
    },
)
def generate_chart(chart_type, title, labels, values, x_label=None, y_label=None, output_path=None, color_palette=None, dpi=300):
    output_path = resolve_output_path(output_path)   # rc22 smoke N3/N8/N9: anchor relative paths to the project (see _paths.py)
    chart_type = (chart_type or "").lower()
    if chart_type not in _CHART_TYPES:
        return {"error": f"chart_type must be one of {sorted(_CHART_TYPES)}."}
    if not labels or not values:
        return {"error": "labels and values must both be non-empty."}
    if len(labels) != len(values):
        return {"error": f"labels ({len(labels)}) and values ({len(values)}) must be the same length."}
    if chart_type == "pie" and any(v < 0 for v in values):
        return {"error": "Pie charts can't represent negative values -- use a bar chart instead."}

    try:
        import matplotlib
        matplotlib.use("Agg")  # headless -- no Qt/Tk backend clash inside QGIS's own event loop
        import matplotlib.pyplot as plt
    except ImportError:
        return {"error": "matplotlib is required for chart generation. Install via qpip, or in the OSGeo4W Shell: python -m pip install matplotlib"}

    palette = color_palette or _DEFAULT_CHART_PALETTE
    pie_note = None
    if chart_type == "pie":
        labels, values, pie_note = _apply_pie_slice_cap(labels, values)

    path = output_path or _temp_png_path()
    try:
        fig, ax = plt.subplots(figsize=(8, 5))
        colors = [palette[i % len(palette)] for i in range(len(labels))]
        if chart_type == "bar":
            ax.bar(labels, values, color=colors)
            ax.set_xlabel(x_label or "")
            ax.set_ylabel(y_label or "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        elif chart_type == "line":
            ax.plot(labels, values, marker="o", color=palette[0])
            ax.set_xlabel(x_label or "")
            ax.set_ylabel(y_label or "")
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        else:  # pie
            ax.pie(values, labels=labels, autopct="%1.1f%%", colors=colors)
            ax.axis("equal")
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(path, dpi=dpi)
        plt.close(fig)
        result = {"success": True, "output_path": path, "chart_type": chart_type}
        if pie_note:
            result["warning"] = pie_note
        return result
    except Exception as e:
        return {"error": f"generate_chart failed: {e}"}


@register_tool(
    "extract_pdf_tables",
    "Extract structured tables from a PDF file -- e.g. a situation report's 'IDPs by district' "
    "table -- as rows of column values, not just plain text. Use this instead of reading PDF text "
    "when the data you need is in a table (funding breakdowns, incident lists, needs-assessment "
    "figures). Returns one entry per detected table, each with its own columns/rows.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the PDF file."},
            "page": {"type": "integer", "description": "1-based page number to limit extraction to. Omit to scan every page."},
        },
        "required": ["file_path"],
    },
)
def extract_pdf_tables(file_path, page=None):
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        import pdfplumber
    except ImportError:
        return {"error": "pdfplumber is required for PDF table extraction. Install via qpip, or in the OSGeo4W Shell: python -m pip install pdfplumber"}

    try:
        tables_found = []
        with pdfplumber.open(file_path) as pdf:
            pages = pdf.pages
            if page is not None:
                if page < 1 or page > len(pages):
                    return {"error": f"page {page} is out of range -- this PDF has {len(pages)} pages."}
                pages = [pages[page - 1]]
                start_index = page
            else:
                start_index = 1

            for offset, pdf_page in enumerate(pages):
                for table in pdf_page.extract_tables():
                    if not table or not any(any(cell for cell in row) for row in table):
                        continue
                    header, *data_rows = table
                    header = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header)]
                    rows = [dict(zip(header, row)) for row in data_rows]
                    tables_found.append({
                        "page": start_index + offset,
                        "columns": header,
                        "row_count": len(rows),
                        "rows": rows,
                    })

        if not tables_found:
            return {"error": "No tables detected in this PDF -- it may be scanned/image-based (no extractable table structure), or the data isn't laid out as a real table."}
        return {"success": True, "file_path": file_path, "table_count": len(tables_found), "tables": tables_found}
    except Exception as e:
        return {"error": f"extract_pdf_tables failed: {e}"}


@register_tool(
    "extract_word_tables",
    "Extract structured tables from a Word (.docx) document as rows of column values, instead of "
    "flattened text. Use this when the data you need is in a table (e.g. a needs-assessment "
    "matrix) rather than prose.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the .docx file."},
        },
        "required": ["file_path"],
    },
)
def extract_word_tables(file_path):
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        from docx import Document
    except ImportError:
        return {"error": "python-docx is required for Word table extraction. Install via qpip, or in the OSGeo4W Shell: python -m pip install python-docx"}

    try:
        doc = Document(file_path)
        tables_found = []
        for table in doc.tables:
            grid = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if not grid or not any(any(cell for cell in row) for row in grid):
                continue
            header, *data_rows = grid
            header = [h if h else f"col_{i}" for i, h in enumerate(header)]
            rows = [dict(zip(header, row)) for row in data_rows]
            tables_found.append({"columns": header, "row_count": len(rows), "rows": rows})

        if not tables_found:
            return {"error": "No tables found in this document."}
        return {"success": True, "file_path": file_path, "table_count": len(tables_found), "tables": tables_found}
    except Exception as e:
        return {"error": f"extract_word_tables failed: {e}"}


def _read_tabular_rows(file_path, sheet_name=None, delimiter=","):
    """Reads a CSV or Excel file into a list of flat {column: value} row dicts
    plus the column list -- for tools that need real rows, not a QGIS layer
    (see load_tabular_data_as_layer in vector_tools.py for the layer-loading
    equivalent). CSV uses the stdlib csv module, no optional dependency
    needed (same reasoning as vector_tools._sniff_csv_header); Excel needs
    pandas/openpyxl, the same optional dependency already used for spreadsheet
    attachments elsewhere."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        import csv
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = list(reader)
            return rows, list(reader.fieldnames or [])
    elif ext in (".xlsx", ".xls"):
        import pandas as pd
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0)
        return df.to_dict(orient="records"), list(df.columns)
    raise ValueError(f"Unsupported file type '{ext}' -- use .csv, .xlsx, or .xls.")


def _is_missing(value):
    """True for None, empty string, or NaN (pandas represents a blank Excel
    cell as float NaN, which `in (None, "")` would silently miss and then
    stringify into the literal unit/org name 'nan')."""
    if value is None or value == "":
        return True
    return value != value  # only NaN is unequal to itself


def _aggregate_3w_presence(rows, admin_field, org_field, sector_field=None):
    """Groups 3W/4W ('who does what where') activity rows into per-admin-unit
    organizational presence: distinct org count/list, optional distinct
    sector count/list, and raw activity-row count. Pure Python, no QGIS.

    Returns (units, skipped_rows), where units maps a normalized (stripped +
    lowercased) admin-unit key to {"unit": <original-cased name>, "orgs": set,
    "sectors": set, "activity_count": int} -- normalized so callers can join
    against a differently-cased/spaced admin boundary layer elsewhere, while
    still keeping the original casing for display."""
    units = {}
    skipped = 0
    for row in rows:
        admin_raw = row.get(admin_field)
        org_raw = row.get(org_field)
        if _is_missing(admin_raw) or _is_missing(org_raw):
            skipped += 1
            continue
        key = str(admin_raw).strip().lower()
        bucket = units.setdefault(key, {"unit": str(admin_raw).strip(), "orgs": set(), "sectors": set(), "activity_count": 0})
        bucket["orgs"].add(str(org_raw).strip())
        if sector_field:
            sector_raw = row.get(sector_field)
            if not _is_missing(sector_raw):
                bucket["sectors"].add(str(sector_raw).strip())
        bucket["activity_count"] += 1
    return units, skipped


@register_tool(
    "load_3w_data",
    "Read a 3W/4W ('who does what where/when') CSV or Excel file -- the standard humanitarian "
    "operational-presence dataset, one row per activity with an organization, admin unit, and "
    "usually a sector/cluster -- and aggregate it into organizational presence per admin unit: how "
    "many distinct organizations are active there, which ones, and (if a sector field is given) "
    "which sectors are covered. Use this for 'which organizations work in X' / 'how many actors "
    "cover district Y' questions. This is a plain tabular read, not a QGIS layer load -- pair with "
    "calculate_presence_gap to cross-reference presence against a severity/needs index.",
    {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the .csv/.xlsx/.xls 3W/4W file."},
            "admin_field": {"type": "string", "description": "Column holding the admin unit name/P-code each activity row belongs to."},
            "org_field": {"type": "string", "description": "Column holding the organization name/acronym running each activity."},
            "sector_field": {"type": "string", "description": "Optional column holding the sector/cluster (e.g. WASH, Health) -- adds sector coverage per unit."},
            "sheet_name": {"type": "string", "description": "Sheet name for Excel files with multiple sheets. Defaults to the first sheet."},
            "delimiter": {"type": "string", "description": "CSV field delimiter. Defaults to ','."},
        },
        "required": ["file_path", "admin_field", "org_field"],
    },
)
def load_3w_data(file_path, admin_field, org_field, sector_field=None, sheet_name=None, delimiter=","):
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        rows, columns = _read_tabular_rows(file_path, sheet_name=sheet_name, delimiter=delimiter)
    except ImportError:
        return {"error": "pandas and openpyxl are required to read Excel files. Install via qpip, or in the OSGeo4W Shell: python -m pip install pandas openpyxl"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Could not read '{file_path}': {e}"}

    required = [admin_field, org_field] + ([sector_field] if sector_field else [])
    missing = [f for f in required if f not in columns]
    if missing:
        return {"error": f"Field(s) {missing} not found in '{file_path}'. Available columns: {columns}"}
    if not rows:
        return {"error": f"'{file_path}' has no data rows."}

    units, skipped = _aggregate_3w_presence(rows, admin_field, org_field, sector_field)
    if not units:
        return {"error": f"No usable rows -- every row was missing '{admin_field}' or '{org_field}'."}

    results = []
    for bucket in units.values():
        entry = {
            "unit": bucket["unit"],
            "organization_count": len(bucket["orgs"]),
            "organizations": sorted(bucket["orgs"]),
            "activity_count": bucket["activity_count"],
        }
        if sector_field:
            entry["sector_count"] = len(bucket["sectors"])
            entry["sectors"] = sorted(bucket["sectors"])
        results.append(entry)
    results.sort(key=lambda r: r["organization_count"], reverse=True)

    return {
        "success": True,
        "admin_field": admin_field,
        "org_field": org_field,
        "sector_field": sector_field,
        "total_rows": len(rows),
        "skipped_rows": skipped,
        "distinct_admin_units": len(results),
        "units": results,
    }


def _coerce_number(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _aggregate_rows(rows, group_by_field, value_field, agg):
    """Pure Python groupby, no QGIS needed -- works on any list of flat dict
    rows, e.g. from extract_pdf_tables/extract_word_tables's 'rows' output, or
    any other list of {field: value} objects the caller already has."""
    if agg == "count":
        counts = {}
        skipped = 0
        for row in rows:
            if group_by_field not in row:
                skipped += 1
                continue
            key = row[group_by_field]
            counts[key] = counts.get(key, 0) + 1
        return counts, skipped

    groups = {}
    skipped = 0
    for row in rows:
        if group_by_field not in row:
            skipped += 1
            continue
        num = _coerce_number(row.get(value_field))
        if num is None:
            skipped += 1
            continue
        groups.setdefault(row[group_by_field], []).append(num)

    result = {}
    for key, nums in groups.items():
        if agg == "sum":
            result[key] = sum(nums)
        elif agg == "mean":
            result[key] = sum(nums) / len(nums)
        elif agg == "min":
            result[key] = min(nums)
        elif agg == "max":
            result[key] = max(nums)
    return result, skipped


@register_tool(
    "aggregate_data",
    "Group rows of data by a field and compute sum/count/mean/min/max of another field per group "
    "-- e.g. 'total incidents by district' or 'average funding by cluster'. Takes structured rows "
    "such as the output of extract_pdf_tables/extract_word_tables (their 'rows' list), or any "
    "other list of flat {field: value} objects you've already gathered.",
    {
        "type": "object",
        "properties": {
            "rows": {"type": "array", "items": {"type": "object"}, "description": "List of flat row objects to aggregate."},
            "group_by_field": {"type": "string"},
            "value_field": {"type": "string", "description": "Numeric field to aggregate. Not needed when agg is 'count'."},
            "agg": {"type": "string", "description": "'sum' (default), 'count', 'mean', 'min', or 'max'."},
        },
        "required": ["rows", "group_by_field"],
    },
)
def aggregate_data(rows, group_by_field, value_field=None, agg="sum"):
    agg = (agg or "sum").lower()
    if agg not in _AGG_FUNCS:
        return {"error": f"agg must be one of {sorted(_AGG_FUNCS)}."}
    if not rows:
        return {"error": "rows must not be empty."}
    if agg != "count" and not value_field:
        return {"error": "value_field is required unless agg is 'count'."}

    result, skipped = _aggregate_rows(rows, group_by_field, value_field, agg)
    if not result:
        missing = f"'{group_by_field}'" + (f"/'{value_field}'" if value_field else "")
        return {"error": f"No rows had a usable {missing} value."}
    return {
        "success": True,
        "group_by_field": group_by_field,
        "value_field": value_field,
        "agg": agg,
        "groups": result,
        "skipped_rows": skipped,
    }


@register_tool(
    "generate_sector_coverage_report",
    "Generate the standard humanitarian 'beneficiaries reached vs. target' coverage table and bar "
    "chart in one call, grouped by sector/cluster (or any other categorical field, e.g. admin unit) "
    "-- instead of chaining aggregate_data + generate_chart by hand. Sums reached_field (and "
    "target_field, if given) per group_by_field value, computes a coverage percentage per group when "
    "a target is given, and renders a bar chart. Returns the underlying table alongside the chart "
    "path so both the numbers and the visual are available. When a target is given, the table is "
    "sorted worst-coverage-first (groups with no target on record sort alongside the worst "
    "performers, not silently last, since missing target data is itself worth flagging in a gap "
    "analysis) -- otherwise sorted by reached, highest first.",
    {
        "type": "object",
        "properties": {
            "rows": {"type": "array", "items": {"type": "object"}, "description": "List of flat row objects, e.g. one per activity/beneficiary record."},
            "group_by_field": {"type": "string", "description": "Field to group by -- typically sector/cluster, but any categorical field works (e.g. admin unit)."},
            "reached_field": {"type": "string", "description": "Numeric field holding beneficiaries reached per row."},
            "target_field": {"type": "string", "description": "Optional numeric field holding the target per row -- enables a coverage percentage."},
            "title": {"type": "string", "description": "Chart title. Defaults to 'Coverage by {group_by_field}'."},
            "output_path": {"type": "string", "description": "Where to save the chart PNG. Defaults to a temp file."},
        },
        "required": ["rows", "group_by_field", "reached_field"],
    },
)
def generate_sector_coverage_report(rows, group_by_field, reached_field, target_field=None, title=None, output_path=None):
    output_path = resolve_output_path(output_path)   # rc22 smoke N3/N8/N9: anchor relative paths to the project (see _paths.py)
    reached_result = aggregate_data(rows, group_by_field, reached_field, agg="sum")
    if "error" in reached_result:
        return reached_result
    reached_by_group = reached_result["groups"]

    target_by_group = {}
    target_skipped_rows = 0
    if target_field:
        target_result = aggregate_data(rows, group_by_field, target_field, agg="sum")
        if "error" in target_result:
            return target_result
        target_by_group = target_result["groups"]
        target_skipped_rows = target_result["skipped_rows"]

    table = []
    for group, reached in reached_by_group.items():
        entry = {group_by_field: group, "reached": reached}
        if target_field:
            target = target_by_group.get(group)
            entry["target"] = target
            entry["coverage_percent"] = round((reached / target) * 100, 1) if target else None
        table.append(entry)

    if target_field:
        table.sort(key=lambda e: e["coverage_percent"] if e["coverage_percent"] is not None else -1)
    else:
        table.sort(key=lambda e: e["reached"], reverse=True)

    chart_title = title or f"Coverage by {group_by_field}"
    if target_field:
        chart_values = [e["coverage_percent"] if e["coverage_percent"] is not None else 0 for e in table]
        y_label = "Coverage %"
    else:
        chart_values = [e["reached"] for e in table]
        y_label = "Reached"

    chart_res = generate_chart(
        "bar", chart_title, [str(e[group_by_field]) for e in table], chart_values,
        x_label=group_by_field, y_label=y_label, output_path=output_path,
    )
    if "error" in chart_res:
        return {"error": chart_res["error"], "table": table}

    return {
        "success": True,
        "group_by_field": group_by_field,
        "reached_field": reached_field,
        "target_field": target_field,
        "table": table,
        "chart_path": chart_res["output_path"],
        "reached_skipped_rows": reached_result["skipped_rows"],
        "target_skipped_rows": target_skipped_rows,
    }
