# -*- coding: utf-8 -*-
"""
Humanitarian Logistics Tools for Cartogen AI.
Hub siting, service-area, and travel-distance analysis for supply chain / last-
mile delivery planning (warehouse coverage, distribution routing). The
service-area and travel-matrix tools rely on QGIS's native Network Analysis
processing algorithms (native:serviceareafrompoint, native:shortestpathpointtolayer)
-- unlike the rest of this codebase's processing.run() calls (native:clip,
native:intersection, etc., which are exercised constantly and well-documented),
these are less commonly used. Confirmed live against real QGIS 4.2.2 as of
2026-09-05 (see point 8 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md):
SPEED_FIELD/DIRECTION_FIELD/STRATEGY all behave as documented, including a
real one-way-road test (a segment tagged forward-only correctly blocked the
reverse route) and a real differential-speed test (the same segment produced
different travel times with vs. without a speed_field). travel_time_matrix
worked cleanly on every network tried; calculate_service_area's
degenerate-small-network edge case (BUG-2026-09-05-2) was fixed 2026-09-10
(GeometrySkipInvalid context for serviceareafrompoint;
_degenerate_hull_fallback for the convexhull LineString/Polygon-sink case)
and live-verified against real QGIS 4.2.2 on 2026-09-11 (collinear
1-segment, L-shaped 2-segment, and a realistic 5-segment grid regression
guard all pass) -- status `fixed-verified` in docs/BUG_TRACKER.md.

population_access_gap chains calculate_service_area with
raster_tools.estimate_population_exposure (native:mergevectorlayers,
native:dissolve, native:intersection in between) and inherits the same
unverified-live caveat, plus its own: the intermediate merge/dissolve/
intersect steps have not been run against a real QGIS session either.
"""

import datetime
import time
from .registry import register_tool
from ._network_closure import routable_network
from .vector_tools import buffer_analysis
from .analysis_tools import _parse_date, _cap_entries
from ._qgis_enum_compat import resolve_qgis_enum
from ...logger import log_event
from . import _background_processing as _bg

try:
    from qgis.core import (
        QgsProject, QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer,
        QgsGeometry, QgsVectorLayer, QgsFeature, QgsProcessingContext,
        QgsField, QgsDistanceArea, QgsCoordinateTransform, QgsPointXY,
        QgsCoordinateReferenceSystem, QgsFeatureRequest, QgsSpatialIndex,
    )
    try:
        from qgis.core import Qgis
    except ImportError:
        Qgis = None
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QVariant
    import processing
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

# PERF-002, 2026-09-14 audit: optimal_hub_siting/location_allocation compute a full
# candidate x demand QgsGeometry.distance() cross product in pure Python, with no upper
# bound on input size -- since every tool call in this codebase's dispatcher runs on the
# QGIS main GUI thread (BlockingQueuedConnection), an unbounded pair count would freeze the
# whole interface for however long that loop takes. A genuine algorithm change (e.g.
# migrating to native:distancematrix) was considered and deliberately not made here -- it
# would need live-QGIS verification that its distance semantics exactly match
# QgsGeometry.distance() (planar, not ellipsoidal) across every existing test's CRS
# assumptions, a real correctness-risk rewrite this audit's own conventions say not to make
# without that evidence. This is the safe, mechanical half instead: a hard cap on the
# candidate x demand pair count, matching the same "protective bound against an unbounded,
# unattended cost" pattern already established elsewhere in this codebase (scheduler.py's
# _MIN_INTERVAL_MINUTES/_MAX_CONCURRENT_SCHEDULES, from an earlier security review). The
# exact number is a conservative estimate (not a live-measured benchmark in this sandbox):
# at a rough ~1-10 microseconds per simple point-point GEOS distance() call, 2,000,000 pairs
# is on the order of a few seconds worst case, not the tens-of-seconds-plus that would
# actually be disruptive -- comfortably above any realistic humanitarian facility-siting
# dataset (this codebase's own docs describe "tens of candidates, low hundreds of demand
# points" as typical), so no legitimate real-world call is expected to be newly rejected.
_MAX_HUB_SITING_PAIRS = 2_000_000


def _check_hub_siting_pair_count(candidate_count, demand_count, tool_name):
    pairs = candidate_count * demand_count
    if pairs > _MAX_HUB_SITING_PAIRS:
        return (
            f"{tool_name}: {candidate_count:,} candidates x {demand_count:,} demand points = "
            f"{pairs:,} distance pairs, over this tool's {_MAX_HUB_SITING_PAIRS:,}-pair safety "
            "limit (this computation runs on the QGIS main thread and would freeze the "
            "interface for its duration). Reduce candidate_layer/demand_layer to a smaller "
            "area of interest, or pre-aggregate demand points (e.g. dissolve to admin-unit "
            "centroids) before calling this tool."
        )
    return None


def unique_labels(raw_labels, fallback_prefix):
    """One distinct text label per feature, in order. Pure.

    These tools keyed their results by the layer's first attribute, so two features with the same name, or a NULL name,
    overwrote each other and silently dropped candidates, stops or origins (audit F23, #159). A unique label is kept as is;
    a repeated one becomes 'name [#n]' (n = 1-based position), an empty/NULL one '<fallback_prefix>_<n>'."""
    texts = [None if v is None or str(v).strip() in ("", "NULL") else str(v) for v in raw_labels]
    counts = {}
    for t in texts:
        if t is not None:
            counts[t] = counts.get(t, 0) + 1
    out = []
    for i, t in enumerate(texts, start=1):
        if t is None:
            out.append(f"{fallback_prefix}_{i}")
        elif counts[t] > 1:
            out.append(f"{t} [#{i}]")
        else:
            out.append(t)
    return out


def _make_distance_area(layer):
    """A QgsDistanceArea configured for real-world (ellipsoidal, in metres) distance in the layer's CRS, or None when it
    cannot be set up (the caller then reports it; see optimal_hub_siting / location_allocation).

    GitHub #142 (audit F06): this used to return None for every PROJECTED CRS on the claim that QgsGeometry.distance() is
    "already correct" there. It is only correct for a CRS whose unit is the metre and whose scale is true: Web Mercator metres
    are inflated by 1/cos(latitude), and a US-survey-foot CRS is not metres at all. measureLine() on an ellipsoid-configured
    QgsDistanceArea returns ellipsoidal metres for ANY source CRS, so it is used for all of them."""
    try:
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        # Live-caught 2026-09-19 (python-qgis.bat, real QGIS 4.2.2): a fresh/default
        # QgsProject.instance().ellipsoid() returns the literal string 'NONE' -- QGIS's own
        # sentinel for "no ellipsoid configured, use planar Cartesian math" -- which is
        # truthy in Python, so `or "WGS84"` never caught it and setEllipsoid("NONE") was
        # silently disabling ellipsoidal mode entirely. Confirmed live: measureLine()
        # returned the same raw-degree value as the old planar distance() call (1.0, not
        # the correct ~71km at 50N) until this was fixed to explicitly check for 'NONE'.
        project_ellipsoid = QgsProject.instance().ellipsoid()
        da.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
        return da
    except Exception:
        return None


def _geoms_in_crs(geoms, from_crs, to_crs):
    """Copies of `geoms` transformed from `from_crs` into `to_crs` (the geometries themselves are not modified). Raises
    ValueError if a transform cannot be built or applied, instead of letting a caller measure coordinates in the wrong CRS.

    GitHub #142 (audit F06): hub siting and location allocation paired demand points with candidates without transforming
    either, so a demand layer in another CRS was read as if its numbers were in the candidates' CRS (EPSG:3857 metres read
    as degrees gave ~18 million m for a 557 m gap) and the tool still said it had measured geodesic metres."""
    if from_crs == to_crs or not from_crs.isValid() or not to_crs.isValid():
        return list(geoms)
    try:
        transform = QgsCoordinateTransform(from_crs, to_crs, QgsProject.instance().transformContext())
        out = []
        for geom in geoms:
            moved = QgsGeometry(geom)
            # QGIS 4 returns a Qgis.GeometryOperationResult enum (Success == 0), QGIS 3 an int: accept either spelling.
            outcome = moved.transform(transform)
            success = getattr(getattr(globals().get("Qgis"), "GeometryOperationResult", None), "Success", 0)
            if outcome != 0 and outcome != success:
                raise ValueError("a geometry could not be transformed")
            out.append(moved)
        return out
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"could not transform from {from_crs.authid()} to {to_crs.authid()}: {e}")


def _network_context(invalid_geometry_check=None):
    """The QgsProcessingContext every network-analysis call (service area, shortest path) runs with.

    Live-reported 2026-09-24/25 ("Health facilities beyond one hour's travel"), reproduced and
    measured 2026-09-25 against a road of known length in real QGIS 4.2.2: these algorithms
    measure distance with the context's ELLIPSOID, and when there is none they fall back to raw
    layer units. calculate_service_area built a bare QgsProcessingContext() -- no project, so no
    ellipsoid, whatever the project's own setting -- so travel_cost was in degrees on a lat/long
    layer (a 1000 m service area covered the whole 10 km network) and in inflated Web Mercator
    metres on EPSG:3857 (about 15% short at Amman, worse further from the equator). The other
    calls used processing.run's default context, which takes the project's ellipsoid and so was
    right only if the project happened to have one set (QGIS new projects do; imported or older
    ones may not). Setting the ellipsoid here, explicitly, makes costs real metres (or hours
    for strategy='fastest') independent of the layers' CRS and of the project's settings.
    Same fallback as _make_distance_area: the project's ellipsoid, else WGS84 -- 'NONE' is
    QGIS's own truthy sentinel for "no ellipsoid", so it must be checked for by value."""
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    project_ellipsoid = QgsProject.instance().ellipsoid()
    # Measured in real QGIS 4.2.2 (2026-09-25): setProject alone does NOT give the context the
    # project's ellipsoid (it stayed 'NONE' with the project set to EPSG:7030), and an ellipsoid set
    # explicitly survives setProject in either order. So this explicit call is what does the work.
    context.setEllipsoid(project_ellipsoid if project_ellipsoid and project_ellipsoid != "NONE" else "WGS84")
    if invalid_geometry_check is not None:
        context.setInvalidGeometryCheck(invalid_geometry_check)
    return context


def _point_for_network(point, source_crs, network):
    """"x,y" for a START_POINT/END_POINT parameter, in the NETWORK layer's CRS.

    The algorithms read a bare "x,y" as being in the network's CRS, but the coordinates came from
    the facility/origin/stop layer's own geometry, which can be in a different one: e.g. an
    origin typed as Web Mercator metres (3999682,3756232) against roads downloaded as lat/long
    was read as degrees, far outside any network. Raises if the transform can't be built, so
    the caller reports it instead of silently routing from the wrong place."""
    pt = _point_xy_in_network_crs(point, source_crs, network)
    return f"{pt.x()},{pt.y()}"


def _point_xy_in_network_crs(point, source_crs, network):
    pt = QgsPointXY(point)
    net_crs = network.crs()
    if source_crs is not None and source_crs.isValid() and net_crs.isValid() and source_crs != net_crs:
        pt = QgsCoordinateTransform(source_crs, net_crs, QgsProject.instance()).transform(pt)
    return pt


# ---- exact clipping of the road network to what a service area can reach ---------------------------
#
# BUG-2026-09-25-2: routing builds a graph from EVERY road in the layer before answering, at about
# 0.6-1 ms per road (measured: 25 s at 39,017 roads, 125 s at 107,719, 331 s for a one-hour service
# area on all 161,041 Jordan roads). But nothing reachable within cost R can be farther than R
# in a straight line from the start, so for a service area only the roads near the start matter.
# Roads in the real Jordan extract inside that reach, around Amman: 829 (1 km), 5,736 (3 km),
# 38,197 (10 km), 75,192 (25 km), 105,076 (51.5 km) of 161,041; the clip itself takes 0.1-1.8 s.
#
# This is exact, not an approximation, as long as the reach is a true upper bound (see
# _reach_metres) and the whole feature is kept when any part of it is inside (so the graph inside
# the disc is identical): the algorithm sees the same local network. It is NOT used for the
# travel-time matrix: the shortest route between two points can detour outside the box around them.
_CLIP_MARGIN_FACTOR = 1.03      # QGIS may use the project's ellipsoid, not WGS84: differences are < 1%
_CLIP_MARGIN_METRES = 100.0
_CLIP_MAX_REACH_METRES = 5_000_000.0
_CLIP_WORTHWHILE_FRACTION = 0.9  # if the box still holds 90%+ of the roads, copying isn't worth it


def _reach_metres(travel_costs, strategy, default_speed, max_field_speed=None):
    """The farthest straight-line distance, in metres, at which anything can still be within the
    largest cost asked for. A route is never shorter than the straight line, so this is a true
    upper bound: for 'shortest' the cost is already metres; for 'fastest' the cost is hours, and the
    most distance a route can cover in that time is at the fastest speed anywhere in the network
    (default_speed, or the largest value in speed_field). Unknown speed_field maximum -> None -> only
    default_speed, which is only safe when there is no speed_field, so the caller must not pass an
    unknown maximum for a network that has one (it doesn't clip in that case)."""
    cost = float(max(travel_costs))
    if strategy == "fastest":
        speeds = [float(default_speed)]
        if max_field_speed:
            speeds.append(float(max_field_speed))
        return cost * max(speeds) * 1000.0
    return cost


# A speed_field with usable values (> 0) on fewer roads than this is ignored: OSM's `maxspeed` is
# set on well under 1% of roads in the Geofabrik extracts (Jordan 0.9%, Yemen 0.66%), 0 meaning
# "unset". Rc7 smoke test, 2026-09-30 (F05): a run with such a field produced a zero-length
# reachable network while the previous good result was replaced and success was reported.
MIN_USABLE_SPEED_SHARE = 0.5


def _usable_speed_share(values):
    """(share, usable, total) of `values` that are numbers > 0. NULL, 0, empty and non-numeric
    all mean "no speed recorded"."""
    total = usable = 0
    for value in values:
        total += 1
        try:
            if value is not None and float(value) > 0:
                usable += 1
        except (TypeError, ValueError):
            pass
    return ((usable / total) if total else 0.0), usable, total


def _field_values(layer, field):
    """Every value of `field` on `layer`, reading attributes only where the QGIS version allows."""
    try:
        from qgis.core import QgsFeatureRequest
        request = QgsFeatureRequest()
        request.setSubsetOfAttributes([field], layer.fields())
        features = layer.getFeatures(request)
    except Exception:
        features = layer.getFeatures()
    for feature in features:
        try:
            yield feature[field]
        except (KeyError, IndexError):
            yield None


def _vet_speed_field(network, speed_field, default_speed):
    """(speed_field_to_use, note). A field that is empty/0 on most roads is dropped in favour of the
    flat default_speed -- with an explanation for the user -- instead of routing on a network where
    nearly every road is untraversable."""
    if not speed_field:
        return None, None
    share, usable, total = _usable_speed_share(_field_values(network, speed_field))
    if total == 0 or share >= MIN_USABLE_SPEED_SHARE:
        # An empty layer gives nothing to judge the field by -- leave the caller's choice alone.
        return speed_field, None
    pct = share * 100
    pct_text = f"{pct:.0f}%" if pct >= 1 or usable == 0 else f"{pct:.2f}%"
    return None, (
        f"speed_field '{speed_field}' has a usable value on only {pct_text} of roads "
        f"({usable:,} of {total:,}; 0/NULL means unset), so it was ignored and a flat "
        f"default_speed of {default_speed} km/h was used instead. Run estimate_road_speeds first "
        "for road-class based speeds."
    )


def _reachable_network_is_degenerate(lines_layer):
    """True when the reachable-network layer has no length at all (no features, only null
    geometries, or a zero-length line at the snapped start point)."""
    for feature in lines_layer.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isNull():
            continue
        if geometry.length() > 0:
            return False
    return True


def _travel_cost_unit_note(strategy, travel_costs):
    """A reminder when travel_cost looks like hours but the strategy makes it metres."""
    if strategy == "shortest" and travel_costs and max(travel_costs) < 100:
        largest = max(travel_costs)
        return (
            f"travel_cost {largest:g} was read in METRES because strategy='shortest' (a "
            f"{largest:g} m service area). For hours of travel time use strategy='fastest'."
        )
    return None


def _max_speed_in_field(network, speed_field):
    """The largest numeric value of speed_field (km/h), or None if it can't be determined."""
    try:
        value = network.maximumValue(network.fields().indexOf(speed_field))
        return float(value) if value is not None and float(value) > 0 else None
    except Exception:
        return None


def _clip_network_to_reach(network, centre_xy, reach_m):
    """(layer_to_route_on, info). The roads that can matter within reach_m of centre_xy (in the
    network's CRS), or the whole network whenever clipping wouldn't be exact or worthwhile:
      * a small network (copying costs more than it saves);
      * an enormous reach (the disc covers much of the globe);
      * the box still holds 90%+ of the roads;
      * no road within reach at all: QGIS snaps a far-away start to the NEAREST road however far,
        and a clipped network could snap to a different one, so keep the old behaviour there;
      * anything going wrong (a CRS that can't be transformed, e.g. at a pole).
    info: {"applied", "roads_full", "roads_used"}."""
    info = {"applied": False, "roads_full": None, "roads_used": None}
    try:
        total = int(network.featureCount())
    except Exception:
        return network, info
    info["roads_full"] = info["roads_used"] = total
    radius = reach_m * _CLIP_MARGIN_FACTOR + _CLIP_MARGIN_METRES
    if total < BACKGROUND_MIN_FEATURES or radius > _CLIP_MAX_REACH_METRES:
        return network, info
    try:
        project = QgsProject.instance()
        net_crs = network.crs()
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        centre = centre_xy
        if net_crs != wgs:
            centre = QgsCoordinateTransform(net_crs, wgs, project).transform(centre_xy)
        # Azimuthal equidistant centred on the start: distances from the centre are true metres,
        # so this disc is exactly "everything within `radius` of the start", in any network CRS.
        aeqd = QgsCoordinateReferenceSystem.fromProj(
            f"+proj=aeqd +lat_0={centre.y():.9f} +lon_0={centre.x():.9f} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs")
        if not aeqd.isValid():
            return network, info
        disc = QgsGeometry.fromPointXY(QgsPointXY(0, 0)).buffer(radius, 64)
        disc.transform(QgsCoordinateTransform(aeqd, net_crs, project))
        clipped = network.materialize(QgsFeatureRequest().setFilterRect(disc.boundingBox()))
        used = int(clipped.featureCount())
        if used >= total * _CLIP_WORTHWHILE_FRACTION:
            return network, info
        if not any(f.geometry().intersects(disc) for f in clipped.getFeatures()):
            return network, info
        info.update(applied=True, roads_used=used)
        return clipped, info
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="logistics_clip_network",
                  error_class=type(e).__name__, error=True)
        return network, info


