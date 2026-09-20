# -*- coding: utf-8 -*-
"""
Layer Semantic Profiler for Cartogen AI.

Inspects live QGIS layers and extracts statistical, spatial, and semantic
metadata into a structured LayerSemanticProfile.
"""

from typing import Any, Dict, List
from .models import LayerSemanticProfile, FieldSemanticProfile

try:
    from qgis.core import (
        QgsMapLayer,
        QgsWkbTypes,
    )
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


_RATE_KEYWORDS = {
    "rate", "pct", "percent", "ratio", "density", "per_capita", "per_1000",
    "per1000", "prevalence", "index", "score", "_per_", "proportion", "share",
}

_COUNT_KEYWORDS = {
    "count", "total", "num_", "_num", "n_", "sum_", "population", "pop_",
    "cases", "incidents", "affected", "beneficiaries", "deaths", "injured", "hospitals",
}

_STATUS_KEYWORDS = {
    "status", "severity", "level", "priority", "phase", "stage", "category", "rank",
}

_DATETIME_KEYWORDS = {
    "date", "time", "datetime", "timestamp", "year", "month", "created_at", "updated_at",
}

_DIRECTION_KEYWORDS = {
    "bearing", "azimuth", "heading", "direction", "wind_dir", "flow_dir", "deg",
}


def _classify_field_semantics(name: str, values: List[Any], field_type_name: str) -> FieldSemanticProfile:
    """Classifies a field into nominal, quantity, rate, datetime, or status based on values and nomenclature."""
    name_lower = name.lower()
    total_count = len(values)
    non_null_values = [v for v in values if v is not None and str(v).strip() != ""]
    missing_pct = ((total_count - len(non_null_values)) / max(1, total_count)) * 100.0
    distinct_set = set(non_null_values)
    distinct_count = len(distinct_set)

    # Check datetime
    if any(k in name_lower for k in _DATETIME_KEYWORDS) or "date" in field_type_name.lower():
        return FieldSemanticProfile(
            name=name,
            semantic_type="datetime",
            distinct_count=distinct_count,
            missing_percent=missing_pct,
            is_numeric=False,
            sample_values=list(distinct_set)[:5],
        )

    # Check numeric
    numeric_values = []
    for v in non_null_values:
        try:
            numeric_values.append(float(v))
        except (ValueError, TypeError):
            pass

    is_numeric = len(numeric_values) == len(non_null_values) and len(numeric_values) > 0

    if not is_numeric:
        # Categorical / Status
        if any(k in name_lower for k in _STATUS_KEYWORDS) or (distinct_count <= 8 and distinct_count > 1):
            sem_type = "ordered_status" if any(k in name_lower for k in _STATUS_KEYWORDS) else "nominal"
        else:
            sem_type = "nominal"

        return FieldSemanticProfile(
            name=name,
            semantic_type=sem_type,
            distinct_count=distinct_count,
            missing_percent=missing_pct,
            is_numeric=False,
            sample_values=list(distinct_set)[:5],
        )

    # Numeric metrics: min, max, mean, skewness
    min_val = min(numeric_values)
    max_val = max(numeric_values)
    mean_val = sum(numeric_values) / len(numeric_values)
    n = len(numeric_values)

    skewness = 0.0
    if n > 5:
        variance = sum((x - mean_val) ** 2 for x in numeric_values) / n
        stddev = variance ** 0.5
        if stddev > 0:
            skewness = sum((x - mean_val) ** 3 for x in numeric_values) / (n * (stddev ** 3))

    # Distribution classification
    if abs(skewness) < 0.5:
        dist = "normal"
    elif skewness > 1.2:
        dist = "right_skewed"
    elif skewness < -1.2:
        dist = "left_skewed"
    else:
        dist = "uniform"

    # Directional check (0 - 360 bearing)
    if any(k in name_lower for k in _DIRECTION_KEYWORDS) and 0 <= min_val and max_val <= 360:
        sem_type = "directional"
    # Rate / Percentage check
    elif any(k in name_lower for k in _RATE_KEYWORDS) or (0 <= min_val and max_val <= 1.0001) or (0 <= min_val and max_val <= 100.0001 and any(not v.is_integer() for v in numeric_values)):
        sem_type = "rate_percentage"
    # Raw count check. Bug found in a code-review pass (2026-09-20): the previous
    # `all(v.is_integer() for v in numeric_values if v >= 0)` is a vacuous-truth trap -- a
    # field with ONLY negative values (e.g. elevation deltas -1.5, -2.3) filters to an empty
    # generator, and Python's all() on an empty iterable is True, so it was misclassified as
    # "positive_quantity" despite being entirely negative. Requiring min_val >= 0 up front
    # (already computed above) and checking is_integer() over the full, unfiltered
    # numeric_values makes this an honest "every value is a non-negative integer" check.
    elif any(k in name_lower for k in _COUNT_KEYWORDS) or (min_val >= 0 and all(v.is_integer() for v in numeric_values)):
        sem_type = "positive_quantity"
    else:
        sem_type = "positive_quantity" if min_val >= 0 else "nominal"

    return FieldSemanticProfile(
        name=name,
        semantic_type=sem_type,
        distinct_count=distinct_count,
        missing_percent=missing_pct,
        is_numeric=True,
        distribution=dist,
        min_value=min_val,
        max_value=max_val,
        mean_value=mean_val,
        skewness=skewness,
        sample_values=numeric_values[:5],
    )


