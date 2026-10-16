"""M2 (roadmap completion plan, package B): the project-level settings that were still MISSING.

rename_layer_group      rename a group in the layer tree
zoom_history            zoom to the previous / next map extent (the canvas's own history)
get_layer_metadata      read a layer's metadata (title, abstract, license, keywords, contacts)
set_layer_metadata      write them (QgsLayerMetadata; saved with the project)
set_snapping_options    project snapping: on/off, type, tolerance, units, mode, topological editing
create_relation         a 1-N relation between two layers
list_relations          the project's relations
set_layer_temporal      make a layer time-aware from a date field (or a start and an end field)
set_project_time_range  the project's temporal range
add_text_annotation     a text note on the map (project annotation layer)
remove_annotations      remove them all

Not done on purpose or not possible from here: map decorations (grid, copyright, north arrow on the canvas) and the 3D map view are
canvas / interface features with no stable scripting API, so they stay MISSING in the coverage matrix. zoom_history needs the canvas
and is not exercised in CI (no canvas there). Everything else is read back from real project objects by
tests/test_project_ops_tools_live.py, whose first CI run is its first execution."""
from .project_ops_options import (check_annotation_text, check_metadata, check_snapping, check_time_range, relation_id)
from .registry import register_tool

try:
    from qgis.core import (Qgis, QgsAbstractMetadataBase, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsDateTimeRange,
                           QgsAnnotationPointTextItem, QgsPointXY, QgsProject, QgsRelation, QgsVectorLayer)
    from qgis.PyQt.QtCore import QDateTime
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None


def _layer(name):
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def _member(owner_names, member):
    """First `Qgis.<owner>.<member>` that exists (QGIS 4 scopes enums, older builds are flat)."""
    for owner in owner_names:
        scope = getattr(Qgis, owner, None)
        value = getattr(scope, member, None) if scope is not None else None
        if value is not None:
            return value
    return getattr(Qgis, member, None)


@register_tool(
    "rename_layer_group",
    "Rename a layer group in the layer tree.",
    {"type": "object", "properties": {"group_name": {"type": "string"}, "new_name": {"type": "string"}}, "required": ["group_name", "new_name"]})
def rename_layer_group(group_name, new_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from .map_view_tools import check_group_name
    name, problem = check_group_name(new_name)
    if problem:
        return {"error": problem}
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(group_name)
    if group is None:
        return {"error": f"Group '{group_name}' not found."}
    if name != group_name and root.findGroup(name) is not None:
        return {"error": f"A group called '{name}' already exists."}
    group.setName(name)
    return {"success": True, "old_name": group_name, "new_name": name}


def extent_changed(before, after, tolerance=1e-9):
    """True when two QgsRectangle-like extents differ (any edge by more than `tolerance`). Pure given plain objects with x/yMinimum/Maximum."""
    pairs = ((before.xMinimum(), after.xMinimum()), (before.xMaximum(), after.xMaximum()),
             (before.yMinimum(), after.yMinimum()), (before.yMaximum(), after.yMaximum()))
    return any(abs(a - b) > tolerance for a, b in pairs)


@register_tool(
    "zoom_history",
    "Zoom the map canvas to the previous or the next extent in its history (like the Zoom Last / Zoom Next buttons). direction: previous or next.",
    {"type": "object", "properties": {"direction": {"type": "string", "description": "previous or next"}}, "required": ["direction"]})
def zoom_history(direction):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    word = str(direction or "").strip().lower()
    if word not in ("previous", "last", "back", "next", "forward"):
        return {"error": "direction must be previous or next."}
    if iface is None:
        return {"error": "QGIS interface not available"}
    canvas = iface.mapCanvas()
    going_back = word in ("previous", "last", "back")
    # QgsMapCanvas has no previousExtentsAvailable()/nextExtentsAvailable() in QGIS 4.2 (only the zoomLastStatusChanged / zoomNextStatusChanged
    # signals), so the first version of this tool raised AttributeError on a real canvas; CI has no canvas and could not see it. Found by
    # checking the calls against the 4.2 API reference. Without a query, the history is stepped and an unchanged extent means there was no step.
    before = canvas.extent()
    canvas.zoomToPreviousExtent() if going_back else canvas.zoomToNextExtent()
    if not extent_changed(before, canvas.extent()):
        return {"error": "There is no earlier map extent in the history." if going_back else "There is no later map extent in the history."}
    canvas.refresh()
    return {"success": True, "scale": round(canvas.scale(), 1)}


def _metadata_dict(layer):
    meta = layer.metadata()
    contacts = [{"name": c.name, "organization": c.organization, "email": c.email} for c in meta.contacts()]
    return {"title": meta.title(), "abstract": meta.abstract(), "licenses": list(meta.licenses()), "rights": list(meta.rights()),
            "keywords": {k: list(v) for k, v in meta.keywords().items()}, "contacts": contacts}


@register_tool(
    "get_layer_metadata",
    "Read a layer's metadata: title, abstract, licenses, rights, keywords and contacts.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}}, "required": ["layer_name"]})
def get_layer_metadata(layer_name):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}
    return {"success": True, "layer_name": layer_name, **_metadata_dict(layer)}


@register_tool(
    "set_layer_metadata",
    "Set a layer's metadata: title, abstract, license, rights, keywords (a list of words) and one contact (name, organization, email). Fields "
    "you leave out are kept. The metadata is stored in the project (save the project to keep it).",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "title": {"type": "string"}, "abstract": {"type": "string"},
                                      "license": {"type": "string"}, "rights": {"type": "string"},
                                      "keywords": {"type": "array", "items": {"type": "string"}}, "contact_name": {"type": "string"},
                                      "contact_organization": {"type": "string"}, "contact_email": {"type": "string"}},
     "required": ["layer_name"]})
