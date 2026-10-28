"""What a request needs, in terms of data sources and actions, and which tools provide each.

Why (2026-10-09 cost investigation): the tool router ranked tools by incidental word overlap with their descriptions, so a long
natural-language request filled its 40 slots with weak matches (a dashboard, PDF-table and NDWI tool for a water-service request)
and, for the scenarios the tools could not cover, offered no fallback; the task matcher led with local-file tools for requests
that name OpenStreetMap or HDX. This table states the dependency directly: a phrase in the request names a CAPABILITY, and each
capability lists the registered tools that provide it, best first. Capabilities with no dedicated tool say so (`tools` empty,
`via` set), and the router then offers the constrained Processing tool and the script fallback instead of nothing.

Pure (stdlib only). tests/test_capabilities.py checks that every tool named here exists in the live registry, so the table cannot
drift from the tools."""
import contextlib
import re

# (id, regex over the lower-cased request, ordered dedicated tools, tools that can cover it when none does)
_TABLE = (
    ("osm_data", r"\b(openstreetmap|open street map|osm|overpass)\b", ("fetch_osm_features", "ingest_osm_features"), ()),
    ("hdx_boundaries", r"\b(hdx|humanitarian data exchange|cod-?ab|administrative boundar\w*|admin\s*[0-4])\b",
     ("fetch_hdx_admin_boundaries", "fetch_geoboundaries", "search_hdx_datasets"), ()),
    ("buffer", r"\bbuffers?\b|\bservice buffer\b|\bexclusion zones?\b|\bcircular (study )?area\b|\b\d+(\.\d+)?\s*(km|m|metre|meter)s?\s+(radius|circular)",
     ("buffer_analysis",), ()),
    ("reproject", r"\b(epsg\s*:?\s*\d{4,5}|utm\b|metric projection|reproject\w*)", ("reproject_layer",), ()),
    ("dissolve", r"\bdissolv\w*", ("dissolve_layer",), ()),
    ("difference", r"\b(spatial difference|difference against|erase|subtract|unserved)\b", ("difference_layers",), ()),
    ("clip", r"\bclip\w*\b", ("clip_layer",), ()),
    ("area", r"\b(area|square kilomet\w*|sq\.? ?km|hectares?|geodesic)\b", ("calculate_area",), ()),
    ("length", r"\b(length|kilomet\w* of road|passable road|road length)\b", ("calculate_length",), ()),
    ("centroids", r"\bcentroids?\b", ("centroid",), ()),
    ("labels", r"\blabel\w*\b", ("apply_labels",), ()),
    ("graduated_style", r"\b(graduated|color ramp|colour ramp|symboli[sz]e\w*|choropleth)\b", ("apply_graduated_style",), ()),
    ("categorized_style", r"\b(style|colou?r)\b.{0,40}\b(red|green|amber|blue|yellow|categor\w*)\b|\bred and green\b",
     ("apply_categorized_style", "change_layer_color"), ()),
    # Long-request audit 2026-10-14: "style them with a pale fill and a grey outline" matched neither style row above (no red/green/blue word),
    # so a 47-word map request was offered no tool that can change a fill or an outline.
    ("fill_outline_style", r"\b(pale|light|dark|solid|no|transparent|semi-?transparent)\s+fill\b|\b(fill|outline|border|stroke)\s+(colou?r|width)\b|\b(grey|gray|black|white|red|blue|green)\s+(outline|border|stroke)\b|\bstyle\s+(it|them|the layer|these)\b",
     ("change_layer_color", "apply_categorized_style"), ()),
    ("slope", r"\b(slope|steep|terrain)\b", ("slope_analysis",), ()),
    # A bare "dem" is NOT a download request: "draw contour lines of the dem every 100" (1.18.0 hand run, row A5) names a DEM that is already
    # loaded, but this row made it a two-step workflow (fetch, then contour), offered fetch_dem and run_steps, and the model planned a fetch that
    # failed on the cell limit before it used the loaded layer. A download is a download verb near the DEM, a named source, or a DEM "for/of" a place.
    ("elevation_download", (r"\b(srtm|opentopography|terrain tiles?|elevation source|digital elevation)\b"
                            r"|\b(download|fetch|retrieve|pull|grab|obtain|get)\b.{0,40}\b(dem|elevation|terrain)\b"
                            r"|\b(dem|elevation data|terrain data)\s+(for|of|covering|around|over)\s+(?!the\s+(layer|raster|dem|map)\b)"),
     ("fetch_dem",), ()),
    ("population_data", r"\b(worldpop|population (raster|grid|data|exposure)|exposed population|people (living|exposed))\b",
     ("fetch_worldpop_population", "estimate_population_exposure"), ()),
    ("pcode_check", r"\bp-?codes?\b.{0,60}\b(valid\w*|check\w*|unique\w*|hierarch\w*|duplicat\w*)|\b(valid\w*|check\w*|verify\w*)\b.{0,40}\bp-?codes?\b",
     ("check_pcode_uniqueness", "check_pcode_hierarchy"), ()),
    ("contours", r"\bcontour\w*\b", ("generate_contours",), ()),
    ("split_lines", r"\bsplit\b.{0,60}\b(geometry|road|highway|line)s?\b|\bsplit (the )?(highway|road)",
     ("split_lines_by_zones",), ()),
    ("walking_access", r"\b(walking|walk|travel|drive|driving)\b.{0,40}\b(access|distance|time|minutes?)\b|\bservice area\b",
     ("calculate_service_area",), ()),
    ("rank", r"\brank\w*\b|\blargest to smallest\b", ("field_statistics",), ("run_query",)),
    ("filter_select", r"\b(filter|select|only)\b.{0,50}\b(governorates?|districts?|admin|where)\b", ("select_by_attribute",), ()),
    ("extent", r"\b(bounding box|bbox|study area)\b", ("get_layer_extent",), ()),
    # 1.18.4 hand run A13 ("find Sentinel-2 scenes over Aden ..."): the router offered the scene search but not geocode_and_enrich, the only
    # tool that turns a place name into the area the search needs, so the model looked for a tool and stopped (DEF-10).
    ("satellite_scenes", r"\b(sentinel[- ]?2|satellite (scenes?|imagery|images?)|stac)\b", ("search_stac_satellite_imagery", "geocode_and_enrich"), ()),
    ("point_from_coordinates", r"\bcoordinates?\b|\b\d{1,2}\.\d+\s*°?\s*[ns]\b", ("add_point_layer",), ()),
    ("zoom", r"\bzoom\b", ("zoom_to_layer",), ()),
    ("export", r"\b(export|save (it |them |the \w+ )?as|write (it |them )?to (a |the )?(file|geopackage|csv|shapefile))\b", ("export_layer", "export_to_csv"), ()),
    ("report_numbers", r"\b(report|total|sum)\b", ("field_statistics",), ()),
)
_COMPILED = tuple((cid, re.compile(rx, re.I), tools, via) for cid, rx, tools, via in _TABLE)

