# -*- coding: utf-8 -*-
"""
Humanitarian Analysis Contract for Cartogen AI.

Enforces a formal contract between the natural-language assistant / user intent
and PyQGIS humanitarian tools, preventing the LLM from silently hallucinating
critical humanitarian parameters (e.g. travel costs, distance thresholds, weights,
poverty cutoffs) or guessing missing geographic/sectoral assumptions.

Workflow:
User Request -> Intent Parser -> HumanitarianAnalysisContract -> Validator -> GIS Tools -> Output Validator
"""

import dataclasses
from typing import Dict, List, Optional, Any, Set


@dataclasses.dataclass
class GeographicScope:
    country_iso3: Optional[str] = None
    admin_level: Optional[int] = None
    layer_name: Optional[str] = None
    pcode_field: Optional[str] = None
    admin_name_field: Optional[str] = None
    aoi_bounds: Optional[List[float]] = None  # [min_lon, min_lat, max_lon, max_lat]


@dataclasses.dataclass
class PopulationContext:
    population_group: str = "total"  # e.g., 'total', 'idps', 'refugees', 'returnees', 'host'
    population_source: Optional[str] = None  # e.g., 'worldpop', 'census', 'unhcr'
    raster_layer: Optional[str] = None
    vector_field: Optional[str] = None


@dataclasses.dataclass
class HumanitarianContext:
    cluster_sector: Optional[str] = None  # e.g., 'wash', 'health', 'food_security', 'multi_sector'
    indicator_names: List[str] = dataclasses.field(default_factory=list)
    analysis_period: Optional[str] = None  # e.g., '2026-Q1', 'HNO 2026'
    unit_of_measurement: Optional[str] = None  # e.g., 'people', 'households', 'percent'


@dataclasses.dataclass
class MethodologicalRules:
    method: str  # e.g., 'jiaf_mosaic', 'service_area_hull', 'weighted_composite', 'presence_gap'
    thresholds: Dict[str, Any] = dataclasses.field(default_factory=dict)
    weights: Dict[str, float] = dataclasses.field(default_factory=dict)
    aggregation_rule: str = "none"  # e.g., 'sum', 'max', 'weighted_mean', 'mosaic'
    tie_breaker_rule: str = "lowest_fid_centroid"
    suppress_min_n: Optional[int] = None


@dataclasses.dataclass
class ExpectedDeliverables:
    analytical_layer: bool = True
    output_format: str = "gpkg"  # Canonical format: 'gpkg' (or 'geojson', 'shp')
    map_symbology: bool = True
    dashboard_kpis: bool = False
    print_layout: bool = False
    export_deliverable: bool = False


@dataclasses.dataclass
class HumanitarianAnalysisContract:
    objective: str  # e.g., 'population_access_gap', 'people_in_need', 'presence_gap', 'damage_exposure'
    geography: GeographicScope
    humanitarian_context: HumanitarianContext
    methodology: MethodologicalRules
    population: Optional[PopulationContext] = None
    expected_outputs: ExpectedDeliverables = dataclasses.field(default_factory=ExpectedDeliverables)
    
    # Critical parameters that MUST be confirmed by user or authoritative specification
    unresolved_parameters: List[str] = dataclasses.field(default_factory=list)
    clarification_prompt: Optional[str] = None

    def validate(self) -> Dict[str, Any]:
        """
        Validates contract completeness before allowing GIS execution.
        Returns a dict with 'valid': bool, 'errors': list, 'needs_clarification': bool.
        """
        errors = []
        needs_clarification = False

        # 1. Check for unresolved parameters
        if self.unresolved_parameters:
            needs_clarification = True
            return {
                "valid": False,
                "needs_clarification": True,
                "unresolved_parameters": self.unresolved_parameters,
                "clarification_prompt": self.clarification_prompt or (
                    f"The analysis objective '{self.objective}' requires clarification on: "
                    f"{', '.join(self.unresolved_parameters)}. Please specify these parameters "
                    "rather than relying on default assumptions."
                ),
            }

        # 2. Objective-specific parameter requirements
        if self.objective == "population_access_gap":
            if "travel_cost" not in self.methodology.thresholds and "travel_distance_km" not in self.methodology.thresholds:
                errors.append("Objective 'population_access_gap' requires a locally-determined travel_cost (minutes) or travel_distance_km threshold (Rule 37).")
                self.unresolved_parameters.append("travel_cost_or_distance")

        elif self.objective == "calculate_severity_index":
            if not self.humanitarian_context.indicator_names:
                errors.append("Objective 'calculate_severity_index' requires at least one explicit indicator field.")
                self.unresolved_parameters.append("indicator_names")

        elif self.objective == "presence_gap":
            if not self.geography.pcode_field:
                # Warning: name joins are discouraged for presence-gap analysis
                errors.append("Presence gap analysis strongly requires a P-code join field to prevent transliteration dropped gaps.")

        if errors or self.unresolved_parameters:
            return {
                "valid": False,
                "needs_clarification": len(self.unresolved_parameters) > 0,
                "errors": errors,
                "unresolved_parameters": self.unresolved_parameters,
            }

        return {"valid": True, "needs_clarification": False, "errors": []}


