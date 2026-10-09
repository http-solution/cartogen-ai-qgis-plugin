# -*- coding: utf-8 -*-
"""Pre-built `run_steps` chains for workflows that recur.

A chain is a vetted skeleton: which tools, in which order, with which argument names, and which results feed which step
(`$prev.layer_name`). The model only fills the `<slots>` from the user's request. This removes the two ways a model-written chain
goes wrong -- a wrong tool order or argument name, and a forgotten preparation step (buffering a geographic layer in degrees, for
example) -- without the plugin guessing any data. Offered as text in the workflow directive; nothing here runs by itself.

Scope is deliberately small: only chains whose tools, argument names and result fields were checked against the real tools
(tests/test_chains.py statically against the registered schemas; tests/test_chains_live.py by running them in QGIS 4.2.2). Chains that
touch the network (fetch_dem) are checked against a local server, not the real bucket in CI. Not measured: whether real models
follow the skeleton."""
import json

from . import step_runner

# id -> (needs: capability ids that must all be named by the request, title, slots, steps)
CHAINS = [
    {"id": "exclusion_zone_split", "needs": ("buffer", "split_lines"),
     "title": "buffer exclusion zones around points, then split a line by them",
     "slots": {"points": "point layer name (checkpoints); it must already exist -- create it first with add_point_layer if the user gave coordinates", "utm": "projected CRS code for the area, e.g. EPSG:32638",
               "metres": "buffer distance in metres", "zones": "name for the buffer layer", "line": "line layer name (the highway)"},
     "steps": [
         {"tool": "reproject_layer", "arguments": {"layer_name": "<points>", "crs_code": "<utm>"}},
         {"tool": "buffer_analysis", "arguments": {"layer_name": "$prev.layer_name", "distance": "<metres>", "output_name": "<zones>"}},
         {"tool": "split_lines_by_zones", "arguments": {"line_layer": "<line>", "zone_layer": "$prev.layer_name"}}]},
    {"id": "buffer_then_clip", "needs": ("buffer", "clip"),
     "title": "buffer a layer in metres, then clip another layer to the buffer",
     "slots": {"source": "layer to buffer", "utm": "projected CRS code for the area, e.g. EPSG:32638", "metres": "buffer distance in metres",
               "target": "layer to clip"},
     "steps": [
         {"tool": "reproject_layer", "arguments": {"layer_name": "<source>", "crs_code": "<utm>"}},
         {"tool": "buffer_analysis", "arguments": {"layer_name": "$prev.layer_name", "distance": "<metres>"}},
         {"tool": "clip_layer", "arguments": {"input_layer": "<target>", "mask_layer": "$prev.layer_name"}}]},
    {"id": "terrain_contours", "needs": ("elevation_download", "contours"),
     "title": "download a DEM for an area, then make contour lines",
     "slots": {"aoi": "layer whose extent is the study area", "interval": "contour spacing in metres"},
     "steps": [
         {"tool": "fetch_dem", "arguments": {"layer_name": "<aoi>"}},
         {"tool": "generate_contours", "arguments": {"raster_layer": "$prev.layer_name", "interval": "<interval>"}}]},
    {"id": "terrain_slope", "needs": ("elevation_download", "slope"),
     "title": "download a DEM for an area, then compute slope",
     "slots": {"aoi": "layer whose extent is the study area"},
     "steps": [
         {"tool": "fetch_dem", "arguments": {"layer_name": "<aoi>"}},
         {"tool": "slope_analysis", "arguments": {"dem_layer": "$prev.layer_name"}}]},
    {"id": "coverage_gap", "needs": ("buffer", "dissolve", "difference"),
     "title": "buffer facilities in metres, merge the buffers, and subtract them from an area to find what lies OUTSIDE that straight-line distance",
     "caveat": ("This is a straight-line distance gap only: it ignores roads, capacity, opening status and where people live. Say so, "
                "and do not call the result an operational service gap; for people beyond a travel time use population_access_gap."),
     "slots": {"facilities": "point layer name", "utm": "projected CRS code for the area, e.g. EPSG:32638", "metres": "buffer distance in metres",
               "area": "polygon layer of the area to check (districts, boundary)"},
     "steps": [
         {"tool": "reproject_layer", "arguments": {"layer_name": "<facilities>", "crs_code": "<utm>"}},
         {"tool": "buffer_analysis", "arguments": {"layer_name": "$prev.layer_name", "distance": "<metres>"}},
         {"tool": "dissolve_layer", "arguments": {"layer_name": "$prev.layer_name"}},
         {"tool": "difference_layers", "arguments": {"input_layer": "<area>", "overlay_layer": "$prev.layer_name"}}]},
    {"id": "outside_distance", "needs": ("buffer", "difference"),
     "title": "buffer a layer in metres and subtract it from another layer (what lies farther than that distance)",
     "slots": {"source": "layer to buffer", "utm": "projected CRS code for the area, e.g. EPSG:32638", "metres": "buffer distance in metres",
               "target": "layer to subtract the buffer from"},
     "steps": [
         {"tool": "reproject_layer", "arguments": {"layer_name": "<source>", "crs_code": "<utm>"}},
         {"tool": "buffer_analysis", "arguments": {"layer_name": "$prev.layer_name", "distance": "<metres>"}},
         {"tool": "difference_layers", "arguments": {"input_layer": "<target>", "overlay_layer": "$prev.layer_name"}}]},
    {"id": "clip_dem_slope", "needs": ("clip", "slope"),
     "title": "clip a DEM raster to a boundary, then compute slope",
     "slots": {"dem": "DEM raster layer name", "boundary": "polygon layer to clip to"},
     "steps": [
         {"tool": "raster_clip", "arguments": {"raster_layer": "<dem>", "mask_layer": "<boundary>"}},
         {"tool": "slope_analysis", "arguments": {"dem_layer": "$prev.layer_name"}}]},
    {"id": "clip_and_style", "needs": ("clip", "graduated_style"),
     "title": "clip a layer to a boundary, colour the result by a numeric field, and zoom to it",
     "slots": {"layer": "layer to clip", "boundary": "polygon layer to clip to", "field": "numeric field to colour by"},
     "steps": [
         {"tool": "clip_layer", "arguments": {"input_layer": "<layer>", "mask_layer": "<boundary>"}},
         {"tool": "apply_graduated_style", "arguments": {"layer_name": "$prev.layer_name", "field": "<field>"}},
         {"tool": "zoom_to_layer", "arguments": {"layer_name": "$1.layer_name"}}]},
    {"id": "reproject_and_export", "needs": ("reproject", "export"),
     "title": "reproject a layer, then export it to a file",
     "slots": {"layer": "layer to reproject", "crs": "target CRS code, e.g. EPSG:32638", "format": "export format the user asked for",
               "path": "output file path"},
     "steps": [
         {"tool": "reproject_layer", "arguments": {"layer_name": "<layer>", "crs_code": "<crs>"}},
         {"tool": "export_layer", "arguments": {"layer_name": "$prev.layer_name", "format": "<format>", "output_path": "<path>"}}]},
    {"id": "population_exposure", "needs": ("population_data",),
     "title": "download the WorldPop population raster for an area, then sum the population inside each polygon of an area layer",
     "slots": {"iso3": "three-letter country code", "extent": "layer covering the area of interest (limits the download)",
               "area": "polygon layer to sum the population in (districts, or a buffer you made)"},
     "steps": [
         {"tool": "fetch_worldpop_population", "arguments": {"iso3": "<iso3>", "extent_layer": "<extent>"}},
         {"tool": "estimate_population_exposure", "arguments": {"population_raster_layer": "$prev.layer_name", "area_layer": "<area>"}}]},
    {"id": "admin_boundary_validation", "needs": ("hdx_boundaries", "pcode_check"),
     "title": "download OCHA COD-AB admin boundaries, then check P-code uniqueness and the parent/child P-code hierarchy",
     "slots": {"iso3": "three-letter country code", "level": "admin level, e.g. 2"},
     "steps": [
         {"tool": "fetch_hdx_admin_boundaries", "arguments": {"iso3": "<iso3>", "admin_level": "<level>"}},
         {"tool": "check_pcode_uniqueness", "arguments": {"layer_name": "$prev.layer_name"}},
         {"tool": "check_pcode_hierarchy", "arguments": {"layer_name": "$1.layer_name"}}]},
]


