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

from ... import _chunked as _ck
from .registry import register_tool
from ._edit_session import EditError, add_numeric_field, edit_command, set_value
from ._network_closure import CLOSED_SPEED_KMH

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


# OSM highway=* tag -> baseline speed (km/h). D of the HU-3b decision (2026-11-23): this tool no longer carries its own table. It reads the one shared with
# estimate_road_speeds (_road_speeds.py), so a road class gets the same assumed speed from either tool; before, primary/secondary/tertiary/residential here
# were 60/50/40/30 and there 70/60/50/40. The surface, damage and slope penalties below still apply on top. The numbers are an assumption from public routing
# profiles, not measured on any network and not checked against a known journey; override with speed_field on the downstream tools when real data exists.
from ._road_speeds import ASSUMED_SPEED_BY_ROAD_CLASS_KMH as _HIGHWAY_BASE_SPEED_KMH  # noqa: E402
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
# vertical unit -- dem_vertical_unit, default metres, converted to metres -- over the segment length in metres -- see build_composite_impedance_field). A gentle, defensible
# default -- not calibrated against real GPS data (the strategy doc's own
# recommended calibration source), which this sandbox has no access to.
_SLOPE_PENALTY_COEFFICIENT = 5.0
_MIN_SLOPE_PENALTY = 0.2

# A speed floor so a segment slowed to (nearly) nothing by surface, slope or a small passability still gets a real, finite
# speed -- avoids a divide-by-zero downstream. A damage_field passability of exactly 0 is NOT floored: it is a closure (see
# _network_closure), written as CLOSED_SPEED_KMH.
_MIN_EFFECTIVE_SPEED_KMH = 0.1


def _slope_penalty(dem_layer, start_point, end_point, segment_length, vertical_factor=1.0):
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
    slope_ratio = abs(end_elev - start_elev) * vertical_factor / segment_length
    return max(_MIN_SLOPE_PENALTY, 1.0 - slope_ratio * _SLOPE_PENALTY_COEFFICIENT)


def _base_speed_kmh(feat, highway_field):
    """The free-flow speed for a segment's OSM highway class (the default when the value is empty or unknown)."""
    highway_val = feat.attribute(highway_field)
    if not highway_val:
        return _DEFAULT_BASE_SPEED_KMH
    return _HIGHWAY_BASE_SPEED_KMH.get(str(highway_val).strip().lower(), _DEFAULT_BASE_SPEED_KMH)


def _surface_penalty(feat, surface_field):
    """The speed multiplier for a segment's surface class (the default when the value is empty or unknown)."""
    surface_val = feat.attribute(surface_field)
    if not surface_val:
        return _DEFAULT_SURFACE_PENALTY
    return _SURFACE_PENALTY.get(str(surface_val).strip().lower(), _DEFAULT_SURFACE_PENALTY)


def _damage_multiplier(feat, damage_field):
    """(passability multiplier clamped to 0..1, True when the value was numeric; fully passable 1.0 when it was not)."""
    raw = feat.attribute(damage_field)
    try:
        return max(0.0, min(1.0, float(raw))), True
    except (TypeError, ValueError):
        return 1.0, False


def _segment_slope_penalty(dem, geom, to_dem, length_m, vertical_factor):
    """The slope penalty of one road segment from the DEM at its end points (1.0 when it has no usable polyline)."""
    polyline = geom.asPolyline() if not geom.isMultipart() else (geom.asMultiPolyline()[0] if geom.asMultiPolyline() else None)
    if not polyline or len(polyline) < 2:
        return 1.0
    start_pt, end_pt = polyline[0], polyline[-1]
    if to_dem is not None:
        start_pt, end_pt = to_dem.transform(QgsPointXY(start_pt)), to_dem.transform(QgsPointXY(end_pt))
    length = length_m.measureLength(geom)
    return _slope_penalty(dem, start_pt, end_pt, length, vertical_factor)


def _dem_measuring(network, dem):
    """(transform from the network CRS to the DEM's, ellipsoidal length measurer) for slope sampling; (None, None) with no DEM. Audit F18 (#154):
    the slope used the endpoints as they are in the NETWORK's CRS (sampled in the DEM without a transform) divided by the planar length in that
    CRS's units, so a geographic or foot-unit network got a meaningless grade. Endpoints are transformed into the DEM's CRS and the length is
    measured in metres on the ellipsoid. Split out of build_composite_impedance_field (LR-21, no behaviour change)."""
    if dem is None:
        return None, None
    to_dem = None
    if network.crs().isValid() and dem.crs().isValid() and network.crs() != dem.crs():
        to_dem = QgsCoordinateTransform(network.crs(), dem.crs(), QgsProject.instance().transformContext())
    length_m = QgsDistanceArea()
    length_m.setSourceCrs(network.crs(), QgsProject.instance().transformContext())
    project_ellipsoid = QgsProject.instance().ellipsoid()
    length_m.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
    return to_dem, length_m


