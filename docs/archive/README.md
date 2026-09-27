# Archive — dated, frozen review/audit/spec/strategy docs

Everything in this folder is a **dated, frozen snapshot** per `CONTRIBUTING.md` §2's convention:
each one is an accurate record of a specific review, audit, proposal, or spec *as of the date it
was written*, and is never edited after the fact to match current reality (rare same-day
correction addenda excepted -- see individual docs for those). Some now contain stale figures or
superseded conclusions; that's expected, not a bug -- see `docs/IMPLEMENTATION_TRACKER.md` for
what's actually still open right now, and `README.md`'s Documentation table for what each of
these files covers.

Nothing in this folder is deleted or historical trivia -- several are still the authoritative
source for a decision or design that's still in effect (e.g. `OPEN_CORE_REPO_STRATEGY.md`,
`MULTITIER_REPO_ARCHITECTURE_SPEC.md`). They're archived by *age and one-off nature*, not by
relevance -- moved here in 2026-08-31's documentation pass so `docs/`'s top level only shows the
living references and trackers you'd actually check first.

## Index

| Doc | Covers |
|---|---|
| [API_COST_OPTIMIZATION_REVIEW.md](API_COST_OPTIMIZATION_REVIEW.md) | Review of LLM token spend and API cost across the agent loop, prompt design, and provider integrations |
| [AUTO_REPORTING_RECIPE.md](AUTO_REPORTING_RECIPE.md) | Recipe (zero new code): composing existing tools into a scheduled program-update workflow |
| [CARTOGEN_AI_FEATURE_LIST.md](CARTOGEN_AI_FEATURE_LIST.md) | Feature list and shipped-vs-planned reality matrix, verified against code |
| [CARTOGEN_AI_PRD.md](CARTOGEN_AI_PRD.md) | Product Requirements Document (v2), with implementation status annotated against code |
| [CVA_MARKET_ACCESS_RECIPE.md](CVA_MARKET_ACCESS_RECIPE.md) | Recipe (zero new code): market-access distance analysis for cash/voucher assistance feasibility, and its honest limits |
| [DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md](DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md) | Audit of which destructive tools have the preview/confirm safety gate and which don't |
| [DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md](DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md) | What was extracted from `ui/dock_widget.py` vs. deliberately deferred, and why |
| [DOCUMENTATION.md](DOCUMENTATION.md) | Earlier, superseded full-repo documentation pass |
| [ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md](ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md) | Specialist product/software-engineering/UI-UX review with concrete recommendations |
| [HUMANITARIAN_GIS_FEATURE_REVIEW.md](HUMANITARIAN_GIS_FEATURE_REVIEW.md) | Humanitarian field GIS analyst review of crisis-management/fund-allocation tool coverage |
| [IMPLEMENTATION_TASK_LIST.md](IMPLEMENTATION_TASK_LIST.md) | PRD implementation task list, verified against code |
| [JIAF_MULTISECTOR_COMPOSITE_SPEC.md](JIAF_MULTISECTOR_COMPOSITE_SPEC.md) | Spec (roadmap, not shipped): combining per-sector severity indices into one intersectoral estimate, grounded in JIAF 2.0's Mosaic Method |
| [LICENSE_AUDIT.md](LICENSE_AUDIT.md) | License compliance audit of every dependency and external data source |
| [MULTITIER_REPO_ARCHITECTURE_SPEC.md](MULTITIER_REPO_ARCHITECTURE_SPEC.md) | Technical spec for the open-core split: namespace package layout, QGIS loading path, sync workflow, distribution channels |
| [OPEN_CORE_REPO_STRATEGY.md](OPEN_CORE_REPO_STRATEGY.md) | Decided (not yet built): public repo stays open Community core, Pro/Enterprise built in a separate private repo |
| [PROJECT_EXECUTION_PLAN.md](PROJECT_EXECUTION_PLAN.md) | Phase 1 delivery control plan: product objective and execution sequencing |
| [PROMPT_REFINEMENT_LAYER_SPEC.md](PROMPT_REFINEMENT_LAYER_SPEC.md) | Spec (roadmap, not shipped): interactive prompt-refinement step before agent processing |
| [PRO_TIER_BUILD_PLAN_2026-08-21.md](PRO_TIER_BUILD_PLAN_2026-08-21.md) | Professional-tier build plan (not a commitment, nothing built) |
| [ROUTE_OPTIMIZATION_STRATEGY.md](ROUTE_OPTIMIZATION_STRATEGY.md) | Strategy (not yet applied): closing the accuracy gap in `logistics_tools.py`'s routing tools, plus a standalone OSMnx/NetworkX prototype |
| [ROUTE_RISK_AND_NOGO_ZONES_SPEC.md](ROUTE_RISK_AND_NOGO_ZONES_SPEC.md) | Spec (roadmap, not shipped): time-windowed incident trends, route-vs-incident risk scoring, no-go zones as routing hard-excludes |
| [SAM_IMAGERY_EXTRACTION_SPEC.md](SAM_IMAGERY_EXTRACTION_SPEC.md) | Spec for SAM-family imagery feature extraction — shipped 2026-08-17 |
| [SECTOR_PRODUCT_STRATEGY.md](SECTOR_PRODUCT_STRATEGY.md) | Sector product strategy across humanitarian, engineering, urban planning, and logistics mapping |
| [SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md](SECURITY_AND_COMPETITIVE_REVIEW_2026-08.md) | Combined security and competitive-position review |
| [STATUS_REVIEW_2026-08-20.md](STATUS_REVIEW_2026-08-20.md) | Full-codebase status review: architecture, tool registry, security, docs, open items, next steps |
| [TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md](TIER_RESTRUCTURE_PROPOSAL_2026-08-20.md) | Proposal (not decided/shipped): Community/Pro/Full-Direct-Connect tiers gated on tool set + connectivity |
| [TRANSPARENCY_CARDS.md](TRANSPARENCY_CARDS.md) | Procurement/compliance-reviewer summary of how higher-risk actions actually behave, cross-referenced to `SECURITY.md` |
| [UX_DOCUMENTATION_AUDIT_2026-08-31.md](UX_DOCUMENTATION_AUDIT_2026-08-31.md) | UX and documentation audit of the shipped plugin as it actually behaves and reads |
| [WEB_MAPPING_ARCHITECTURE.md](WEB_MAPPING_ARCHITECTURE.md) | Ground-up implementation notes for the proposed web mapping architecture |