def check_contract_for_tool(tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Mandatory Execution Gate for Humanitarian Analytical Tools.
    Blocks tool execution if essential humanitarian parameters are missing or ambiguous,
    forcing the agent to halt and request user clarification rather than hallucinating parameters.
    """
    if tool_name == "population_access_gap":
        # Rule 37: Never invent a distance or travel_cost threshold
        travel_cost = arguments.get("travel_cost")
        if travel_cost is None or travel_cost == "":
            return {
                "status": "HALT_AND_CLARIFY",
                "tool_name": tool_name,
                "needs_clarification": True,
                "parameter": "travel_cost",
                "message": (
                    "Rule 37 Enforcement: No universal travel distance or time threshold exists for "
                    "population access analysis. Please specify a locally-determined travel_cost "
                    "(e.g. 30 minutes, 60 minutes) rather than using an unconfirmed assumption."
                ),
            }

    elif tool_name == "calculate_severity_index":
        indicators = arguments.get("indicator_fields") or arguments.get("indicators")
        if not indicators:
            return {
                "status": "HALT_AND_CLARIFY",
                "tool_name": tool_name,
                "needs_clarification": True,
                "parameter": "indicator_fields",
                "message": (
                    "Severity Index requires explicit specification of indicator_fields. "
                    "Please specify which vulnerability fields to include in the index."
                ),
            }

    return None


def parse_humanitarian_intent(request_text: str) -> HumanitarianAnalysisContract:
    """
    Parses a natural-language humanitarian request into a structured HumanitarianAnalysisContract.
    Extracts sector, geography, administrative level, population measure, travel thresholds, and expected deliverables.
    """
    text_lower = request_text.lower()
    
    # 1. Sector Identification
    sector = "multi_sector"
    if "health" in text_lower or "hospital" in text_lower or "clinic" in text_lower:
        sector = "health"
    elif "wash" in text_lower or "water" in text_lower or "sanitation" in text_lower:
        sector = "wash"
    elif "food" in text_lower or "nutrition" in text_lower or "famine" in text_lower:
        sector = "food_security"
    elif "shelter" in text_lower or "nfi" in text_lower:
        sector = "shelter"
    elif "protection" in text_lower or "gbv" in text_lower:
        sector = "protection"

    # 2. Administrative Level
    admin_level = None
    import re
    adm_match = re.search(r"admin\s*([0-4])|adm\s*([0-4])|level\s*([0-4])", text_lower)
    if adm_match:
        for g in adm_match.groups():
            if g is not None:
                admin_level = int(g)
                break

    # 3. Objective & Threshold Extraction
    objective = "general_analysis"
    thresholds = {}
    unresolved = []

    if "access" in text_lower or "outside" in text_lower or "reach" in text_lower:
        objective = "population_access_gap"
        # Extract travel threshold (e.g., '60-minute', '60 minutes', '30 min', '5 km')
        min_match = re.search(r"(\d+)\s*[- ]*(minute|min)", text_lower)
        dist_match = re.search(r"(\d+)\s*[- ]*(km|kilometer)", text_lower)
        if min_match:
            thresholds["travel_cost"] = float(min_match.group(1))
            thresholds["travel_unit"] = "minutes"
        elif dist_match:
            thresholds["travel_distance_km"] = float(dist_match.group(1))
            thresholds["travel_unit"] = "km"
        else:
            unresolved.append("travel_cost_or_distance")

    elif "people in need" in text_lower or "pin" in text_lower:
        objective = "people_in_need"
    elif "severity" in text_lower:
        objective = "calculate_severity_index"
    elif "presence" in text_lower or "3w" in text_lower or "4w" in text_lower:
        objective = "presence_gap"

    # 4. Expected Deliverables
    has_map = "map" in text_lower
    has_stats = "statistics" in text_lower or "figures" in text_lower or "summary" in text_lower or "numbers" in text_lower
    has_dash = "dashboard" in text_lower or "interactive" in text_lower
    has_layout = "layout" in text_lower or "print" in text_lower or "pdf" in text_lower

    deliverables = ExpectedDeliverables(
        analytical_layer=True,
        output_format="gpkg",
        map_symbology=has_map or True,
        dashboard_kpis=has_dash or has_stats,
        print_layout=has_layout,
        export_deliverable=True
    )

    contract = HumanitarianAnalysisContract(
        objective=objective,
        geography=GeographicScope(
            admin_level=admin_level,
        ),
        humanitarian_context=HumanitarianContext(
            cluster_sector=sector,
            unit_of_measurement="population" if "pop" in text_lower else "units"
        ),
        methodology=MethodologicalRules(
            method="service_area_hull" if objective == "population_access_gap" else "standard",
            thresholds=thresholds,
        ),
        expected_outputs=deliverables,
        unresolved_parameters=unresolved
    )
    return contract


def generate_analysis_id(contract: HumanitarianAnalysisContract) -> str:
    """
    Generates a deterministic analysis lineage ID and hash:
    HUM-YYYYMMDD-<HASH6>
    """
    import datetime
    import hashlib
    import json

    date_str = datetime.datetime.now().strftime("%Y%m%d")
    raw = f"{contract.objective}|{contract.geography.admin_level}|{contract.humanitarian_context.cluster_sector}|{json.dumps(contract.methodology.thresholds, sort_keys=True)}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6].upper()
    return f"HUM-{date_str}-{h}"


