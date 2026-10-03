# -*- coding: utf-8 -*-
"""
Deterministic hydrologic engineering checks and calculations (watershed / peak-flow requests).

Why this module exists: a live request -- "determine watershed area, steam length, h, slope, return period 20 year, intensity,
tc, and peak flow at this location 32° 1'47.39"N, 35°48'21.00"E" -- was answered without any of the inputs such numbers
depend on. The task matcher picked "Map conflict intensity" from the word "intensity", the router offered unrelated incident
tools, nothing converted the DMS coordinate in code, and nothing defined H, told the longest hydraulic flow path apart from
total stream length, tied the rainfall intensity's duration to Tc, or refused to guess. A coordinate and a return period cannot
determine a watershed, an IDF intensity, a runoff coefficient or a discharge: those need a DEM-derived basin and locally
authoritative design inputs.

What it does and does NOT do, stated plainly (CONTRIBUTING.md: say shipped vs unverified):
  * It converts DMS, checks that the inputs are explicit, and computes slope, Kirpich Tc and the Rational Method discharge
    from numbers the caller supplies.
  * It does NOT delineate a basin, build a flow path or sample a DEM. That GIS phase needs a loaded DEM and a hydrology
    provider and is not implemented here, so none of it is verified in a live QGIS session.
  * Every result is labelled preliminary and subject to the governing local drainage standard.

The equations are the standard published ones (FHWA HDS-2 / HDS-4, USDA-NRCS NEH 630 ch. 15); see
docs/HYDROLOGY_ENGINEERING_TOOLS_2026-10-04.md for the references and the original finding.
"""

import math
import re

from .registry import register_tool


_DMS_COMPONENT = re.compile(
    r"(?P<degrees>\d{1,3})\s*[°º]\s*"
    r"(?P<minutes>\d{1,2})\s*['′]\s*"
    r"(?P<seconds>\d{1,2}(?:\.\d+)?)\s*(?:[\"″])?\s*"
    r"(?P<hemisphere>[NSEW])",
    re.IGNORECASE,
)

# Area limits quoted in the warnings below. 0.8 km2 = 80 ha (FHWA HDS-4: Rational Method for highway drainage); 0.453 km2 = 112
# acres, the upper end of the data Kirpich's relation was originally fitted to (FHWA HDS-2).
RATIONAL_AREA_LIMIT_KM2 = 0.8
KIRPICH_CALIBRATION_AREA_KM2 = 0.453

# The IDF duration the caller reads must match the computed Tc: within 10%, but never tighter than a minute (curves are not
# read to the second).
_TC_MATCH_FRACTION = 0.10
_TC_MATCH_MIN_MINUTES = 1.0


