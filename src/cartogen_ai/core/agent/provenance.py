# -*- coding: utf-8 -*-
"""
Deterministic Provenance Record for Cartogen AI -- point 17 of
docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md.

That entry flagged a REAL GAP: no JSON provenance/processing-log writer
exists anywhere in this codebase. The closest thing,
`export_tools.py`'s `_layer_provenance_entries`, only ever builds a
human-readable *text* section for a Word/Markdown report -- there was
nothing machine-readable, and nothing that folded in QA results.

Per that entry's own suggestion, this module does NOT track lineage or
QA-gate status a second time -- it reads both off the two records that
already exist and are already tracked per-layer as JSON custom
properties: `lineage.py`'s tool-execution history (the algorithm-chain
half) and `dataset_status.py`'s status/history/checks record (the
QA-results half, point 2). This module is purely the assembly step:
build_provenance_record(layer) reads both, adds the QGIS version the
record was generated under, and returns one combined dict. Writing that
dict to an actual sidecar *file* on disk is a separate, side-effecting
step deliberately left to agent/tools/provenance_tools.py's
write_provenance_sidecar -- this module stays pure computation, duck-typed
on layer.name()/customProperty() the same way lineage.py and
dataset_status.py already are, so it's directly unit-testable without a
live QGIS install (see tests/test_provenance.py).
"""

import time

try:
    from qgis.core import Qgis
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _qgis_version():
    """Returns the running QGIS version string (e.g. "3.34.5-Prizren"), or
    None when QGIS isn't available/importable -- never guessed."""
    if not QGIS_AVAILABLE:
        return None
    try:
        return Qgis.QGIS_VERSION
    except Exception:
        return None


def build_provenance_record(layer) -> dict:
    """Builds a machine-readable provenance record for a layer:

        {
            "layer_name": <str>,
            "generated_at": "<local timestamp>",
            "qgis_version": <str or None>,
            "lineage": [...],     # lineage.py's get_layer_lineage(layer)
            "qa_status": {...},   # dataset_status.py's get_dataset_status(layer)
        }

    Pure computation, no file I/O. Duck-typed on layer.name() plus
    whatever lineage.py/dataset_status.py themselves require
    (customProperty) -- a layer object missing name() entirely is
    rejected outright rather than producing a record with a guessed or
    missing identity."""
    if layer is None or not hasattr(layer, "name"):
        return {"error": "build_provenance_record requires a QGIS layer object."}

    from .lineage import get_layer_lineage
    from .dataset_status import get_dataset_status

    return {
        "layer_name": layer.name(),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "qgis_version": _qgis_version(),
        "lineage": get_layer_lineage(layer),
        "qa_status": get_dataset_status(layer),
    }
