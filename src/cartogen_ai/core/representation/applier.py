# -*- coding: utf-8 -*-
"""
Representation Applier for Cartogen AI.

Applies recommended representation candidates directly to QGIS layers using native
renderers (Cluster, Displacement, Heatmap, Graduated, Categorized, Proportional).
"""

from typing import Any, Dict, Optional
from .models import RepresentationCandidate

try:
    from qgis.core import (
        QgsProject, QgsVectorLayer, QgsWkbTypes, QgsSymbol, QgsMarkerSymbol,
        QgsPointClusterRenderer, QgsPointDisplacementRenderer, QgsHeatmapRenderer,
        QgsSingleSymbolRenderer, QgsGradientColorRamp, QgsStyle,
        QgsSimpleMarkerSymbolLayer, QgsSimpleFillSymbolLayer, QgsFillSymbol,
        QgsUnitTypes,
    )
    from qgis.PyQt.QtGui import QColor, QFont
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name: str):
    if not QGIS_AVAILABLE or not QgsProject.instance():
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


def apply_representation(layer_or_name: Any, candidate: RepresentationCandidate) -> Dict[str, Any]:
    """Applies the specified candidate representation to the layer."""
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}

    if isinstance(layer_or_name, str):
        layer = _find_layer_by_name(layer_or_name)
    else:
        layer = layer_or_name

    if layer is None or not layer.isValid():
        return {"error": f"Layer '{layer_or_name}' not found or invalid"}

    renderer_id = candidate.id
    target_field = candidate.target_field

    try:
        # 1. Point Cluster Renderer
        if renderer_id == "point_cluster":
            cluster_renderer = QgsPointClusterRenderer()
            # Base symbol for individual points
            base_sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "color": "#2563eb",
                "outline_color": "#ffffff",
                "outline_width": "0.5",
                "size": "3",
            })
            # Cluster symbol
            cluster_sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "color": "#0ea5e9",
                "outline_color": "#ffffff",
                "outline_width": "1.0",
                "size": "8",
            })
            cluster_renderer.setEmbeddedRenderer(QgsSingleSymbolRenderer(base_sym))
            cluster_renderer.setClusterSymbol(cluster_sym)
            layer.setRenderer(cluster_renderer)
            layer.triggerRepaint()
            return {"success": True, "applied": "point_cluster", "layer_name": layer.name()}

        # 2. Point Displacement Renderer (for co-located points)
        if renderer_id == "point_displacement":
            disp_renderer = QgsPointDisplacementRenderer()
            base_sym = QgsMarkerSymbol.createSimple({
                "name": "circle",
                "color": "#e11d48",
                "outline_color": "#ffffff",
                "size": "3.5",
            })
            disp_renderer.setEmbeddedRenderer(QgsSingleSymbolRenderer(base_sym))
            disp_renderer.setCircleRadiusSymbol(None)
            layer.setRenderer(disp_renderer)
            layer.triggerRepaint()
            return {"success": True, "applied": "point_displacement", "layer_name": layer.name()}

        # 3. Continuous Heatmap Renderer
        if renderer_id == "point_heatmap":
            from qgis.core import QgsGradientColorRamp, QgsGradientStop
            from qgis.PyQt.QtGui import QColor
            heatmap_renderer = QgsHeatmapRenderer()
            heatmap_renderer.setRadius(12.0)
            heatmap_renderer.setRadiusUnit(QgsUnitTypes.RenderMillimeters)

            # CRITICAL: Stop 0.0 MUST have alpha = 0 (100% transparent) so
            # zero-density areas do not blot out the basemap with solid dark purple!
            color1 = QColor(68, 1, 84, 0)
            color2 = QColor(253, 231, 37, 255)
            stops = [
                QgsGradientStop(0.15, QColor(65, 68, 135, 110)),
                QgsGradientStop(0.35, QColor(42, 120, 142, 170)),
                QgsGradientStop(0.60, QColor(35, 168, 119, 215)),
                QgsGradientStop(0.80, QColor(115, 208, 85, 245)),
            ]
            ramp = QgsGradientColorRamp(color1, color2, False, stops)
            heatmap_renderer.setColorRamp(ramp)

            # Disable point text labels so continuous density field is clean
            if hasattr(layer, "setLabelsEnabled"):
                layer.setLabelsEnabled(False)

            layer.setRenderer(heatmap_renderer)
            layer.triggerRepaint()

            # Auto zoom to layer
            from ..agent.tools.map_tools import zoom_to_layer
            zoom_to_layer(layer.name())

            return {"success": True, "applied": "point_heatmap", "layer_name": layer.name()}

        # 4. Proportional Circles
        if renderer_id in ("point_proportional", "polygon_proportional_centroid"):
            from ..agent.tools.styling_tools import apply_graduated_symbol_style
            if target_field:
                return apply_graduated_symbol_style(
                    layer_name=layer.name(),
                    field=target_field,
                    min_size=2.0,
                    max_size=14.0,
                )
            return {"error": "Proportional symbol representation requires target_field."}

        # 5. Categorized Symbols
        if renderer_id in ("point_categorized", "polygon_categorized"):
            from ..agent.tools.styling_tools import apply_categorized_style
            if target_field:
                return apply_categorized_style(layer_name=layer.name(), field=target_field)
            return {"error": "Categorized representation requires target_field."}

        # 6. Graduated Rate Choropleth
        if renderer_id == "polygon_choropleth_rate":
            from ..agent.tools.styling_tools import apply_graduated_style
            if target_field:
                return apply_graduated_style(layer_name=layer.name(), field=target_field, mode="auto")
            return {"error": "Graduated choropleth representation requires target_field."}

        # 7. Semi-Transparent Operational Overlay
        if renderer_id == "polygon_translucent_overlay":
            from ..agent.map_intelligence import apply_component_symbology, MapOutputDescriptor
            desc = MapOutputDescriptor(
                layer_id=layer.id(),
                output_role="proximity_buffer",
                style_profile="proximity_buffer",
            )
            apply_component_symbology(layer, desc)
            return {"success": True, "applied": "polygon_translucent_overlay", "layer_name": layer.name()}

        # 8. Hollow Boundary Outline
        if renderer_id == "polygon_hollow_boundary":
            from ..agent.map_intelligence import apply_component_symbology, MapOutputDescriptor
            desc = MapOutputDescriptor(
                layer_id=layer.id(),
                output_role="administrative_boundary",
                style_profile="administrative_boundary",
            )
            apply_component_symbology(layer, desc)
            return {"success": True, "applied": "polygon_hollow_boundary", "layer_name": layer.name()}

        return {"error": f"Unknown or unsupported representation candidate id '{renderer_id}'"}

    except Exception as e:
        return {"error": f"apply_representation failed: {e}"}