def _measure_distance(distance_area, geom_a, geom_b):
    """geom_a/geom_b are point geometries -- both callers (optimal_hub_siting, location_allocation) require point layers,
    per their own tool descriptions, and pass them in the SAME CRS (see _geoms_in_crs). Returns real-world metres via
    ellipsoidal QgsDistanceArea.measureLine() when distance_area is given.

    With no distance_area (its setup failed) the raw QgsGeometry.distance() is returned, in the CRS's own units; the callers
    say so in their warning. A measurement that raises is NOT papered over with that planar number any more (GitHub #142): it
    used to be, and the result then claimed geodesic metres. The error propagates and the tool reports it."""
    if distance_area is not None:
        return distance_area.measureLine(geom_a.asPoint(), geom_b.asPoint())
    return geom_a.distance(geom_b)


# Below this many roads a routing call takes roughly a couple of seconds (measured: about 1 ms per
# road for the graph build), which isn't worth a worker thread; the delivery-route tool makes
# hundreds of small calls and would pay the hand-off cost on every one of them.
BACKGROUND_MIN_FEATURES = 2000


def _run_with_quiet_feedback(alg, prm, context=None):
    """processing.run with the feedback that keeps 'no route' messages out of the CRITICAL log (F15). Outside QGIS
    there is no such feedback and the plain call is made."""
    feedback = _bg.new_feedback()
    if feedback is None:
        return processing.run(alg, prm, context=context)
    return processing.run(alg, prm, context=context, feedback=feedback)


def _run_network_algorithm(algorithm_id, params, context, network, label):
    """processing.run for the network algorithms, off the GUI thread when the network is big.

    BUG-2026-09-25-2: on a national road network (161,041 roads) one call took 292-572 s and
    froze QGIS with no way to stop it. See _background_processing.py for the design and its
    measurements. Raises _bg.AnalysisCancelled on Stop: callers must let it through (the generic
    `except Exception` around these calls would otherwise record a user's Stop as an ordinary
    failure and carry on with the next facility)."""
    try:
        use_background = int(network.featureCount()) >= BACKGROUND_MIN_FEATURES
    except Exception:
        use_background = True
    return _bg.run_algorithm(
        algorithm_id, params, context,
        fallback=_run_with_quiet_feedback,
        use_background=use_background, label=label,
    )


def _cancelled_result(what):
    return {"error": f"Stopped before the {what} finished. Nothing was added to the project.", "cancelled": True}


def _closed_note(closed):
    """Result entry for the closed segments that were left out of the routing network, or {}. Pure."""
    if not closed:
        return {}
    return {"closed_segments_removed": closed,
            "closed_note": f"{closed} closed road segment(s) (negative speed in the speed field) were removed from the network "
                           "for this analysis; no route or service area crosses them."}


def _open_network(network, speed_field, layer_name):
    """(network_to_route_on, closed_count, error) -- the network without closed segments (audit F19, #155; see
    _network_closure). `layer_name` only words the error."""
    open_network, closed, error = routable_network(network, speed_field)
    if error:
        return None, closed, f"'{layer_name}': {error}"
    return open_network, closed, None


def _network_geometry_error(network, layer_name):
    """An error string when `network` can't be a road network, else None.

    QGIS's network algorithms don't reject a point layer; they run and return a result that
    means nothing. Live-reported 2026-09-24: a Road Network ingested as points (see
    ingest_osm_features) went through calculate_service_area as a success, and the model spent
    its remaining tool calls trying to work out why the result was wrong. Saying so up front
    points it at the real fix: re-ingest or load a line layer."""
    if QgsWkbTypes.geometryType(network.wkbType()) != QgsWkbTypes.GeometryType.LineGeometry:
        return (f"'{layer_name}' is not a line layer, so it can't be used as a road network. "
                "Load or ingest the roads as lines (e.g. ingest_osm_features with key='highway').")
    return None


def _network_direction_speed_params(network, speed_field=None, direction_field=None,
                                     value_forward="yes", value_backward="-1", value_both="no"):
    """Wires speed_field/direction_field through to native:serviceareafrompoint/
    native:shortestpathpointtolayer's real SPEED_FIELD/DIRECTION_FIELD parameters
    -- point 8 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md, §2 item 1 of
    docs/archive/ROUTE_OPTIMIZATION_STRATEGY.md ("the highest-value, lowest-risk change
    available... a parameter addition to an existing processing.run() call, not a new
    algorithm"). Both params previously went entirely unused -- every route was computed
    on a flat DEFAULT_SPEED with no way to make one-way streets one-way or give some
    segments a different speed than others. value_forward/value_backward/value_both
    default to OSM's own standard `oneway` tag values (a way digitized in the forward
    direction is "yes"=forward-only, "-1"=backward-only, "no"/absent=both directions),
    since fetch_osm_features (humanitarian_tools.py) is this codebase's primary road-
    network source -- overridable for a direction_field with different encoding.
    DEFAULT_DIRECTION is fixed at "Both directions" (index 2) so a feature with no
    matching direction_field value still routes rather than being silently excluded.
    Returns (extra_params, error) -- error is a caller-facing string when a given field
    name doesn't actually exist on the network layer, matching the same
    validate-before-processing.run() convention this session's other new tools use (e.g.
    export_layout_atlas's filename_field check)."""
    extra = {}
    if speed_field:
        if network.fields().indexOf(speed_field) == -1:
            return None, f"speed_field '{speed_field}' not found on the road network layer."
        extra["SPEED_FIELD"] = speed_field
    if direction_field:
        dir_idx = network.fields().indexOf(direction_field)
        if dir_idx == -1:
            return None, f"direction_field '{direction_field}' not found on the road network layer."
        if (value_forward, value_backward, value_both) == ("yes", "-1", "no"):
            # Geofabrik shapefile extracts encode one-way as F (forward) / T (towards, i.e. backward) / B (both), not OSM's
            # yes / -1 / no. With the OSM defaults nothing matched, every road counted as two-way and one-way streets were
            # silently ignored (rc11 smoke test: the Yemen roads layer held F and B). Detected from the layer's own values.
            try:
                seen = {str(v) for v in network.uniqueValues(dir_idx) if v is not None}
                if seen and seen <= {"F", "T", "B"}:
                    value_forward, value_backward, value_both = "F", "T", "B"
            except Exception:
                pass
        extra["DIRECTION_FIELD"] = direction_field
        extra["VALUE_FORWARD"] = value_forward
        extra["VALUE_BACKWARD"] = value_backward
        extra["VALUE_BOTH"] = value_both
        extra["DEFAULT_DIRECTION"] = 2
    return extra, None


def _find_layer_by_name(name):
    if not QGIS_AVAILABLE:
        return None
    layers = QgsProject.instance().mapLayersByName(name)
    if not layers:
        return None
    return layers[0]


def _show_on_top(name):
    """Makes the named layer visible and the topmost tree entry. The classified facilities layer was found unticked and
    under the original facilities layer on the rc10 smoke test, so the green/red result was not what the map showed.
    Never raises: placement is cosmetic."""
    try:
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        for layer in project.mapLayersByName(name):
            node = root.findLayer(layer.id())
            if node is None:
                continue
            node.setItemVisibilityChecked(True)
            if node.parent() is root and root.children() and root.children()[0] is not node:
                moved = root.insertChildNode(0, node.clone())
                root.removeChildNode(node)
                if moved is not None:
                    moved.setItemVisibilityChecked(True)
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="show_on_top", error_class=type(e).__name__, error=True)


def _hide_layers(names):
    """Unchecks the layers' tree nodes (they stay in the project). Never raises: hiding is cosmetic."""
    try:
        root = QgsProject.instance().layerTreeRoot()
        for name in names:
            for layer in QgsProject.instance().mapLayersByName(name):
                node = root.findLayer(layer.id())
                if node is not None:
                    node.setItemVisibilityChecked(False)
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="hide_layers", error_class=type(e).__name__, error=True)


# #130 point 3: the parameters a result layer was built with, stored on the layer so a later run that replaces it by name can say what changed.
_RESULT_PARAMS_KEY = "cartogen_ai/result_params"


def describe_param_changes(old, new):
    """[(key, old value, new value)] for the parameters that differ between two results' parameter dicts, in a stable order. Pure.

    A key present in only one dict counts as a change (None on the other side). Lists are compared as sorted lists so a band list is not
    'different' for being written in another order."""
    def norm(v):
        return sorted(v) if isinstance(v, (list, tuple)) else v
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = norm(old.get(k)), norm(new.get(k))
        if a != b:
            out.append((k, a, b))
    return out


def replacement_note(name, changes):
    """The sentence the reply must relay when a result layer was replaced by one built with different parameters. Pure."""
    detail = "; ".join(f"{k}: {a if a is not None else 'not set'} -> {b if b is not None else 'not set'}" for k, a, b in changes)
    return (f"Replaced the existing layer '{name}' with a new one built with different parameters ({detail}). The earlier result is no longer in "
            "the project; to keep both, ask for the new result under a different origin name or export the earlier one first.")


def _replace_named_layer(name, new_layer, to_tree=True, params=None):
    """Adds `new_layer` under `name`, first removing every existing layer already using that
    exact name -- calculate_service_area's output names are deterministic (derived from the
    facility layer's name and its feature index, not a per-call id), so re-running the same
    analysis, or a follow-up request that reuses the same origin, produced a second layer with
    the identical name every time: QgsProject.addMapLayer() does not deduplicate by name at
    all, so the old one was never replaced, just buried under the new one. Live-reported,
    2026-09-28: a multi-step session ("health facilities beyond 1hr", then "population outside
    the catchment") left THREE separately-named-but-identical "Origin Point_service_area_0"-
    style layers stacked in the project, described as the map "losing control" on anything
    beyond a single simple request. Removing every prior same-named layer first, rather than
    just the first match, also cleans up any already-accumulated duplicates from before this
    fix, not just prevents new ones."""
    new_layer.setName(name)
    project = QgsProject.instance()
    replaced = None
    for stale in project.mapLayersByName(name):
        # #130 point 3: when the layer being replaced was built with different parameters, say so (the caller relays it); a re-run with the same
        # parameters stays silent, and a layer with no recorded parameters (made before this was added) is not reported.
        if params is not None and replaced is None:
            try:
                import json as _json
                raw = stale.customProperty(_RESULT_PARAMS_KEY)
                old = _json.loads(raw) if raw else None
            except Exception:
                old = None
            if old is not None:
                changes = describe_param_changes(old, params)
                if changes:
                    replaced = {"layer": name, "changes": [{"parameter": k, "was": a, "now": b} for k, a, b in changes],
                                "note": replacement_note(name, changes)}
        project.removeMapLayer(stale.id())
    if params is not None:
        try:
            import json as _json
            new_layer.setCustomProperty(_RESULT_PARAMS_KEY, _json.dumps(params, sort_keys=True, default=str))
        except Exception:
            pass
    if to_tree:
        project.addMapLayer(new_layer)
    else:
        project.addMapLayer(new_layer, False)   # the caller puts the layer in a group itself
    # F06: keep the output across Save/Reopen (a no-op for an unsaved project; see results_store.py).
    try:
        from ..results_store import persist_layer
        persist_layer(new_layer, tool="analysis")
    except Exception:
        pass
    return replaced


def _style_risk_buffer_layer(layer):
    """Hardcoded, consistent 'risk corridor' look for score_route_incident_risk's
    buffer output -- same reasoning as humanitarian_tools._style_incident_layer:
    fixing this in plugin code guarantees every risk-scored route reads as risk
    (translucent orange, no border) regardless of what QGIS's default random
    single-symbol color would otherwise assign, and low enough opacity that the
    route line and basemap underneath stay visible rather than getting buried
    under a solid fill (same 75%-opacity-for-overlap reasoning styling_tools.py
    already applies elsewhere, tuned down further since this sits on top of a
    route line specifically)."""
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    symbol.setColor(QColor(255, 140, 0, 90))  # translucent orange, ~35% opacity
    for i in range(symbol.symbolLayerCount()):
        sym_layer = symbol.symbolLayer(i)
        if hasattr(sym_layer, "setStrokeStyle"):
            sym_layer.setStrokeStyle(0)  # Qt.PenStyle.NoPen -- no border ring
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def _rank_hub_candidates(candidate_distances, max_distance=None):
    """Pure Python, no QGIS needed -- candidate_distances is
    {candidate_name: [distance_to_each_demand_point, ...]}. Ranks candidates
    by average distance to all demand points (ascending = best coverage),
    optionally also reporting how many demand points fall within
    max_distance ("served")."""
    results = []
    for name, distances in candidate_distances.items():
        if not distances:
            continue
        avg_distance = sum(distances) / len(distances)
        entry = {
            "candidate": name,
            "avg_distance": round(avg_distance, 2),
            "max_distance_to_any_demand_point": round(max(distances), 2),
        }
        if max_distance is not None:
            served = sum(1 for d in distances if d <= max_distance)
            entry["demand_points_served"] = served
            entry["demand_points_served_percent"] = round(served / len(distances) * 100, 1)
        results.append(entry)
    results.sort(key=lambda r: r["avg_distance"])
    return results


@register_tool(
    "optimal_hub_siting",
    "Rank candidate hub/warehouse/facility locations by how well they serve a set of demand points "
    "(e.g. villages, distribution sites) -- for each candidate, computes the average straight-line "
    "distance to all demand points and (if max_distance is given) how many fall within it. Returns "
    "candidates ranked best (lowest average distance) first. Use this instead of eyeballing a map "
    "when choosing between several possible hub locations. Uses straight-line distance, not road "
    "network distance -- for network-based reachability use calculate_service_area instead.",
    {
        "type": "object",
        "properties": {
            "candidate_layer": {"type": "string", "description": "Point layer of possible hub/facility locations to evaluate."},
            "demand_layer": {"type": "string", "description": "Point layer of locations needing service (villages, distribution sites)."},
            "max_distance": {"type": "number", "description": "Distance (in the layers' CRS units, usually meters) within which a demand point counts as 'served'. Omit to rank on average distance alone."},
        },
        "required": ["candidate_layer", "demand_layer"],
    },
)
def optimal_hub_siting(candidate_layer, demand_layer, max_distance=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    candidates = _find_layer_by_name(candidate_layer)
    demand = _find_layer_by_name(demand_layer)
    if candidates is None:
        return {"error": f"Layer '{candidate_layer}' not found"}
    if demand is None:
        return {"error": f"Layer '{demand_layer}' not found"}

    try:
        demand_geoms = [f.geometry() for f in demand.getFeatures() if not f.geometry().isEmpty()]
        if not demand_geoms:
            return {"error": f"'{demand_layer}' has no usable point features."}
        demand_geoms = _geoms_in_crs(demand_geoms, demand.crs(), candidates.crs())

        pair_count_error = _check_hub_siting_pair_count(
            candidates.featureCount(), len(demand_geoms), "optimal_hub_siting"
        )
        if pair_count_error:
            return {"error": pair_count_error}

        distance_area = _make_distance_area(candidates)
        candidate_distances = {}
        usable_candidates = [f for f in candidates.getFeatures() if not f.geometry().isEmpty()]
        candidate_names = unique_labels(
            [f.attribute(0) if f.fields().count() else None for f in usable_candidates], "candidate")
        for cand_feat, name in zip(usable_candidates, candidate_names):
            candidate_distances[name] = [_measure_distance(distance_area, cand_feat.geometry(), dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}

        ranked = _rank_hub_candidates(candidate_distances, max_distance)
        result = {
            "success": True,
            "candidate_count": len(ranked),
            "demand_point_count": len(demand_geoms),
            "ranked_candidates": ranked,
        }
        # QGIS-006, 2026-09-13 audit (fixed 2026-09-19): same CRS-unit-mismatch class
        # buffer_analysis already warns about (Point 3 of
        # docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md) -- cand_geom.distance(dg)
        # used to be a raw, unconverted CRS-unit distance (degrees on a geographic CRS,
        # despite this tool's own docstring describing values as "usually meters"). Now
        # measured via _make_distance_area/_measure_distance instead: real-world ellipsoidal
        # meters on a geographic CRS, unchanged planar meters on an already-projected one.
        # The warning below only fires if ellipsoidal setup itself failed (distance_area is
        # None on a geographic CRS) -- an honest fallback statement, not a guessed
        # reprojection, for the one case this fix doesn't cover.
        try:
            if candidates.crs().isGeographic():
                if distance_area is not None:
                    result["note"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}) -- "
                        "distances above are real-world meters via ellipsoidal (WGS84 geodesic) "
                        "measurement, not raw planar degrees."
                    )
                else:
                    result["warning"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}), but "
                        "ellipsoidal distance measurement could not be set up, so every distance value "
                        "above is in DEGREES, not meters -- reproject to a projected/UTM CRS first for "
                        "meaningful distances."
                    )
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="logistics_crs_warning",
                      error_class=type(e).__name__, error=True)
        return result
    except Exception as e:
        return {"error": f"optimal_hub_siting failed: {e}"}


def _greedy_p_median(candidate_distances, demand_weights, num_facilities):
    """Pure Python, no QGIS needed -- candidate_distances is {candidate_name:
    [dist_to_demand_0, dist_to_demand_1, ...]}, demand_weights is a list of
    weights per demand point (all 1.0 if unweighted). Greedily selects
    num_facilities candidates that together minimize total weighted distance
    from each demand point to its NEAREST selected facility. This is the
    standard greedy approximation to the p-median problem (exact p-median is
    NP-hard for anything but a small candidate set) -- unlike
    optimal_hub_siting, which ranks each candidate independently, this
    accounts for overlap: two candidates that are both close to the same
    demand points don't both get "credit" for covering them."""
    candidates = list(candidate_distances.keys())
    n_demand = len(next(iter(candidate_distances.values())))
    selected = []
    remaining = set(candidates)
    current_min = [float("inf")] * n_demand

    for _ in range(min(num_facilities, len(candidates))):
        best_candidate = None
        best_total = None
        best_new_min = None
        for cand in remaining:
            distances = candidate_distances[cand]
            new_min = [min(current_min[j], distances[j]) for j in range(n_demand)]
            total = sum(new_min[j] * demand_weights[j] for j in range(n_demand))
            if best_total is None or total < best_total:
                best_total = total
                best_candidate = cand
                best_new_min = new_min
        selected.append(best_candidate)
        remaining.discard(best_candidate)
        current_min = best_new_min

    total_weighted_distance = sum(current_min[j] * demand_weights[j] for j in range(n_demand))
    avg_distance = sum(current_min) / n_demand if n_demand else 0
    return {
        "selected_facilities": selected,
        "total_weighted_distance": round(total_weighted_distance, 2),
        "avg_distance_per_demand_point": round(avg_distance, 2),
    }


