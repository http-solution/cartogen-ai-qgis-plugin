# -*- coding: utf-8 -*-
"""
Composite impedance field builder for road-network routing -- point 8 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, per
docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 2 item 2: "precompute a
single blended impedance_cost field on the network layer (surface penalty x
damage penalty x slope penalty x base travel time) and pass that field as
the algorithm's cost basis, rather than trying to add new cost dimensions
to the algorithm itself." v1.7.0 workstream 4.

Deliberately writes a value in the SAME km/h unit convention
calculate_service_area/travel_time_matrix's existing speed_field parameter
already expects (agent/tools/logistics_tools.py, point 8's earlier
closure) -- feeds directly into it, no new plumbing needed on either of
those two tools' side, matching the strategy doc's own stated integration
path.
"""

from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value

try:
    from qgis.core import QgsCoordinateTransform, QgsDistanceArea, QgsPointXY, QgsProject
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    return layers[0] if layers else None


# OSM highway=* tag -> baseline speed (km/h), a starting default speed
# table per docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md section 1 item 1.
# Not a claim these are locally accurate for any specific road network --
# a starting point meant to be adjusted (or overridden entirely via
# speed_field on the downstream tools) once real local knowledge or GPS
# calibration data is available, same honesty as that strategy doc's own
# framing of this recommendation.
_HIGHWAY_BASE_SPEED_KMH = {
    "motorway": 100, "motorway_link": 80,
    "trunk": 80, "trunk_link": 60,
    "primary": 60, "primary_link": 50,
    "secondary": 50, "secondary_link": 40,
    "tertiary": 40, "tertiary_link": 30,
    "unclassified": 30, "residential": 30, "living_street": 15,
    "service": 20, "track": 15, "path": 5, "footway": 5, "cycleway": 15,
}
_DEFAULT_BASE_SPEED_KMH = 30.0

# OSM surface=* tag -> a multiplicative speed penalty. "the single most
# direct way to address 'sends heavy vehicles down unsuitable roads,'
# since a sufficiently low effective speed makes the routing algorithm
# itself avoid that segment when a paved alternative exists" (strategy
# doc section 1 item 1).
_SURFACE_PENALTY = {
    "paved": 1.0, "asphalt": 1.0, "concrete": 1.0, "paving_stones": 0.9,
    "unpaved": 0.5, "compacted": 0.6, "fine_gravel": 0.55, "gravel": 0.5,
    "dirt": 0.35, "earth": 0.35, "ground": 0.4, "sand": 0.25, "mud": 0.15,
}
_DEFAULT_SURFACE_PENALTY = 1.0

# How strongly slope reduces speed: penalty = max(_MIN_SLOPE_PENALTY, 1 -
# slope_ratio * _SLOPE_PENALTY_COEFFICIENT), where slope_ratio is
# abs(elevation_change) / segment_length (elevation change in the DEM's
# vertical unit, ASSUMED metres, over the segment length in metres -- see build_composite_impedance_field). A gentle, defensible
# default -- not calibrated against real GPS data (the strategy doc's own
# recommended calibration source), which this sandbox has no access to.
_SLOPE_PENALTY_COEFFICIENT = 5.0
_MIN_SLOPE_PENALTY = 0.2

# A speed floor so a fully-impassable segment (damage_multiplier reaching
# 0.0) still gets a real, finite, very slow speed rather than literal 0 --
# avoids a divide-by-zero or undefined-cost downstream in whatever
# consumes this field, while still making that segment overwhelmingly
# unattractive to any routing algorithm comparing real alternatives.
_MIN_EFFECTIVE_SPEED_KMH = 0.1