# Everyday QGIS actions that have NO dedicated tool and whose Processing algorithm is not on the allow-list (QGIS vocabulary audit 2026-10-14).
# Kept apart from _TABLE on purpose: _TABLE entries count toward "multi-step workflow" detection, and these must not turn a plain request
# into one. Before this, a request such as "extract the vertices of the roads" was offered neither a tool nor the script fallback (the
# script is only offered when NOTHING else matched), so the model answered that it could not. Each phrase now earns the script fallback
# and find_tools. Adding an algorithm to the Processing allow-list instead is a security decision with per-algorithm parameter checks
# (docs/IMPLEMENTATION_TRACKER.md, owner decision) and is deliberately not made here.
_NO_TOOL_ACTIONS = (
    ("extract_vertices", r"\b(extract|get)\s+(the\s+)?vertices\b|\bvertices of\b"),
    ("densify", r"\bdensif\w*"),
    ("polygons_lines", r"\bpolygons?\s+to\s+lines?\b|\blines?\s+to\s+polygons?\b"),
    ("bounding_geometry", r"\bminimum bounding\b|\boriented (minimum )?bounding\b|\bbounding (box|geometry|rectangle) of (each|every)\b"),
    ("random_points", r"\brandom points?\b"),
    ("split_layer", r"\bsplit (the )?(vector )?layer\b"),
    ("delete_duplicates", r"\b(delete|remove)\s+(the\s+)?duplicate\s+(geometr\w+|features|points|records)\b"),
    ("raster_calculator", r"\braster calculator\b|\bband math\b|\bmap algebra\b"),
    ("polygonize", r"\bpolygoni[sz]e\b"),
    ("rasterize", r"\brasteri[sz]e\b"),
    ("viewshed", r"\bviewshed\b|\bline of sight\b|\bintervisibility\b"),
    ("basemap", r"\b(add|load|show|insert)\b.{0,25}\b(basemap|base map|xyz tiles?)\b"),
    ("measure", r"\bmeasure\b.{0,30}\b(distance|length|area|angle)\b|\bdistance between (two|these|the) points\b"),
)
_NO_TOOL_COMPILED = tuple((cid, re.compile(rx, re.I)) for cid, rx in _NO_TOOL_ACTIONS)
NO_TOOL_FALLBACK_TOOLS = ("execute_pyqgis_script", "run_allowlisted_processing_algorithm")


def uncovered_actions(query):
    """Ids of everyday QGIS actions the request names that have no dedicated tool. Pure."""
    text = (query or "").lower()
    return [cid for cid, rx in _NO_TOOL_COMPILED if rx.search(text)]

# A request may need many of these; this bounds how many tool slots the table can claim so it never crowds out the rest.
MAX_REQUIRED_TOOLS = 16


def needed_capabilities(query):
    """[(capability id, dedicated tools, fallback tools)] for the capabilities the request names, in table order. Pure."""
    text = (query or "").lower()
    return [(cid, tools, via) for cid, rx, tools, via in _COMPILED if rx.search(text)]