@register_tool(
    "location_allocation",
    "Choose the best COMBINATION of num_facilities locations (out of a larger candidate list) to "
    "collectively minimize distance to all demand points -- e.g. 'which 3 of these 10 possible "
    "warehouse sites should we actually build, together, to best cover all these villages'. "
    "Different from optimal_hub_siting, which ranks candidates independently and doesn't account "
    "for overlap between them (two candidates both close to the same villages don't both get "
    "credit for covering them here). Uses a standard greedy approximation, not a guaranteed "
    "globally-optimal solution -- exact optimization is computationally infeasible beyond a "
    "handful of candidates anyway.",
    {
        "type": "object",
        "properties": {
            "candidate_layer": {"type": "string", "description": "Point layer of possible facility locations."},
            "demand_layer": {"type": "string", "description": "Point layer of locations needing service."},
            "num_facilities": {"type": "integer", "description": "How many facilities to select."},
            "weight_field": {"type": "string", "description": "Optional numeric field on demand_layer to weight points by (e.g. population). Defaults to equal weight."},
        },
        "required": ["candidate_layer", "demand_layer", "num_facilities"],
    },
)
def location_allocation(candidate_layer, demand_layer, num_facilities, weight_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if num_facilities < 1:
        return {"error": "num_facilities must be at least 1."}

    candidates = _find_layer_by_name(candidate_layer)
    demand = _find_layer_by_name(demand_layer)
    if candidates is None:
        return {"error": f"Layer '{candidate_layer}' not found"}
    if demand is None:
        return {"error": f"Layer '{demand_layer}' not found"}
    if weight_field and weight_field not in [f.name() for f in demand.fields()]:
        return {"error": f"Field '{weight_field}' not found in '{demand_layer}'"}

    try:
        demand_feats = [f for f in demand.getFeatures() if not f.geometry().isEmpty()]
        if not demand_feats:
            return {"error": f"'{demand_layer}' has no usable point features."}
        demand_geoms = _geoms_in_crs([f.geometry() for f in demand_feats], demand.crs(), candidates.crs())

        if weight_field:
            demand_weights = []
            for f in demand_feats:
                try:
                    demand_weights.append(float(f[weight_field]))
                except (TypeError, ValueError):
                    demand_weights.append(0.0)
        else:
            demand_weights = [1.0] * len(demand_feats)

        pair_count_error = _check_hub_siting_pair_count(
            candidates.featureCount(), len(demand_geoms), "location_allocation"
        )
        if pair_count_error:
            return {"error": pair_count_error}

        distance_area = _make_distance_area(candidates)
        candidate_distances = {}
        usable_candidates = [f for f in candidates.getFeatures() if not f.geometry().isEmpty()]
        candidate_names = unique_labels(
            [f.attribute(0) if f.fields().count() else None for f in usable_candidates], "candidate")
        for cand_feat, name in zip(usable_candidates, candidate_names):
            candidate_distances[name] = [_measure_distance(distance_area, cand_feat.geometry(), dg) for dg in demand_geoms]

        if not candidate_distances:
            return {"error": f"'{candidate_layer}' has no usable point features."}
        if num_facilities > len(candidate_distances):
            return {"error": f"num_facilities ({num_facilities}) exceeds the number of usable candidates ({len(candidate_distances)})."}

        result = _greedy_p_median(candidate_distances, demand_weights, num_facilities)
        result["success"] = True
        result["candidate_count"] = len(candidate_distances)
        result["demand_point_count"] = len(demand_geoms)
        # Same fix as optimal_hub_siting -- see its own comment for the full history
        # (QGIS-006, 2026-09-13 audit; fixed 2026-09-19).
        try:
            if candidates.crs().isGeographic():
                if distance_area is not None:
                    result["note"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}) -- "
                        "distances are real-world meters via ellipsoidal (WGS84 geodesic) measurement, "
                        "not raw planar degrees."
                    )
                else:
                    result["warning"] = (
                        f"'{candidate_layer}' is in a geographic CRS ({candidates.crs().authid()}), but "
                        "ellipsoidal distance measurement could not be set up, so every distance value "
                        "is in DEGREES, not meters -- reproject to a projected/UTM CRS first for "
                        "meaningful distances."
                    )
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="logistics_crs_warning",
                      error_class=type(e).__name__, error=True)
        return result
    except Exception as e:
        return {"error": f"location_allocation failed: {e}"}


def _tour_length(tour, distance_matrix):
    """Pure Python -- total length of a tour (list of indices) over a
    symmetric distance_matrix."""
    return sum(distance_matrix[tour[i]][tour[i + 1]] for i in range(len(tour) - 1))


def _tsp_nearest_neighbor(distance_matrix, start_index=0):
    """Pure Python -- builds an initial tour via the nearest-neighbor
    heuristic: starting at start_index, repeatedly jump to the closest
    unvisited stop. A standard, simple TSP construction heuristic -- not
    optimal on its own, which is why _two_opt below refines it."""
    n = len(distance_matrix)
    visited = [False] * n
    tour = [start_index]
    visited[start_index] = True
    current = start_index
    for _ in range(n - 1):
        nearest = min(
            (j for j in range(n) if not visited[j]),
            key=lambda j: distance_matrix[current][j],
        )
        tour.append(nearest)
        visited[nearest] = True
        current = nearest
    return tour


def _two_opt(tour, distance_matrix, max_iterations=2000):
    """Pure Python -- classic 2-opt local search: repeatedly tries reversing a
    segment of the tour and keeps the reversal if it shortens the total
    route. Standard, well-understood TSP improvement heuristic -- not a
    guaranteed optimal solution, but reliably improves on the raw
    nearest-neighbor tour."""
    improved = True
    iterations = 0
    n = len(tour)
    while improved and iterations < max_iterations:
        improved = False
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                if j - i == 1:
                    continue
                new_tour = tour[:i] + tour[i:j][::-1] + tour[j:]
                if _tour_length(new_tour, distance_matrix) < _tour_length(tour, distance_matrix):
                    tour = new_tour
                    improved = True
                iterations += 1
                if iterations >= max_iterations:
                    break
            if iterations >= max_iterations:
                break
    return tour


def _optimize_route(distance_matrix, start_index=0):
    """Pure Python -- nearest-neighbor construction followed by 2-opt
    refinement. Returns (tour, total_length)."""
    tour = _tsp_nearest_neighbor(distance_matrix, start_index)
    tour = _two_opt(tour, distance_matrix)
    return tour, _tour_length(tour, distance_matrix)


@register_tool(
    "optimize_delivery_route",
    "Find a good visiting order for a set of delivery/distribution stops -- e.g. 'what order "
    "should the truck visit these 8 distribution points'. Uses a standard nearest-neighbor + "
    "2-opt heuristic to pick the *order* (not a guaranteed globally-optimal order). Without "
    "road_network_layer, ordering uses straight-line distance and the result is a stop order "
    "only -- do NOT draw a straight line between the stops and present it as a route on an "
    "operational map; it is not a routable path. Pass road_network_layer to make the ordering "
    "itself road-network-aware (real road distance between every pair of stops, not straight-line) "
    "and to build an actual road-snapped route line, added to the project and safe to render as a "
    "real route. speed_field/direction_field (same meaning as calculate_service_area's) only "
    "affect ordering when road_network_layer is given. Not a substitute for a full commercial VRP "
    "solver with vehicle capacity/time-window constraints.",
    {
        "type": "object",
        "properties": {
            "stops_layer": {"type": "string", "description": "Point layer of stops to visit."},
            "start_stop_name": {"type": "string", "description": "Optional name (from the layer's first attribute field) of the stop to start from. Defaults to the first feature."},
            "road_network_layer": {"type": "string", "description": "Optional line layer representing the road/path network. When given, visiting order uses real road-network distance (not straight-line) and a road-snapped route line is built and added to the project -- required before the output may be rendered as a route on a map."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects ordering when road_network_layer is given."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Only affects ordering when road_network_layer is given."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (travel time). Use 'fastest' when the user asks for the fastest route or a travel time; it needs road_network_layer. The time is an ESTIMATE from speed_field (km/h per segment) or default_speed, not measured traffic."},
            "default_speed": {"type": "number", "description": "Speed in km/h for road segments with no speed_field value. Only used with strategy='fastest'. Defaults to 50."},
        },
        "required": ["stops_layer"],
    },
)
def optimize_delivery_route(stops_layer, start_stop_name=None, road_network_layer=None,
                             speed_field=None, direction_field=None,
                             value_forward="yes", value_backward="-1", value_both="no",
                             strategy="shortest", default_speed=50):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}
    if strategy == "fastest" and road_network_layer is None:
        return {"error": "strategy='fastest' needs road_network_layer: a travel time cannot be computed from straight-line distance."}
    if not isinstance(default_speed, (int, float)) or isinstance(default_speed, bool) or default_speed <= 0:
        return {"error": "default_speed must be a positive number of km/h."}
    fastest = strategy == "fastest"
    layer = _find_layer_by_name(stops_layer)
    if layer is None:
        return {"error": f"Layer '{stops_layer}' not found"}

    network = None
    closed_segments = 0
    extra_params = {}
    if road_network_layer is not None:
        network = _find_layer_by_name(road_network_layer)
        if network is None:
            return {"error": f"Layer '{road_network_layer}' not found"}
        geometry_error = _network_geometry_error(network, road_network_layer)
        if geometry_error:
            return {"error": geometry_error}
        network, closed_segments, closed_error = _open_network(network, speed_field, road_network_layer)
        if closed_error:
            return {"error": closed_error}
        extra_params, field_error = _network_direction_speed_params(
            network, speed_field, direction_field, value_forward, value_backward, value_both
        )
        if field_error:
            return {"error": field_error}

    try:
        feats = [f for f in layer.getFeatures() if not f.geometry().isEmpty()]
        if len(feats) < 2:
            return {"error": f"'{stops_layer}' needs at least 2 usable point features."}

        has_name_field = feats[0].fields().count() > 0
        names = unique_labels([f.attribute(0) if has_name_field else None for f in feats], "stop")
        geoms = [f.geometry() for f in feats]

        start_index = 0
        if start_stop_name is not None:
            if start_stop_name not in names:
                return {"error": f"start_stop_name '{start_stop_name}' not found among stops: {names}"}
            start_index = names.index(start_stop_name)

        n = len(geoms)
        network_aware = network is not None
        two_stop_route = network_aware and n == 2
        if two_stop_route:
            # rc11 smoke test C1: a two-stop route took 14 minutes because the network distance matrix ran two shortest-path
            # searches (A->B and B->A) before the route itself ran a third, ~3 minutes each on 140k roads. With two stops
            # there is nothing to order, so the matrix is skipped; the distance is read from the route afterwards.
            distance_matrix = None
        elif network_aware:
            distance_matrix = _build_network_distance_matrix(network, geoms, extra_params, source_crs=layer.crs(),
                                                             fastest=fastest, default_speed=default_speed)
        else:
            distance_area = _make_distance_area(layer)
            distance_matrix = [
                [_measure_distance(distance_area, geoms[i], geoms[j]) for j in range(n)]
                for i in range(n)
            ]

        if two_stop_route:
            tour, total_distance = [start_index, 1 - start_index], None
        else:
            tour, total_distance = _optimize_route(distance_matrix, start_index)
        ordered_names = [names[i] for i in tour]

        result = {
            "success": True,
            "stops_layer": stops_layer,
            "stop_count": n,
            "route_order": ordered_names,
            "network_aware_ordering": network_aware,
            **_closed_note(closed_segments),
        }
        if total_distance is not None:
            # With strategy='fastest' the matrix cost is HOURS, not metres (#131), so it is not a distance.
            if fastest:
                result["total_travel_time_hours"] = round(total_distance, 3)
            else:
                result["total_distance"] = round(total_distance, 2)
        if network_aware and not fastest:
            result["distance_unit"] = "meters"

        if network is None:
            warning = (
                "No road_network_layer given -- total_distance is straight-line and route_order "
                "is a stop sequence only, not a routable path. Do not render a line through these "
                "stops as a delivery route; pass road_network_layer to build one."
            )
            # QGIS-006, 2026-09-13 audit (fixed 2026-09-19): the straight-line distance_matrix
            # above now goes through _make_distance_area/_measure_distance -- real-world
            # ellipsoidal meters on a geographic CRS, unchanged planar meters on a projected
            # one. Warning only fires if ellipsoidal setup itself failed.
            try:
                if layer.crs().isGeographic():
                    if distance_area is not None:
                        warning += (
                            f" '{stops_layer}' is in a geographic CRS ({layer.crs().authid()}) -- "
                            "total_distance is real-world meters via ellipsoidal (WGS84 geodesic) "
                            "measurement, not raw planar degrees."
                        )
                    else:
                        warning += (
                            f" '{stops_layer}' is also in a geographic CRS ({layer.crs().authid()}), "
                            "but ellipsoidal distance measurement could not be set up, so "
                            "total_distance is in DEGREES, not any real distance unit -- reproject "
                            "to a projected/UTM CRS first for a meaningful figure."
                        )
            except Exception as e:
                log_event("swallowed_exception", tag="Tools", tool="logistics_route_crs_warning",
                          error_class=type(e).__name__, error=True)
            result["warning"] = warning
            return result

        route_layer_name = _build_road_snapped_route(stops_layer, network, geoms, tour, source_crs=layer.crs(),
                                                      extra_params=extra_params, fastest=fastest,
                                                      default_speed=default_speed)
        if route_layer_name is None:
            result["warning"] = (
                "Could not build a road-snapped route (stops may be too far from the network) -- "
                "falling back to stop order only. Do not render a line through these stops as a "
                "delivery route."
            )
        else:
            result["route_layer"] = route_layer_name
            result["road_snapped"] = True
            routed = _route_cost_sum(route_layer_name)
            result.update(route_strategy_summary(fastest, routed, default_speed, speed_field))
            if not fastest and total_distance is None and routed is not None:
                result["total_distance"] = round(routed, 2)
            if fastest:   # the cost is hours, so give the length separately, from the geometry
                length_m = _route_length_m(route_layer_name)
                if length_m is not None:
                    result["route_length_m"] = round(length_m, 1)

        return result
    except _bg.AnalysisCancelled:
        return _cancelled_result("delivery route")
    except Exception as e:
        return {"error": f"optimize_delivery_route failed: {e}"}


def _build_network_distance_matrix(network, geoms, extra_params=None, source_crs=None, fastest=False, default_speed=50):
    """Real road-network point-to-point distance between every ordered pair
    of stops, via native:shortestpathpointtopoint's own 'cost' output
    field -- confirmed live this is the robust way to get this, not
    travel_time_matrix: calling that tool with the stops layer as both
    origins and destinations DOES work (same layer object twice is fine),
    but its destination-side matrix keys come from an internal
    coordinate-string field on shortestpathpointtolayer's output, not any
    of the stop layer's own attributes -- confirmed live they don't match
    the origin-side keys' naming at all, so there's no reliable way to map
    a destination key back to a specific stop by name. Point-to-point's
    'cost' field has no such ambiguity: each call names its one exact
    start/end pair, so indices line up by construction.

    O(n^2) processing.run() calls for n stops -- optimize_delivery_route's
    own tool description already frames this as suited to a route-sized
    stop list ("not a substitute for a full commercial VRP solver"), not
    hundreds of stops, so this is an acceptable cost for the gap it closes
    (real road distance driving the visiting ORDER, not just the final
    drawn line).

    BUG-2026-09-25-2 follow-up: STRATEGY is fixed at 0 (shortest, not
    time-based) for every call here, so the only thing that can make
    matrix[i][j] != matrix[j][i] on the SAME road network is one-way
    restrictions -- DIRECTION_FIELD. Without one, the network is
    undirected for this call's purposes and a route is reversible, so
    the (j, i) call is skipped and its cost copied from the (i, j) result
    already computed -- exactly halving the call count (and the graph
    rebuilds that dominate its cost, see _run_network_algorithm's
    docstring) for the common case of a plain road layer with no
    one-way data. With a direction_field this optimization is unsafe (a
    one-way street can make A->B and B->A genuinely different routes) and
    is skipped, keeping the original O(n^2) behavior unchanged.

    Unreachable/failed pairs get float('inf') so _optimize_route naturally
    routes around them (nearest-neighbor never picks an infinite-cost hop
    while a finite one is available) instead of crashing on a missing
    matrix entry."""
    n = len(geoms)
    matrix = [[0.0] * n for _ in range(n)]
    context = _network_context()
    undirected = not (extra_params and extra_params.get("DIRECTION_FIELD"))
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if undirected and j < i:
                matrix[i][j] = matrix[j][i]
                continue
            start = geoms[i].asPoint()
            end = geoms[j].asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": 1 if fastest else 0,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "OUTPUT": "memory:",
            }
            if extra_params:
                params.update(extra_params)
            try:
                params["START_POINT"] = _point_for_network(start, source_crs, network)
                params["END_POINT"] = _point_for_network(end, source_crs, network)
                output = _run_network_algorithm("native:shortestpathpointtopoint", params, context, network,
                                                "Delivery route")
                result_layer = output.get("OUTPUT")
                feats = list(result_layer.getFeatures()) if result_layer is not None else []
                cost = feats[0]["cost"] if feats else None
                matrix[i][j] = float(cost) if cost is not None else float("inf")
            except _bg.AnalysisCancelled:
                raise
            except Exception:
                matrix[i][j] = float("inf")
    return matrix


def route_strategy_summary(fastest, routed_cost, default_speed, speed_field):
    """The strategy fields of an optimize_delivery_route result. Pure.

    rc11 smoke test C1/#131: "fastest route" returned a shortest-distance route that the reply called fastest. Now the
    tool offers both and says which one it ran. A travel time is an ESTIMATE from per-segment speeds (or the default), never
    measured traffic, and the note says so; `routed_cost` is metres for 'shortest' and hours for 'fastest'."""
    if not fastest:
        return {"route_strategy": "shortest distance",
                "route_note": ("This is the shortest-distance road route, not a fastest-time route. Report it as 'shortest "
                               "route' and do not call it 'fastest' or give a travel time. Call again with "
                               "strategy='fastest' for a travel-time route.")}
    basis = (f"the '{speed_field}' field (km/h) where it has a value, otherwise {default_speed:g} km/h" if speed_field
             else f"a flat {default_speed:g} km/h on every road")
    out = {"route_strategy": "fastest travel time (estimated)",
           "route_note": (f"Fastest route by estimated travel time, using {basis}. It is a model estimate, not measured "
                          "traffic: say 'about' and give the speed basis when reporting the time.")}
    if routed_cost is not None:
        out["total_travel_time_hours"] = round(routed_cost, 3)
        out["total_travel_time_minutes"] = round(routed_cost * 60, 1)
    return out


