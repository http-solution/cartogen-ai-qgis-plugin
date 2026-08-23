# Cartogen AI Workspace — Provenance and Licensing Register

**Status:** Phase 0 working register
**Owner:** HTTP-Solution / Cartogen AI

## Rule

The web platform is a new Cartogen implementation. Public QGIS workflows and standards may inform product requirements, but no QGIS source code, UI assets, branded copy, or distinctive implementation should be copied into this product without legal review.

## Reference categories

| Reference | Intended use | Copying status | Review |
|---|---|---|---|
| QGIS desktop workflows | Product research and user interviews | Ideas/workflows only | Legal review before any source reuse |
| QGIS source repository | Licence and architecture reference | No source reuse planned | Required before any component reuse |
| QGIS Server | Optional standards-compatible service integration | External service or separately reviewed component | Dependency/licence review |
| OGC API standards | API interoperability requirements | Standards implementation | Verify conformance and trademarks |
| PostGIS | Spatial persistence and indexing | Dependency/service | Licence and operational review |
| MapLibre GL JS | Browser map rendering | Dependency | Licence and attribution review |
| OpenLayers | Browser GIS/OGC capabilities | Dependency | Licence and attribution review |

## Original Cartogen assets required

- Cartogen AI logo and brand system;
- Cartogen navigation and information architecture;
- Cartogen map/workspace components;
- Cartogen AI plan/confirm/execute interaction;
- Cartogen sector templates;
- Cartogen report templates;
- Cartogen copy and help content;
- Cartogen iconography or approved open icon set.

## Evidence to retain

- research links and access dates;
- screenshots used only for user research, not copied into production;
- architecture decisions;
- dependency manifests and licences;
- generated or original design files;
- code provenance notes;
- legal review decisions;
- attribution notices;
- source release obligations.

## Red lines

- Do not call the product QGIS Web or imply QGIS endorsement.
- Do not copy QGIS logos or product branding.
- Do not copy QGIS source files into the Cartogen web tree without a reviewed licence plan.
- Do not copy QGIS interface text or distinctive layout as a literal clone.
- Do not remove licence notices from dependencies.
- Do not claim the Cartogen web platform is QGIS unless it actually incorporates and complies with the relevant reviewed components.