def required_tools(query, limit=MAX_REQUIRED_TOOLS):
    """Ordered, de-duplicated tool names the request needs: the dedicated tools of every capability it names, then the fallback
    tools of any capability that has no dedicated tool. Capped at `limit`."""
    ordered = []
    needs = needed_capabilities(query)
    for _cid, tools, _via in needs:
        for name in tools:
            if name not in ordered:
                ordered.append(name)
    for _cid, tools, via in needs:
        if not tools:
            for name in via:
                if name not in ordered:
                    ordered.append(name)
    if uncovered_actions(query):
        for name in NO_TOOL_FALLBACK_TOOLS:
            if name not in ordered:
                ordered.append(name)
    return ordered[:limit]


def uncovered_capabilities(query):
    """Capability ids the request names that have NO dedicated tool: these are the steps the plugin can only do through Processing or
    a script, so the user (and the cost guard) can be told up front instead of after a dozen failed rounds."""
    return [cid for cid, tools, _via in needed_capabilities(query) if not tools] + uncovered_actions(query)


def lead_tools_for_task(tools, query):
    """Re-order a task's tool chain for what the request names: a named data source puts its fetch tools first and local-file loaders
    (`add_layer_from_path`) go last unless the request names a file. Pure; returns a new list."""
    tools = list(tools or [])
    text = (query or "").lower()
    lead = []
    for cid, rx, dedicated, _via in _COMPILED:
        if cid in ("osm_data", "hdx_boundaries") and rx.search(text):
            lead.extend(t for t in dedicated if t not in lead)
    names_file = bool(re.search(r"\.(shp|gpkg|geojson|csv|tif|tiff|kml)\b|[a-z]:\\|/[\w.-]+/", text))
    rest = [t for t in tools if t not in lead]
    if not names_file and lead:
        loaders = [t for t in rest if t == "add_layer_from_path"]
        rest = [t for t in rest if t != "add_layer_from_path"] + loaders
    return lead + rest


MULTI_STEP_MIN_CAPABILITIES = 3
_PLAIN_NAMES = {
    "osm_data": "get OpenStreetMap data", "hdx_boundaries": "get HDX / COD administrative boundaries", "buffer": "buffer",
    "reproject": "reproject", "dissolve": "dissolve", "difference": "difference / erase", "clip": "clip", "area": "area",
    "length": "length", "centroids": "centroids", "labels": "labels", "graduated_style": "graduated colour style",
    "categorized_style": "categorised colour style", "slope": "slope", "elevation_download": "elevation (DEM) download",
    "contours": "contour lines", "population_data": "population data / exposure", "pcode_check": "P-code validation", "split_lines": "split lines by zones", "walking_access": "walking / travel access",
    "rank": "rank", "filter_select": "filter / select", "extent": "bounding box", "satellite_scenes": "satellite scene search", "point_from_coordinates": "point from coordinates",
    "zoom": "zoom", "export": "export", "report_numbers": "report totals",
}


def ordered_steps(query):
    """[(capability id, dedicated tools, fallback tools)] in the order the request first mentions them. Pure."""
    text = (query or "").lower()
    found = []
    for cid, rx, tools, via in _COMPILED:
        match = rx.search(text)
        if match:
            found.append((match.start(), cid, tools, via))
    return [(cid, tools, via) for _pos, cid, tools, via in sorted(found, key=lambda x: x[0])]


def is_multi_step(query):
    """Three or more named steps, or any request a pre-built chain covers (a two-step chain is still a multi-step workflow)."""
    needed = needed_capabilities(query)
    if len(needed) >= MULTI_STEP_MIN_CAPABILITIES:
        return True
    try:
        from .chains import chains_for
        return bool(chains_for([cid for cid, _t, _v in needed]))
    except Exception:
        return False


def workflow_directive(query):
    """Directive text for a request that names several steps. A single matched 'task' misleads such a request (a Taizz terrain
    study matched 'Collect GPS coordinates'; a coastal-highway analysis matched 'Produce security briefings'), so this lists what the
    request itself names, in its own order, with the tool for each step, and states which steps have no dedicated tool."""
    steps = ordered_steps(query)
    lines, fallback = [], []
    for cid, tools, via in steps:
        label = _PLAIN_NAMES.get(cid, cid)
        if tools:
            lines.append(f"{label}: {', '.join(tools[:2])}")
        else:
            lines.append(f"{label}: no dedicated tool")
            fallback.extend(n for n in via if n not in fallback)
    text = ("This request is a multi-step workflow, not one task. Steps it names, in its own order: " + "; ".join(lines) + ".")
    if fallback:
        text += (" Steps marked 'no dedicated tool' can only be done with " + " or ".join(f"`{n}`" for n in fallback)
                 + " (prefer a constrained Processing algorithm; use a script only as a last resort and say so).")
    with contextlib.suppress(Exception):
        from .chains import chains_for, chain_directive
        from .discovery import is_execution_request
        found = chains_for([cid for cid, _t, _v in needed_capabilities(query)]) if is_execution_request(query) else []
        if found:
            text += " " + chain_directive(found)
    text += (" Do each step once. When you already know every argument of a chain of steps (you choose the output layer names), "
             "send that chain as ONE `run_steps` call instead of one turn per step; check results before continuing only where the "
             "next step genuinely depends on what you see. If a step cannot be completed say which steps are done and "
             "which are not -- never report the whole request as complete.")
    return text
