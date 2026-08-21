# -*- coding: utf-8 -*-
"""
Makes tests/ a proper package and puts src/ on sys.path before any test
module imports from cartogen_ai.core.* -- mirrors the same bootstrap in the
repo root __init__.py (see its comment for why this is needed). Unlike that
one, this path IS exercised every time the test suite runs (including in
CI), so if this bootstrap is wrong the test suite itself won't collect --
there's no separate "trust me" claim needed here the way there is for the
QGIS runtime path.
"""
import os
import sys

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
