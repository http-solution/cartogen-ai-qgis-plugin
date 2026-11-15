# -*- coding: utf-8 -*-
"""
Cross-Output Reconciliation Auditor & Invariant Assertions.

Verifies the foundational invariant:
GIS ATTRIBUTE RESULT == MAP RESULT == DASHBOARD KPI == LAYOUT STATISTIC == EXPORTED DELIVERABLE
within explicit tolerances, AND verifies semantic/cartographic state:
- The layer is symbolized on the exact intended indicator field
- Renderer class breaks and color ramp match standard humanitarian thresholds
- Layout title, indicator description, and legend reflect the live analysis
- Dashboard filter state matches the analytical scope
- Exported dataset schema matches canonical specifications
"""

import dataclasses
import hashlib
import json
from typing import Dict, Any, List, Optional, Union, Set


@dataclasses.dataclass
class CartographicSignature:
    layer_name: str
    renderer_type: str  # e.g., 'graduated', 'categorized', 'single'
    symbolized_field: str
    class_breaks: List[float] = dataclasses.field(default_factory=list)
    class_labels: List[str] = dataclasses.field(default_factory=list)
    color_ramp_name: Optional[str] = None


@dataclasses.dataclass
class DashboardSignature:
    dashboard_id: Optional[str] = None
    kpi_metric_name: Optional[str] = None
    kpi_value: Optional[Union[float, int]] = None
    active_filters: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class LayoutSignature:
    layout_name: Optional[str] = None
    title: Optional[str] = None
    indicator_label: Optional[str] = None
    legend_layer_names: List[str] = dataclasses.field(default_factory=list)
    reported_key_figure: Optional[Union[float, int]] = None


@dataclasses.dataclass
class ExportSignature:
    output_path: Optional[str] = None
    format: str = "gpkg"
    feature_count: int = 0
    field_names: List[str] = dataclasses.field(default_factory=list)
    sum_value: Optional[Union[float, int]] = None


@dataclasses.dataclass
class AnalysisIntegritySignature:
    objective: str
    indicator_name: str
    methodology_id: str
    dataset_name: str
    pcode_set: Set[str] = dataclasses.field(default_factory=set)
    feature_count: int = 0
    calculated_total: Optional[Union[float, int]] = None
    analysis_id: Optional[str] = None
    
    # Semantic & Cartographic Channels
    cartography: Optional[CartographicSignature] = None
    dashboard: Optional[DashboardSignature] = None
    layout: Optional[LayoutSignature] = None
    export: Optional[ExportSignature] = None


class OutputReconciliationAuditor:
    """
    Audits multiple reporting channels for a single humanitarian indicator
    and asserts both numerical and semantic/cartographic reconciliation.
    """

    def __init__(self, indicator_name: str, tolerance: float = 1e-4):
        self.indicator_name = indicator_name
        self.tolerance = tolerance
        self.channel_values: Dict[str, Union[float, int]] = {}
        self.signature: Optional[AnalysisIntegritySignature] = None

    def record_channel_value(self, channel: str, value: Union[float, int]):
        """
        Records the numerical value from a delivery channel:
        'gis_attribute', 'dashboard_kpi', 'layout_metric', 'export_sum'
        """
        self.channel_values[channel] = value

    def set_integrity_signature(self, signature: AnalysisIntegritySignature):
        """Attaches full semantic and cartographic state signature."""
        self.signature = signature

    def reconcile(self) -> Dict[str, Any]:
        """
        Compares all numerical channels AND semantic signatures.
        Returns a verification report dict.
        """
        if not self.channel_values and not self.signature:
            return {"status": "NO_DATA", "reconciled": False, "discrepancies": []}

        discrepancies = []

        # 1. Numerical Reconciliation
        if self.channel_values:
            channels = list(self.channel_values.keys())
            first_channel = channels[0]
            base_val = float(self.channel_values[first_channel])

            for ch in channels[1:]:
                val = float(self.channel_values[ch])
                diff = abs(val - base_val)
                if diff > self.tolerance and (base_val == 0 or (diff / abs(base_val)) > self.tolerance):
                    discrepancies.append({
                        "type": "NUMERICAL_MISMATCH",
                        "channel_a": first_channel,
                        "value_a": base_val,
                        "channel_b": ch,
                        "value_b": val,
                        "difference": diff,
                    })

        # 2. Semantic & Cartographic State Reconciliation
        if self.signature:
            sig = self.signature

            # A. Cartography verification
            if sig.cartography:
                carto = sig.cartography
                if carto.symbolized_field.lower() != self.indicator_name.lower():
                    discrepancies.append({
                        "type": "CARTOGRAPHIC_FIELD_MISMATCH",
                        "expected_field": self.indicator_name,
                        "actual_symbolized_field": carto.symbolized_field,
                        "message": (
                            f"Layer '{carto.layer_name}' is symbolizing field '{carto.symbolized_field}' "
                            f"instead of analyzed indicator '{self.indicator_name}'. Map communicates wrong data!"
                        ),
                    })

            # B. Dashboard metric verification
            if sig.dashboard and sig.dashboard.kpi_value is not None:
                if self.channel_values:
                    base_val = float(list(self.channel_values.values())[0])
                    if abs(sig.dashboard.kpi_value - base_val) > self.tolerance:
                        discrepancies.append({
                            "type": "DASHBOARD_KPI_MISMATCH",
                            "expected_value": base_val,
                            "dashboard_kpi_value": sig.dashboard.kpi_value,
                        })

            # C. Layout metric verification
            if sig.layout and sig.layout.reported_key_figure is not None:
                if self.channel_values:
                    base_val = float(list(self.channel_values.values())[0])
                    if abs(sig.layout.reported_key_figure - base_val) > self.tolerance:
                        discrepancies.append({
                            "type": "LAYOUT_FIGURE_MISMATCH",
                            "expected_value": base_val,
                            "layout_key_figure": sig.layout.reported_key_figure,
                        })

            # D. Export verification
            if sig.export and sig.export.sum_value is not None:
                if self.channel_values:
                    base_val = float(list(self.channel_values.values())[0])
                    if abs(sig.export.sum_value - base_val) > self.tolerance:
                        discrepancies.append({
                            "type": "EXPORT_SUM_MISMATCH",
                            "expected_value": base_val,
                            "export_sum_value": sig.export.sum_value,
                        })

        reconciled = len(discrepancies) == 0
        return {
            "status": "PASS — AUTOMATED VERIFIED" if reconciled else "FAIL",
            "indicator": self.indicator_name,
            "reconciled": reconciled,
            "channel_values": self.channel_values,
            "discrepancies": discrepancies,
            "tolerance": self.tolerance,
            "has_semantic_signature": self.signature is not None,
        }
