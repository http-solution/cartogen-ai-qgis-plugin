# -*- coding: utf-8 -*-
"""
Map tools compatibility module for Cartogen AI.

Re-exports canvas navigation and visibility tools from vector_tools.
"""

from .vector_tools import zoom_to_layer, toggle_visibility, _extent_to_canvas_crs

__all__ = ["zoom_to_layer", "toggle_visibility", "_extent_to_canvas_crs"]
