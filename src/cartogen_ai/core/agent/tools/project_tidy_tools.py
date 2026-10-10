# -*- coding: utf-8 -*-
"""
Tidy an existing project's layers (GitHub #120 / #128, rc11 smoke test).

Fixes for new work (CRS question, origin reuse, population ramp, re-download replace) stop NEW clutter, but a project made
with an older build keeps what it already has: an opaque black WorldPop raster, the same layer loaded two or three times,
and scratch origin layers that vanish when the project closes. This tool finds those and, only when asked, repairs them.

It never deletes a layer: a duplicate copy is hidden (untick it; `remove_layer` is the confirmed way to delete), a
population raster is restyled with the population ramp, and a scratch layer is written into the project's results
GeoPackage. Called without apply=true it only reports. The detection rules are pure and unit tested; the repair needs real
QGIS and is covered by tests/test_project_tidy_live.py in CI.
"""
import hashlib

from .registry import register_tool

try:
    from qgis.core import QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


# ---------------------------------------------------------------- pure --

def duplicate_groups(entries):
    """Groups of layer ids that are the same layer loaded more than once. Pure.

    entries: iterable of {id, name, signature, visible}. Two layers are duplicates only when the name AND a data signature
    match (a missing signature never matches: two different memory layers can share a name). Each group lists the copy to
    KEEP first -- the visible one, else the earliest -- followed by the extra copies."""
    buckets = {}
    for e in entries:
        sig = e.get("signature")
        if not sig:
            continue
        buckets.setdefault((e.get("name"), sig), []).append(e)
    groups = []
    for items in buckets.values():
        if len(items) < 2:
            continue
        keep = next((i for i in items if i.get("visible")), items[0])
        groups.append([keep["id"]] + [i["id"] for i in items if i is not keep])
    return groups


def needs_population_ramp(name, renderer_type, is_population_name):
    """True for a WorldPop-named raster that is drawn with something other than a pseudocolour ramp (the old black raster). Pure."""
    return bool(is_population_name) and str(renderer_type or "").lower() != "singlebandpseudocolor"


def vector_signature(provider, source, feature_count, wkb_samples):
    """A comparable signature for a vector layer, or None when one cannot be trusted. Pure.

    A file/database layer is identified by its source. A memory layer has the same source string whatever it holds, so it is
    identified by its feature count plus a hash of its geometries; without geometries to hash there is no signature."""
    if str(provider).lower() != "memory":
        return f"src:{source}" if source else None
    if not wkb_samples:
        return None
    digest = hashlib.sha1("|".join(sorted(wkb_samples)).encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"mem:{feature_count}:{digest}"


# ---------------------------------------------------------------- QGIS --

def _entries(project):
    from .raster_tools import _describe_population_raster
    out = []
    root = project.layerTreeRoot()
    for node in root.findLayers():
        layer = node.layer()
        if layer is None:
            continue
        is_raster = hasattr(layer, "bandCount")
        provider = layer.providerType() if hasattr(layer, "providerType") else ""
        if is_raster:
            signature = f"src:{layer.source()}" if layer.source() else None
        else:
            samples = []
            if str(provider).lower() == "memory":
                for i, f in enumerate(layer.getFeatures()):
                    if i >= 500:
                        break
                    g = f.geometry()
                    if g is not None and not g.isEmpty():
                        samples.append(bytes(g.asWkb()).hex())
            signature = vector_signature(provider, layer.source(), layer.featureCount(), samples)
        renderer = layer.renderer().type() if layer.renderer() is not None else ""
        out.append({
            "id": layer.id(), "name": layer.name(), "layer": layer, "node": node, "signature": signature,
            "visible": node.isVisible(), "is_raster": is_raster, "provider": provider,
            "renderer": renderer, "population": _describe_population_raster(layer.name())[1] is not None,
            "features": 0 if is_raster else layer.featureCount(),
        })
    return out


@register_tool(
    "tidy_project_layers",
    "Find and repair clutter left in a project by older Cartogen AI builds: (1) the same layer loaded more than once "
    "(identical name and data) -- the extra copies are HIDDEN, never deleted; (2) a WorldPop population raster drawn "
    "opaque black instead of with the population colour ramp -- restyled; (3) temporary scratch layers (such as origin "
    "points) that are lost when the project is closed -- saved into the project's results GeoPackage (the project must "
    "already be saved). Call with apply=false (default) to only list what it found, then apply=true to repair. It does "
    "not delete layers; use remove_layer, which asks for confirmation, to delete a hidden duplicate.",
    {
        "type": "object",
        "properties": {
            "apply": {"type": "boolean", "description": "false (default): report only. true: hide duplicate copies, restyle population rasters and save scratch layers."},
        },
    },
)
def tidy_project_layers(apply=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    try:
        project = QgsProject.instance()
        entries = _entries(project)
        by_id = {e["id"]: e for e in entries}

        groups = duplicate_groups(entries)
        duplicates = [{"keep": by_id[g[0]]["name"], "keep_id": g[0], "extra_ids": g[1:],
                       "copies": len(g)} for g in groups]
        ramps = [e for e in entries if e["is_raster"] and needs_population_ramp(e["name"], e["renderer"], e["population"])]
        scratch = [e for e in entries if not e["is_raster"] and str(e["provider"]).lower() == "memory" and e["features"] > 0]

        report = {
            "success": True,
            "applied": bool(apply),
            "duplicate_layers": [{"name": d["keep"], "copies": d["copies"]} for d in duplicates],
            "population_rasters_without_ramp": [e["name"] for e in ramps],
            "scratch_layers": [{"name": e["name"], "features": e["features"]} for e in scratch],
        }
        if not (duplicates or ramps or scratch):
            report["message"] = "Nothing to tidy."
            return report
        if not apply:
            report["message"] = ("Nothing was changed. Call again with apply=true to hide the extra duplicate copies, "
                                 "restyle the population rasters and save the scratch layers.")
            return report

        changes = []
        for d in duplicates:
            for layer_id in d["extra_ids"]:
                by_id[layer_id]["node"].setItemVisibilityChecked(False)
                changes.append(f"hid duplicate copy of '{d['keep']}'")
        if ramps:
            from .output_style import style_continuous_raster
            for e in ramps:
                ok = style_continuous_raster(e["layer"], "population")
                changes.append(f"restyled '{e['name']}' with the population ramp" if ok
                               else f"could not restyle '{e['name']}'")
        persist_notes = []
        if scratch:
            from ..results_store import persist_layer
            for e in scratch:
                res = persist_layer(e["layer"], tool="tidy_project_layers")
                if res.get("persisted"):
                    changes.append(f"saved scratch layer '{e['name']}' into the results GeoPackage")
                else:
                    persist_notes.append(f"'{e['name']}': {res.get('reason')}")
        report["changes"] = changes
        if persist_notes:
            report["not_saved"] = persist_notes
        report["message"] = "Tidied. Duplicates were hidden, not deleted."
        return report
    except Exception as e:
        return {"error": f"tidy_project_layers failed: {e}"}
