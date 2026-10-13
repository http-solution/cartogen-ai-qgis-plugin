---
description: The humanitarian tools grouped by the six workflows they support, with what is new in the latest builds.
---
The humanitarian tools follow six workflows: field operations first, then strategic orchestration. Tools marked **new** were added in the two most recent releases and have been tested offline and in CI on QGIS 4.2.2, not by hand. For what each tool does, what it draws and how to get better results, read the [Tools catalogue](@humanitarian/catalogue); exact arguments are in the [Tool reference](@tools/index).

| # | Workflow | In one line |
|---|---|---|
| 1 | Rapid crisis and base mapping | Boundaries, OSM, footprints, imagery, change detection, damage exposure, mapping task grids |
| 2 | MSNA and field data | Sampling frames, population, tabular and PDF/Word table intake, survey indicators |
| 3 | Logistics, routes and catchments | Road speeds, impedance, barriers, service areas, travel-time matrices, hub siting, allocation, delivery routes, critical links |
| 4 | Severity mapping (JIAF-style) | Severity indices, presence gaps, 3W, population in need, hotspots, trends, JIAF 2 analysis support |
| 5 | Allocation and prioritisation | MCDA ranking, funding data, sector coverage, weighted overlay, allocation envelope |
| 6 | Anticipatory action | Forecast triggers, hazard feeds, incident search, dashboards, scheduled monitoring |

Two further groups cut across them: **data quality and governance** (P-code checks, schema contracts, dataset status, provenance, sensitivity, QA checklists) and **reporting and products** (charts, dashboards, spatial reports, the humanitarian look).

## Judgement calls are asked for, not chosen

Where a number is a judgement call (a trigger threshold, criteria weights, a design effect, a minimum survey cell size) the tool asks you for it and repeats it in the result instead of choosing one.

## JIAF 2 analysis support

The JIAF 2 tools compute what the OCHA worksheet specifies and **record** what is an analyst decision. Every result carries two open validation blockers on purpose: (1) the flag formulas have not been compared with a real country's Flags dashboard export, and (2) the Annex 4 reader (an unsupported optional format) has not seen a real filled sector-input file. Results say "not the JIAF method, not endorsed by OCHA or the IASC". See the [Status and open work](@project/status) page.

## The tools, by workflow