def set_layer_metadata(layer_name, title=None, abstract=None, license=None, rights=None, keywords=None,  # noqa: A002
                       contact_name=None, contact_organization=None, contact_email=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if layer is None:
        return {"error": f"Layer '{layer_name}' not found."}
    values, problem = check_metadata(title, abstract, license, rights, keywords, contact_name, contact_organization, contact_email)
    if problem:
        return {"error": problem}
    meta = layer.metadata()
    if "title" in values:
        meta.setTitle(values["title"])
    if "abstract" in values:
        meta.setAbstract(values["abstract"])
    if "license" in values:
        meta.setLicenses([values["license"]])
    if "rights" in values:
        meta.setRights([values["rights"]])
    if "keywords" in values:
        meta.setKeywords({"keywords": values["keywords"]})
    if any(k in values for k in ("contact_name", "contact_organization", "contact_email")):
        contact = QgsAbstractMetadataBase.Contact()
        contact.name = values.get("contact_name", "")
        contact.organization = values.get("contact_organization", "")
        contact.email = values.get("contact_email", "")
        meta.setContacts([contact])
    layer.setMetadata(meta)
    return {"success": True, "layer_name": layer_name, "changed": sorted(values), "note": "Saved with the project; save the project to keep it."}


@register_tool(
    "set_snapping_options",
    "Set the project's snapping: enabled, snap_type (vertex, segment, vertex and segment, centroid, middle of segment, line endpoint, area), "
    "tolerance, units (pixels or project units), mode (all layers, active layer, advanced) and topological editing. Options you leave out are kept.",
    {"type": "object", "properties": {"enabled": {"type": "boolean"}, "snap_type": {"type": "string"}, "tolerance": {"type": "number"},
                                      "units": {"type": "string"}, "mode": {"type": "string"}, "topological_editing": {"type": "boolean"}},
     "required": []})
def set_snapping_options(enabled=None, snap_type=None, tolerance=None, units=None, mode=None, topological_editing=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    options, problem = check_snapping(enabled, snap_type, tolerance, units, mode, topological_editing)
    if problem:
        return {"error": problem}
    project = QgsProject.instance()
    config = project.snappingConfig()
    if "enabled" in options:
        config.setEnabled(options["enabled"])
    if "type" in options:
        member = _member(("SnappingType",), options["type"])
        if member is None:
            return {"error": f"This QGIS does not know the snapping type {options['type']}."}
        flags = getattr(Qgis, "SnappingTypes", None)
        config.setTypeFlag(flags(member) if flags is not None else member)
    if "mode" in options:
        member = _member(("SnappingMode",), options["mode"])
        if member is None:
            return {"error": f"This QGIS does not know the snapping mode {options['mode']}."}
        config.setMode(member)
    if "units" in options:
        member = _member(("MapToolUnit",), options["units"])
        if member is None:
            return {"error": f"This QGIS does not know the snapping unit {options['units']}."}
        config.setUnits(member)
    if "tolerance" in options:
        config.setTolerance(options["tolerance"])
    project.setSnappingConfig(config)
    if "topological" in options:
        project.setTopologicalEditing(options["topological"])
    config = project.snappingConfig()
    return {"success": True, "enabled": config.enabled(), "tolerance": config.tolerance(), "topological_editing": project.topologicalEditing(),
            "changed": sorted(options)}


@register_tool(
    "create_relation",
    "Create a 1-N relation between two layers: parent_layer.parent_field is referenced by child_layer.child_field (for example districts.pcode "
    "and schools.district_pcode). The relation is stored in the project.",
    {"type": "object", "properties": {"name": {"type": "string"}, "parent_layer": {"type": "string"}, "parent_field": {"type": "string"},
                                      "child_layer": {"type": "string"}, "child_field": {"type": "string"}},
     "required": ["name", "parent_layer", "parent_field", "child_layer", "child_field"]})
def create_relation(name, parent_layer, parent_field, child_layer, child_field):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    rel_id, problem = relation_id(name)
    if problem:
        return {"error": problem}
    parent, child = _layer(parent_layer), _layer(child_layer)
    for label, layer, given in (("Parent", parent, parent_layer), ("Child", child, child_layer)):
        if not isinstance(layer, QgsVectorLayer):
            return {"error": f"{label} layer '{given}' was not found or is not a vector layer."}
    for label, layer, field in (("parent", parent, parent_field), ("child", child, child_field)):
        if layer.fields().indexOf(field) < 0:
            return {"error": f"The {label} layer has no field '{field}'. It has: {', '.join(layer.fields().names())}."}
    manager = QgsProject.instance().relationManager()
    if manager.relation(rel_id).isValid() or any(r.name() == rel_id for r in manager.relations().values()):
        return {"error": f"A relation called '{rel_id}' already exists."}
    relation = QgsRelation()
    relation.setId(rel_id)
    relation.setName(rel_id)
    relation.setReferencedLayer(parent.id())
    relation.setReferencingLayer(child.id())
    relation.addFieldPair(child_field, parent_field)
    if not relation.isValid():
        return {"error": "QGIS found the relation invalid (check the layers and fields)."}
    manager.addRelation(relation)
    return {"success": True, "relation": rel_id, "parent": f"{parent_layer}.{parent_field}", "child": f"{child_layer}.{child_field}"}


@register_tool(
    "list_relations",
    "List the project's relations between layers.",
    {"type": "object", "properties": {}, "required": []})
def list_relations():
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    rows = []
    for relation in QgsProject.instance().relationManager().relations().values():
        pairs = relation.fieldPairs()
        rows.append({"name": relation.name(), "parent_layer": relation.referencedLayer().name() if relation.referencedLayer() else None,
                     "child_layer": relation.referencingLayer().name() if relation.referencingLayer() else None,
                     "field_pairs": [f"{child}->{parent}" for child, parent in pairs.items()], "valid": relation.isValid()})
    return {"success": True, "count": len(rows), "relations": rows}


@register_tool(
    "set_layer_temporal",
    "Make a vector layer time-aware: give the date or date-time field (start_field) and optionally an end_field for features that last a "
    "period. Set clear=true to switch it off. The fields must be of date or date-time type.",
    {"type": "object", "properties": {"layer_name": {"type": "string"}, "start_field": {"type": "string"}, "end_field": {"type": "string"},
                                      "clear": {"type": "boolean"}}, "required": ["layer_name"]})
def set_layer_temporal(layer_name, start_field=None, end_field=None, clear=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = _layer(layer_name)
    if not isinstance(layer, QgsVectorLayer):
        return {"error": f"Vector layer '{layer_name}' not found."}
    props = layer.temporalProperties()
    if clear:
        props.setIsActive(False)
        return {"success": True, "layer_name": layer_name, "temporal": False}
    if not start_field:
        return {"error": "Give start_field (a date or date-time field), or clear=true."}
    for label, field in (("start_field", start_field), ("end_field", end_field)):
        if not field:
            continue
        index = layer.fields().indexOf(field)
        if index < 0:
            return {"error": f"{label} '{field}' not found. The layer has: {', '.join(layer.fields().names())}."}
        if "date" not in layer.fields().at(index).typeName().lower() and "time" not in layer.fields().at(index).typeName().lower():
            return {"error": f"{label} '{field}' is a {layer.fields().at(index).typeName()} field, not a date or date-time field."}
    mode_name = "FeatureDateTimeStartAndEndFromFields" if end_field else "FeatureDateTimeInstantFromField"
    mode = _member(("VectorTemporalMode",), mode_name)
    if mode is None:
        return {"error": "This QGIS does not support field-based temporal layers."}
    props.setMode(mode)
    props.setStartField(start_field)
    if end_field:
        props.setEndField(end_field)
    props.setIsActive(True)
    return {"success": True, "layer_name": layer_name, "temporal": True, "start_field": start_field, "end_field": end_field or None}


@register_tool(
    "set_project_time_range",
    "Set the project's temporal range (the period the temporal controller covers). start and end are dates such as 2026-03-01 or "
    "2026-03-01T12:00:00.",
    {"type": "object", "properties": {"start": {"type": "string"}, "end": {"type": "string"}}, "required": ["start", "end"]})
def set_project_time_range(start, end):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    span, problem = check_time_range(start, end)
    if problem:
        return {"error": problem}
    first, last = (QDateTime(d.year, d.month, d.day, d.hour, d.minute, d.second) for d in span)
    QgsProject.instance().timeSettings().setTemporalRange(QgsDateTimeRange(first, last))
    return {"success": True, "start": span[0].isoformat(), "end": span[1].isoformat()}


@register_tool(
    "add_text_annotation",
    "Put a text note on the map at x, y (in crs, default EPSG:4326). It is kept in the project's annotation layer.",
    {"type": "object", "properties": {"text": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "crs": {"type": "string"}},
     "required": ["text", "x", "y"]})
def add_text_annotation(text, x, y, crs=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    cleaned, problem = check_annotation_text(text)
    if problem:
        return {"error": problem}
    try:
        point = QgsPointXY(float(x), float(y))
    except (TypeError, ValueError):
        return {"error": "x and y must be numbers."}
    source = QgsCoordinateReferenceSystem(crs or "EPSG:4326")
    if not source.isValid():
        return {"error": f"Unknown crs '{crs}'. Use a code such as EPSG:4326."}
    layer = QgsProject.instance().mainAnnotationLayer()
    if layer.crs().isValid() and layer.crs() != source:
        point = QgsCoordinateTransform(source, layer.crs(), QgsProject.instance()).transform(point)
    item_id = layer.addItem(QgsAnnotationPointTextItem(cleaned, point))
    return {"success": True, "annotation_id": str(item_id), "annotations": len(layer.items())}


@register_tool(
    "remove_annotations",
    "Remove all text annotations from the map. Destructive: a preview with the count is shown first.",
    {"type": "object", "properties": {}, "required": []})
def remove_annotations(confirmed=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    layer = QgsProject.instance().mainAnnotationLayer()
    count = len(layer.items())
    if not count:
        return {"error": "There are no annotations to remove."}
    if not confirmed:
        from .attribute_edit_tools import preview
        return preview("remove_annotations", {}, f"Remove all {count} annotation(s) from the map.", "mainAnnotationLayer().clear()")
    layer.clear()
    return {"success": True, "removed": count}
