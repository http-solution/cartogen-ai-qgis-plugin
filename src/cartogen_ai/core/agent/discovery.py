# -*- coding: utf-8 -*-
"""Input discovery for pre-built chains: what is actually in the project, and which chain slots it can fill.

Layer NAMES alone were all the preflight knew. A chain also depends on geometry type (a line layer to split, polygons to clip to),
on whether a field is numeric, and on a projected CRS that suits the area. `gather_facts` reads those from the open project (main thread
only); everything else here is pure so it can be unit tested without QGIS.

What this does and does not do: it proposes bindings (a layer the request names, or the only layer of the right kind) and a UTM zone
derived from a layer's extent, and says plainly when a slot has no candidate. It never invents data, never picks between several equally
good layers (it lists them and the model must ask), and a derived UTM zone is a suggestion for the model to pass on, not a rule.
Not verified against a real model."""
import re

from .tools.corridor_tools import utm_epsg_for

_QUESTION = re.compile(r"^\s*(how (do|can|could|would|should|does)|what (is|are|does|would|do)|why\b|explain\b|which tool|can you explain|"
                       r"tell me (how|about|what)|describe how)", re.I)
_GEOM = {"Point": "point", "Line": "line", "Polygon": "polygon"}


def is_execution_request(query):
    """False for a question about method ('how do I buffer...', 'explain...'): those are answered, not run. Pure."""
    return not _QUESTION.search(query or "")


def gather_facts(_unused=None):
    """{layer name: fact} for the open project; None outside QGIS. Main thread only."""
    try:
        from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes
    except ImportError:
        return None
    wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
    facts = {}
    for layer in QgsProject.instance().mapLayers().values():
        fact = {"geographic": bool(layer.crs().isGeographic()), "crs": layer.crs().authid()}
        if isinstance(layer, QgsRasterLayer):
            fact.update(kind="raster", geometry=None, features=None, fields=[])
        elif isinstance(layer, QgsVectorLayer):
            geometry = {QgsWkbTypes.GeometryType.PointGeometry: "point", QgsWkbTypes.GeometryType.LineGeometry: "line",
                        QgsWkbTypes.GeometryType.PolygonGeometry: "polygon"}.get(QgsWkbTypes.geometryType(layer.wkbType()))
            fact.update(kind="vector", geometry=geometry, features=layer.featureCount(),
                        fields=[(f.name(), bool(f.isNumeric())) for f in layer.fields()])
        else:
            continue
        try:
            rect = layer.extent()
            if layer.crs() != wgs84 and not rect.isNull():
                rect = QgsCoordinateTransform(layer.crs(), wgs84, QgsProject.instance()).transformBoundingBox(rect)
            if not rect.isNull():       # isEmpty() is also true for a one-point layer (zero width and height)
                fact["extent_wgs84"] = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        except Exception:  # nosec B110 (best-effort: failure is non-fatal)
            pass
        facts[layer.name()] = fact
    return facts


def _norm(text):
    return re.sub(r"[\s_\-]+", " ", (text or "").lower()).strip()


def _fits(fact, kind):
    if kind == "any":
        return True
    if kind == "vector":
        return fact.get("kind") == "vector"
    if kind == "raster":
        return fact.get("kind") == "raster"
    return fact.get("kind") == "vector" and fact.get("geometry") == kind


def bind_slot(kind, facts, query, taken=()):
    """(status, names): 'named' (the request names a fitting layer), 'only' (single fitting layer), 'ambiguous' (several, none
    named), or 'none'. Pure."""
    fitting = [n for n, f in facts.items() if _fits(f, kind) and n not in taken]
    text = _norm(query)
    named = [n for n in fitting if _norm(n) and _norm(n) in text]
    if named:
        named.sort(key=lambda n: -len(n))          # "roads_primary" beats "roads" when the request names the longer one
        return "named", named[:1]
    if len(fitting) == 1:
        return "only", fitting
    return ("ambiguous", fitting[:8]) if fitting else ("none", [])


def utm_for_fact(fact):
    box = (fact or {}).get("extent_wgs84")
    if not box:
        return None
    return "EPSG:%d" % utm_epsg_for((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def chain_report(chain, facts, query):
    """{'bindings': {slot: (status, names)}, 'derived': {slot: value}, 'blocked': [reasons]} for one chain against the project. Pure."""
    bindings, taken, blocked = {}, [], []
    for slot, kind in (chain.get("inputs") or {}).items():
        status, names = bind_slot(kind, facts, query, taken)
        bindings[slot] = (status, names)
        if status in ("named", "only"):
            taken.extend(names)
        elif status == "none":
            blocked.append(f"no {'' if kind in ('any', 'vector') else kind + ' '}layer in the project for <{slot}>")
    derived = {}
    for slot, source in (chain.get("derive") or {}).items():
        status, names = bindings.get(source, ("none", []))
        if status in ("named", "only"):
            value = utm_for_fact(facts.get(names[0]))
            if value:
                derived[slot] = value
    field_spec = chain.get("numeric_field")
    if field_spec:
        layer_slot, field_slot = field_spec
        status, names = bindings.get(layer_slot, ("none", []))
        if status in ("named", "only"):
            numeric = [n for n, is_num in facts[names[0]].get("fields", []) if is_num]
            derived[field_slot + "_candidates"] = ", ".join(numeric[:8]) if numeric else "(none: the layer has no numeric field)"
            if not numeric:
                blocked.append(f"'{names[0]}' has no numeric field to colour by")
    return {"bindings": bindings, "derived": derived, "blocked": blocked}


def chain_context(query, facts, chains):
    """The 'project check' text for the chains that fit the request, or ''. Pure. Skipped for questions about method."""
    if not chains or facts is None or not is_execution_request(query):
        return ""
    lines = []
    for chain in chains:
        rep = chain_report(chain, facts, query)
        bits = []
        for slot, (status, names) in rep["bindings"].items():
            if status in ("named", "only"):
                f = facts[names[0]]
                bits.append(f"<{slot}> = '{names[0]}' ({f.get('geometry') or f.get('kind')}"
                            + (f", {f['features']} features" if f.get("features") is not None else "")
                            + (", named in the request" if status == "named" else ", the only such layer") + ")")
            elif status == "ambiguous":
                bits.append(f"<{slot}> could be any of: {', '.join(repr(n) for n in names)} -- ask the user which")
            else:
                bits.append(f"<{slot}> has NO candidate layer")
        for slot, value in rep["derived"].items():
            bits.append(f"<{slot}> suggested {value}" + (" (the UTM zone of that layer's centre)" if str(value).startswith("EPSG:") else ""))
        head = f"Project check for chain '{chain['id']}': " + ("; ".join(bits) if bits else "nothing to bind from the project")
        if rep["blocked"]:
            head += ". Cannot run as is: " + "; ".join(rep["blocked"]) + " -- ask the user, or fetch the data first, instead of guessing"
        lines.append(head + ".")
    return " ".join(lines)
