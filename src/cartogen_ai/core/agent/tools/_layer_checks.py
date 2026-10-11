"""One-line validity check for a freshly created layer.

The PyQGIS cookbook (loading layers) says to test isValid() after every layer is created: QgsVectorLayer never raises on a bad
URI or CRS, it just returns an invalid layer whose dataProvider() is None, so the next line fails with an AttributeError that
says nothing useful. A function, not an inline `if`, so the long tool functions do not gain a branch (ruff C901, max 25)."""


def require_valid_layer(layer):
    """Return `layer`, or raise ValueError (the tool dispatcher turns it into an error result) when QGIS could not create it."""
    if not layer.isValid():
        raise ValueError("QGIS could not create a temporary (memory) layer here; check the input layer's coordinate system.")
    return layer