def _route_length_m(route_layer_name):
    """Ellipsoidal length in metres of the route layer just added (the 'cost' field is hours for a fastest route), or None.
    Never raises."""
    try:
        layers = QgsProject.instance().mapLayersByName(route_layer_name)
        if not layers:
            return None
        area = _make_distance_area(layers[0])
        total = 0.0
        for f in layers[0].getFeatures():
            g = f.geometry()
            if g is not None and not g.isEmpty():
                total += area.measureLength(g) if area is not None else g.length()
        return total if total > 0 else None
    except Exception:
        return None


def _route_cost_sum(route_layer_name):
    """Sum of the 'cost' field (metres for the shortest-path strategy, hours for fastest) of the route layer just added, or None. Never raises."""
    try:
        layers = QgsProject.instance().mapLayersByName(route_layer_name)
        if not layers or layers[0].fields().indexOf("cost") < 0:
            return None
        total = sum(float(f["cost"]) for f in layers[0].getFeatures() if f["cost"] is not None)
        return total if total > 0 else None
    except Exception:
        return None


def _build_road_snapped_route(stops_layer_name, network, geoms, tour, source_crs=None, extra_params=None,
                               fastest=False, default_speed=50):
    """Chain native:shortestpathpointtopoint across each consecutive pair in
    visiting order and merge the segments into one line layer added to the
    project, so optimize_delivery_route's output is an actual road-snapped
    route rather than a straight line between stops (closes the gap flagged
    in docs/HUMANITARIAN_CARTOGRAPHY_STANDARDS.md Section IV -- see
    docs/BUG_TRACKER.md). Same unverified-live caveat as this module's other
    native-network-analysis calls (see module docstring). Returns the new
    layer's name, or None if no segment could be built."""
    segment_layers = []
    context = _network_context()
    for i in range(len(tour) - 1):
        start = geoms[tour[i]].asPoint()
        end = geoms[tour[i + 1]].asPoint()
        params = {
            "INPUT": network,
            "STRATEGY": 1 if fastest else 0,
            "DEFAULT_SPEED": default_speed,
            "TOLERANCE": 0,
            "OUTPUT": "memory:",
        }
        if extra_params:
            # The distance matrix always honoured the direction/speed fields but the route itself did not, so a route could
            # run the wrong way along a one-way street (found while reading this code for rc11 smoke test C1). The
            # strategy is 'shortest' (0) unless the caller asked for 'fastest' (1, #131).
            params.update(extra_params)
        try:
            params["START_POINT"] = _point_for_network(start, source_crs, network)
            params["END_POINT"] = _point_for_network(end, source_crs, network)
            output = _run_network_algorithm("native:shortestpathpointtopoint", params, context, network,
                                            "Delivery route")
        except _bg.AnalysisCancelled:
            raise
        except Exception:
            continue
        segment = output.get("OUTPUT")
        if segment is not None and segment.featureCount() > 0:
            segment_layers.append(segment)

    if not segment_layers:
        return None

    route_name = f"{stops_layer_name}_road_route"
    if len(segment_layers) == 1:
        route_layer = segment_layers[0]
    else:
        merged = processing.run(
            "native:mergevectorlayers", {"LAYERS": segment_layers, "OUTPUT": "memory:"}
        )
        route_layer = merged.get("OUTPUT")
        if route_layer is None:
            return None

    route_layer.setName(route_name)
    QgsProject.instance().addMapLayer(route_layer)
    # Map Intelligence Engine: standard road-casing line symbology (BUG-2026-09-27-3) --
    # this call was previously missing entirely, so the route layer got QGIS's raw default
    # new-layer symbology every time, same gap buffer_analysis's own process_map_output
    # call (vector_tools.py) already closed for polygon outputs.
    try:
        from ..map_intelligence import process_map_output
        process_map_output(route_layer, output_role="route_line")
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="optimize_delivery_route_styling",
                  error_class=type(e).__name__, error=True)
    return route_name


def _geom_usable(geom):
    """True if geom is a real, non-empty QgsGeometry -- shared by every
    None/isEmpty check in _degenerate_hull_fallback below."""
    return geom is not None and not geom.isEmpty()


def _degenerate_hull_fallback(lines_layer, travel_cost):
    """BUG-2026-09-05-2 root cause (isolated 2026-09-10, reasoned from QGIS's own
    documented Processing/GEOS behaviour -- no live QGIS available in this session
    to additionally confirm live): native:convexhull's OUTPUT sink is declared as a
    fixed Polygon geometry type regardless of what the input actually produces. The
    convex hull of a set of collinear points (a straight 1-segment road, or a
    reachable-network that happens to reduce to one straight line) is geometrically
    a line, not an area -- QgsGeometry.convexHull() correctly returns that as a
    LineString (or a Point, for a single coincident point), and the algorithm's own
    Polygon-typed sink then refuses to write it, which is exactly the recorded
    "Could not add feature with geometry type LineString to layer of type Polygon"
    error. native:convexhull has no parameter to accept a non-Polygon result, so
    this is not fixable by changing our call's parameters -- it has to be computed
    ourselves instead of delegating to that algorithm.

    Recomputes the hull directly via QgsGeometry.unaryUnion()/.convexHull() on the
    same input features. If that result is already a polygon (should not normally
    happen here, since native:convexhull would have succeeded in that case, but
    handled defensively), it is used as-is. If it is degenerate (a line or a
    point), it is buffered by a small fraction of the travel cost so the caller
    gets a thin but valid, well-formed polygon representing that degenerate
    service area instead of no hull at all. Returns None (never raises) if the
    input has no usable geometry or the hull computation itself fails -- callers
    should treat that exactly as the pre-fix behaviour: an unrecoverable skip for
    the convexhull stage.
    """
    try:
        geoms = [g for g in (f.geometry() for f in lines_layer.getFeatures()) if _geom_usable(g)]
        if not geoms:
            return None
        combined = QgsGeometry.unaryUnion(geoms)
        if not _geom_usable(combined):
            return None
        hull = combined.convexHull()
        if not _geom_usable(hull):
            return None
        if hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
            # Degenerate hull (collinear points): buffer it into a thin polygon
            # rather than fabricating an arbitrary area shape. The buffer distance
            # is a small fraction of travel_cost so it stays visually negligible
            # relative to the service area's own scale, in the same CRS units as
            # the network layer.
            hull = hull.buffer(max(travel_cost * 0.001, 0.01), 8)
            if not _geom_usable(hull) or hull.type() != QgsWkbTypes.GeometryType.PolygonGeometry:
                return None
        layer = QgsVectorLayer(f"Polygon?crs={lines_layer.crs().authid()}", "service_area_hull", "memory")
        provider = layer.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(hull)
        provider.addFeatures([feat])
        layer.updateExtents()
        return layer
    except Exception:
        return None


