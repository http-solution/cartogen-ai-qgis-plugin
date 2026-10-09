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
]


def chains_for(needed_ids, limit=2):
    """Every chain whose required capabilities are all in `needed_ids`, in table order, at most `limit`. A request may fit two (a
    terrain study asking for contours AND slope). Pure."""
    needed = set(needed_ids or ())
    return [c for c in CHAINS if set(c["needs"]) <= needed][:limit]


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
            "stops there and tells you which steps ran.")


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
