"""
Representation Planning & Intelligence Engine for Cartogen AI.

Profiles datasets, determines statistical and spatial distributions, generates
and multi-criteria scores candidate cartographic representations, and applies
native QGIS renderers directly.
"""

from .models import (
    FieldSemanticProfile,
    LayerSemanticProfile,
    RepresentationCandidate,
    CandidateScore,
)
from .profiler import profile_layer
from .planner import plan_representations
from .applier import apply_representation

__all__ = [
    "CandidateScore",
    "FieldSemanticProfile",
    "LayerSemanticProfile",
    "RepresentationCandidate",
    "apply_representation",
    "plan_representations",
    "profile_layer",
]
