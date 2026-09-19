# -*- coding: utf-8 -*-
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
    "FieldSemanticProfile",
    "LayerSemanticProfile",
    "RepresentationCandidate",
    "CandidateScore",
    "profile_layer",
    "plan_representations",
    "apply_representation",
]
