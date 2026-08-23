# Phase 0 — Cartogen AI Workspace

## Phase status

**Active:** discovery and validation
**Implementation status:** no production implementation started
**Repository:** private `CARTOGEN-AI`

## Artifacts

- `prototype/index.html` — clickable browser prototype of the Map Workspace.
- `validation-hub/index.html` — local-only candidate pipeline and Phase 0 exit-gate dashboard.
- `DESIGN_PARTNER_VALIDATION_PACK.md` — interview script, prototype tasks, measures, and gates.
- `HUMANITARIAN_PILOT_CHARTER.md` — pilot scope, data approval, and success template.
- `HUMANITARIAN_CANDIDATE_SCORING.md` — candidate qualification rubric.
- `OCHA_3W_STRUCTURED_ANALYSIS_2026-08-23.md` — private structured analysis of the public OCHA/HDX global 3W resource.
- `ARCHITECTURE_SPIKE.md` — rendering/data/processing/AI architecture experiments.
- `PROVENANCE_REGISTER.md` — QGIS inspiration, standards, dependency, and original-work record.
- `LEGAL_TRUST_REVIEW_CHECKLIST.md` — private legal, licensing, privacy, AI, and security checklist.

## Run the prototype

From the repository root:

```bash
python -m http.server 4173 --directory web-platform/phase-0/prototype
```

Open:

```text
http://127.0.0.1:4173/index.html
```

## Run the private Validation Hub

```bash
python -m http.server 4174 --directory web-platform/phase-0/validation-hub
```

Open:

```text
http://127.0.0.1:4174/index.html
```

The Validation Hub stores candidate records only in the browser's local storage and supports JSON export. Do not enter sensitive personal, beneficiary, or operational data.

## Prototype flow

1. Switch between Projects, Map, Data, Analysis, Reports, Activity, and Admin.
2. Toggle layers in the left panel.
3. Use the Cartogen AI panel on the right.
4. Select **Preview plan**.
5. Review the four-step plan.
6. Select **Run safely**.
7. Confirm that the result states no source data was modified.

## Phase 0 exit gate

Move to Phase 1 only when:

- five qualified organizations have reviewed the concept;
- three identify the same recurring humanitarian workflow;
- three can provide approved pilot data;
- two agree to pilot/design-partner activity;
- one credible funding path is identified;
- licensing/provenance objections are resolved;
- the MVP scope is stable enough to estimate.

The next requested decision is approval of the prototype direction and authorization to begin design-partner interviews and architecture spikes.