@register_tool(
    "calculate_service_area",
    "Calculate the reachable road-network area around one or more facilities (warehouse, clinic, "
    "distribution point) within a given travel distance or time -- e.g. 'what area can this "
    "warehouse serve within 30km by road'. Produces, per facility, both the reachable road network "
    "and an approximate coverage polygon (convex hull around it). Requires a real line layer "
    "representing the road network -- for simple straight-line/as-the-crow-flies coverage, use "
    "buffer_analysis instead. Without speed_field, every road segment is treated as one flat "
    "default_speed regardless of surface or condition, which overstates reachability on unpaved/"
    "damaged roads -- when the network layer has a per-segment speed or condition field (e.g. from "
    "OSM highway/surface tags), pass it as speed_field with strategy='fastest' for a more realistic "
    "area. direction_field makes one-way roads one-way instead of assuming every segment is "
    "traversable both directions. Pass travel_cost as a LIST (e.g. [15, 30, 60]) instead of a "
    "single number for a real isochrone/access-band map: builds one combined polygon layer per "
    "facility with a travel_cost_band field, one ring per value, auto-styled with a graduated "
    "renderer -- a single call instead of one per band plus manual styling.",
    {
        "type": "object",
        "properties": {
            "facility_layer": {"type": "string", "description": "Point layer with the facility/facilities to calculate service areas for."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "travel_cost": {
                "description": "Maximum travel distance in METRES (real-world, measured on the ellipsoid whatever the "
                "layers' CRS is) or time in HOURS if strategy='fastest'. Pass a single number for one service area, or a list of ascending "
                "values (e.g. [15, 30, 60]) for a multi-band isochrone/access map -- one combined, "
                "auto-styled polygon layer per facility instead of separate calls.",
                "anyOf": [
                    {"type": "number"},
                    {"type": "array", "items": {"type": "number"}},
                ],
            },
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h (e.g. derived from OSM highway/surface tags). Only affects routing when strategy='fastest'."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways."},
            "style_by_cost": {"type": "boolean", "description": "Default true: also add a road layer graded by travel cost (near = dark, far = warm, labelled bands) and hide the plain reached-roads line layer, which stays in the project for analysis. Set false to keep only the plain lines."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
        },
        "required": ["facility_layer", "road_network_layer", "travel_cost"],
    },
)
def calculate_service_area(facility_layer, road_network_layer, travel_cost, strategy="shortest", default_speed=50,
                            speed_field=None, direction_field=None,
                            value_forward="yes", value_backward="-1", value_both="no", style_by_cost=True):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    # v1.8.0 workstream 4: travel_cost as a list builds a real isochrone/
    # access-band map (one combined, auto-styled polygon layer per facility)
    # instead of requiring N separate calls plus manual styling. The
    # single-value path below is otherwise completely unchanged from its
    # already-live-verified behavior -- multi_band only ever adds new
    # branches, it never alters what a scalar travel_cost does.
    is_multi_band = isinstance(travel_cost, (list, tuple))
    if is_multi_band:
        if not travel_cost:
            return {"error": "travel_cost list must contain at least one value."}
        travel_costs = sorted(float(v) for v in travel_cost)
        if travel_costs[0] <= 0:
            return {"error": "travel_cost must be positive."}
    else:
        if travel_cost <= 0:
            return {"error": "travel_cost must be positive."}
        travel_costs = [travel_cost]
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}

    network = _find_layer_by_name(road_network_layer)
    facilities = _find_layer_by_name(facility_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    if facilities is None:
        return {"error": f"Layer '{facility_layer}' not found"}
    geometry_error = _network_geometry_error(network, road_network_layer)
    if geometry_error:
        return {"error": geometry_error}
    network, closed_segments, closed_error = _open_network(network, speed_field, road_network_layer)
    if closed_error:
        return {"error": closed_error}

    extra_params, field_error = _network_direction_speed_params(
        network, speed_field, direction_field, value_forward, value_backward, value_both
    )
    if field_error:
        return {"error": field_error}

    notes = []
    if speed_field:
        vetted, speed_note = _vet_speed_field(network, speed_field, default_speed)
        if speed_note:
            notes.append(speed_note)
            extra_params.pop("SPEED_FIELD", None)
            speed_field = vetted
    unit_note = _travel_cost_unit_note(strategy, travel_costs)
    if unit_note:
        notes.append(unit_note)

    try:
        strategy_val = 1 if strategy == "fastest" else 0
        layers_created = []
        styled_layers = []
        served_count = 0
        skipped = []
        # #130 point 3: what these result layers are built with; a later run that replaces one by name compares against it.
        run_params = {"tool": "calculate_service_area", "road_network_layer": road_network_layer, "strategy": strategy, "travel_cost": travel_costs,
                      "speed_field": speed_field, "direction_field": direction_field, "default_speed": default_speed}
        replaced_results = []

        def _put(name, layer, **kw):
            r = _replace_named_layer(name, layer, params=run_params, **kw)
            if r:
                replaced_results.append(r)
        # BUG-2026-09-05-2 fix (2026-09-08): both processing.run() calls below used to
        # sit inside one try/except that spans the whole facility loop, so a single
        # facility hitting the known small/degenerate-network edge case (a collinear
        # 1-segment network's convex hull degenerating to a LineString that a Polygon-
        # typed sink then refuses, or a 2-segment L-shaped network making
        # native:serviceareafrompoint itself raise on invalid intermediate geometry)
        # aborted the ENTIRE multi-facility request, discarding results already computed
        # for every other facility. Each stage is now isolated per facility: a failure is
        # recorded and that facility is skipped (or, if only the hull step fails, its
        # already-built reachable-network lines are still kept), so the rest of the batch
        # still comes back.
        #
        # BUG-2026-09-05-2 further fix (2026-09-10): the two failure shapes themselves
        # are now addressed, not just isolated. (1) serviceareafrompoint's own
        # "invalid geometry" abort: pass a QgsProcessingContext with
        # GeometrySkipInvalid so the algorithm skips an invalid input feature
        # internally, exactly the remedy its own error message names ("change the
        # 'Invalid features filtering' option") -- reasoned from QGIS's documented
        # Processing API, not independently re-run against live QGIS this session
        # (no live/headless QGIS available in this environment -- see docs/BUG_TRACKER.md).
        # Built once here (same setting for every facility in the batch, not per-facility
        # state) rather than reconstructed inside the loop below. The real enum lives on
        # Qgis.InvalidGeometryCheck (QgsProcessingContext.setInvalidGeometryCheck's own
        # signature is `check: Qgis.InvalidGeometryCheck`, confirmed live against QGIS
        # 4.2.2 -- not QgsProcessing, which has no such nested enum at all on that
        # install) -- resolved via resolve_qgis_enum rather than hard-coded, matching
        # this file's own QgsWkbTypes.GeometryType.* precedent for enums that moved
        # between QGIS majors.
        # (2) the convexhull LineString/Polygon-sink failure: see
        # _degenerate_hull_fallback's own docstring for the isolated root cause and fix,
        # which *is* provable without live QGIS since it follows from convex-hull
        # geometry (collinear points) rather than from QGIS-specific runtime behaviour.
        # QGIS-005, 2026-09-14 audit: was passed straight to setInvalidGeometryCheck() with no
        # explicit None check -- only "safe" by whatever this function's own outer exception
        # handling happens to do with the resulting error, not by design (QGIS-004's identical
        # class of gap). Today inert (this enum resolves fine on both QGIS 3.x/4.x).
        _max_speed = _max_speed_in_field(network, speed_field) if (strategy == "fastest" and speed_field) else None
        # With a speed field whose maximum can't be read, the reach isn't a safe upper bound: no clipping.
        reach_m = None if (strategy == "fastest" and speed_field and _max_speed is None) else \
            _reach_metres(travel_costs, strategy, default_speed, _max_speed)
        clip_summary = {"facilities_clipped": 0, "roads_full": None, "roads_routed_max": 0}
        _invalid_geom_check = resolve_qgis_enum(Qgis, "InvalidGeometryCheck", "GeometrySkipInvalid")
        if _invalid_geom_check is None:
            return {"error": "Could not resolve QgsProcessing's InvalidGeometryCheck enum in this QGIS version."}
        context = _network_context(_invalid_geom_check)
        for i, feat in enumerate(facilities.getFeatures()):
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            point = geom.asPoint()
            try:
                start_point = _point_for_network(point, facilities.crs(), network)
                routed_network, clip = network, {"applied": False}
                if reach_m is not None:
                    routed_network, clip = _clip_network_to_reach(
                        network, _point_xy_in_network_crs(point, facilities.crs(), network), reach_m)
            except Exception as e:
                skipped.append({"facility_index": i, "stage": "coordinate_transform", "reason": str(e)})
                continue
            if clip.get("applied"):
                clip_summary["facilities_clipped"] += 1
                clip_summary["roads_full"] = clip["roads_full"]
                clip_summary["roads_routed_max"] = max(clip_summary["roads_routed_max"], clip["roads_used"])

            band_hulls = []  # (band_value, hull_layer) -- only populated/used when is_multi_band
            facility_served = False
            for band in travel_costs:
                params = {
                    "INPUT": routed_network,
                    "STRATEGY": strategy_val,
                    "DEFAULT_SPEED": default_speed,
                    "TOLERANCE": 0,
                    "START_POINT": start_point,
                    "TRAVEL_COST2": band,
                    "OUTPUT_LINES": "memory:",
                }
                params.update(extra_params)
                try:
                    output = _run_network_algorithm("native:serviceareafrompoint", params, context, routed_network,
                                                    "Service area")
                except _bg.AnalysisCancelled:
                    raise
                except Exception as e:
                    skipped.append({"facility_index": i, "travel_cost": band, "stage": "serviceareafrompoint", "reason": str(e)})
                    continue
                lines_layer = output.get("OUTPUT_LINES")
                if lines_layer is None or lines_layer.featureCount() == 0:
                    continue
                if _reachable_network_is_degenerate(lines_layer):
                    # Never replace an existing good layer with an empty result (rc7 smoke test F05):
                    # _replace_named_layer below removes the previous layer of the same name first.
                    skipped.append({
                        "facility_index": i, "travel_cost": band, "stage": "serviceareafrompoint",
                        "reason": "the reachable network has zero length: the start point snapped to a "
                                  "road but nothing is reachable within travel_cost. Check travel_cost's "
                                  "unit (metres for 'shortest', hours for 'fastest') and the speed_field. "
                                  "The existing layers were left untouched.",
                    })
                    continue

                lines_name = (
                    f"{facility_layer}_service_area_lines_{i}" if not is_multi_band
                    else f"{facility_layer}_service_area_lines_{i}_band_{band:g}"
                )
                _put(lines_name, lines_layer)
                layers_created.append(lines_name)
                try:
                    from ..map_intelligence import process_map_output
                    process_map_output(lines_layer, output_role="route_line")
                except Exception as style_e:
                    log_event("swallowed_exception", tag="Tools", tool="calculate_service_area_styling",
                              error_class=type(style_e).__name__, error=True)
                # Matches the original single-band semantics exactly: a
                # facility/band counts as "served" once its lines layer is
                # built, regardless of whether hull-building below succeeds
                # -- the hull is a bonus output, not the served/skipped
                # criterion.
                facility_served = True

                hull_layer = None
                try:
                    hull = processing.run("native:convexhull", {"INPUT": lines_layer, "OUTPUT": "memory:"})
                    hull_layer = hull.get("OUTPUT")
                except Exception as e:
                    # Match native:convexhull's Polygon-typed-sink rejection on its own
                    # constant wording ("...to layer of type Polygon") rather than the
                    # source geometry type name -- live-confirmed against real QGIS 4.2.2
                    # that this rejection's source-type name varies by exactly how the
                    # reachable network degenerates (LineString for a collinear road,
                    # GeometryCollection for other degenerate shapes; _degenerate_hull_fallback's
                    # own docstring further documents a single-Point case) -- an earlier
                    # version of this guard matched only "LineString"/"Point" and missed the
                    # GeometryCollection variant found live.
                    if "to layer of type Polygon" in str(e):
                        hull_layer = _degenerate_hull_fallback(lines_layer, band)
                    if hull_layer is None:
                        skipped.append({"facility_index": i, "travel_cost": band, "stage": "convexhull", "reason": str(e)})

                if hull_layer is not None:
                    if is_multi_band:
                        band_hulls.append((band, hull_layer))
                    else:
                        hull_name = f"{facility_layer}_service_area_{i}"
                        _put(hull_name, hull_layer)
                        layers_created.append(hull_name)
                        # Live-reported, 2026-09-28: this single-band hull polygon (the
                        # common case -- one travel_cost value, not a list) was left at
                        # QGIS's raw default new-layer symbology every time -- unlike the
                        # multi-band path just below, which already gets
                        # apply_graduated_style, and unlike buffer_analysis's polygon
                        # output, which already gets this exact call. Same gap class as
                        # BUG-2026-09-27-3 (route line casing), just for this tool's
                        # polygon output instead of its line output.
                        try:
                            from ..map_intelligence import process_map_output
                            process_map_output(
                                hull_layer, output_role="proximity_buffer",
                                source_layer_id=facilities.id() if hasattr(facilities, "id") else None,
                            )
                        except Exception as style_e:
                            log_event("swallowed_exception", tag="Tools", tool="calculate_service_area_hull_styling",
                                      error_class=type(style_e).__name__, error=True)

            if facility_served and style_by_cost:
                graded_name = f"{facility_layer}_roads_by_cost_{i}"
                try:
                    from . import routing_style
                    max_cost = max(travel_costs)
                    graded, graded_reason = _cost_graded_roads(
                        routed_network, _point_xy_in_network_crs(point, facilities.crs(), network), strategy,
                        default_speed, extra_params.get("SPEED_FIELD"), extra_params.get("DIRECTION_FIELD"),
                        value_forward, value_backward, value_both, context.ellipsoid(), max_cost, graded_name)
                    if graded is None:
                        notes.append(f"Roads were not graded by travel cost for facility {i}: {graded_reason}.")
                    else:
                        _put(graded_name, graded)
                        unit = "hours" if strategy == "fastest" else "meters"
                        routing_style.style_lines_by_cost(
                            graded, "travel_cost", routing_style.cost_band_edges(max_cost), unit)
                        styled_layers.append(graded_name)
                        _hide_layers([n for n in layers_created
                                      if n == f"{facility_layer}_service_area_lines_{i}"
                                      or n.startswith(f"{facility_layer}_service_area_lines_{i}_band_")])
                except _bg.AnalysisCancelled:
                    raise
                except Exception as grade_e:
                    notes.append(f"Roads were not graded by travel cost for facility {i} ({type(grade_e).__name__}: {grade_e}); "
                                 "the plain reached-roads layer is shown instead.")

            if is_multi_band and band_hulls:
                merged_name = f"{facility_layer}_service_area_bands_{i}"
                merged_layer = _merge_band_hulls(band_hulls, merged_name)
                if merged_layer is not None:
                    _put(merged_name, merged_layer)
                    layers_created.append(merged_name)
                    from .styling_tools import apply_graduated_style
                    apply_graduated_style(merged_name, "travel_cost_band")

            if facility_served:
                served_count += 1

        if served_count == 0:
            failure = {"error": "Could not build a service area for any facility -- check the facility points are near the road network."}
            if skipped:
                failure["error"] += " Details: " + "; ".join(str(x.get("reason")) for x in skipped[:3])
                failure["skipped"] = skipped
            if notes:
                failure["notes"] = notes
            return failure

        result = {
            "success": True,
            "facility_count": served_count,
            "travel_cost": travel_costs if is_multi_band else travel_costs[0],
            "strategy": strategy,
            "travel_cost_unit": "hours" if strategy == "fastest" else "meters",
            "layers_created": layers_created,
        }
        if styled_layers:
            result["styled_layers"] = styled_layers
            result["styling_note"] = (
                "Roads are drawn in travel-cost bands (dark = near the origin, warm = far); the plain reached-roads line layers "
                "are hidden but kept for analysis.")
        if clip_summary["facilities_clipped"]:
            # Exact, not an approximation (see _clip_network_to_reach): worth saying so the model
            # doesn't describe the analysis as "limited to nearby roads".
            result["network_clipping"] = {
                **clip_summary,
                "note": "Only roads that can be reached within the requested cost were routed; the result "
                        "is identical to routing over the whole network, just faster.",
            }
        if replaced_results:
            result["replaced_results"] = replaced_results
            extra = len(replaced_results) - 1
            result["replace_note"] = ("Tell the user: " + replaced_results[0]["note"]
                                      + (f" {extra} related result layer(s) of the same run were replaced the same way." if extra else ""))
        if speed_field:
            result["speed_field"] = speed_field
        result.update(_closed_note(closed_segments))
        if direction_field:
            result["direction_field"] = direction_field
        # rc7 smoke test F06: the result layers are memory (scratch) layers; the reply used to speak
        # of them as saved analysis output. State the truth so the model relays it.
        result["hull_note"] = (
            "The '..._service_area_N' polygons are CONVEX HULLS of the reached roads -- a display outline and an "
            "UPPER BOUND on reach (they include land between the roads). Do not sum population inside them as "
            "'people reached'; use population_access_gap (road-buffer reach) for that."
        )
        result["storage_note"] = (
            "The layers created here are temporary (in-memory) layers: they are NOT saved to disk and "
            "are lost when QGIS closes unless exported (export_layer) or saved into a GeoPackage."
        )
        if notes:
            result["notes"] = notes
        if skipped:
            result["warnings"] = (
                f"{len(skipped)} facility/band combination(s) could not be fully processed -- see "
                "'skipped' for detail. Known limitation on very small/degenerate road networks "
                "(BUG-2026-09-05-2); real road datasets are very unlikely to hit this."
            )
            result["skipped"] = skipped
        return result
    except _bg.AnalysisCancelled:
        return _cancelled_result("service area")
    except Exception as e:
        return {"error": f"calculate_service_area failed: {e}"}


def _merge_band_hulls(band_hulls, output_name):
    """Combines one facility's per-band hull polygon layers into ONE memory
    layer with a travel_cost_band field -- a legible single isochrone/
    access-band layer instead of N separately-named, separately-styled
    layers. Not a processing.run() merge (native:mergevectorlayers): these
    hull layers start with no fields at all, so building the combined layer
    directly, feature by feature, is simpler than reconciling schemas
    through an extra Processing call for what's a small number of features
    (one per band, typically 2-5). Returns None if no band produced any
    usable hull geometry (caller then adds nothing to the project for this
    facility, matching the existing single-band "hull_layer is None" case)."""
    if not band_hulls:
        return None
    crs = band_hulls[0][1].crs()
    merged = QgsVectorLayer(f"Polygon?crs={crs.authid()}", output_name, "memory")
    merged.dataProvider().addAttributes([QgsField("travel_cost_band", QVariant.Double)])
    merged.updateFields()
    feats = []
    for band, hull_layer in band_hulls:
        for hull_feat in hull_layer.getFeatures():
            geom = hull_feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            new_feat = QgsFeature(merged.fields())
            new_feat.setGeometry(geom)
            new_feat.setAttribute("travel_cost_band", band)
            feats.append(new_feat)
    if not feats:
        return None
    merged.dataProvider().addFeatures(feats)
    merged.updateExtents()
    return merged


# ---- many-destination travel costs from ONE shortest-path tree (F08) -------------------------------------------
#
# native:shortestpathpointtolayer ties every destination into the road graph (QgsVectorLayerDirector.makeGraph compares each
# road segment with each tied point: segments x destinations, source-read, not profiled) and then runs ONE Dijkstra per origin.
# For many destinations the same costs come from tying only the ORIGIN into the graph, running that one Dijkstra
# (QgsGraphAnalyzer.dijkstra returns the incoming-edge tree and the cost to every vertex) and reading each destination's cost
# from its nearest graph vertex. Edges are the segments between consecutive road vertices, so a destination is placed
# at most half a segment from where the native algorithm would tie it; the leg from the destination to the road is reported,
# not added (same convention as classify_facilities_by_access). API as in the PyQGIS developer cookbook, "Network analysis library".
UNREACHABLE_COST = 1.0e300           # QgsGraphAnalyzer.dijkstra marks an unreachable vertex with DOUBLE_MAX (~1.8e308)
_KMH_TO_MS = 1000.0 / 3600.0


def single_tree_costs_available():
    """True when the graph classes this path needs are importable (QGIS only)."""
    if not QGIS_AVAILABLE:
        return False
    try:
        from qgis.analysis import (QgsGraphAnalyzer, QgsGraphBuilder, QgsNetworkDistanceStrategy,  # noqa: F401
                                   QgsNetworkSpeedStrategy, QgsVectorLayerDirector)
        return True
    except ImportError:
        return False


def _director_both_directions(director_cls):
    value = resolve_qgis_enum(director_cls, "Direction", "Both")
    return value if value is not None else getattr(director_cls, "DirectionBoth", 2)


def _build_cost_tree(network, origin_xy, strategy, default_speed, speed_field, direction_field,
                     value_forward, value_backward, value_both, ellipsoid):
    """(graph, costs, to_output, start_vertex): the road graph with ONLY the origin tied in, and the cost from the origin
    to every vertex (QgsGraphAnalyzer.dijkstra). `to_output` converts a cost to the reported unit (metres, or hours for
    strategy='fastest'). Raises RuntimeError with a reason when the origin cannot be tied into the graph."""
    from qgis.analysis import (QgsGraphAnalyzer, QgsGraphBuilder, QgsNetworkDistanceStrategy,
                               QgsNetworkSpeedStrategy, QgsVectorLayerDirector)
    direction_idx = network.fields().indexOf(direction_field) if direction_field else -1
    director = QgsVectorLayerDirector(
        network, direction_idx, value_forward if direction_field else "", value_backward if direction_field else "",
        value_both if direction_field else "", _director_both_directions(QgsVectorLayerDirector))
    if strategy == "fastest":
        speed_idx = network.fields().indexOf(speed_field) if speed_field else -1
        director.addStrategy(QgsNetworkSpeedStrategy(speed_idx, float(default_speed), _KMH_TO_MS))
        to_output = 1.0 / 3600.0               # the strategy's cost is seconds; the matrix reports hours, like the native tool
    else:
        director.addStrategy(QgsNetworkDistanceStrategy())
        to_output = 1.0
    builder = QgsGraphBuilder(network.crs(), True, 0.0, ellipsoid)
    tied = director.makeGraph(builder, [QgsPointXY(origin_xy)])
    graph = builder.graph()
    if not tied or tied[0] is None:
        raise RuntimeError("the origin could not be tied into the road network")
    start = graph.findVertex(tied[0])
    if start < 0:
        raise RuntimeError("the origin's snapped point is not a vertex of the road graph")
    _tree, costs = QgsGraphAnalyzer.dijkstra(graph, start, 0)
    return graph, costs, to_output, start


def project_on_segment(px, py, ax, ay, bx, by):
    """(t, distance): where the point (px, py) projects onto the segment A->B, as a fraction t in [0, 1] of the way from A to B,
    and how far the point is from that projected spot (in the coordinates' own units). Pure. A zero-length segment gives t = 0."""
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    qx, qy = ax + t * dx, ay + t * dy
    return t, ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def partial_edge_cost(cost_a, cost_b, edge_ab, edge_ba, t, unreachable=UNREACHABLE_COST):
    """Cost from the origin to a point a fraction `t` of the way along the edge A->B, or None when it cannot be reached.

    `cost_a` / `cost_b` are the tree costs to the two ends, `edge_ab` / `edge_ba` the full-edge costs in each direction (None
    when that direction does not exist, e.g. a one-way road). Enter at A and run forward, or enter at B and run back; the
    cheaper allowed way wins. Cost is proportional to distance along an edge for both strategies (one speed per feature).
    Audit F16 (#152): the single-tree matrix used the cost of the nearest VERTEX, so on a 1,000 m road points at 490 m and 510 m
    came back as 0 and 1,000 m instead of about 490 and 510. Pure."""
    options = []
    if edge_ab is not None and cost_a is not None and cost_a < unreachable:
        options.append(cost_a + t * edge_ab)
    if edge_ba is not None and cost_b is not None and cost_b < unreachable:
        options.append(cost_b + (1.0 - t) * edge_ba)
    return min(options) if options else None


def _single_tree_costs(network, origin_xy, dest_xys, strategy, default_speed, speed_field, direction_field,
                       value_forward, value_backward, value_both, ellipsoid):
    """Cost from origin_xy to each point in dest_xys, in the network's CRS, from one Dijkstra tree.

    Each destination is projected onto its nearest road edge and charged the cost to that spot (partial edge, direction
    aware: see partial_edge_cost), which is what QGIS's own point-to-layer tool does; before, it took the cost of the nearest
    graph vertex, wrong by up to a whole edge. The short leg from the destination to the road is still not added.

    Returns a list aligned with dest_xys: a cost (metres, or hours for strategy='fastest') or None when the destination cannot
    be reached. Raises RuntimeError with a reason when the origin cannot be tied into the graph."""
    graph, costs, to_output, _start = _build_cost_tree(
        network, origin_xy, strategy, default_speed, speed_field, direction_field,
        value_forward, value_backward, value_both, ellipsoid)
    # One entry per undirected vertex pair; the two directed edge costs are kept apart so one-way roads stay one-way.
    directed = {}
    for i in range(graph.edgeCount()):
        edge = graph.edge(i)
        key = (edge.fromVertex(), edge.toVertex())
        cost = edge.cost(0)
        if key not in directed or cost < directed[key]:
            directed[key] = cost
    pairs, index = [], QgsSpatialIndex()
    for a, b in {(min(k), max(k)) for k in directed if k[0] != k[1]}:
        pa, pb = graph.vertex(a).point(), graph.vertex(b).point()
        feat = QgsFeature(len(pairs))
        feat.setGeometry(QgsGeometry.fromPolylineXY([pa, pb]))
        index.addFeature(feat)
        pairs.append((a, b, pa, pb))
    out = []
    for xy in dest_xys:
        point = QgsPointXY(xy)
        best = None
        # The index ranks by bounding box, which can put a nearer edge behind a few nearer boxes: take several, measure exactly.
        for pid in index.nearestNeighbor(point, 8):
            a, b, pa, pb = pairs[pid]
            t, dist = project_on_segment(point.x(), point.y(), pa.x(), pa.y(), pb.x(), pb.y())
            if best is None or dist < best[0]:
                best = (dist, a, b, t)
        if best is None:
            out.append(None)
            continue
        _dist, a, b, t = best
        cost = partial_edge_cost(costs[a], costs[b], directed.get((a, b)), directed.get((b, a)), t)
        out.append(None if cost is None else cost * to_output)
    return out


def _cost_graded_roads(network, origin_xy, strategy, default_speed, speed_field, direction_field,
                       value_forward, value_backward, value_both, ellipsoid, max_cost, name):
    """A line layer of the roads reached within max_cost, each carrying the travel cost at its far end ('travel_cost',
    metres or hours like the tool's own unit), for grading by cost. Built from the same one-origin shortest-path tree as
    travel_time_matrix. An edge is kept when its near end is within max_cost, so the outermost road may run a little past
    the limit (a whole segment, not a cut one); the native service-area lines stay the exact result. Returns
    (layer or None, reason)."""
    graph, costs, to_output, _start = _build_cost_tree(
        network, origin_xy, strategy, default_speed, speed_field, direction_field,
        value_forward, value_backward, value_both, ellipsoid)
    layer = QgsVectorLayer(f"LineString?crs={network.crs().authid()}", name, "memory")
    layer.dataProvider().addAttributes([QgsField("travel_cost", QVariant.Double)])
    layer.updateFields()
    seen = {}
    for i in range(graph.edgeCount()):
        edge = graph.edge(i)
        a, b = edge.fromVertex(), edge.toVertex()
        cost_a, cost_b = costs[a], costs[b]
        if cost_a >= UNREACHABLE_COST:
            continue
        near = cost_a * to_output
        if near > max_cost:
            continue
        far = (cost_b * to_output) if cost_b < UNREACHABLE_COST else near
        key = (a, b) if a < b else (b, a)
        if key in seen and seen[key][0] <= far:
            continue
        seen[key] = (far, a, b)
    feats = []
    for far, a, b in seen.values():
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([graph.vertex(a).point(), graph.vertex(b).point()]))
        feat.setAttribute("travel_cost", float(far))
        feats.append(feat)
    if not feats:
        return None, "no road edge was reached within the travel cost"
    layer.dataProvider().addFeatures(feats)
    layer.updateExtents()
    return layer, None


def parse_xy(text):
    """(x, y) from the first two numbers in text such as 'POINT(1.5 2)' or '1.5,2', else None. Pure."""
    import re
    numbers = re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(text))
    if len(numbers) < 2:
        return None
    return float(numbers[0]), float(numbers[1])


def match_destination_key(x, y, candidates, tolerance):
    """The id of the candidate [(id, x, y), ...] nearest to (x, y) and within `tolerance`, else None. Pure. Used to give the
    native point-to-layer output the same destination keys (feature ids) as the single-tree path (audit F16, #152): QGIS
    reports the end point as coordinates, not as a feature id."""
    best = None
    for ident, cx, cy in candidates:
        dist = ((cx - x) ** 2 + (cy - y) ** 2) ** 0.5
        if dist <= tolerance and (best is None or dist < best[0]):
            best = (dist, ident)
    return None if best is None else best[1]


