# -*- coding: utf-8 -*-
"""
Processing Provider package for Cartogen AI.
Provides native QGIS Processing algorithms callable via GUI Processing Toolbox,
Graphical Model Designer, batch processing, and headless qgis_process CLI.
"""

from .provider import (
    CartogenProcessingProvider,
    OptimalHubSitingAlgorithm,
    CalculateServiceAreaAlgorithm,
)

__all__ = [
    "CartogenProcessingProvider",
    "OptimalHubSitingAlgorithm",
    "CalculateServiceAreaAlgorithm",
]
