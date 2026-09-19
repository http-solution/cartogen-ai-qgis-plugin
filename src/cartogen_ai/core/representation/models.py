# -*- coding: utf-8 -*-
"""
Representation Planner Models for Cartogen AI.

Typed data classes capturing:
- Field semantic profiles (nominal, count, rate, datetime, directional)
- Layer semantic profiles (geometry, density, overlap ratio, cardinality, skewness)
- Representation candidate scores and definitions
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldSemanticProfile:
    name: str
    semantic_type: str  # 'nominal', 'ordered_status', 'positive_quantity', 'rate_percentage', 'datetime', 'directional', 'identifier'
    distinct_count: int = 0
    missing_percent: float = 0.0
    is_numeric: bool = False
    distribution: Optional[str] = None  # 'normal', 'right_skewed', 'uniform', 'bimodal', 'power_law'
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    skewness: Optional[float] = None
    sample_values: List[Any] = field(default_factory=list)


@dataclass
class LayerSemanticProfile:
    layer_name: str
    layer_type: str  # 'vector', 'raster', 'mesh', 'pointcloud', 'vectortile', 'annotation'
    geometry: Optional[str] = None  # 'point', 'line', 'polygon', 'raster', 'unknown'
    feature_count: int = 0
    extent_type: str = "regional"  # 'local', 'regional', 'national', 'global'
    spatial_density: str = "medium"  # 'low', 'medium', 'high', 'extreme'
    overlap_ratio: float = 0.0  # Fraction of features sharing bounding-box overlap (0.0 - 1.0)
    crs_authid: str = "EPSG:4326"
    is_geographic: bool = True
    fields: Dict[str, FieldSemanticProfile] = field(default_factory=dict)
    raster_bands: int = 0
    raster_data_type: Optional[str] = None  # 'elevation_dem', 'multiband_rgb', 'categorical', 'index_ndvi'


@dataclass
class CandidateScore:
    total_score: float
    semantic_fit: float
    geometry_fit: float
    scale_fit: float
    density_fit: float
    statistical_honesty: float
    readability: float
    accessibility: float
    clutter_risk: float
    misleading_risk: float


@dataclass
class RepresentationCandidate:
    id: str  # e.g. 'point_cluster', 'proportional_symbol', 'choropleth_rate', 'heatmap'
    label: str
    renderer_type: str  # 'cluster', 'displacement', 'proportional', 'categorized', 'graduated', 'heatmap', 'relief', 'single'
    target_field: Optional[str] = None
    configuration: Dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    warnings: List[str] = field(default_factory=list)
    score: Optional[CandidateScore] = None
