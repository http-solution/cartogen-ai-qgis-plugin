# PLAN-030: becoming the leading AI plugin in the QGIS directory

Status: planned

## Goal
Decide what "leading" means for this plugin and the order of work that gets there, so the individual plans (PLAN-031 to PLAN-037) are steps of one strategy and not a list. Source: the owner's codebase-analysis document of 2026-10-28 (nine flagship QGIS AI plugins and a secondary tier), checked against this repository the same day. The document's own figures about other plugins (downloads, benchmark scores, tool counts) are taken from its sources and were not verified here. Its description of this plugin is out of date (it names v1.16.1 and two providers); today the plugin is 1.18.5 with five providers, 296 tools and roughly 435 allow-listed Processing algorithms.

## Scope
In: three definitions of "leading" and the order for them; the gaps against the leaders; the decisions only the owner can make; the metrics that say whether it worked.
1. **Be in the official repository (plugins.qgis.org).** Directory ranking is downloads, votes and ratings there. Without a listing nothing else counts (master list OWN-12, PLAN-037).
2. **Own a niche before competing on breadth.** The generalist plugins will out-feature this one on generic tasks. Verified humanitarian and field GIS (JIAF, IPC, MSNA, access analysis, sitrep, an evidence trail per request) is not offered by any plugin in the document. Proposed positioning: "the trusted GIS agent for humanitarian and field work". This is a decision for the owner (LEAD-1).
3. **Close the credibility gaps the leaders already close**, in this order: verified result gate (PLAN-031), canvas as an image (PLAN-032), MCP server over the existing write, egress and sensitivity gates (PLAN-034), a published benchmark (PLAN-035).
4. **Remove the cause of the bug class the hand runs keep finding** (PLAN-033): arguments dropped between a tool and the orchestrator's special-cased paths.
5. **Decide on QGIS 3.x** (PLAN-036): the plugin requires 4.2+, most rivals list 3.22 or 3.28 upward, and the 3.x long-term releases probably hold most users (an assumption; no statistics here).
Out: a rewrite for style's sake; any tier gating (CLAUDE.md); a paid cloud service; copying another plugin's code (their licences differ: MIT, GPL-2.0-or-later, freemium).

## Acceptance
Measured, not asserted. Each is a number the owner can look at:
1. The plugin is published on plugins.qgis.org and its download count and rating are recorded monthly in the master list.
2. The benchmark (PLAN-035) is published with a score per provider and the method to reproduce it.
3. A hand-test run (the runbook) shows the verified result gate catching one wrong answer a model would have reported, on camera (a demo for PLAN-037).
4. The gaps table below has no row marked Absent that the owner chose to close.
Hand test: all of 1 to 3 need a person. Nothing in this plan is verified by CI.

## Gaps against the leaders (checked in this repository, 2026-10-28)
| Capability the document rates highly | State here | Plan |
|---|---|---|
| MCP server | Absent | PLAN-034 |
| Visual self-inspection | Partial: the canvas tool returns base64 text, not an image part | PLAN-032 |
| Result verification after an analysis | Absent as a system; many one-off guards | PLAN-031 |
| Published benchmark | None; fixtures with known answers exist | PLAN-035 |
| QGIS 3.x LTR support | Not supported (4.2+ only) | PLAN-036 |
| Open-data catalogue breadth | Partial (HDX, geoBoundaries, OSM, WorldPop, STAC and event feeds) | master list RM-C, RM-E |
| No-key use (CLI bridge, managed cloud) | Partial (Ollama, free OpenRouter key) | not planned; owner decision |
| PyQGIS API retrieval for script fallback | Partial (algorithm finder, no PyQGIS signature search) | not planned |
| Humanitarian depth and an evidence trail | Present, unique in the document | protect and show it (PLAN-037) |

## Guard tests
none, because this plan changes no behaviour; the plans it points at each name their own.

## Rollback
Nothing to roll back. If the owner rejects the positioning, mark this plan abandoned and keep PLAN-031 to PLAN-034, which stand on their own.

## Status log
- 2026-10-28: plan written from the owner's analysis document and a check of the repository. Decisions needed: LEAD-1 (positioning and order), LEAD-2 (QGIS 3.x). Nothing built.