def _finite_number(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number, not a boolean.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


def _dms_to_decimal(match):
    degrees = int(match.group("degrees"))
    minutes = int(match.group("minutes"))
    seconds = float(match.group("seconds"))
    hemisphere = match.group("hemisphere").upper()
    maximum = 90 if hemisphere in {"N", "S"} else 180
    # Compare the whole value, not just the degrees: 90°30'N has degrees == 90 but is past the pole, and the first version of
    # this check accepted it.
    value = degrees + minutes / 60.0 + seconds / 3600.0
    if minutes >= 60 or seconds >= 60 or value > maximum:
        raise ValueError(f"Invalid DMS coordinate component: {match.group(0)!r}.")
    return -value if hemisphere in {"S", "W"} else value, hemisphere


def parse_dms_location_text(location):
    """(longitude, latitude) in decimal WGS84 degrees from a two-component DMS string. Pure; raises ValueError."""
    matches = list(_DMS_COMPONENT.finditer(str(location or "")))
    if len(matches) != 2:
        raise ValueError(
            "location must contain one latitude and one longitude in DMS form, "
            "for example 32° 1'47.39\"N, 35°48'21.00\"E."
        )
    values = [_dms_to_decimal(match) for match in matches]
    latitude = next((value for value, hemi in values if hemi in {"N", "S"}), None)
    longitude = next((value for value, hemi in values if hemi in {"E", "W"}), None)
    if latitude is None or longitude is None:
        raise ValueError("location must contain one N/S component and one E/W component.")
    return longitude, latitude


def kirpich_tc_minutes(length_m, slope_m_per_m):
    """Kirpich channel-flow time of concentration in minutes: 0.0195 * L^0.77 * S^-0.385 (L in metres, S in m/m). Pure."""
    return 0.0195 * (length_m ** 0.77) * (slope_m_per_m ** -0.385)


def rational_peak_flow_m3_s(coefficient, intensity_mm_h, area_km2):
    """Rational Method discharge Q = 0.278 * C * i * A for i in mm/h and A in km2, giving m3/s. Pure."""
    return 0.278 * coefficient * intensity_mm_h * area_km2


@register_tool(
    "parse_dms_location",
    "Convert a user-supplied latitude/longitude in degrees-minutes-seconds (DMS) to an exact "
    "WGS84 decimal-degree outlet coordinate. Use this instead of manually converting DMS. This "
    "only normalizes the coordinate; it does not delineate a watershed or infer elevations.",
    {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "DMS latitude and longitude, including N/S and E/W hemispheres.",
            }
        },
        "required": ["location"],
    },
)
def parse_dms_location(location):
    try:
        longitude, latitude = parse_dms_location_text(location)
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "success": True,
        "crs": "EPSG:4326",
        "longitude": round(longitude, 10),
        "latitude": round(latitude, 10),
        "coordinate_order": "longitude, latitude",
    }


@register_tool(
    "assess_watershed_hydrology_request",
    "Preflight a watershed/peak-flow engineering request before any result is reported. It "
    "normalizes a DMS outlet and identifies the measured data and cited design inputs still "
    "required. A coordinate plus return period is insufficient: never invent a DEM-derived basin, "
    "IDF intensity, runoff coefficient, elevation drop, flow length, Tc, or peak flow. Call this "
    "first for coordinate-only watershed requests.",
    {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "Outlet location in DMS form."},
            "return_period_years": {
                "type": "number",
                "description": "Requested design return period in years.",
            },
            "dem_source": {
                "type": "string",
                "description": "Loaded DEM layer or authoritative DEM dataset and resolution, if available.",
            },
            "idf_source": {
                "type": "string",
                "description": "Local authoritative IDF station/curve/publication, if available.",
            },
            "runoff_coefficient": {
                "type": "number",
                "description": "Locally justified Rational Method runoff coefficient C, if available.",
            },
        },
        "required": ["location", "return_period_years"],
    },
)
def assess_watershed_hydrology_request(
    location,
    return_period_years,
    dem_source=None,
    idf_source=None,
    runoff_coefficient=None,
):
    try:
        longitude, latitude = parse_dms_location_text(location)
        period = _finite_number(return_period_years, "return_period_years")
        if period <= 0:
            raise ValueError("return_period_years must be greater than zero.")
        coefficient = None
        if runoff_coefficient is not None:
            coefficient = _finite_number(runoff_coefficient, "runoff_coefficient")
            if not 0 <= coefficient <= 1:
                raise ValueError("runoff_coefficient must be between 0 and 1.")
    except ValueError as exc:
        return {"error": str(exc)}

    missing = []
    if not str(dem_source or "").strip():
        missing.append("DEM source, horizontal CRS, vertical datum, and cell size")
    if not str(idf_source or "").strip():
        missing.append(
            f"authoritative local {period:g}-year IDF curve; intensity duration must equal Tc"
        )
    if coefficient is None:
        missing.append("locally justified Rational Method runoff coefficient C")

    return {
        "status": "INPUT_REQUIRED" if missing else "READY_FOR_GIS_DELINEATION",
        "outlet": {
            "crs": "EPSG:4326",
            "longitude": round(longitude, 10),
            "latitude": round(latitude, 10),
        },
        "return_period_years": period,
        "missing_inputs": missing,
        "required_gis_measurements": [
            "snap the outlet to the derived drainage network with a documented tolerance",
            "hydrologically condition the DEM and delineate the upstream basin",
            "measure basin area in a suitable projected/equal-area CRS",
            "measure the longest hydraulic flow path, not total stream-network length",
            "sample upstream and outlet elevations in the DEM vertical datum",
        ],
        "definitions": {
            "H": "upstream elevation minus outlet elevation along the selected hydraulic flow path",
            "channel_slope": "H divided by longest hydraulic flow-path length (m/m)",
            "Tc": "travel time from the hydraulically most remote point to the outlet",
            "intensity": "local IDF intensity for the selected return period and duration equal to Tc",
        },
        "calculation_tool": "calculate_rational_watershed_peak_flow",
        "gis_phase_note": (
            "This plugin does not yet delineate the basin or measure the flow path. Those measurements need a loaded "
            "DEM and a hydrology provider; do not report area, flow length or elevations until they are measured."
        ),
        "engineering_note": (
            "The Rational Method is a preliminary small-catchment method. Confirm its applicability "
            "and every design input against the governing local drainage standard."
        ),
    }


