# Cartogen AI — License Compliance Audit

**Audit Date:** 2026-08-08 (dependency matrix; updated 2026-08-13 for pdfplumber/matplotlib and
new external API endpoints; updated 2026-08-14 for folium/branca and the Microsoft Global ML
Building Footprints data source); license basis reaffirmed 2026-08-11.
**Scope:** Runtime Python packages, QGIS API linkages, external web REST endpoints, and plugin source code.

---

## 1. Plugin Source Code License

The Cartogen AI plugin source code is released under the **GNU General Public
License v2 (GPL-v2)** or later, in compliance with the QGIS Plugin Architecture
Guidelines and PyQGIS's own GPL-v2 licensing.

A proprietary/all-rights-reserved license was considered for a period on
2026-08-11, specifically to weigh commercializing the plugin's code directly. That
path was deliberately not taken: PyQGIS modules (`qgis.core`, `qgis.gui`,
`qgis.utils`) are GPL-v2 components this plugin imports directly at runtime, and
whether that creates an obligation for the plugin itself to be GPL-compatible was
judged a genuine, unresolved legal question not worth betting a commercial license
on. Monetization is services-based instead (paid support, hosting/managed
deployment, a SaaS layer, custom integration work) — see the plugin's business
proposal document (not part of this repository) for details. This removes the
licensing question entirely rather than resolving it.

- **License File:** [LICENSE](LICENSE)
- **QGIS API Linkage:** PyQGIS modules are imported dynamically at runtime inside
  QGIS, not statically linked — but since the plugin is GPL-v2 itself, this
  distinction no longer carries any licensing risk either way.

---

## 2. Third-Party Dependency License Matrix

| Package | Version Range | License | Linking Type | Compliance Status |
|---|---|---|---|---|
| `pypdf` | ^3.0.0 | BSD-3-Clause | Isolated runtime subprocess / import | **Compliant** |
| `python-docx` | ^0.8.11 | MIT | Isolated runtime import | **Compliant** |
| `openpyxl` | ^3.0.0 | MIT | Isolated runtime import | **Compliant** |
| `pandas` | ^2.0.0 | BSD-3-Clause | Isolated runtime import | **Compliant** |
| `duckduckgo-search` | ^6.0.0 | MIT | Isolated HTTP client import | **Compliant** |
| `requests` | ^2.28.0 | Apache-2.0 | Isolated HTTP client import | **Compliant** |
| `pdfplumber` | unpinned | MIT | Isolated runtime import | **Compliant** |
| `matplotlib` | unpinned | Matplotlib License (PSF-derived, BSD-style permissive) | Isolated runtime import | **Compliant** |
| `folium` | unpinned | MIT | Isolated runtime import | **Compliant** |
| `branca` | unpinned | MIT | Isolated runtime import (folium's own dependency, also imported directly for choropleth colormaps) | **Compliant** |

---

## 3. External API Services

All external REST APIs queried by the plugin operate over HTTPS standard network endpoints without linking binary code:
- **OpenRouter API**: Cloud LLM inference endpoint (HTTP JSON).
- **Google Gemini API**: Multimodal vision endpoint (HTTP JSON).
- **Ollama API**: Local REST endpoint (HTTP JSON).
- **Humanitarian Data Exchange (HDX) API**: Open Data Commons Attribution License (ODC-BY).
- **OpenStreetMap Overpass API**: Open Database License (ODbL).
- **geoBoundaries API**: Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Nominatim Geocoding API**: Open Database License (ODbL).
- **OCHA Financial Tracking Service (FTS) API**: Publicly accessible humanitarian
  funding data (api.hpc.tools) -- see fts.unocha.org for OCHA's data-use terms; not
  independently re-verified against a specific open-data license by this audit.
- **WorldPop API**: Gridded population data (hub.worldpop.org / data.worldpop.org),
  published under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Microsoft Global ML Building Footprints**: Pre-computed building footprint polygons
  (minedbuildings.z5.web.core.windows.net), published under Community Data License Agreement --
  Permissive, Version 2.0 (CDLA Permissive 2.0), confirmed 2026-08-14 against the dataset's own
  repository. Note: this dataset's license has changed at least once before (earlier
  documentation cited ODbL) -- re-verify at the source before relying on this for a formal audit
  rather than treating this as a permanent, one-time confirmation.

---

## 4. Conclusion & Audit Verification

No proprietary software, copyleft-incompatible code, or statically vendored libraries exist inside the codebase. All optional third-party Python packages are installed dynamically into the user's OSGeo4W Python environment without license conflict.