def chains_for(needed_ids, limit=2):
    """Every chain whose required capabilities are all in `needed_ids`, in table order, at most `limit`. A request may fit two (a
    terrain study asking for contours AND slope). Pure."""
    needed = set(needed_ids or ())
    fits = [c for c in CHAINS if set(c["needs"]) <= needed]
    # A chain whose steps are all contained in a more specific chain that also fits is redundant (buffer+dissolve+difference
    # already includes buffer+difference).
    fits = [c for c in fits if not any(set(c["needs"]) < set(o["needs"]) for o in fits)]
    return fits[:limit]


def skeleton_json(chain):
    return json.dumps({"steps": chain["steps"]}, separators=(",", ":"))


def chain_directive(chains):
    """Directive text for one or more chains."""
    if not chains:
        return ""
    parts = [_one_directive(c) for c in chains]
    if len(chains) > 1:
        parts.append("Where chains share a step (the same fetch_dem), run it once and reuse its layer.")
    return " ".join(parts)


def _one_directive(chain):
    slots = "; ".join(f"<{k}> = {v}" for k, v in chain["slots"].items())
    return (f"Known-good chain for this ({chain['title']}): call `run_steps` with {skeleton_json(chain)} -- replace each <slot> with a "
            f"value from the user's request ({slots}); keep the $prev references and the step order. If a slot is not stated and "
            "cannot be read from the project, ask instead of guessing. If a step reports an error or waits for confirmation the chain "
            "stops there and tells you which steps ran." + (" " + chain["caveat"] if chain.get("caveat") else ""))


def validate_chain(chain, schemas, operation_of):
    """Error text or None: the skeleton must itself pass run_steps' validation against the real tool schemas, and use only argument
    names those tools declare. Used by the tests so a renamed parameter fails CI rather than a user's request."""
    problem = step_runner.validate_steps(chain["steps"], schemas, operation_of)
    if problem:
        return problem
    for i, step in enumerate(chain["steps"], 1):
        declared = set((schemas[step["tool"]] or {}).get("properties", {}))
        unknown = [a for a in step["arguments"] if a not in declared]
        if unknown:
            return f"Step {i} ({step['tool']}) uses undeclared argument(s): {', '.join(unknown)}."
    return None