def _segment_speed(feat, geom, counts, ctx):
    """The effective speed (km/h) for one road segment, adding to `counts` (non_numeric_damage, sampled_slope, closed). `ctx` holds the field names
    that exist (None when absent), the DEM and its transforms. Split out of build_composite_impedance_field (LR-21, no behaviour change)."""
    highway_field, surface_field, damage_field = ctx["highway_field"], ctx["surface_field"], ctx["damage_field"]
    base_speed = _base_speed_kmh(feat, highway_field) if highway_field else _DEFAULT_BASE_SPEED_KMH
    surface_penalty = _surface_penalty(feat, surface_field) if surface_field else _DEFAULT_SURFACE_PENALTY
    damage_multiplier = 1.0
    if damage_field:
        damage_multiplier, was_numeric = _damage_multiplier(feat, damage_field)
        if not was_numeric:
            counts["non_numeric_damage"] += 1
    slope_penalty = 1.0
    if ctx["dem"] is not None:
        slope_penalty = _segment_slope_penalty(ctx["dem"], geom, ctx["to_dem"], ctx["length_m"], ctx["vertical_factor"])
        if slope_penalty != 1.0:
            counts["sampled_slope"] += 1
    # Audit F19 (#155): passability 0 used to be clamped to the 0.1 km/h floor, so routing could still cross a
    # "closed" road. It now writes the closed sentinel, which the routing tools remove from the network.
    if damage_field and damage_multiplier == 0.0:
        counts["closed"] += 1
        return CLOSED_SPEED_KMH
    return max(_MIN_EFFECTIVE_SPEED_KMH, base_speed * surface_penalty * damage_multiplier * slope_penalty)


def _impedance_result(network, road_network_layer, output_field, damage_field, dem_layer, counts, owned):
    """The success reply of build_composite_impedance_field. Split out of it (LR-21, no behaviour change)."""
    result = {
        "success": True,
        "layer_name": road_network_layer,
        "output_field": output_field,
        "feature_count": network.featureCount(),
    }
    from .humanitarian_style import measure_hint
    result["map_looks"] = [measure_hint(road_network_layer, output_field, "The composite impedance cost per road segment")]
    if not owned:
        result["note"] = ("The layer is already in edit mode, so the new values are in your edit session and are NOT saved: "
                          "save or discard the layer edits yourself.")
    closed_count = counts["closed"]
    if closed_count:
        result["closed_segments"] = closed_count
        result["closure_note"] = (f"{closed_count} segment(s) with passability 0 are written as closed (speed {CLOSED_SPEED_KMH:g}); "
                                  "calculate_service_area / travel_time_matrix / optimize_delivery_route remove them from the network.")
    if damage_field is not None:
        result["damage_field"] = damage_field
        if counts["non_numeric_damage"]:
            result["warning"] = (
                f"{counts['non_numeric_damage']} feature(s) had a non-numeric or unparsable value in "
                f"'{damage_field}' -- defaulted to fully passable (1.0) for those."
            )
    if dem_layer is not None:
        result["dem_layer"] = dem_layer
        result["slope_penalized_segment_count"] = counts["sampled_slope"]
    return result


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
            "damage_field": {"type": "string", "description": "Optional numeric field, 0.0-1.0, giving each segment's passability (1.0=fully passable, 0.0=closed: the segment is removed from the network by the routing tools, e.g. from a road-status assessment). Non-numeric values default to 1.0 (unknown = assumed passable)."},
            "dem_layer": {"type": "string", "description": "Optional DEM raster layer. When given, each segment's endpoints are sampled for elevation and a slope penalty applied -- steeper segments get a lower effective speed."},
            "output_field": {"type": "string", "description": "Name of the new field to write the blended speed (km/h) into. Defaults to 'impedance_cost'."},
            "dem_vertical_unit": {"type": "string", "description": "Vertical unit of the DEM's elevation values: 'm' (default), 'ft' or 'us_ft'. A raster does not carry it."},
        },
        "required": ["road_network_layer"],
    },
)
def build_composite_impedance_field(road_network_layer, highway_field="highway", surface_field="surface",
                                     damage_field=None, dem_layer=None, output_field="impedance_cost", dem_vertical_unit="m"):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    from .raster_tools import vertical_unit_factor
    vertical_factor = vertical_unit_factor(dem_vertical_unit)
    if vertical_factor is None:
        return {"error": f"dem_vertical_unit must be 'm', 'ft' or 'us_ft', got {dem_vertical_unit!r}."}
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
    counts = {"non_numeric_damage": 0, "sampled_slope": 0, "closed": 0}
    # Audit F18 (#154): the slope used the endpoints as they are in the NETWORK's CRS (sampled in the DEM without a
    # transform) divided by the planar length in that CRS's units, so a geographic or foot-unit network got a meaningless
    # grade. Endpoints are now transformed into the DEM's CRS and the length is measured in metres on the ellipsoid.
    # The DEM's vertical unit is still ASSUMED to be metres: it is not stored in a form QGIS exposes reliably.
    to_dem, length_m = _dem_measuring(network, dem)
    try:
        with edit_command(network, "Cartogen AI: write " + output_field) as owned:
            out_idx = add_numeric_field(network, output_field)
            for feat in _ck.features(network, "Impedance: reading features"):
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue

                effective_speed = _segment_speed(feat, geom, counts, {
                    "highway_field": highway_field if has_highway else None, "surface_field": surface_field if has_surface else None,
                    "damage_field": damage_field if has_damage else None, "dem": dem, "to_dem": to_dem, "length_m": length_m,
                    "vertical_factor": vertical_factor})
                set_value(network, feat.id(), out_idx, effective_speed)
    except EditError as e:
        return {"error": f"build_composite_impedance_field failed, nothing was changed: {e}"}
    except Exception as e:
        return {"error": f"build_composite_impedance_field failed: {e}"}

    return _impedance_result(network, road_network_layer, output_field, damage_field, dem_layer, counts, owned)

