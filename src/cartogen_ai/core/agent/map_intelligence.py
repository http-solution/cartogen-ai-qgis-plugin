# -*- coding: utf-8 -*-
"""
Map Intelligence Engine & Chat Action Registry for Cartogen AI.

Centralized, context-aware cartographic post-processing service invoked
whenever Cartogen creates or mutates layers in QGIS.

Responsibilities:
1. Local, role-based layer insertion (preserves user group structure).
2. Component-level cartographic styling profiles (faint interiors with crisp borders).
3. Scale-aware intelligent PAL labeling (obstacle boundaries, geometry-specific placement).
4. Map quality evaluation (occlusion, stacking inversion, clutter detection).
5. Typed ChatActionRegistry for secure, interactive in-chat action chips.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from qgis.core import (
        QgsProject, QgsMapLayer, QgsVectorLayer, QgsWkbTypes,
        QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer,
        QgsFillSymbol, QgsLineSymbol, QgsSingleSymbolRenderer,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling, QgsUnitTypes, QgsLabelObstacleSettings,
        QgsLayerTreeLayer,
    )
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QColor, QFont
    from qgis.utils import iface
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    iface = None


# ---------------------------------------------------------------------------
# 1. Output Descriptors & Role Vocabulary
# ---------------------------------------------------------------------------

@dataclass
class MapOutputDescriptor:
    layer_id: str
    output_role: str  # 'proximity_buffer', 'administrative_boundary', 'facilities', 'thematic_choropleth', 'hazard_extent', 'selection_overlay', 'route_line'
    source_layer_id: Optional[str] = None
    geometry_role: str = "operational_overlay"  # 'focal_point', 'context_overlay', 'boundary', 'raster_dem', 'hillshade'
    recommended_label_field: Optional[str] = None
    style_profile: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 2. Typed Chat Action Registry
# ---------------------------------------------------------------------------

@dataclass
class ChatAction:
    id: str
    kind: str  # 'export', 'zoom', 'set_transparency', 'apply_style', 'label_layer', 'undo'
    label: str
    payload: Dict[str, Any]
    safety: str = "dialog"  # 'immediate', 'dialog', 'confirm'
    project_id: Optional[str] = None
    expires_on_project_change: bool = True


class ChatActionRegistry:
    """In-memory session registry mapping opaque IDs (act_...) to validated actions."""

    _actions: Dict[str, ChatAction] = {}

    @classmethod
    def register(cls, kind: str, label: str, payload: Dict[str, Any], safety: str = "dialog") -> str:
        act_id = f"act_{uuid.uuid4().hex[:8]}"
        project_id = None
        if QGIS_AVAILABLE and QgsProject.instance():
            project_id = QgsProject.instance().fileName() or "unsaved_project"
        action = ChatAction(
            id=act_id,
            kind=kind,
            label=label,
            payload=payload,
            safety=safety,
            project_id=project_id,
        )
        cls._actions[act_id] = action
        return act_id

    @classmethod
    def get(cls, act_id: str) -> Optional[ChatAction]:
        action = cls._actions.get(act_id)
        if not action:
            return None
        if action.expires_on_project_change and QGIS_AVAILABLE and QgsProject.instance():
            current_project = QgsProject.instance().fileName() or "unsaved_project"
            if action.project_id and action.project_id != current_project:
                return None
        return action

    @classmethod
    def clear(cls):
        cls._actions.clear()


# ---------------------------------------------------------------------------
# 3. Local, Role-Based Layer Insertion
# ---------------------------------------------------------------------------

def insert_layer_semantically(layer: 'QgsMapLayer', descriptor: MapOutputDescriptor) -> bool:
    """Inserts a layer at its semantic cartographic position without disturbing unrelated layers.

    Uses QgsProject.instance().addMapLayer(layer, False) followed by explicit
    tree node insertion relative to parent groups or source layers.
    """
    if not QGIS_AVAILABLE or not layer or not layer.isValid():
        return False

    project = QgsProject.instance()
    root = project.layerTreeRoot()
    if root is None:
        project.addMapLayer(layer, True)
        return True

    # Register in project without auto-adding to tree root
    project.addMapLayer(layer, False)

    target_parent = root
    insert_index = 0  # default to top

    source_node = None
    if descriptor.source_layer_id:
        source_node = root.findLayer(descriptor.source_layer_id)

    role = descriptor.output_role

    if role == "proximity_buffer" and source_node is not None:
        # Buffers sit immediately below their source layer
        parent = source_node.parent() or root
        idx = parent.children().index(source_node)
        target_parent = parent
        insert_index = idx + 1  # below source
    elif role in ("facilities", "selection_overlay"):
        # Focal points / active highlights sit at the top of their target group
        if source_node is not None:
            target_parent = source_node.parent() or root
        insert_index = 0
    elif role == "administrative_boundary":
        # Boundary outlines sit above thematic polygons
        insert_index = 0
    elif role == "thematic_choropleth":
        # Statistical polygons sit near the bottom, above basemaps/rasters
        insert_index = len(target_parent.children())
    else:
        # Generic role placement based on geometry: point (top) -> line -> polygon (bottom)
        geom_type = getattr(layer, "geometryType", lambda: None)()
        if geom_type == QgsWkbTypes.PointGeometry:
            insert_index = 0
        elif geom_type == QgsWkbTypes.LineGeometry:
            insert_index = min(1, len(target_parent.children()))
        elif geom_type == QgsWkbTypes.PolygonGeometry:
            insert_index = len(target_parent.children())
        else:
            insert_index = len(target_parent.children())

    target_parent.insertChildNode(insert_index, QgsLayerTreeLayer(layer))
    return True


# ---------------------------------------------------------------------------
# 4. Component-Level Cartographic Styling Profiles
# ---------------------------------------------------------------------------

STYLE_PROFILES = {
    "proximity_buffer": {
        "fill_alpha": 50,      # ~20% opacity
        "stroke_alpha": 255,   # 100% opacity
        "stroke_width": 0.8,   # mm
        "join_style": "round",
        "default_hue": "#2563eb",  # Blue
    },
    "administrative_boundary": {
        "fill_alpha": 0,       # Hollow
        "stroke_alpha": 230,   # 90% opacity
        "stroke_width": 1.2,   # mm
        "join_style": "miter",
        "default_hue": "#1e293b",  # Dark slate
    },
    "hazard_extent": {
        "fill_alpha": 75,      # ~30% opacity
        "stroke_alpha": 255,   # 100% opacity
        "stroke_width": 1.4,   # mm
        "join_style": "round",
        "default_hue": "#dc2626",  # Red
    },
    "selection_overlay": {
        "fill_alpha": 40,      # ~15% opacity
        "stroke_alpha": 255,   # 100% opacity
        "stroke_width": 1.0,   # mm
        "join_style": "round",
        "default_hue": "#06b6d4",  # Cyan
    },
    "coverage_gap": {
        "fill_alpha": 70,      # ~28% opacity
        "stroke_alpha": 255,   # 100% opacity
        "stroke_width": 1.0,   # mm
        "join_style": "round",
        "default_hue": "#f59e0b",  # Amber
    },
    # Every profile above is polygon-only (apply_component_symbology returned False for any
    # line-geometry layer with no styling at all, every time -- routing/logistics-corridor
    # output got QGIS's raw default new-layer symbology, never this engine's treatment).
    # This is the standard professional "casing" technique for route/road lines: a slightly
    # wider, darker outline beneath a narrower, brighter fill line, giving contrast against
    # any basemap and visually distinguishing a real route from ordinary background linework
    # -- the same technique OSM Carto, Mapbox Streets, and ArcGIS's own transportation symbol
    # categories all use, documented in cartographic design references such as Krygier &
    # Wood's "Making Maps: A Visual Guide to Map Design for GIS" (road/route symbolization).
    "route_line": {
        "stroke_width": 1.6,     # mm, the bright fill line on top
        "casing_width": 2.6,     # mm, the darker outline beneath
        "default_hue": "#ea580c",   # Orange -- distinct from every other profile's hue here
        "casing_hue": "#7c2d12",    # Dark brown-red casing
        "cap_style": "round",
    },
}


def apply_component_symbology(layer: 'QgsMapLayer', descriptor: MapOutputDescriptor) -> bool:
    """Applies component-level symbology (faint fill, crisp stroke) instead of blanket layer opacity."""
    if not QGIS_AVAILABLE or not isinstance(layer, QgsVectorLayer):
        return False

    profile_name = descriptor.style_profile or descriptor.output_role
    profile = STYLE_PROFILES.get(profile_name, STYLE_PROFILES["proximity_buffer"])

    geom_type = layer.geometryType()
    if geom_type == QgsWkbTypes.LineGeometry:
        return _apply_line_component_symbology(layer, descriptor, profile)
    if geom_type != QgsWkbTypes.PolygonGeometry:
        return False

    base_color_hex = descriptor.properties.get("color") or profile["default_hue"]
    base_color = QColor(base_color_hex)
    if not base_color.isValid():
        base_color = QColor("#2563eb")

    fill_color = QColor(base_color)
    fill_color.setAlpha(profile["fill_alpha"])

    stroke_color = QColor(base_color).darker(130)
    stroke_color.setAlpha(profile["stroke_alpha"])

    symbol_layer = QgsSimpleFillSymbolLayer()
    no_brush = Qt.BrushStyle.NoBrush if hasattr(Qt, "BrushStyle") else getattr(Qt, "NoBrush", 0)
    solid_brush = Qt.BrushStyle.SolidPattern if hasattr(Qt, "BrushStyle") else getattr(Qt, "SolidPattern", 1)
    round_join = Qt.PenJoinStyle.RoundJoin if hasattr(Qt, "PenJoinStyle") else getattr(Qt, "RoundJoin", 64)

    if profile["fill_alpha"] == 0:
        symbol_layer.setBrushStyle(no_brush)
    else:
        symbol_layer.setBrushStyle(solid_brush)
        symbol_layer.setFillColor(fill_color)

    symbol_layer.setStrokeColor(stroke_color)
    symbol_layer.setStrokeWidth(profile["stroke_width"])
    symbol_layer.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)

    if profile.get("join_style") == "round":
        symbol_layer.setPenJoinStyle(round_join)

    symbol = QgsFillSymbol()
    symbol.changeSymbolLayer(0, symbol_layer)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setOpacity(1.0)  # Keep overall layer at 100% so stroke remains sharp
    layer.triggerRepaint()
    return True


def _apply_line_component_symbology(layer: 'QgsVectorLayer', descriptor: MapOutputDescriptor, profile: dict) -> bool:
    """Standard road/route casing technique: a wider, darker outline layer beneath a
    narrower, brighter fill layer, so a real routed line (optimize_delivery_route's
    road-snapped output, a service-area reachable network, etc.) reads clearly against
    any basemap instead of QGIS's raw default new-layer symbology every prior version of
    this engine left it with. Falls back to STYLE_PROFILES['route_line'] for any profile
    that has no line-specific keys (e.g. a caller passing a polygon profile name by mistake)."""
    line_profile = profile if "casing_width" in profile else STYLE_PROFILES["route_line"]

    base_color_hex = descriptor.properties.get("color") or line_profile["default_hue"]
    fill_color = QColor(base_color_hex)
    if not fill_color.isValid():
        fill_color = QColor(STYLE_PROFILES["route_line"]["default_hue"])
    casing_color = QColor(line_profile.get("casing_hue") or fill_color.darker(160).name())

    round_cap = Qt.PenCapStyle.RoundCap if hasattr(Qt, "PenCapStyle") else getattr(Qt, "RoundCap", 32)
    round_join = Qt.PenJoinStyle.RoundJoin if hasattr(Qt, "PenJoinStyle") else getattr(Qt, "RoundJoin", 64)

    casing_layer = QgsSimpleLineSymbolLayer()
    casing_layer.setColor(casing_color)
    casing_layer.setWidth(line_profile["casing_width"])
    casing_layer.setWidthUnit(QgsUnitTypes.RenderMillimeters)
    casing_layer.setPenCapStyle(round_cap)
    casing_layer.setPenJoinStyle(round_join)

    fill_layer = QgsSimpleLineSymbolLayer()
    fill_layer.setColor(fill_color)
    fill_layer.setWidth(line_profile["stroke_width"])
    fill_layer.setWidthUnit(QgsUnitTypes.RenderMillimeters)
    fill_layer.setPenCapStyle(round_cap)
    fill_layer.setPenJoinStyle(round_join)

    symbol = QgsLineSymbol()
    symbol.changeSymbolLayer(0, casing_layer)
    symbol.appendSymbolLayer(fill_layer)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setOpacity(1.0)
    layer.triggerRepaint()
    return True


# ---------------------------------------------------------------------------
# 5. Scale-Aware Intelligent PAL Labeling
# ---------------------------------------------------------------------------

def configure_intelligent_labels(
    layer: 'QgsVectorLayer',
    field_name: Optional[str] = None,
    priority: int = 5,
    min_scale: Optional[float] = None,
    max_scale: Optional[float] = None,
) -> bool:
    """Configures high-quality PAL labeling with halos, obstacle boundaries, and scale thresholds."""
    if not QGIS_AVAILABLE or not isinstance(layer, QgsVectorLayer) or not field_name:
        return False

    fields = [f.name() for f in layer.fields()]
    if field_name not in fields:
        return False

    settings = QgsPalLayerSettings()
    text_format = QgsTextFormat()

    # Off-black high-legibility typography
    text_format.setFont(QFont("Source Sans 3", 9))
    text_format.setColor(QColor("#1C1C1E"))

    # 0.8 mm 80% opacity white text buffer (halo)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
    buf.setColor(QColor(255, 255, 255, 204))
    pen_round = Qt.PenJoinStyle.RoundJoin if hasattr(Qt, "PenJoinStyle") else getattr(Qt, "RoundJoin", 64)
    buf.setJoinStyle(pen_round)
    text_format.setBuffer(buf)
    settings.setFormat(text_format)

    settings.fieldName = field_name
    settings.isExpression = False
    settings.priority = max(0, min(10, priority))

    geom = layer.geometryType()
    if geom == QgsWkbTypes.PointGeometry:
        settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
        settings.obstacleSettings().setIsObstacle(True)
    elif geom == QgsWkbTypes.LineGeometry:
        settings.placement = QgsPalLayerSettings.Curved
        settings.placementFlags = QgsPalLayerSettings.AboveLine | QgsPalLayerSettings.MapOrientation
    elif geom == QgsWkbTypes.PolygonGeometry:
        settings.placement = QgsPalLayerSettings.Horizontal
        settings.fitInPolygonOnly = True
        # Polygon boundaries are obstacles, not the entire interior
        if hasattr(QgsLabelObstacleSettings, "PolygonBoundary"):
            settings.obstacleSettings().setType(QgsLabelObstacleSettings.PolygonBoundary)

    # Scale-aware visibility heuristics based on feature count
    count = layer.featureCount()
    if min_scale is not None or max_scale is not None:
        settings.scaleVisibility = True
        if min_scale:
            settings.minimumScale = min_scale
        if max_scale:
            settings.maximumScale = max_scale
    elif count > 500:
        settings.scaleVisibility = True
        settings.minimumScale = 150000  # Visible only when zoomed in past 1:150,000

    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.triggerRepaint()
    return True


# ---------------------------------------------------------------------------
# 6. Map Quality Evaluator
# ---------------------------------------------------------------------------

def evaluate_map_quality(layer: 'QgsMapLayer', descriptor: MapOutputDescriptor) -> List[Dict[str, Any]]:
    """Evaluates canvas readability and structural correctness after layer generation."""
    findings = []
    if not QGIS_AVAILABLE or not layer:
        return findings

    project = QgsProject.instance()
    root = project.layerTreeRoot()

    # Check 1: Inverted Stacking (Buffer placed above source)
    if descriptor.output_role == "proximity_buffer" and descriptor.source_layer_id:
        src_node = root.findLayer(descriptor.source_layer_id)
        buf_node = root.findLayer(layer.id())
        if src_node and buf_node and src_node.parent() == buf_node.parent():
            parent = src_node.parent()
            src_idx = parent.children().index(src_node)
            buf_idx = parent.children().index(buf_node)
            if buf_idx < src_idx:
                findings.append({
                    "code": "STACKING_INVERSION",
                    "severity": "warning",
                    "message": f"Buffer layer '{layer.name()}' is rendered above its source layer, partially obscuring it.",
                    "repair_action": "move_below_source",
                })

    # Check 2: Dense Label Clutter
    if isinstance(layer, QgsVectorLayer) and layer.labelsEnabled():
        count = layer.featureCount()
        if count > 800 and not layer.labeling().settings().scaleVisibility:
            findings.append({
                "code": "LABEL_CLUTTER",
                "severity": "warning",
                "message": f"Layer '{layer.name()}' has {count} labels with no scale thresholds, creating visual clutter.",
                "repair_action": "enable_scale_limits",
            })

    # Check 3: Full Opaque Polygon Fill Covering Map
    if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry:
        if layer.opacity() >= 0.9:
            renderer = layer.renderer()
            if isinstance(renderer, QgsSingleSymbolRenderer):
                sym = renderer.symbol()
                if sym and sym.symbolLayerCount() > 0:
                    sl = sym.symbolLayer(0)
                    if isinstance(sl, QgsSimpleFillSymbolLayer) and sl.fillColor().alpha() > 200:
                        findings.append({
                            "code": "OVERLAY_OCCLUSION",
                            "severity": "warning",
                            "message": f"Polygon layer '{layer.name()}' has an opaque solid fill that blocks the underlying basemap.",
                            "repair_action": "apply_translucent_fill",
                        })

    return findings


# ---------------------------------------------------------------------------
# 7. Master Engine Coordinator
# ---------------------------------------------------------------------------

def process_map_output(
    layer: 'QgsMapLayer',
    output_role: str,
    source_layer_id: Optional[str] = None,
    recommended_label_field: Optional[str] = None,
    style_profile: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Single post-processing service invoked whenever a layer is created or substantially modified."""
    # Design-state memory (§1.16 "smart mapping" -- see map_state_memory.py's module
    # docstring): if a PRIOR call already produced this output_role in this project and
    # the caller here didn't explicitly ask for a different style_profile/color, reuse
    # what was actually used last time instead of always falling back to STYLE_PROFILES'
    # hardcoded default -- a follow-up request for a similar output then visually matches
    # the one before it. Caller-supplied values always win; this only fills in what the
    # caller left unset. Lazy imports: keeps this module free of a hard dependency on the
    # tools package, matching the "lazy import for cross-module agent state" convention
    # already used elsewhere (e.g. chat_tab_widget.py's _maybe_ask_local_data).
    from . import map_state_memory
    from .tools.task_tools import get_memory_manager
    memory_manager = get_memory_manager()
    remembered = map_state_memory.recall_output(memory_manager, output_role)

    effective_style_profile = style_profile
    effective_properties = dict(properties or {})
    if remembered:
        if effective_style_profile is None and remembered.get("style_profile"):
            effective_style_profile = remembered["style_profile"]
        remembered_color = (remembered.get("properties") or {}).get("color")
        if "color" not in effective_properties and remembered_color:
            effective_properties["color"] = remembered_color

    descriptor = MapOutputDescriptor(
        layer_id=layer.id() if hasattr(layer, "id") else "",
        output_role=output_role,
        source_layer_id=source_layer_id,
        recommended_label_field=recommended_label_field,
        style_profile=effective_style_profile or output_role,
        properties=effective_properties,
    )

    # 1. Local Semantic Insertion
    insert_layer_semantically(layer, descriptor)

    # 2. Component Symbology
    styled = apply_component_symbology(layer, descriptor)
    if styled:
        map_state_memory.record_output(
            memory_manager, output_role, descriptor.layer_id,
            layer.name() if hasattr(layer, "name") else "",
            descriptor.style_profile, descriptor.properties,
        )

    # 3. Intelligent Labeling (if requested)
    if recommended_label_field and isinstance(layer, QgsVectorLayer):
        configure_intelligent_labels(layer, recommended_label_field)

    # 4. Map Quality Evaluation
    findings = evaluate_map_quality(layer, descriptor)

    # 5. Generate Safe Contextual Chat Actions
    action_chips = []
    layer_name = layer.name() if hasattr(layer, "name") else "Layer"

    # Export action
    act_export = ChatActionRegistry.register(
        kind="export",
        label=f"Export {layer_name}…",
        payload={"layer_name": layer_name, "layer_id": descriptor.layer_id, "only_selected": True},
        safety="dialog",
    )
    action_chips.append({"id": act_export, "label": f"📁 Export {layer_name}", "url": f"cartogen://action/{act_export}"})

    # Zoom action
    act_zoom = ChatActionRegistry.register(
        kind="zoom",
        label=f"Zoom to {layer_name}",
        payload={"layer_name": layer_name},
        safety="immediate",
    )
    action_chips.append({"id": act_zoom, "label": f"🔍 Zoom to {layer_name}", "url": f"cartogen://action/{act_zoom}"})

    return {
        "success": True,
        "descriptor": descriptor,
        "findings": findings,
        "action_chips": action_chips,
    }