@register_tool(
    "calculate_rational_watershed_peak_flow",
    "Calculate H, main-channel slope, Kirpich channel-flow Tc, and Rational Method peak discharge "
    "from explicit measured inputs. First call it WITHOUT rainfall_intensity_mm_h to get Tc, then read "
    "the cited local IDF curve at that duration and call again with the intensity, its duration, its "
    "source and the runoff coefficient. It does not delineate a watershed and must never receive "
    "guessed area, length, elevations, intensity, or C.",
    {
        "type": "object",
        "properties": {
            "area_km2": {"type": "number", "description": "Delineated watershed area in km²."},
            "flow_length_km": {
                "type": "number",
                "description": "Longest hydraulic flow-path/main-channel length in km; not total stream length.",
            },
            "upstream_elevation_m": {
                "type": "number",
                "description": "DEM elevation at the selected hydraulically remote upstream point in metres.",
            },
            "outlet_elevation_m": {
                "type": "number",
                "description": "DEM elevation at the snapped outlet in metres, using the same vertical datum.",
            },
            "return_period_years": {"type": "number", "description": "Design return period in years."},
            "rainfall_intensity_mm_h": {
                "type": "number",
                "description": "Local IDF rainfall intensity in mm/h for the return period and Tc duration. Omit on the first call to get Tc.",
            },
            "intensity_duration_minutes": {
                "type": "number",
                "description": "Duration in minutes used to read/interpolate the supplied IDF intensity.",
            },
            "intensity_source": {
                "type": "string",
                "description": "Authoritative local IDF station, curve, publication, and edition/date.",
            },
            "runoff_coefficient": {
                "type": "number",
                "description": "Dimensionless Rational Method runoff coefficient C, locally justified.",
            },
        },
        "required": [
            "area_km2",
            "flow_length_km",
            "upstream_elevation_m",
            "outlet_elevation_m",
            "return_period_years",
        ],
    },
)
def calculate_rational_watershed_peak_flow(
    area_km2,
    flow_length_km,
    upstream_elevation_m,
    outlet_elevation_m,
    return_period_years,
    rainfall_intensity_mm_h=None,
    intensity_duration_minutes=None,
    intensity_source=None,
    runoff_coefficient=None,
):
    try:
        area = _finite_number(area_km2, "area_km2")
        length_km = _finite_number(flow_length_km, "flow_length_km")
        upstream = _finite_number(upstream_elevation_m, "upstream_elevation_m")
        outlet = _finite_number(outlet_elevation_m, "outlet_elevation_m")
        period = _finite_number(return_period_years, "return_period_years")
        if area <= 0 or length_km <= 0 or period <= 0:
            raise ValueError("Area, flow length and return period must be greater than zero.")
        elevation_drop = upstream - outlet
        if elevation_drop <= 0:
            raise ValueError("upstream_elevation_m must be greater than outlet_elevation_m.")

        length_m = length_km * 1000.0
        channel_slope = elevation_drop / length_m
        tc_minutes = kirpich_tc_minutes(length_m, channel_slope)

        design_given = [rainfall_intensity_mm_h, intensity_duration_minutes, runoff_coefficient]
        tc_only = all(v is None for v in design_given) and not str(intensity_source or "").strip()
        if not tc_only:
            intensity = _finite_number(rainfall_intensity_mm_h, "rainfall_intensity_mm_h")
            duration = _finite_number(intensity_duration_minutes, "intensity_duration_minutes")
            coefficient = _finite_number(runoff_coefficient, "runoff_coefficient")
            source = str(intensity_source or "").strip()
            if intensity <= 0 or duration <= 0:
                raise ValueError("Rainfall intensity and its duration must be greater than zero.")
            if not 0 <= coefficient <= 1:
                raise ValueError("runoff_coefficient must be between 0 and 1.")
            if not source:
                raise ValueError("intensity_source is required; an uncited rainfall intensity is not accepted.")
            tolerance = max(_TC_MATCH_MIN_MINUTES, tc_minutes * _TC_MATCH_FRACTION)
            if abs(duration - tc_minutes) > tolerance:
                raise ValueError(
                    f"IDF duration ({duration:.2f} min) does not match computed Tc "
                    f"({tc_minutes:.2f} min) within the allowed ±{tolerance:.2f} min. "
                    "Interpolate the cited IDF curve at Tc and call again."
                )
            peak_flow = rational_peak_flow_m3_s(coefficient, intensity, area)
    except ValueError as exc:
        return {"error": str(exc)}

    measurements = {
        "watershed_area_km2": area,
        "longest_hydraulic_flow_path_km": length_km,
        "upstream_elevation_m": upstream,
        "outlet_elevation_m": outlet,
        "H_elevation_drop_m": round(elevation_drop, 3),
        "channel_slope_m_per_m": round(channel_slope, 8),
        "channel_slope_percent": round(channel_slope * 100.0, 4),
    }
    equations = {
        "H": "upstream_elevation_m - outlet_elevation_m",
        "slope": "H / flow_length_m",
        "Kirpich_Tc": "0.0195 * L_m^0.77 * S^-0.385 (minutes)",
    }
    if tc_only:
        return {
            "success": True,
            "status": "TC_COMPUTED_INTENSITY_REQUIRED",
            "method": "Kirpich channel-flow Tc",
            "return_period_years": period,
            "measurements": measurements,
            "results": {"time_of_concentration_minutes": round(tc_minutes, 3)},
            "equations": equations,
            "next_step": (
                f"Read the cited local {period:g}-year IDF curve at a duration of {tc_minutes:.1f} minutes, then call "
                "again with that intensity (mm/h), the duration, the source and a justified runoff coefficient. "
                "Do not estimate the intensity."
            ),
            "design_status": "PRELIMINARY_REQUIRES_LOCAL_ENGINEERING_REVIEW",
        }

    warnings = [
        "Kirpich is an empirical channel-flow relation developed for small, well-defined drainage basins; validate it locally.",
    ]
    if area >= RATIONAL_AREA_LIMIT_KM2:
        warnings.append(
            "Area is at least 0.8 km² (80 ha), outside FHWA's recommended Rational Method limit for highway drainage; "
            "use a hydrograph/rainfall-runoff model required by the local authority."
        )
    if area > KIRPICH_CALIBRATION_AREA_KM2:
        warnings.append(
            "Area exceeds the approximately 112-acre upper end of the original Kirpich calibration dataset."
        )
    equations["Rational_Q"] = "0.278 * C * i_mm_h * A_km2 (m3/s)"
    return {
        "success": True,
        "method": "Rational Method with Kirpich channel-flow Tc",
        "return_period_years": period,
        "measurements": measurements,
        "design_inputs": {
            "rainfall_intensity_mm_h": intensity,
            "intensity_duration_minutes": duration,
            "intensity_source": source,
            "runoff_coefficient": coefficient,
        },
        "results": {
            "time_of_concentration_minutes": round(tc_minutes, 3),
            "peak_flow_m3_s": round(peak_flow, 4),
        },
        "equations": equations,
        "warnings": warnings,
        "design_status": "PRELIMINARY_REQUIRES_LOCAL_ENGINEERING_REVIEW",
    }
