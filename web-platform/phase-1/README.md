# Cartogen AI Workspace — Phase 1 Vertical Slice

**Status:** Started
**Scope:** Pakistan humanitarian service-coverage screening
**Repository:** Private `CARTOGEN-AI`

## Run locally

From the repository root:

```bash
python -m http.server 4175 --directory web-platform/phase-1
```

Open:

```text
http://127.0.0.1:4175/index.html
```

## Included in this slice

- Cartogen AI Workspace shell;
- project/layer workspace;
- source catalogue;
- real Pakistan public-data summary loaded from `demo-data.json`;
- 714 Pakistan 3W presence records;
- 4,849 health facilities;
- accessibility source summaries;
- logistics/security/IT source metadata;
- source freshness labels;
- population/boundary compatibility warning;
- humanitarian coverage-screening question;
- AI plan preview and safe-run state;
- provenance/limitation export;
- humanitarian map/legend/status presentation.

## Rebuild demo data

```bash
python web-platform/phase-1/scripts/build_demo_data.py
```

The script reads the locally downloaded Phase 0 bundle and creates the non-sensitive summary consumed by the browser slice.

## Phase 1 acceptance checks

- [x] Project workspace loads.
- [x] Source catalogue loads.
- [x] Pakistan 3W count is data-backed.
- [x] Healthsites count is data-backed.
- [x] Freshness warnings are visible.
- [x] Compatibility warning is visible.
- [x] AI plan is reviewable before execution.
- [x] Safe-run state confirms source data is not modified.
- [x] Structured provenance report can be exported.
- [ ] Real PostGIS/API persistence.
- [ ] Real geometry rendering from uploaded layers.
- [ ] Real asynchronous spatial processing.
- [ ] Real authentication and organization permissions.
- [ ] Real PDF/print export engine.

The unchecked items are the next implementation slices; this artifact is intentionally a data-backed interface vertical slice, not production SaaS infrastructure.