def _single_tree_matrix(origins, origin_features, destinations, network, strategy, default_speed, speed_field,
                        direction_field, value_forward, value_backward, value_both):
    """{'matrix': {origin: {destination feature id: cost or None}}, 'unreachable_count': n} or {'error': ...}."""
    dest_feats = [f for f in destinations.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
    if not dest_feats:
        return {"error": "The destination layer has no usable point features."}
    ellipsoid = _network_context().ellipsoid()
    matrix, unreachable = {}, 0
    origin_ids = unique_labels([f.attribute(0) if f.fields().count() else None for f in origin_features], "origin")
    for origin_feat, origin_id in zip(origin_features, origin_ids):
        try:
            origin_xy = _point_xy_in_network_crs(origin_feat.geometry().asPoint(), origins.crs(), network)
            dest_xys = [_point_xy_in_network_crs(f.geometry().asPoint(), destinations.crs(), network) for f in dest_feats]
            costs = _single_tree_costs(network, origin_xy, dest_xys, strategy, default_speed, speed_field,
                                       direction_field, value_forward, value_backward, value_both, ellipsoid)
        except Exception as e:
            return {"error": f"travel_time_matrix could not build the shortest-path tree for origin '{origin_id}': {e}"}
        row = {}
        for feat, cost in zip(dest_feats, costs):
            row[str(feat.id())] = cost
            if cost is None:
                unreachable += 1
        matrix[str(origin_id)] = row
    return {"matrix": matrix, "unreachable_count": unreachable}


@register_tool(
    "travel_time_matrix",
    "Calculate road-network distance or travel time from each origin point to each destination "
    "point -- e.g. delivery distance from each warehouse to each distribution site. Returns a "
    "matrix of costs (metres for strategy='shortest' -- real-world distance whatever the layers' CRS is -- or hours for strategy='fastest') "
    "keyed by origin then destination. Requires a line layer representing the road network, not "
    "straight-line distance. Without speed_field, every segment is treated as one flat "
    "default_speed regardless of surface or condition -- when the network layer has a per-segment "
    "speed or condition field, pass it as speed_field with strategy='fastest' for a more realistic "
    "matrix. direction_field makes one-way roads one-way instead of assuming every segment is "
    "traversable both directions. SLOW for many destinations (every destination is tied into the road graph, which QGIS does by brute force; "
    "~44 minutes for 3,369): for 'which facilities are within/beyond N of this origin' use "
    "classify_facilities_by_access instead; destination layers over 200 features use a single shortest-path tree per origin (fast; each destination is charged the cost to its projected point on the nearest road segment) when the QGIS network classes are available.",
    {
        "type": "object",
        "properties": {
            "origins_layer": {"type": "string", "description": "Point layer of origin locations (e.g. warehouses)."},
            "destinations_layer": {"type": "string", "description": "Point layer of destination locations (e.g. distribution sites)."},
            "road_network_layer": {"type": "string", "description": "Line layer representing the road/path network."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h for any segment with no speed_field value, used only when strategy='fastest'. Defaults to 50."},
            "speed_field": {"type": "string", "description": "Optional numeric field on road_network_layer giving per-segment speed in km/h. Only affects the matrix when strategy='fastest'."},
            "direction_field": {"type": "string", "description": "Optional field on road_network_layer marking one-way segments (e.g. OSM's 'oneway' tag). Segments with no matching value still route both ways."},
            "value_forward": {"type": "string", "description": "direction_field value meaning forward-only travel. Defaults to 'yes' (OSM convention)."},
            "value_backward": {"type": "string", "description": "direction_field value meaning backward-only travel. Defaults to '-1' (OSM convention)."},
            "value_both": {"type": "string", "description": "direction_field value meaning both directions. Defaults to 'no' (OSM convention)."},
            "allow_large": {"type": "boolean", "description": "Only needed if the fast single-tree method is unavailable: set true to run a matrix over more than 200 destinations the slow way."},
        },
        "required": ["origins_layer", "destinations_layer", "road_network_layer"],
    },
)
def travel_time_matrix(origins_layer, destinations_layer, road_network_layer, strategy="shortest", default_speed=50,
                        speed_field=None, direction_field=None,
                        value_forward="yes", value_backward="-1", value_both="no", allow_large=False):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    strategy = (strategy or "shortest").lower()
    if strategy not in ("shortest", "fastest"):
        return {"error": "strategy must be 'shortest' or 'fastest'."}
    origins = _find_layer_by_name(origins_layer)
    destinations = _find_layer_by_name(destinations_layer)
    use_single_tree = (destinations is not None and _matrix_destination_count(destinations) > MATRIX_LARGE_DESTINATIONS
                       and single_tree_costs_available())
    if destinations is not None and not allow_large and not use_single_tree and _matrix_destination_count(destinations) > MATRIX_LARGE_DESTINATIONS:
        # rc7 smoke test F08: 3,369 destinations took ~37 minutes after a ~6 minute graph build. (Not one
        # shortest-path search per destination: QGIS runs a single Dijkstra per origin. The likely cost is tying every
        # destination into the graph -- QgsVectorLayerDirector.makeGraph compares each road segment with each tie point, so
        # it grows with segments x destinations. Source-read, not profiled.) The usual question behind such a call --
        # which facilities are within/beyond a travel cost of an origin -- has a seconds-long answer.
        return {"error": (
            f"'{destinations_layer}' has {_matrix_destination_count(destinations):,} features; travel_time_matrix ties every "
            "destination into the road graph and would take a very long time. To find which facilities are "
            "within/beyond a travel cost of an origin, call classify_facilities_by_access instead. If a full "
            "matrix is genuinely needed, call travel_time_matrix again with allow_large=true."),
            "suggested_tool": "classify_facilities_by_access"}
    network = _find_layer_by_name(road_network_layer)
    if origins is None:
        return {"error": f"Layer '{origins_layer}' not found"}
    if destinations is None:
        return {"error": f"Layer '{destinations_layer}' not found"}
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    geometry_error = _network_geometry_error(network, road_network_layer)
    if geometry_error:
        return {"error": geometry_error}
    network, closed_segments, closed_error = _open_network(network, speed_field, road_network_layer)
    if closed_error:
        return {"error": closed_error}

    extra_params, field_error = _network_direction_speed_params(
        network, speed_field, direction_field, value_forward, value_backward, value_both
    )
    if field_error:
        return {"error": field_error}

    try:
        origin_features = [f for f in origins.getFeatures() if not f.geometry().isEmpty()]
        if not origin_features:
            return {"error": f"'{origins_layer}' has no usable point features."}

        strategy_val = 1 if strategy == "fastest" else 0
        matrix = {}
        if use_single_tree:
            fast = _single_tree_matrix(origins, origin_features, destinations, network, strategy, default_speed,
                                       speed_field, direction_field, value_forward, value_backward, value_both)
            if "error" in fast:
                return fast
            result = {
                "success": True, "origins_layer": origins_layer, "destinations_layer": destinations_layer,
                "strategy": strategy, "cost_unit": "hours" if strategy == "fastest" else "meters",
                "matrix": fast["matrix"], "method": "single_shortest_path_tree",
                "unreachable_count": fast["unreachable_count"],
                "note": ("Costs come from one shortest-path tree per origin; each destination is projected onto its nearest road "
                         "segment and charged the cost to that spot, direction-aware, as QGIS's own point-to-layer tool does. "
                         "The short leg from the destination to the road is not added. Destination keys are feature ids."),
            }
            if speed_field:
                result["speed_field"] = speed_field
            result.update(_closed_note(closed_segments))
            if direction_field:
                result["direction_field"] = direction_field
            return result
        origin_ids = unique_labels([f.attribute(0) if f.fields().count() else None for f in origin_features], "origin")
        destination_points = []
        for dest in destinations.getFeatures():
            if dest.hasGeometry() and not dest.geometry().isEmpty():
                xy = _point_xy_in_network_crs(dest.geometry().asPoint(), destinations.crs(), network)
                destination_points.append((dest.id(), xy.x(), xy.y()))
        # The end point is printed with limited precision: match to the nearest destination within a tiny distance.
        key_tolerance = 1e-4 if network.crs().isGeographic() else 0.1
        unmatched_keys = 0
        for origin_feat, origin_id in zip(origin_features, origin_ids):
            point = origin_feat.geometry().asPoint()
            params = {
                "INPUT": network,
                "STRATEGY": strategy_val,
                "DEFAULT_SPEED": default_speed,
                "TOLERANCE": 0,
                "START_POINT": _point_for_network(point, origins.crs(), network),
                "END_POINTS": destinations,
                "OUTPUT": "memory:",
            }
            params.update(extra_params)
            output = _run_network_algorithm("native:shortestpathpointtolayer", params, _network_context(), network,
                                            "Travel time matrix")
            result_layer = output.get("OUTPUT")
            if result_layer is None:
                continue

            fields = [f.name() for f in result_layer.fields()]
            cost_field = next((f for f in fields if "cost" in f.lower()), None)
            dest_field = next((f for f in fields if "end" in f.lower() or "destination" in f.lower()), None)

            distances = {}
            for feat in result_layer.getFeatures():
                dest_key = feat.attribute(dest_field) if dest_field else feat.id()
                cost = feat.attribute(cost_field) if cost_field else None
                # Same keys as the single-tree path: the destination's feature id, found from the end point QGIS reports.
                parsed = parse_xy(dest_key) if dest_field else None
                matched = match_destination_key(parsed[0], parsed[1], destination_points, key_tolerance) if parsed else None
                if matched is None:
                    unmatched_keys += 1
                    key = str(dest_key)
                else:
                    key = str(matched)
                distances[key] = cost
            matrix[str(origin_id)] = distances

        if not matrix:
            return {"error": "Could not compute any routes -- check the origin/destination points are near the road network."}
        result = {
            "success": True,
            "origins_layer": origins_layer,
            "destinations_layer": destinations_layer,
            "strategy": strategy,
            "cost_unit": "hours" if strategy == "fastest" else "meters",
            "matrix": matrix,
            "destination_keys": "feature id",
        }
        if unmatched_keys:
            result["destination_keys_note"] = (f"{unmatched_keys} destination(s) could not be matched back to a feature id and "
                                               "keep the end-point text QGIS reported as their key.")
        if speed_field:
            result["speed_field"] = speed_field
        result.update(_closed_note(closed_segments))
        if direction_field:
            result["direction_field"] = direction_field
        return result
    except _bg.AnalysisCancelled:
        return _cancelled_result("travel-time matrix")
    except Exception as e:
        return {"error": f"travel_time_matrix failed: {e}"}


REACH_METHODS = ("concave_hull", "road_buffer", "convex_hull")
DEFAULT_REACH_GEOMETRY = "concave_hull"
# The published hospital-access method converts reached road vertices to a polygon with a GEOS concave hull at
# ratio 0.85 (arXiv 2609.12696, found by search; the paper itself was not read in full). QGIS passes the ratio to GEOS
# through QgsGeometry.concaveHull(targetPercent, allowHoles) (QGIS >= 3.28, needs GEOS >= 3.11).
CONCAVE_HULL_RATIO = 0.85
REACH_LABELS = {
    "concave_hull": "Concave hull of the reached roads (ratio %s) -- headline" % CONCAVE_HULL_RATIO,
    "road_buffer": "Reached roads buffered -- tight lower figure",
    "convex_hull": "Convex hull of the reached roads -- upper bound",
}
CONCAVE_HULL_REACH_NOTE = (
    "Reach polygon = the CONCAVE hull (GEOS ratio {r:g}) of the roads reached within the travel cost: it follows the "
    "road pattern more closely than a convex hull but still counts land between roads, so it can overstate who is "
    "reached where the network is sparse. Read it together with the road-buffer (lower) and convex-hull (upper) figures."
)


def _concave_reach_polygon(line_layers, ratio, name):
    """One polygon layer (in the lines' CRS): the concave hull of every reached road. Raises RuntimeError with a
    reason when QGIS/GEOS cannot produce a polygon (older GEOS lacks concave hulls)."""
    geoms = []
    for layer in line_layers:
        for feat in layer.getFeatures():
            g = feat.geometry()
            if g is not None and not g.isEmpty():
                geoms.append(g)
    if not geoms:
        raise RuntimeError("the reached-road layers have no geometry")
    collected = QgsGeometry.collectGeometry(geoms)
    hull = collected.concaveHull(float(ratio), False)
    if hull is None or hull.isNull() or hull.isEmpty() or QgsWkbTypes.geometryType(hull.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
        raise RuntimeError("no concave-hull polygon could be built (too few reached roads, or GEOS older than 3.11)")
    layer = QgsVectorLayer(f"Polygon?crs={line_layers[0].crs().authid()}", name, "memory")
    feat = QgsFeature()
    feat.setGeometry(hull)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return layer


# ---- population reach geometry (F09) ---------------------------------------------------------------
#
# rc7 smoke test F09 (2026-09-30): the population counted as reached (778,156) was summed inside the
# CONVEX HULL of the reached roads. A convex hull fills every gap between the roads -- valleys, water,
# empty land and districts the roads never enter -- so it overstates who can be reached, and in a
# humanitarian access-gap statistic that flatters the coverage. The reach polygon used for population
# is now the reached roads buffered by reach_buffer_m (default = the snap distance classify_facilities_by_access
# uses), which only covers land within walking distance of a road the travel cost actually reaches.
# The convex hull stays available as reach_geometry="convex_hull" and is labelled an upper bound.
ROAD_BUFFER_REACH_NOTE = (
    "Reach polygon = the roads reached within the travel cost, buffered by {m:g} m. Land farther than that from every "
    "reached road is counted as NOT reached, which removes the empty land a convex hull would add between sparse "
    "roads. In a DENSE road network the buffer also reaches up to {m:g} m past the last reached road, so it can be "
    "as large as or larger than a hull there; it can undercount settlements on tracks missing from the road layer."
)
CONVEX_HULL_REACH_NOTE = (
    "Reach polygon = the CONVEX HULL of the reached roads: an UPPER BOUND that also counts the land between the "
    "roads, so 'people reached' is overstated and the gap understated. Use reach_geometry='road_buffer' for a "
    "defensible figure."
)


def _utm_epsg_for(lon, lat):
    """EPSG code of the WGS84 UTM zone containing (lon, lat) -- a metric CRS to buffer in. Pure."""
    zone = int((float(lon) + 180.0) // 6) + 1
    zone = max(1, min(60, zone))
    return (32600 if float(lat) >= 0 else 32700) + zone


def _road_reach_polygon(line_layers, buffer_m, name):
    """One dissolved polygon layer (in the lines' CRS) covering every point within buffer_m metres of the
    reached roads. Buffered in the local UTM zone, so the distance is real metres whatever the road layer's CRS."""
    if len(line_layers) > 1:
        merged = processing.run(
            "native:mergevectorlayers",
            {"LAYERS": line_layers, "CRS": line_layers[0].crs().authid(), "OUTPUT": "memory:"},
        )["OUTPUT"]
    else:
        merged = line_layers[0]
    src_crs = merged.crs()
    centre = QgsCoordinateTransform(src_crs, QgsCoordinateReferenceSystem("EPSG:4326"),
                                    QgsProject.instance()).transform(merged.extent().center())
    metric = QgsCoordinateReferenceSystem(f"EPSG:{_utm_epsg_for(centre.x(), centre.y())}")
    projected = processing.run("native:reprojectlayer",
                               {"INPUT": merged, "TARGET_CRS": metric, "OUTPUT": "memory:"})["OUTPUT"]
    buffered = processing.run("native:buffer", {
        "INPUT": projected, "DISTANCE": float(buffer_m), "SEGMENTS": 8, "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0, "MITER_LIMIT": 2, "DISSOLVE": True, "OUTPUT": "memory:",
    })["OUTPUT"]
    back = processing.run("native:reprojectlayer",
                          {"INPUT": buffered, "TARGET_CRS": src_crs, "OUTPUT": "memory:"})["OUTPUT"]
    back.setName(name)
    return back


# ---- which facilities are within / beyond a travel cost (F08) --------------------------------------
#
# rc7 smoke test F08 (2026-09-30): "health facilities beyond one hour" took 43 min 48 s, 97% of it
# travel_time_matrix: native:shortestpathpointtolayer ties EVERY destination (3,369 of them) into the road graph
# after a ~6 minute graph build; QGIS runs only one Dijkstra per origin, and the graph tie-in compares each road segment with
# each tie point (source-read, not profiled), so the cost grows with segments x destinations. The same question is answered by ONE
# service area (calculate_service_area took 5.8 s in that session): a facility is within the cost
# when it lies on, or within a short snap distance of, a road reached within the cost.
#
# This is NOT identical to routing to each facility: it ignores the access leg from the road to the
# facility (bounded by snap_distance_m) and a facility farther than snap_distance_m from every
# reached road counts as beyond even if its nearest road is reached. The result says so.
DEFAULT_SNAP_DISTANCE_M = 500.0
MATRIX_LARGE_DESTINATIONS = 200


def _exact_spatial_index():
    """A QgsSpatialIndex that stores the feature geometries, so nearestNeighbor() ranks by the geometry itself.

    GitHub #148 (audit F12): the index was built with no flags, so nearestNeighbor() ranked by BOUNDING BOX. For a road whose
    envelope encloses the query point (a U- or L-shaped road), the box distance is zero while the road itself can be hundreds of
    metres away, so the true nearest road was missed when more than three envelopes ranked ahead of it (three U-shaped roads and
    a straight road 1 m away gave 100 m) and facilities near a threshold were classified wrongly. QGIS documents this limit of an
    index without stored geometries."""
    flag_type = getattr(QgsSpatialIndex, "Flag", QgsSpatialIndex)
    flag = getattr(flag_type, "FlagStoreFeatureGeometries")
    try:
        return QgsSpatialIndex(flags=flag)
    except TypeError:
        return QgsSpatialIndex(flag)


def _classify_by_distance(distances_m, snap_distance_m):
    """'within' / 'beyond' per facility from its distance (metres) to the nearest reached road.
    None (no reached road at all) is beyond. Pure, so it is unit tested without QGIS."""
    return ["within" if (d is not None and d <= snap_distance_m) else "beyond" for d in distances_m]


def _matrix_destination_count(layer):
    """Feature count for the travel_time_matrix size guard; 0 when it cannot be read, so the guard never
    blocks a call it cannot measure."""
    try:
        n = layer.featureCount()
        return n if isinstance(n, int) and n > 0 else 0
    except Exception:
        return 0


def _access_summary(classes):
    within = sum(1 for c in classes if c == "within")
    return {"within": within, "beyond": len(classes) - within, "total": len(classes)}


def _nearest_distances_m(facilities, facilities_crs, reached_layers):
    """Metres from each facility to the nearest reached road (None when there is none)."""
    da = QgsDistanceArea()
    ellipsoid = QgsProject.instance().ellipsoid()
    da.setEllipsoid(ellipsoid if ellipsoid and ellipsoid != "NONE" else "WGS84")
    indexed = []
    for lyr in reached_layers:
        feats = {f.id(): f for f in lyr.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()}
        if not feats:
            continue
        index = _exact_spatial_index()
        for f in feats.values():
            index.addFeature(f)
        xf = QgsCoordinateTransform(facilities_crs, lyr.crs(), QgsProject.instance())
        indexed.append((lyr.crs(), index, feats, xf))
    out = []
    for fac in facilities:
        best = None
        for crs, index, feats, xf in indexed:
            pt = xf.transform(QgsPointXY(fac.geometry().asPoint()))
            da.setSourceCrs(crs, QgsProject.instance().transformContext())
            # QgsSpatialIndex ranks in layer units; take a few candidates, then measure in metres.
            for fid in index.nearestNeighbor(pt, 3):
                near = feats[fid].geometry().nearestPoint(QgsGeometry.fromPointXY(pt)).asPoint()
                d = da.measureLine(pt, near)
                best = d if best is None else min(best, d)
        out.append(best)
    return out


@register_tool(
    "classify_facilities_by_access",
    "Answer 'which facilities are within / beyond N hours (or N metres) of this origin' FAST. Runs ONE "
    "service area from origin_layer (seconds, the same engine as calculate_service_area) and labels every "
    "facility in facility_layer 'within' when it lies on or within snap_distance_m of a road reached inside "
    "travel_cost, else 'beyond'. Use THIS instead of travel_time_matrix for any 'beyond/within X of the "
    "origin' question over many facilities: travel_time_matrix ties every destination into the road graph "
    "and took ~44 minutes for 3,369 facilities. Adds a copy of the facility layer with "
    "access_class and dist_to_reach_m fields, plus the service-area layers. APPROXIMATION to state in the "
    "answer: it ignores the access leg from the road to the facility (up to snap_distance_m) and is not a "
    "per-facility routed cost; use travel_time_matrix (small destination sets only) when exact per-facility "
    "costs are needed.",
    {
        "type": "object",
        "properties": {
            "origin_layer": {"type": "string", "description": "Point layer holding the origin(s) the travel cost is measured from."},
            "facility_layer": {"type": "string", "description": "Point layer of the facilities to classify."},
            "road_network_layer": {"type": "string", "description": "Line layer of the road/path network."},
            "travel_cost": {"type": "number", "description": "Max travel distance in METRES (strategy='shortest') or time in HOURS (strategy='fastest')."},
            "strategy": {"type": "string", "description": "'shortest' (distance, default) or 'fastest' (time)."},
            "default_speed": {"type": "number", "description": "Default speed in km/h, used only when strategy='fastest'. Defaults to 50."},
            "speed_field": {"type": "string", "description": "Optional per-segment speed field (km/h); ignored with a note if mostly empty."},
            "direction_field": {"type": "string", "description": "Optional one-way field on the road layer."},
            "snap_distance_m": {"type": "number", "description": "A facility counts as reached when it is within this many metres of a reached road. Defaults to 500."},
        },
        "required": ["origin_layer", "facility_layer", "road_network_layer", "travel_cost"],
    },
)
def classify_facilities_by_access(origin_layer, facility_layer, road_network_layer, travel_cost,
                                  strategy="shortest", default_speed=50, speed_field=None,
                                  direction_field=None, snap_distance_m=DEFAULT_SNAP_DISTANCE_M):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    facilities = _find_layer_by_name(facility_layer)
    if facilities is None:
        return {"error": f"Layer '{facility_layer}' not found"}
    try:
        snap = float(snap_distance_m)
    except (TypeError, ValueError):
        return {"error": "snap_distance_m must be a number of metres."}
    if snap < 0:
        return {"error": "snap_distance_m must not be negative."}
    if isinstance(travel_cost, (list, tuple)):
        return {"error": "travel_cost must be a single number here; call again for another threshold."}

    _t0 = time.monotonic()
    service = calculate_service_area(origin_layer, road_network_layer, travel_cost, strategy, default_speed,
                                     speed_field=speed_field, direction_field=direction_field)
    _t_service = time.monotonic()
    if "error" in service:
        return service
    reached = [_find_layer_by_name(n) for n in service.get("layers_created", []) if "_lines_" in n]
    reached = [lyr for lyr in reached if lyr is not None]
    if not reached:
        return {"error": "The service area produced no reached-road layer to classify against.",
                "service_area": service}

    try:
        feats = [f for f in facilities.getFeatures() if f.hasGeometry() and not f.geometry().isEmpty()]
        if not feats:
            return {"error": f"'{facility_layer}' has no usable point features."}
        _t_prep = time.monotonic()
        distances = _nearest_distances_m(feats, facilities.crs(), reached)
        _t_dist = time.monotonic()
        classes = _classify_by_distance(distances, snap)

        out = QgsVectorLayer(f"Point?crs={facilities.crs().authid()}", "tmp", "memory")
        provider = out.dataProvider()
        provider.addAttributes(list(facilities.fields()) + [
            QgsField("access_class", QVariant.String), QgsField("dist_to_reach_m", QVariant.Double)])
        out.updateFields()
        rows = []
        for f, cls, d in zip(feats, classes, distances):
            nf = QgsFeature(out.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes(list(f.attributes()) + [cls, None if d is None else round(d, 1)])
            rows.append(nf)
        provider.addFeatures(rows)
        out.updateExtents()
        out_name = f"{facility_layer}_access_{travel_cost:g}"
        _t_built = time.monotonic()
        _replace_named_layer(out_name, out)
        # rc10 smoke test: this tool took 151 s on 3,369 facilities x ~140k roads, of which only ~5 s was the network
        # algorithm. Say where the rest goes (counts and milliseconds only) so the next run can be fixed from evidence.
        log_event("classify_facilities_timing", tag="Tools", facilities=len(feats), reached_layers=len(reached),
                  service_area_ms=int((_t_service - _t0) * 1000), prepare_ms=int((_t_prep - _t_service) * 1000),
                  nearest_ms=int((_t_dist - _t_prep) * 1000), build_ms=int((_t_built - _t_dist) * 1000),
                  replace_ms=int((time.monotonic() - _t_built) * 1000))
        try:
            from . import routing_style
            if not routing_style.style_access_points(out, "access_class"):
                from .styling_tools import apply_categorized_style
                apply_categorized_style(out_name, "access_class")
            from .output_style import style_auto_labels
            style_auto_labels(out)        # facility names, so "beyond reach" points can be read off the map
            _show_on_top(out_name)
        except Exception as e:
            log_event("swallowed_exception", tag="Tools", tool="classify_facilities_by_access_styling",
                      error_class=type(e).__name__, error=True)

        name_field = next((fld.name() for fld in facilities.fields() if fld.name().lower() in ("name", "name_en")), None)
        beyond_names = []
        if name_field:
            beyond_names = [str(f[name_field]) for f, c in zip(feats, classes) if c == "beyond" and f[name_field]][:25]
        summary = _access_summary(classes)
        result = {
            "success": True,
            "travel_cost": travel_cost,
            "travel_cost_unit": "hours" if (strategy or "").lower() == "fastest" else "meters",
            "strategy": strategy,
            "snap_distance_m": snap,
            **summary,
            "layer_created": out_name,
            "service_area_layers": service.get("layers_created", []),
            "method_note": (
                "Classified from one service area, not routed per facility: a facility is 'within' when it is "
                f"within {snap:g} m of a road reached inside the travel cost. The access leg from the road to the "
                "facility is not counted, so this can differ slightly from a routed cost near the threshold."
            ),
        }
        if beyond_names:
            result["beyond_examples"] = beyond_names
        if service.get("notes"):
            result["notes"] = service["notes"]
        return result
    except Exception as e:
        return {"error": f"classify_facilities_by_access failed: {e}"}


@register_tool(
    "population_access_gap",
    "Compute how many people, and what percentage of a population base, are BEYOND a given travel "
    "distance/time from the nearest facility -- e.g. 'X people / Y% of the population are more than "
    "30 minutes from a functioning health facility', the standard access-to-services statistic in "
    "humanitarian gap analysis and cluster reporting. A thin composite over calculate_service_area "
    "(network-based reach per facility) and estimate_population_exposure (population sum within a "
    "polygon) rather than reimplementing either -- area_layer defines the population base to check "
    "coverage for (e.g. an admin-boundary or catchment polygon) and must already have a population "
    "raster available (see fetch_worldpop_population). As a side effect of calling "
    "calculate_service_area internally, per-facility service-area polygons are also added to the "
    "project, plus the combined reachable-area layers this tool builds from them. It reports THREE labelled "
    "figures (reach_figures): a concave hull of the reached roads (the headline, the method used in published "
    "hospital-access work), the reached roads buffered by reach_buffer_m (a tight lower figure) and the convex hull "
    "(an UPPER BOUND that fills the land between roads). Always give the user the range "
    "(reachable_population_range), not only the headline. Returns a MODELED "
    "estimate -- network-based reachability against a gridded population raster, not a verified count "
    "of people confirmed to lack access -- report it as 'an estimated N people/percent are beyond X', "
    "not as a confirmed access-gap figure.",
    {
        "type": "object",
        "properties": {
            "facility_layer": {"type": "string", "description": "Point layer of facilities (health centers, warehouses, etc.)."},
            "road_network_layer": {"type": "string", "description": "Line layer of the road/path network."},
            "population_raster_layer": {"type": "string", "description": "Population-per-pixel raster (e.g. from fetch_worldpop_population)."},
            "area_layer": {"type": "string", "description": "Polygon layer defining the population base to check coverage for."},
            "travel_cost": {"type": "number", "description": "Max travel distance in METRES (real-world, whatever the layers' CRS is) or time in HOURS if strategy='fastest'."},
            "strategy": {"type": "string", "description": "'shortest' (distance-based, default) or 'fastest' (time-based)."},
            "default_speed": {"type": "number", "description": "Default travel speed in km/h, used only when strategy='fastest'. Defaults to 50."},
            "reach_geometry": {"type": "string", "description": "Which figure is the headline: 'concave_hull' (default), 'road_buffer' (people within reach_buffer_m of a reached road) or 'convex_hull' (an UPPER BOUND). All three are always reported in reach_figures."},
            "reach_buffer_m": {"type": "number", "description": "Buffer distance in metres around the reached roads for the road-buffer figure. Defaults to 500."},
        },
        "required": ["facility_layer", "road_network_layer", "population_raster_layer", "area_layer", "travel_cost"],
    },
)
def population_access_gap(facility_layer, road_network_layer, population_raster_layer, area_layer, travel_cost, strategy="shortest", default_speed=50,
                          reach_geometry="concave_hull", reach_buffer_m=DEFAULT_SNAP_DISTANCE_M):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    reach_geometry = (reach_geometry or DEFAULT_REACH_GEOMETRY).lower()
    if reach_geometry not in REACH_METHODS:
        return {"error": "reach_geometry must be 'concave_hull', 'road_buffer' or 'convex_hull'."}
    try:
        reach_buffer_m = float(reach_buffer_m)
    except (TypeError, ValueError):
        return {"error": "reach_buffer_m must be a number of metres."}
    if reach_buffer_m <= 0:
        return {"error": "reach_buffer_m must be greater than zero."}

    area = _find_layer_by_name(area_layer)
    if area is None:
        return {"error": f"Layer '{area_layer}' not found"}
    if QgsWkbTypes.geometryType(area.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
        return {"error": f"'{area_layer}' must be a polygon layer."}

    # Reuses calculate_service_area exactly as a normal caller would -- same
    # validation, same per-facility hull-polygon layers added to the project.
    service_result = calculate_service_area(facility_layer, road_network_layer, travel_cost, strategy, default_speed)
    if "error" in service_result:
        return service_result

    # calculate_service_area names lines layers "..._service_area_lines_{i}"
    # and hull layers "..._service_area_{i}".
    line_names = [n for n in service_result["layers_created"] if "_lines_" in n]
    line_layers = [layer for layer in (_find_layer_by_name(n) for n in line_names) if layer is not None]
    hull_names = [n for n in service_result["layers_created"] if "_lines_" not in n]
    hull_layers = [layer for layer in (_find_layer_by_name(n) for n in hull_names) if layer is not None]
    if not line_layers and not hull_layers:
        return {"error": "calculate_service_area produced no reached-road or reachable-area layer to build a reach polygon from."}

    from .raster_tools import estimate_population_exposure

    total_pop_result = estimate_population_exposure(population_raster_layer, area_layer)
    if "error" in total_pop_result:
        return total_pop_result
    total_population = total_pop_result["total_population"]

    base_name = f"{facility_layer}_reachable_area"

    def build_reach(method, name):
        if method == "road_buffer":
            if not line_layers:
                raise RuntimeError("no reached-road layer to buffer")
            return _road_reach_polygon(line_layers, reach_buffer_m, name), ROAD_BUFFER_REACH_NOTE.format(m=reach_buffer_m)
        if method == "concave_hull":
            if not line_layers:
                raise RuntimeError("no reached-road layer to build a concave hull from")
            return _concave_reach_polygon(line_layers, CONCAVE_HULL_RATIO, name), CONCAVE_HULL_REACH_NOTE.format(r=CONCAVE_HULL_RATIO)
        if not hull_layers:
            raise RuntimeError("no reachable-area polygons for the convex hull")
        if len(hull_layers) > 1:
            merged = processing.run(
                "native:mergevectorlayers",
                {"LAYERS": hull_layers, "CRS": hull_layers[0].crs().authid(), "OUTPUT": "memory:"},
            )["OUTPUT"]
        else:
            merged = hull_layers[0]
        # Dissolve away overlaps between facilities' service areas -- a location reachable from two
        # facilities must only count once.
        reachable = processing.run("native:dissolve", {"INPUT": merged, "FIELD": [], "OUTPUT": "memory:"})["OUTPUT"]
        reachable.setName(name)
        return reachable, CONVEX_HULL_REACH_NOTE

    figures = {}
    for method in REACH_METHODS:
        layer_name = base_name if method == reach_geometry else f"{base_name}_{method}"
        try:
            reachable, note = build_reach(method, layer_name)
            _replace_named_layer(layer_name, reachable, to_tree=False)   # grouped below, with the headline on top
            within_name = f"{area_layer}_reachable_by_{facility_layer}" if method == reach_geometry \
                else f"{area_layer}_reachable_by_{facility_layer}_{method}"
            within = processing.run(
                "native:intersection", {"INPUT": area, "OVERLAY": reachable, "OUTPUT": "memory:"})["OUTPUT"]
            _replace_named_layer(within_name, within, to_tree=False)
            # A zero-feature intersection means literally 0 people are covered -- handled explicitly rather than
            # trusting zonal statistics against an empty layer.
            if within.featureCount() == 0:
                reachable_pop = 0.0
            else:
                pop_result = estimate_population_exposure(population_raster_layer, within_name)
                if "error" in pop_result:
                    raise RuntimeError(pop_result["error"])
                reachable_pop = pop_result["total_population"]
            figures[method] = {"layer": layer_name, "within_layer": within_name, "note": note,
                               "reachable_population": reachable_pop, "_reach": reachable, "_within": within}
        except Exception as e:
            figures[method] = {"available": False, "reason": str(e)}

    headline = reach_geometry
    if "reachable_population" not in figures.get(headline, {}):
        # The requested figure could not be computed: fall back in a fixed order and say so.
        headline = next((m for m in ("road_buffer", "convex_hull", "concave_hull") if "reachable_population" in figures[m]), None)
        if headline is None:
            reasons = "; ".join(f"{m}: {f.get('reason')}" for m, f in figures.items())
            return {"error": f"population_access_gap geometry processing failed for every reach method ({reasons})."}

    def gap_fields(reachable_pop):
        # Clamped at zero: zonal statistics over an intersected geometry can differ by a hair at the pixel level.
        gap = max(0.0, total_population - reachable_pop)
        return gap, (round(gap / total_population * 100, 2) if total_population > 0 else None)

    reach_figures = []
    for method in REACH_METHODS:
        fig = figures[method]
        if "reachable_population" not in fig:
            reach_figures.append({"method": method, "available": False, "reason": fig.get("reason")})
            continue
        gap, pct = gap_fields(fig["reachable_population"])
        reach_figures.append({
            "method": method, "label": REACH_LABELS[method], "reachable_population": fig["reachable_population"],
            "gap_population": gap, "gap_percent": pct, "is_upper_bound": method == "convex_hull",
            "is_headline": method == headline, "layer": fig["layer"], "note": fig["note"],
        })
    available = [f["reachable_population"] for f in reach_figures if f.get("reachable_population") is not None]

    # Visualization: distinct translucent colours, one group with the headline on top and visible, the other figures hidden.
    try:
        from . import routing_style
        groupable = {m: f["_reach"] for m, f in figures.items() if "_reach" in f}
        for m, lyr in groupable.items():
            routing_style.style_reach_polygon(lyr, m)
        routing_style.group_reach_layers(
            groupable, headline, facility_layer,
            extra_hidden=[f["_within"] for f in figures.values() if "_within" in f])
    except Exception as e:
        log_event("swallowed_exception", tag="Tools", tool="population_access_gap_styling",
                  error_class=type(e).__name__, error=True)
        # The layers were added without a tree node; make sure they are still visible.
        for f in figures.values():
            for key in ("_reach", "_within"):
                lyr = f.get(key)
                try:
                    if lyr is not None and QgsProject.instance().layerTreeRoot().findLayer(lyr.id()) is None:
                        QgsProject.instance().layerTreeRoot().addLayer(lyr)
                except Exception:
                    pass

    head = figures[headline]
    reachable_population = head["reachable_population"]
    gap_population, gap_pct = gap_fields(reachable_population)
    result = {
        "success": True,
        "facility_count": service_result["facility_count"],
        "travel_cost": travel_cost,
        "strategy": strategy,
        "total_population": total_population,
        "reachable_population": reachable_population,
        "gap_population": gap_population,
        "gap_percent": gap_pct,
        "reachable_area_layer": head["layer"],
        "reachable_within_area_layer": head["within_layer"],
        "reach_geometry": headline,
        "reach_note": head["note"],
        "is_upper_bound_on_reach": headline == "convex_hull",
        # Three labelled figures, not one: the published method is a concave hull, a road buffer is the tight bound
        # and a convex hull the upper bound. The spread between them is the honest uncertainty of the estimate --
        # report the range, not only the headline.
        "reach_figures": reach_figures,
        "reachable_population_range": [min(available), max(available)],
        # Point 9 of docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md: this
        # is a modeled gap (network reachability vs. a gridded population raster),
        # not a verified count of people confirmed to lack access -- carried
        # through from estimate_population_exposure's own estimate fields rather
        # than restated as a plain, unqualified number.
        "gap_population_est": gap_population,
        "pop_source": total_pop_result.get("pop_source"),
        "pop_reference_year": total_pop_result.get("pop_reference_year"),
        "confidence": "estimate (modeled network reachability + gridded population raster; not field-verified)",
    }
    if headline != reach_geometry:
        result["headline_fallback"] = (
            f"'{reach_geometry}' could not be computed ({figures[reach_geometry].get('reason')}); the headline uses "
            f"'{headline}' instead.")
    return result


@register_tool(
    "score_route_incident_risk",
    "Score a planned route (or any line layer) against how close it passes to recent security/"
    "safety incidents -- 'does this route go near any recent incidents'. Reuses buffer_analysis's "
    "exact processing call to build a buffer around the route, then counts/lists incident_layer "
    "points falling within it, each with its own distance to the route. Optionally restrict to "
    "recent incidents only (date_field + days_back) and/or weight by a numeric field (e.g. a "
    "severity score) for a weighted risk total instead of a flat count. The buffer layer it "
    "creates is auto-styled as a translucent orange risk corridor (not QGIS's default random "
    "single-symbol color) so it reads as risk on the map without a separate styling call. Does "
    "NOT re-route or exclude anything automatically -- this scores a route for a human to act on; for a genuine "
    "hard-exclude of a security-restricted area from routing itself, use difference_layers to "
    "remove that area from the road network layer before calling calculate_service_area/"
    "travel_time_matrix, see docs/archive/ROUTE_RISK_AND_NOGO_ZONES_SPEC.md.",
    {
        "type": "object",
        "properties": {
            "route_layer": {"type": "string", "description": "Line layer of the planned route (any line layer -- a hand-drawn route, a road-network subset, etc.)."},
            "incident_layer": {"type": "string", "description": "Point layer of incidents to check proximity against, e.g. the shared 'Incidents' layer from add_incident_point."},
            "buffer_distance": {"type": "number", "description": "How close counts as 'near' the route, in the layers' CRS units (usually meters)."},
            "date_field": {"type": "string", "description": "Optional date field on incident_layer, required if days_back is set."},
            "days_back": {"type": "integer", "description": "Optional: only count incidents from the last N days. Requires date_field."},
            "weight_field": {"type": "string", "description": "Optional numeric field on incident_layer (e.g. a severity score) to compute a weighted risk total instead of a flat count."},
        },
        "required": ["route_layer", "incident_layer", "buffer_distance"],
    },
)
def score_route_incident_risk(route_layer, incident_layer, buffer_distance, date_field=None, days_back=None, weight_field=None):
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    route = _find_layer_by_name(route_layer)
    if route is None:
        return {"error": f"Layer '{route_layer}' not found"}
    incidents = _find_layer_by_name(incident_layer)
    if incidents is None:
        return {"error": f"Layer '{incident_layer}' not found"}

    incident_fields = [f.name() for f in incidents.fields()]
    if date_field and date_field not in incident_fields:
        return {"error": f"Field '{date_field}' not found on '{incident_layer}'. Available: {incident_fields}"}
    if weight_field and weight_field not in incident_fields:
        return {"error": f"Field '{weight_field}' not found on '{incident_layer}'. Available: {incident_fields}"}
    if days_back is not None and not date_field:
        return {"error": "days_back requires date_field to also be set."}
    if buffer_distance <= 0:
        return {"error": "buffer_distance must be positive."}

    route_geom = None
    for feat in route.getFeatures():
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        route_geom = g if route_geom is None else route_geom.combine(g)
    if route_geom is None:
        return {"error": f"'{route_layer}' has no usable geometry."}

    buffer_result = buffer_analysis(route_layer, buffer_distance)
    if "error" in buffer_result:
        return buffer_result
    # QGIS-006/QGIS-007, 2026-09-13 audit: buffer_analysis already detects and warns when
    # route_layer is in a geographic CRS (Point 3 of docs/QGIS_PRODUCTION_ARCHITECTURE_
    # REVIEW_2026-09-04.md -- distance/buffer values applied in degrees, not meters), but
    # this function used to discard that warning entirely (only checked "error" in
    # buffer_result). The SAME underlying issue also mislabels distance_to_route_m below
    # (a raw route_geom.distance(geom) in the layer's own CRS units, but the field name
    # asserts meters) -- this is the more safety-relevant of the two, since this tool
    # exists specifically to score incident proximity to a route for humanitarian/security
    # decisions. Propagate the warning and extend it to cover both.
    # Fixed 2026-09-19 (was: raw route_geom.distance(geom) in CRS units, mislabeled as
    # meters on a geographic CRS -- see the comment above). route_geom is a line, not a
    # point, so _measure_distance's point-to-point ellipsoidal path doesn't directly apply
    # here -- nearestPoint() finds the closest point ON the route to each incident first,
    # then that point and the incident (itself a point, per this tool's own "Point layer of
    # incidents" schema description) go through the same _make_distance_area/
    # _measure_distance ellipsoidal measurement optimal_hub_siting/location_allocation use.
    distance_area = _make_distance_area(route)
    crs_warning = buffer_result.get("warning")
    if crs_warning:
        if distance_area is not None:
            crs_warning += (
                " 'distance_to_route_m' values below are real-world meters via ellipsoidal "
                "(WGS84 geodesic) measurement, not raw planar degrees."
            )
        else:
            crs_warning += (
                " This also means every 'distance_to_route_m' value below is in DEGREES, not "
                "meters, despite the field name."
            )
    buffer_layer_name = buffer_result["layer_name"]
    buffer_layer = _find_layer_by_name(buffer_layer_name)
    if buffer_layer is None:
        return {"error": f"Buffer layer '{buffer_layer_name}' was created but could not be found afterward."}
    _style_risk_buffer_layer(buffer_layer)

    buffer_geom = None
    for feat in buffer_layer.getFeatures():
        g = feat.geometry()
        if g is None or g.isEmpty():
            continue
        buffer_geom = g if buffer_geom is None else buffer_geom.combine(g)
    if buffer_geom is None:
        return {"error": "Route buffer produced no usable geometry."}

    cutoff_date = None
    if days_back is not None:
        cutoff_date = datetime.date.today() - datetime.timedelta(days=days_back)

    matched = []
    total_weight = 0.0
    for feat in incidents.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty() or not buffer_geom.intersects(geom):
            continue
        if cutoff_date is not None:
            d = _parse_date(feat[date_field])
            if d is None or d < cutoff_date:
                continue
        weight = 1.0
        if weight_field:
            val = feat[weight_field]
            weight = float(val) if isinstance(val, (int, float)) else 1.0
        total_weight += weight
        nearest_on_route = route_geom.nearestPoint(geom)
        matched.append({
            "incident_id": feat.id(),
            "distance_to_route_m": round(_measure_distance(distance_area, nearest_on_route, geom), 1),
            "date": str(feat[date_field]) if date_field else None,
            "weight": weight if weight_field else None,
        })

    matched.sort(key=lambda e: e["distance_to_route_m"])
    matched_capped, matched_total, truncated = _cap_entries(matched)

    result = {
        "success": True,
        "route_layer": route_layer,
        "incident_layer": incident_layer,
        "buffer_distance": buffer_distance,
        "buffer_layer_name": buffer_layer_name,
        "days_back": days_back,
        "incident_count": matched_total,
        "total_weighted_risk": round(total_weight, 2) if weight_field else None,
        "incidents": matched_capped,
        "truncated": truncated,
    }
    if crs_warning:
        result["warning"] = crs_warning
    return result


# BUG-2026-09-25-3: measured on the real Jordan Geofabrik extract, maxspeed is set on only 0.9%
# of roads (1,504 of 161,041) -- with strategy='fastest', every other road falls back to the flat
# DEFAULT_SPEED parameter, so a road network with almost no real speed data still produces a
# uniform-speed travel time, not a meaningfully differentiated one. The road CLASS is present far
# more often (fclass on a Geofabrik extract; highway on an OSM/Overpass ingest -- same OSM
# vocabulary, since Geofabrik's fclass mirrors the highway tag it was derived from). This table is
# an assumption, not measured data -- common values from public routing profiles (OSRM/GraphHopper
# car profiles), not this project's own measurement of Jordan or any other specific road network.
# Per docs/BUG_TRACKER.md's own framing, this is a judgement call that changes results and ideally
# wants checking against a known real journey -- so it ships as an explicit, separately-invoked
# tool (never run automatically by calculate_service_area/travel_time_matrix/
# optimize_delivery_route), not a silent default, and its own tool description says so.
ASSUMED_SPEED_BY_ROAD_CLASS_KMH = {
    "motorway": 100, "motorway_link": 80,
    "trunk": 80, "trunk_link": 60,
    "primary": 70, "primary_link": 50,
    "secondary": 60, "secondary_link": 45,
    "tertiary": 50, "tertiary_link": 40,
    "unclassified": 30,
    "residential": 40, "living_street": 20,
    "service": 20, "track": 20,
    "pedestrian": 5, "footway": 5, "path": 5, "cycleway": 15, "steps": 3,
}
_ROAD_CLASS_FIELD_CANDIDATES = ("fclass", "highway")

# Optional per-country override, addressing this table's own standing limitation (a single
# global set of numbers, not this network's real legal limits) without needing a live lookup.
# Modeled on the same three-tier (urban/rural/motorway) legal-default-speed convention real
# open-source routing infrastructure already uses for exactly this gap -- see
# https://github.com/westnordost/osm-legal-default-speeds (BSD-3-Clause code, its underlying
# data is CC BY-SA 2.0 from the OpenStreetMap wiki's "Default speed limits" page) and the
# Valhalla-consumed https://github.com/OpenStreetMapSpeeds/schema dataset. Values below are a
# curated subset (not a full port of either project's much larger tag-filter-matching data
# model, which needs per-subdivision OSM tag evaluation this project has no use for at its
# current scope) verified via live web search 2026-09-28 against public references (Wikipedia's
# "Speed limits by country" and per-country articles, TyreMap, AARoads Wiki) -- national legal
# defaults, honestly approximate: many countries' real limits vary by state/province/specific
# road (the US and Australia especially), and this table cannot and does not capture that.
# tags: (urban, rural, motorway) in km/h, applied only when the caller passes a matching
# ISO 3166-1 alpha-2 `country` code -- omitting it keeps today's behavior exactly as before.
COUNTRY_SPEED_TIERS_KMH = {
    "JO": (40, 80, 110),   # Jordan
    "SA": (50, 80, 120),   # Saudi Arabia
    "AE": (60, 100, 120),  # United Arab Emirates
    "EG": (60, 100, 100),  # Egypt
    "DE": (50, 100, 130),  # Germany (130 is the advisory Autobahn limit, not a hard cap)
    "AT": (50, 100, 130),  # Austria
    "CZ": (50, 90, 130),   # Czechia
    "HU": (50, 90, 130),   # Hungary
    "FR": (50, 80, 130),   # France
    "ES": (50, 90, 120),   # Spain
    "GB": (48, 97, 113),   # United Kingdom (30/60/70 mph)
    "CA": (50, 80, 110),   # Canada
    "US": (40, 105, 113),  # United States (national default; varies heavily by state)
    "AU": (60, 100, 110),  # Australia (national default; varies by state/territory)
    "CN": (50, 80, 120),   # China
}
# Road-class tiers this table's three values map onto, and the fraction applied to a "_link"
# variant of a tiered class -- same reduction shape (~75-80%) the existing global table above
# already uses between e.g. motorway (100) and motorway_link (80).
_COUNTRY_TIER_ROAD_CLASSES = {
    "motorway": ("motorway", "trunk"),
    "rural": ("primary", "secondary", "tertiary", "unclassified"),
    "urban": ("residential", "living_street", "service", "track"),
}
_COUNTRY_LINK_FACTOR = 0.75


def _country_speed_overrides(country):
    """Expand COUNTRY_SPEED_TIERS_KMH's 3 tier values into the same per-road-class shape
    ASSUMED_SPEED_BY_ROAD_CLASS_KMH uses, for one country code. Returns {} for an unknown/
    omitted country -- callers then simply fall back to the existing global table untouched."""
    tiers = COUNTRY_SPEED_TIERS_KMH.get((country or "").strip().upper())
    if not tiers:
        return {}
    urban_kmh, rural_kmh, motorway_kmh = tiers
    tier_value = {"motorway": motorway_kmh, "rural": rural_kmh, "urban": urban_kmh}
    overrides = {}
    for tier, classes in _COUNTRY_TIER_ROAD_CLASSES.items():
        value = tier_value[tier]
        for road_class in classes:
            overrides[road_class] = value
            overrides[f"{road_class}_link"] = round(value * _COUNTRY_LINK_FACTOR)
    return overrides


@register_tool(
    "estimate_road_speeds",
    "Write an 'assumed_speed_kmh' field onto a road network layer's features, filled in from a "
    "fixed table of typical speeds per road class (motorway/primary/residential/track/etc, common "
    "routing-profile values -- see ASSUMED_SPEED_BY_ROAD_CLASS_KMH), read from the layer's 'fclass' "
    "(Geofabrik OSM extracts) or 'highway' (OSM/Overpass ingests) field. Use this when a road "
    "network has little or no real maxspeed data (very common: a real Jordan extract had maxspeed "
    "on only 0.9% of roads) and calculate_service_area/travel_time_matrix/optimize_delivery_route "
    "with strategy='fastest' would otherwise fall back to one flat default speed for nearly every "
    "road. IMPORTANT: this is an ASSUMPTION, not measured data for this specific road network -- "
    "tell the user the travel times that follow from it are estimates based on typical road-class "
    "speeds, not this network's real posted limits, especially if they ask for a precise duration. "
    "Never call this automatically as part of another tool's workflow; only when the user has "
    "actual maxspeed data will speed_field give a materially better answer. Pass country (an "
    "ISO 3166-1 alpha-2 code, e.g. 'JO', 'DE', 'US') to scale the table to that country's real "
    "legal urban/rural/motorway speed limits (see COUNTRY_SPEED_TIERS_KMH) instead of the generic "
    "global defaults -- covers a curated set of countries; falls back to the generic table for any "
    "other code or when omitted. Destructive action requiring UI confirmation -- in-place attribute "
    "mutation on the live layer, same class of operation as calculate_area/field_calculator.",
    {
        "type": "object",
        "properties": {
            "road_network_layer": {"type": "string", "description": "Line layer of the road network, with an 'fclass' or 'highway' field."},
            "default_speed_kmh": {"type": "number", "description": "Speed assumed for a road class not in the table (default 30)."},
            "overwrite": {"type": "boolean", "description": "If assumed_speed_kmh already exists, overwrite it. Default false: existing values are left alone, only missing/null ones are filled in."},
            "country": {"type": "string", "description": "Optional ISO 3166-1 alpha-2 country code (e.g. 'JO', 'DE', 'US') to scale the speed table to that country's real legal urban/rural/motorway limits instead of generic global defaults. Unrecognized or omitted falls back to the generic table."},
        },
        "required": ["road_network_layer"],
    },
)
def estimate_road_speeds(road_network_layer, default_speed_kmh=30, overwrite=False, country=None, confirmed: bool = False):
    if not confirmed:
        return {
            "status": "PREVIEW_REQUIRED",
            "requires_confirmation": True,
            "is_destructive": True,
            "tool_name": "estimate_road_speeds",
            "arguments": {"road_network_layer": road_network_layer, "default_speed_kmh": default_speed_kmh,
                          "overwrite": overwrite, "country": country, "confirmed": True},
            "code_snippet": "layer.startEditing()\n# Add/update field 'assumed_speed_kmh' from a fixed table keyed by "
                            "fclass/highway\nlayer.commitChanges()",
            "rationale": f"Data Mutation Preview: Add/update field 'assumed_speed_kmh' on layer "
                        f"'{road_network_layer}', filled from typical per-road-class speeds -- an assumption, "
                        "not this network's own measured speed data.",
            "message": f"Confirmation required before mutating attribute field 'assumed_speed_kmh' on "
                      f"'{road_network_layer}'.",
        }
    if not QGIS_AVAILABLE:
        return {"error": "QGIS not available"}
    network = _find_layer_by_name(road_network_layer)
    if network is None:
        return {"error": f"Layer '{road_network_layer}' not found"}
    geometry_error = _network_geometry_error(network, road_network_layer)
    if geometry_error:
        return {"error": geometry_error}

    field_names = [f.name() for f in network.fields()]
    class_field = next((f for f in _ROAD_CLASS_FIELD_CANDIDATES if f in field_names), None)
    if class_field is None:
        return {"error": (
            f"'{road_network_layer}' has neither an 'fclass' nor a 'highway' field to read a road "
            "class from -- estimate_road_speeds needs one of those (Geofabrik extracts use "
            "'fclass'; OSM/Overpass ingests use 'highway')."
        )}

    try:
        country_code = (country or "").strip().upper()
        country_overrides = _country_speed_overrides(country_code)
        speed_table = {**ASSUMED_SPEED_BY_ROAD_CLASS_KMH, **country_overrides}

        provider = network.dataProvider()
        if "assumed_speed_kmh" not in field_names:
            provider.addAttributes([QgsField("assumed_speed_kmh", QVariant.Double)])
            network.updateFields()
        field_idx = network.fields().indexOf("assumed_speed_kmh")
        if field_idx < 0:
            # rc11 smoke test C1: this surfaced as the bare error "estimate_road_speeds failed: '-1'" (PyQGIS raises
            # KeyError('-1') for attribute(-1)). The provider silently refused the new field -- a read-only or filtered data
            # source (the OSM Roads layer shows a filter) -- and every later call used index -1.
            existing_speed = [n for n in field_names if n.lower() in ("speed_kmh", "maxspeed", "speed")]
            hint = (f" This layer already has a speed field ({existing_speed[0]!r}); pass it as speed_field to the routing tool "
                    "instead." if existing_speed else "")
            return {"error": (
                f"Could not add the 'assumed_speed_kmh' field to '{road_network_layer}': its data source does not accept new "
                "fields (read-only, or opened with a filter). Export a copy of the layer (export_layer) and run this on the "
                "copy." + hint)}

        network.startEditing()
        updated = 0
        skipped_existing = 0
        unknown_classes = set()
        for feature in network.getFeatures():
            existing = feature.attribute(field_idx)
            if existing not in (None, "") and not overwrite:
                skipped_existing += 1
                continue
            road_class = str(feature.attribute(class_field) or "").strip().lower()
            speed = speed_table.get(road_class)
            if speed is None:
                unknown_classes.add(road_class or "(empty)")
                speed = default_speed_kmh
            network.changeAttributeValue(feature.id(), field_idx, float(speed))
            updated += 1
        network.commitChanges()

        result = {
            "success": True,
            "layer_name": road_network_layer,
            "speed_field": "assumed_speed_kmh",
            "class_field_used": class_field,
            "features_updated": updated,
            "features_left_unchanged": skipped_existing,
            "note": "Speeds are a fixed assumption table by road class, not measured data for this "
                    "network -- pass speed_field='assumed_speed_kmh' to calculate_service_area/"
                    "travel_time_matrix/optimize_delivery_route to use it, and tell the user travel "
                    "times are estimates.",
        }
        if country_overrides:
            result["country_used"] = country_code
            result["note"] += f" Scaled to {country_code}'s real legal urban/rural/motorway defaults."
        elif country_code:
            result["note"] += f" country='{country_code}' isn't in the curated table (see COUNTRY_SPEED_TIERS_KMH); used the generic global defaults instead."
        if unknown_classes:
            result["unknown_road_classes"] = sorted(unknown_classes)
            result["note"] += f" {len(unknown_classes)} road class value(s) not in the table used default_speed_kmh={default_speed_kmh}."
        return result
    except Exception as e:
        if network.isEditable():
            network.rollBack()
        return {"error": f"estimate_road_speeds failed: {e}"}