def _slope_penalty(dem_layer, start_point, end_point, segment_length):
    """Endpoint-based slope estimate -- samples the DEM at a line
    feature's two endpoints only, not every vertex along it. A real
    simplification (a long, winding segment's actual grade profile isn't
    captured), documented here rather than silently implied to be more
    rigorous than it is, matching this project's own standard for
    unverified/simplified logic. Returns 1.0 (no penalty) if either sample
    falls outside the DEM's extent or segment_length is degenerate --
    failing open to "no slope information available" rather than treating
    a sampling miss as an impassable segment."""
    if segment_length <= 0:
        return 1.0
    provider = dem_layer.dataProvider()
    start_elev, start_ok = provider.sample(QgsPointXY(start_point.x(), start_point.y()), 1)
    end_elev, end_ok = provider.sample(QgsPointXY(end_point.x(), end_point.y()), 1)
    if not (start_ok and end_ok):
        return 1.0
    slope_ratio = abs(end_elev - start_elev) / segment_length
    return max(_MIN_SLOPE_PENALTY, 1.0 - slope_ratio * _SLOPE_PENALTY_COEFFICIENT)


@register_tool(
    "build_composite_impedance_field",
    "Builds a single blended per-segment speed field on a road network layer -- combining OSM "
    "highway-class baseline speed, OSM surface-condition penalty, an optional damage/passability "
    "field, and an optional DEM-derived slope penalty into one number in km/h. Feeds directly into "
    "calculate_service_area/travel_time_matrix/optimize_delivery_route's existing speed_field "
    "parameter -- run this first, then pass output_field's name as speed_field to those tools with "
    "strategy='fastest' for realistic routing that avoids unpaved/damaged/steep roads instead of "
    "treating every segment as equally fast. Requires highway_field/surface_field to already exist "
    "on the layer (e.g. from fetch_osm_features) -- a layer without them still gets a flat default "
    "speed with no penalties, not an error.",
    {
        "type": "object",
        "properties": {
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "highway_field": {"type": "string", "description": "Field holding the OSM highway=* class (e.g. 'primary', 'track'). Defaults to 'highway'."},
            "surface_field": {"type": "string", "description": "Field holding the OSM surface=* value (e.g. 'paved', 'gravel'). Defaults to 'surface'."},
            "damage_field": {"type": "string", "description": "Optional numeric field, 0.0-1.0, giving each segment's passability (1.0=fully passable, 0.0=impassable, e.g. from a road-status assessment). Non-numeric values default to 1.0 (unknown = assumed passable)."},
            "dem_layer": {"type": "string", "description": "Optional DEM raster layer. When given, each segment's endpoints are sampled for elevation and a slope penalty applied -- steeper segments get a lower effective speed."},
            "output_field": {"type": "string", "description": "Name of the new field to write the blended speed (km/h) into. Defaults to 'impedance_cost'."},
        },
        "required": ["road_network_layer"],
    },
)
def build_composite_impedance_field(road_network_layer, highway_field="highway", surface_field="surface",
                                     damage_field=None, dem_layer=None, output_field="impedance_cost"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    network = _find_layer_by_name(road_network_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}

    dem = None
    if dem_layer is not None:
        dem = _find_layer_by_name(dem_layer)
        if dem is None:
            return {"error": f"Layer '{dem_layer}' not found"}

    field_names = [f.name() for f in network.fields()]
    has_highway = highway_field in field_names
    has_surface = surface_field in field_names
    has_damage = damage_field is not None and damage_field in field_names
    if damage_field is not None and not has_damage:
        return {"error": f"Field '{damage_field}' not found in '{road_network_layer}'"}

    # All validation above must pass before any mutation below -- an
    # invalid damage_field previously still left a new output_field
    # attribute added to the layer before the error was returned.
    #
    # GitHub #143 / #144 (audit F07, F08): the field is now added through the edit buffer, inside one edit command, and every
    # write is checked. A road layer the user already has in edit mode keeps its session (nothing is committed or rolled back
    # on their behalf), and a read-only source reports an error instead of "success" with nothing written.
    non_numeric_damage_count = 0
    sampled_slope_count = 0
    # Audit F18 (#154): the slope used the endpoints as they are in the NETWORK's CRS (sampled in the DEM without a
    # transform) divided by the planar length in that CRS's units, so a geographic or foot-unit network got a meaningless
    # grade. Endpoints are now transformed into the DEM's CRS and the length is measured in metres on the ellipsoid.
    # The DEM's vertical unit is still ASSUMED to be metres: it is not stored in a form QGIS exposes reliably.
    to_dem = length_m = None
    if dem is not None:
        if network.crs().isValid() and dem.crs().isValid() and network.crs() != dem.crs():
            to_dem = QgsCoordinateTransform(network.crs(), dem.crs(), QgsProject.instance().transformContext())
        length_m = QgsDistanceArea()
        length_m.setSourceCrs(network.crs(), QgsProject.instance().transformContext())
        project_ellipsoid = QgsProject.instance().ellipsoid()
        length_m.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
    try:
        with edit_command(network, "Cartogen AI: write " + output_field) as owned:
            out_idx = add_numeric_field(network, output_field)
            for feat in network.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue

                base_speed = _DEFAULT_BASE_SPEED_KMH
                if has_highway:
                    highway_val = feat.attribute(highway_field)
                    if highway_val:
                        base_speed = _HIGHWAY_BASE_SPEED_KMH.get(str(highway_val).strip().lower(), _DEFAULT_BASE_SPEED_KMH)

                surface_penalty = _DEFAULT_SURFACE_PENALTY
                if has_surface:
                    surface_val = feat.attribute(surface_field)
                    if surface_val:
                        surface_penalty = _SURFACE_PENALTY.get(str(surface_val).strip().lower(), _DEFAULT_SURFACE_PENALTY)

                damage_multiplier = 1.0
                if has_damage:
                    raw = feat.attribute(damage_field)
                    try:
                        damage_multiplier = max(0.0, min(1.0, float(raw)))
                    except (TypeError, ValueError):
                        non_numeric_damage_count += 1
                        damage_multiplier = 1.0

                slope_penalty = 1.0
                if dem is not None:
                    polyline = geom.asPolyline() if not geom.isMultipart() else (geom.asMultiPolyline()[0] if geom.asMultiPolyline() else None)
                    if polyline and len(polyline) >= 2:
                        start_pt, end_pt = polyline[0], polyline[-1]
                        if to_dem is not None:
                            start_pt, end_pt = to_dem.transform(QgsPointXY(start_pt)), to_dem.transform(QgsPointXY(end_pt))
                        length = length_m.measureLength(geom)
                        slope_penalty = _slope_penalty(dem, start_pt, end_pt, length)
                        if slope_penalty != 1.0:
                            sampled_slope_count += 1

                effective_speed = max(
                    _MIN_EFFECTIVE_SPEED_KMH,
                    base_speed * surface_penalty * damage_multiplier * slope_penalty,
                )
                set_value(network, feat.id(), out_idx, effective_speed)
    except EditError as e:
        return {"error": f"build_composite_impedance_field failed, nothing was changed: {e}"}
    except Exception as e:
        return {"error": f"build_composite_impedance_field failed: {e}"}

    result = {
        "success": True,
        "layer_name": road_network_layer,
        "output_field": output_field,
        "feature_count": network.featureCount(),
    }
    if not owned:
        result["note"] = ("The layer is already in edit mode, so the new values are in your edit session and are NOT saved: "
                          "save or discard the layer edits yourself.")
    if damage_field is not None:
        result["damage_field"] = damage_field
        if non_numeric_damage_count:
            result["warning"] = (
                f"{non_numeric_damage_count} feature(s) had a non-numeric or unparsable value in "
                f"'{damage_field}' -- defaulted to fully passable (1.0) for those."
            )
    if dem is not None:
        result["dem_layer"] = dem_layer
        result["slope_penalized_segment_count"] = sampled_slope_count
    return result