def _estimate_spatial_density_and_overlap(layer: Any) -> (str, float):
    """Samples bounding boxes of up to 250 features to estimate point/polygon crowding and overlap ratio."""
    if not hasattr(layer, "getFeatures"):
        return "medium", 0.0

    features = []
    try:
        for i, feat in enumerate(layer.getFeatures()):
            if i >= 250:
                break
            geom = feat.geometry() if hasattr(feat, "geometry") else None
            if geom and not (hasattr(geom, "isEmpty") and geom.isEmpty()):
                bb = geom.boundingBox() if hasattr(geom, "boundingBox") else None
                if bb is not None:
                    features.append(bb)
    except Exception:
        return "medium", 0.0

    if len(features) < 2:
        return "low", 0.0

    # Calculate overall extent area
    try:
        layer_extent = layer.extent() if hasattr(layer, "extent") else None
        if layer_extent and hasattr(layer_extent, "width") and hasattr(layer_extent, "height"):
            w = layer_extent.width()
            h = layer_extent.height()
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                overall_area = w * h
                if overall_area <= 0:
                    return "extreme", 1.0
    except Exception:
        pass

    # Count pairwise overlaps
    overlap_count = 0
    total_pairs = 0
    sample_limit = min(50, len(features))
    for i in range(sample_limit):
        for j in range(i + 1, sample_limit):
            total_pairs += 1
            b1, b2 = features[i], features[j]
            try:
                if hasattr(b1, "intersects"):
                    res = b1.intersects(b2)
                    if isinstance(res, bool) and res:
                        overlap_count += 1
            except Exception:
                pass

    overlap_ratio = (overlap_count / max(1, total_pairs))

    total_count = 0
    if hasattr(layer, "featureCount"):
        cnt = layer.featureCount()
        if isinstance(cnt, (int, float)):
            total_count = cnt
    if total_count == 0:
        total_count = len(features)

    if overlap_ratio > 0.4 or total_count > 5000:
        density = "high" if overlap_ratio < 0.7 else "extreme"
    elif total_count > 500:
        density = "medium"
    else:
        density = "low"

    return density, round(overlap_ratio, 2)


def profile_layer(layer: Any) -> LayerSemanticProfile:
    """Extracts a comprehensive LayerSemanticProfile from a live or mocked QGIS layer."""
    if layer is None:
        return LayerSemanticProfile(layer_name="unknown", layer_type="vector")

    if hasattr(layer, "isValid") and not layer.isValid():
        name = layer.name() if hasattr(layer, "name") else "unknown"
        return LayerSemanticProfile(layer_name=name, layer_type="vector")

    name = layer.name() if hasattr(layer, "name") else "unknown"
    crs = "EPSG:4326"
    is_geo = True
    if hasattr(layer, "crs"):
        try:
            crs = layer.crs().authid()
            is_geo = layer.crs().isGeographic()
        except Exception:
            pass

    # 1. Raster Layer
    if (
        QGIS_AVAILABLE
        and hasattr(layer, "type")
        and hasattr(QgsMapLayer, "LayerType")
        and layer.type() == QgsMapLayer.LayerType.RasterLayer
    ):
        band_count = layer.bandCount() if hasattr(layer, "bandCount") else 1
        name_lower = name.lower()
        if any(k in name_lower for k in ("dem", "elevation", "srtm", "altitude", "dtm")):
            raster_type = "elevation_dem"
        elif any(k in name_lower for k in ("ndvi", "ndwi", "ndre", "index")):
            raster_type = "index_ndvi"
        elif band_count >= 3:
            raster_type = "multiband_rgb"
        else:
            raster_type = "categorical"

        return LayerSemanticProfile(
            layer_name=name,
            layer_type="raster",
            geometry="raster",
            feature_count=1,
            crs_authid=crs,
            is_geographic=is_geo,
            raster_bands=band_count,
            raster_data_type=raster_type,
        )

    # 2. Vector Layer
    geom_kind = "unknown"
    if hasattr(layer, "geometryType"):
        gt = layer.geometryType()
        point_enum = getattr(QgsWkbTypes, "PointGeometry", 0) if QGIS_AVAILABLE else 0
        line_enum = getattr(QgsWkbTypes, "LineGeometry", 1) if QGIS_AVAILABLE else 1
        polygon_enum = getattr(QgsWkbTypes, "PolygonGeometry", 2) if QGIS_AVAILABLE else 2
        if gt == point_enum or gt == 0:
            geom_kind = "point"
        elif gt == line_enum or gt == 1:
            geom_kind = "line"
        elif gt == polygon_enum or gt == 2:
            geom_kind = "polygon"

    feature_count = layer.featureCount() if hasattr(layer, "featureCount") else 0
    density, overlap = _estimate_spatial_density_and_overlap(layer)

    # Field analysis (sampling up to 300 features for value statistics)
    fields_dict: Dict[str, FieldSemanticProfile] = {}
    if hasattr(layer, "fields") and hasattr(layer, "getFeatures"):
        field_names = [f.name() for f in layer.fields()]
        field_types = {f.name(): f.typeName() for f in layer.fields()}
        values_per_field = {fn: [] for fn in field_names}

        for i, feat in enumerate(layer.getFeatures()):
            if i >= 300:
                break
            for fn in field_names:
                values_per_field[fn].append(feat[fn])

        for fn in field_names:
            fields_dict[fn] = _classify_field_semantics(
                fn, values_per_field[fn], field_types.get(fn, "string")
            )

    return LayerSemanticProfile(
        layer_name=name,
        layer_type="vector",
        geometry=geom_kind,
        feature_count=feature_count,
        spatial_density=density,
        overlap_ratio=overlap,
        crs_authid=crs,
        is_geographic=is_geo,
        fields=fields_dict,
    )
