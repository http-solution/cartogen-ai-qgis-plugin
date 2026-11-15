"""One-line validity check for a freshly created layer.

The PyQGIS cookbook (loading layers) says to test isValid() after every layer is created: QgsVectorLayer never raises on a bad
URI or CRS, it just returns an invalid layer whose dataProvider() is None, so the next line fails with an AttributeError that
says nothing useful. A function, not an inline `if`, so the long tool functions do not gain a branch (ruff C901, max 25)."""


def require_valid_layer(layer):
    """Return `layer`, or raise ValueError (the tool dispatcher turns it into an error result) when QGIS could not create it."""
    if not layer.isValid():
        raise ValueError("QGIS could not create a temporary (memory) layer here; check the input layer's coordinate system.")
    return layer


def degrees_value_problem(layer, value, label):
    """Error text when `value` (a distance, radius, tolerance or cell size taken in the layer's own CRS units) is implausible for a layer in
    latitude/longitude, else None. Pure apart from reading the CRS.

    Self-audit round 2 (2026-10-26), the same class as the route-risk buffer that applied 500 as 500 degrees (1.18.2 hand test C9): a
    layer in EPSG:4326 measures in degrees, so "1 km" typed as 1000 moves points 1000 degrees (off the globe) and 1 is already 111 km.
    One degree or more is never what a user means by a blur radius, kernel radius, cell size or simplification tolerance here, so it is
    refused with the conversion. `is True` keeps a test double's auto-attributes from reading as geographic."""
    try:
        crs = layer.crs()
        if crs.isValid() is not True or crs.isGeographic() is not True:
            return None
        number = float(value)
    except (TypeError, ValueError, AttributeError):
        return None
    if abs(number) >= 1.0:
        return (f"'{layer.name()}' is in latitude/longitude ({crs.authid()}), so {label} is measured in DEGREES and {number:g} degrees is about "
                f"{number * 111:,.0f} km. Give {label} in degrees (0.01 is about 1.1 km, 0.001 about 110 m), or reproject the layer to a "
                "projected CRS such as the local UTM zone and give metres.")
    return None


def empty_fetch_result(layer_name, what, filters=None):
    """The reply for a data fetch that matched nothing when no layer of that name exists yet: success, zero items, and NO layer. 1.18.4 smoke A10:
    a UCDP request for a year with no events left an empty 'UCDP Conflict Events - Yemen 2025' layer in the project, one more unrequested layer (DEF-3).
    A layer that already exists is still replaced as before, so re-running a fetch that now matches nothing empties it."""
    return {"success": True, "layer_name": layer_name, "event_count": 0, "layer_added": False,
            "message": f"No {what} matched{' (' + filters + ')' if filters else ''}, so no layer '{layer_name}' was added. Say so plainly; do not create an empty layer or retry with other filters unless asked."}

