# Humanitarian QA/QC Smoke Live Test Plan & Execution Protocol
**Target Release Candidate:** `v1.16.0-rc22`  
**Classification:** `VERIFIED RELEASE CANDIDATE — Core Humanitarian Integrity Framework`  
**Environment:** QGIS 4.2.3, GDAL 3.x, PROJ 9.x, Python 3.12, Qt6 on Windows 11  
**Scope:** Live functional verification across UI components, map canvas, layout composition, HTML dashboards, and data export layers.

---

## 1. Scope & Objective

The objective of the Humanitarian Smoke Live Test is to validate that the complete analytical chain:
$$\text{Human Request} \to \text{Contract Interpretation} \to \text{GIS Processing} \to \text{Symbology} \to \text{Dashboard} \to \text{Print Layout} \to \text{Export}$$
executes with operational reliability, cartographic fidelity, and zero data leakage inside a live QGIS session.

---

## 2. The 10 Critical Humanitarian Live Test Workflows

### Workflow 1: Complete Positive Natural-Language Intent Translation (`GS-PROMPT-001`)
- **Action**: Submit natural-language request: *"Show the population outside 60-minute health-service access in Admin 2 areas, with a map and summary statistics."*
- **Verification**:
  - Intent parser extracts `population_access_gap`, sector `health`, admin level `2`, `travel_cost=60`.
  - No parameter hallucination; contract validates cleanly without halting.
  - Reproducible `Analysis ID` generated (`HUM-YYYYMMDD-HASH`).

### Workflow 2: Rule 37 Missing Threshold Enforcement (`GS-PROMPT-002`)
- **Action**: Submit ambiguous request: *"Calculate population access gap for health facilities in District Alpha."* (No travel threshold provided).
- **Verification**:
  - Mandatory execution gate intercepts call before processing.
  - Returns `HALT_AND_CLARIFY` card indicating Rule 37 compliance.
  - Does NOT invent arbitrary 30-min or 50-km defaults.

### Workflow 3: Joint People in Need (JIAF Mosaic Method) Map Rendering
- **Action**: Run multi-sector Joint PiN calculation over district boundaries using Mosaic rule (highest sectoral need).
- **Verification**:
  - Generates `joint_pin` attribute.
  - Applies graduated symbology with standard OCHA/JIAF color ramp.
  - Confirms zero-population and missing-data areas are not styled as high-need.

### Workflow 4: Exploratory Composite Severity Index & Disclaimer Assertion
- **Action**: Execute composite severity scoring across multi-sector vulnerabilities with indicator inversion.
- **Verification**:
  - Normalized scores (0–1) and 1–5 classes written to layer.
  - Returned payload and UI card explicitly state: `"methodological_authority_level": "TECHNICALLY VERIFIED — EXPLORATORY METHODOLOGY"`.
  - Confirms no false claims of "official JIAF standard" are displayed.

### Workflow 5: 3W Operational Presence vs Severity Gap Styling
- **Action**: Cross-reference high-severity admin units against 3W operational presence table.
- **Verification**:
  - Distinguishes between `gap` (high severity, 0 partners), `covered` ($\ge 1$ partners), and `unmatched` (P-code mismatch).
  - Categorized map style renders `gap` in high-visibility red, `covered` in muted green, and `unmatched` in dashed/distinct styling.

### Workflow 6: Road Network Reachability & Zonal Population Exposure
- **Action**: Execute network service area analysis with concave hull reach geometry.
- **Verification**:
  - Generates concave reach polygon adhering to road network.
  - Zonal intersection with population raster computes reachable population and access gap.
  - Conserves total population invariant ($\text{Reachable Pop} + \text{Gap Pop} \equiv \text{Total Pop}$).

### Workflow 7: JIAF 2 Full Traceability Chain & Consensus Override
- **Action**: Ingest 8-cluster sectoral needs, evaluate Table 3A Flag 2 (divergent sectoral needs $>30\%$), and apply recorded consensus decision.
- **Verification**:
  - Flag 2 correctly fires on outlier units.
  - Final consensus decision recorded with rationale, overwriting preliminary calculation without corrupting audit trail.

### Workflow 8: Interactive HTML Dashboard & Tile Dependency Warning
- **Action**: Generate self-contained Leaflet HTML dashboard deliverable.
- **Verification**:
  - Headline KPI matches attribute table total within zero tolerance.
  - Interactive map includes prompt notice indicating basemap tiles require internet access.

### Workflow 9: Print Layout Composition & Cartographic Invariant Check
- **Action**: Build print layout composer with map frame, legend, scale bar, and north arrow.
- **Verification**:
  - North arrow linked to map rotation.
  - Legend items render without truncating Arabic/Unicode names.
  - Layout subtitle displays `Analysis ID` and data date.

### Workflow 10: Strict Data Protection & Canonical GeoPackage Export
- **Action**: Tag point layer as `HIGHLY_SENSITIVE` and attempt raw export; apply grid snap and export derivative.
- **Verification**:
  - Raw unmasked export is strictly **BLOCKED** (`blocked_by_protection_policy=True`).
  - Obfuscated point layer exports cleanly to `.gpkg` without field truncation.
  - Shapefile export attempts emit DBF 10-character truncation and collision warnings.
