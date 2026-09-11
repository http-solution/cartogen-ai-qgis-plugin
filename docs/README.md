# docs/ index

Living references and trackers for the Cartogen AI QGIS plugin, grouped the same way as
[the main README's Documentation table](../README.md#documentation) — the two are kept in sync
by hand; if you add or move a doc, update both.

## Getting started

| Doc | Covers |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | Chat, Task Manager, memory, file attachments, settings |
| [TOOLS_REFERENCE.md](TOOLS_REFERENCE.md) | All 165 tools, auto-generated from the live registry — see `generate_tools_reference.py` below |

## Security & compliance

| Doc | Covers |
|---|---|
| [../SECURITY.md](../SECURITY.md) | Threat model, protections, adversarial testing results, known limitations |
| [GDPR_COMPLIANCE_REVIEW.docx](GDPR_COMPLIANCE_REVIEW.docx) | GDPR compliance review |
| [DPIA_SCREENING_WORKSHEET.docx](DPIA_SCREENING_WORKSHEET.docx) | Data Protection Impact Assessment screening worksheet |
| [GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md](GDPR_HOSTED_ACCOUNT_ADDENDUM_2026-09-08.md) | GDPR addendum specific to the planned hosted-account (Professional tier) data flows |

## Engineering & process

| Doc | Covers |
|---|---|
| [IMPLEMENTATION_TRACKER.md](IMPLEMENTATION_TRACKER.md) | **Start here for "what's open right now."** Living doc consolidating every genuinely open item, kept current as things resolve |
| [MASTER_TASK_REGISTRY.md](MASTER_TASK_REGISTRY.md) | The full humanitarian mapping task register plus engineering task history |
| [BUG_TRACKER.md](BUG_TRACKER.md) | Living, in-repo bug tracker — currently-open real defects only, plus the known sandbox test-artifact baseline |
| [RELEASE_SMOKE_TEST.md](RELEASE_SMOKE_TEST.md) | ~15-minute manual checklist to run in a real QGIS session before each release |
| [RELEASE_GOVERNANCE.md](RELEASE_GOVERNANCE.md) | Who can cut a release and the steps a release must follow |
| [OPERATIONS_LOG.md](OPERATIONS_LOG.md) | Dated operational narrative — incidents, sandbox quirks, decisions made in the moment |
| [QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md](QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md) | 27-point production-readiness architecture review |
| [CODE_REVIEW_2026-09-08.md](CODE_REVIEW_2026-09-08.md) | Dated code review with concrete findings |

## Product & humanitarian standards

| Doc | Covers |
|---|---|
| [PRODUCT_TIERS.md](PRODUCT_TIERS.md) | Editions/pricing tiers, target clients, verticals — shipped vs. roadmap |
| [HUMANITARIAN_CARTOGRAPHY_STANDARDS.md](HUMANITARIAN_CARTOGRAPHY_STANDARDS.md) | Cartographic design/QA standards the agent's styling and layout tools follow |
| [HUMANITARIAN_MAPPING_TASK_REFERENCE.md](HUMANITARIAN_MAPPING_TASK_REFERENCE.md) | Humanitarian mapping task taxonomy for tool coverage, prompts, workflows, and acceptance testing |

## Roadmap, specs & dated reviews (archive)

Frozen historical documents — see [archive/README.md](archive/README.md) for the full index and
[../CLAUDE.md](../CLAUDE.md) for the never-edit-after-the-fact convention they follow.

## Scripts

These two files live in `docs/` alongside the written references above but are executable dev
tooling, not documentation — they stay here (rather than moving to a `tools/`-style directory)
because every command that invokes them, across this repo's own docs and history, already uses
this exact path.

| Script | Purpose |
|---|---|
| [generate_tools_reference.py](generate_tools_reference.py) | Regenerates `TOOLS_REFERENCE.md` from the live tool registry — run after adding or changing a tool (`python docs/generate_tools_reference.py`) |
| [route_optimization_prototype.py](route_optimization_prototype.py) | Standalone OSMnx/NetworkX prototype referenced by `archive/ROUTE_OPTIMIZATION_STRATEGY.md`, not wired into the plugin |
