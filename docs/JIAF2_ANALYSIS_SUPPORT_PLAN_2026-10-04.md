# JIAF 2 analysis-support module -- stage 1 plan and specification (2026-10-04)

**Status: plan and specification only. Nothing is built.**

Sources, all supplied by the project owner:

1. *JIAF 2 Technical Manual*, **July 2024** (86 pages, "final for 2025 HPC") -- **the edition this plan follows.** Page numbers below are its printed page numbers.
2. *JIAF 2.0 Technical Manual*, July 2023 (62 pages) -- read first; superseded. Differences that matter are in section 8.
3. `jiaf_yemen_2026.xlsx` -- a filled-in Workspace 3A/3B worksheet for Yemen 2026 (333 admin-2 units).
4. `yemen_jiaf_hnrp_2026.xlsx` and `yemen-hnrp-2025.xlsx` -- the published Yemen HNO/HNRP datasets (HXL-tagged: PiN, severity and targets per sector per district).

Not read in full: Annex 2 (the long sector-by-sector severity table), the 2024 Annexes 1-4 and 7-8, and the 2024 text of Reference Tables 2A/2B beyond the headings (the 2023 text was read). Where the plan relies on those, it says so.

## 1. What we are and are not building

**Support for people who run the JIAF process -- not a replacement, not endorsed by OCHA or the IASC.** The manual says JIAF "utilizes both automated statistical analysis as well as structured, participatory, and consensus-building processes". So the module computes what the manual makes mechanical and records what it makes a group decision:

| Mechanical (module computes) | Group decision (module records and checks) |
|---|---|
| Preliminary joint PiN: highest sectoral PiN per unit; national = sum of units (Box 21, p.50) | Which sector's PiN becomes the **Final PiN** for a flagged unit (Step 3.4, p.52) |
| The six PiN flags with recommended thresholds (Table 3A, p.42) | Each sector's own PiN and severity (JIAF gives no sector method) |
| Preliminary intersectoral severity from the overlap of sectoral severities (Box 22, p.50) | Final severity of flagged units, by "convergence of evidence" (Step 3.5, p.53) |
| The automated severity flags 1-4 (Table 3B1, p.42) | Context, shocks, scope, linkages (Module 1, Workspace 3C text) |
| Parts of the 10 pattern outputs (Table 3C, pp.48-49) | Thresholds and their rationale, set by the country team |

Rules the module keeps:

- **Never average sector scores and never sum PiNs across sectors.** Sums happen only across *units*.
- **Intersectoral severity is per unit only.** "There is no national or country-wide severity aggregation or classification, nor can the overall PiN be distributed by severity in JIAF 2" (Box 25, p.53). No national severity figure and no "PiN per severity phase" output.
- **Never compute the final severity of a flagged unit.** Unflagged units keep the preliminary phase; flagged units get a recorded, agreed phase.
- **No imputation, no invented thresholds**; missing data stays missing.
- **Not for ranking crises** (p.7): the results "should not be used to prioritize one crisis over another".
- **No "JIAF-compliant" claims.** The existing `calculate_severity_index` keeps its "JIAF-style exploratory analysis" description.

## 2. What the current manual specifies (July 2024)

**Process.** Three modules, steps 1.1-3.6 (pp.18-55). Module 2: each sector submits one PiN and one severity phase (1-5) per unit of analysis in "the standard Microsoft Excel file" (Step 2.3, p.38), plus its methods and, since 2024, "the list of indicators used for the estimate and thresholds applied" for severity (p.30). Protection: the overarching protection figure is used for the joint results; the AoRs (CP, GBV, HLP, Mine Action) travel alongside for display (pp.29, 39).

**Joint overall PiN -- Mosaic Method (Box 21, p.50).** (1) At each unit, take the highest sectoral PiN; (2) the sum over units is the *preliminary* joint PiN; (3) address the automatic flags and decide, per flagged unit, which sectoral PiN is used; (4) once flags are resolved, the sum over units is the **Final Joint Overall PiN**. The decision is recorded in a column "Final PiN", and "the conclusions and actions taken ... must be fully and transparently documented in the column 'Evidence & Comments'" (Box 24, p.52). The text offers "EITHER the highest ... OR the second highest" and also "whether an alternative approach should be adopted" (p.52); section 4 shows what Yemen actually did.

**PiN flags (Table 3A, p.42)** -- recommended thresholds, adaptable with the rationale recorded (Box 18, p.41; Annex 6, pp.76-77):

| # | Flag | Recommended |
|---|---|---|
| 1 | Number of sectors with missing or zero PiN | 1 or 2 |
| 2 | % difference between 1st and 2nd highest PiN | 30% |
| 3 | % difference between 1st and 3rd highest PiN | 50% |
| 4 | Highest sector's PiN targets sub-population group(s) | 50% |
| 5 | PiN greater than 90% of total population | 90% |
| 6 | Change from last year | 100% |
| 7 | Manual flag | explanation required |

Annex 5 (pp.74-75) adds practical rules: flags 1, 5 and 6 are usually errors to fix with the cluster *before* the session; flag 5 above **100%** of the (sub-)population is a data error, and for sectors that use a subset (e.g. Nutrition: children under 5 and PLW) the comparison is to that subset; flag 6 is checked "only for the host population (or entire population) of a given area, and preferably only for PiN figures above one thousand", with "at least 200 percent" as the extreme-outlier level.

**Preliminary intersectoral severity (Box 22, p.50).** Phase 1: fewer than 4 sectors in phase 2 or worse; phase 2/3/4: at least 4 sectors in that phase or worse; phase 5: at least 2 sectors in phase 5 **and** at least 2 other sectors in phase 4 or worse.

**Severity flags (Table 3B1, p.42) -- four automated; "Two ... are mandatory (Number 1 and 2), two are optional (Number 3 and 4)"; not changeable by the country:** (1) any sector in phase 5; (2) one outcome indicator +2/-2 from the preliminary phase; (3) two or more outcome indicators +1/-1; (4) more than 4 sectors in phase 4 and preliminary phase 4; (5) manual flag. The final severity "must match the area-based descriptions in the table, particularly to review any results that indicate Severity Phase 5", and a found Phase 5 "should be flagged immediately to the HCT" (pp.42-43). Outcome-indicator values are assigned an indicative phase by the analyst from Table 3B2 (p.46); several thresholds are relative to a baseline or have no numbers (epidemics), so the module takes the assigned phase as input.

**Patterns (Workspace 3C, pp.48-49).** Ten questions; default thresholds adjustable: sectors with more than 40% of the administrative population in need; phases 4-5; five or more sectors in phase 4-5; sector pairs with PiN correlation above 0.7; PiN change vs the previous year.

**Disaggregation (Box 27, p.55).** Joint PiN x share of the population in the group; the output must state it is by population share, not by differing need.

## 3. The real input and output files (Yemen)

**The filled worksheet (`jiaf_yemen_2026.xlsx`).** Visible sheets: "WS - 3.1 Overall PiN" (columns: Admin 1, Admin 1 P-Code, Admin 2, Admin 2 P-Code, Population, Population Group, then PiN per CCCM, Education, Nutrition, Food Security, Health, Overarching Protection, Shelter, WASH, then AoRs CP, GBV, Mine Action, HLP, then Severity, **Preliminary PiN**, **Final PiN**, Evidence & Comments), "WS - 3.2 Intersectoral Severity" (same keys; sectoral severity phases; **Preliminary Intersectoral Severity**; outcome-indicator columns Mortality, Malnutrition, Epidemics, Livelihood Coping, HR/IHL Violation; **Final Severity**; Evidence & Comments) and "PiN Historical Trend" (previous year's cluster PiNs, current, absolute and % differences). Hidden sheets hold the pattern analysis (sector correlation via CORREL, overlap, "1st & 2nd highest" counts). In this copy the main sheets hold values, not formulas, and **no flag columns**: the flag formulas are not present, so their exact comparison rules remain to be settled (section 6). The manual's Annex 4 shows the simpler per-sector template: Admin 1/2 names and P-codes, Population, and one column "Cluster's PiN (Number)" on sheet "WS - 3.1 Overall PiN" or "Cluster's Severity (Number)" on "WS - 3.2 Intersectoral Severity".

**The published datasets** are HXL-tagged: row 3 holds tags such as `#adm2 +code`, `#inneed`, `#inneed +wsh`, `#severity +shl`, per sector (wsh, shl, nut, edu, fsac, cccm, hea, pro, plus GBV, MA, CP, rrm, rmms), with boys/men/girls/women splits, plus separate target sheets. The 2025 file also has IDP/resident population columns. A realistic importer must therefore read **both** the Annex 4 sector template **and** HXL-tagged published tables, in addition to the OCHA 3A/3B worksheet.

## 4. What the real data shows about the manual's rules (checked)

Checked on the 333 Yemen admin-2 units in `jiaf_yemen_2026.xlsx` and the published `HNO 2026` sheet:

| Check | Result |
|---|---|
| Rule of Box 22 applied to the 8 main sectors' severities vs the worksheet's Preliminary Severity | **333 of 333 match** |
| Same rule vs the published HNO intersectoral severity | **333 of 333 match**; Final Severity equals Preliminary in all 333 (no flagged unit was reclassified in this file) |
| Preliminary PiN = highest of the 8 main sectors (AoRs excluded) | 331 of 333; the 2 exceptions (YE1920, YE1928) show a preliminary value of 0 although sectors have figures -- a data/entry quirk to surface, not to copy |
| Final PiN = the highest sector | 305 units |
| Final PiN = the **second** highest | 11 units |
| Final PiN = the **third** highest | **17 units** (e.g. YE1705, YE1907) |
| Worksheet Final PiN vs published HNO total PiN | **333 of 333 equal**; national total **22,325,198** |
| Evidence & Comments filled | 0 units in this copy |

Consequences for the design:

- The mosaic and preliminary-severity rules are **confirmed against real, published numbers** and can be unit-tested on the Yemen file.
- **A Final PiN is "the PiN of a chosen sector", not only first or second.** Practice (17 third-highest cases) goes beyond the manual's two options. The module records *which sector* was chosen for each unit and requires a note, instead of restricting to two choices; the report states where the choice differs from the first/second highest.
- The module must not trust a stored "Preliminary PiN" column; it recomputes and reports mismatches.

## 5. The analyst's workflow in QGIS

In the manual's own step order.

| Manual step | The analyst | The module | Stage |
|---|---|---|---|
| 1.5 Scope | Records unit of analysis, areas, population groups, manual edition, and HCT endorsement of scope. | Project "analysis set-up" record; repeated on every output. | 2 |
| 2.1 Alignment (2A, 2B) | Notes per sector: PiN aligned Yes/No, severity Aligned/Adapted, with explanations; and the indicators/thresholds the sector used. | Stores them; a No/Adapted shows beside that sector's figures. | 2 |
| 2.3 Sector inputs | Loads sector data: Annex 4 template, the OCHA 3A/3B worksheet, or an HXL-tagged published table. | Reads xlsx/csv, maps columns explicitly, joins to the admin layer by P-code, validates (severity integer 1-5; PiN a non-negative number; PiN not above its population base; duplicates, missing and unmatched units listed, never filled). | 2 |
| 3.1 Prepare | Reviews the computed workspace. | Preliminary PiN (mosaic), flags 1-6 with the country's thresholds, preliminary severity, severity flags; which sector drives each unit. Recomputes rather than trusting stored columns. | 3 |
| 3.2-3.3 Review flags | Reads flagged units; sectors justify or correct. | Lists flags with reasons, grouped as in Annexes 5-6 (fix-before-session vs discuss); keeps original and revised sector figures side by side. | 4 |
| 3.4 Final PiN | Group chooses the sector whose PiN is used per flagged unit. | Records the chosen sector, rationale, who/when; writes "Final PiN"; total = sum of units. | 4 |
| 3.5 Severity | Group classifies flagged units from the evidence. | Takes analyst-assigned indicator phases; shows flags 2-3 against them; records the agreed phase with evidence and note. Raises the Phase 5 "inform the HCT" notice. Never computes it. | 4 |
| 3.6 Patterns | Answers the 10 questions. | The specified maps and lists with the existing humanitarian map looks. | 4 |
| Export | Shares. | Tables with sector source, edition, thresholds used and why, flags, decisions, and the not-endorsed statement. | 4 |

## 6. Open ambiguities (to be settled against the OCHA worksheet formulas)

The saved Yemen copy has no flag formulas, so these stay open; the module will not guess and will make each a documented setting:

1. Flag 1: fires when the count of missing/zero-PiN sectors is exactly 1 or 2, or at least 1?
2. Flags 2-3: "% difference" -- relative to which value, and `>=` or `>`?
3. Flag 4: how "targets a sub-population group" is supplied (yes/no per sector per unit?).
4. Flag 6: comparison basis and behaviour when last year is zero or missing; the 200% / above-1,000 refinements in Annex 5 vs the 100% table value.
5. Flag 5: the "total population" base per unit and for subset sectors.
6. Severity flag 4: "More than 4" (strictly) vs "at least 4".
7. Treatment of units where fewer than 8 sectors report.
8. Whether AoR columns ever enter the main logic (the files and the manual say no).

## 7. Build stages (each its own PR, labelled "support for the JIAF 2 process, not endorsed")

1. **This specification.** Reviewed by the owner.
2. **Inputs and validation:** set-up record, alignment records, importers for the Annex 4 template, the 3A/3B worksheet and HXL-tagged published tables (same explicit-mapping/P-code pattern as `import_humanitarian_table`), validator.
3. **Calculation engine:** mosaic preliminary PiN, flags 1-6, preliminary severity, severity flags -- pure Python. **Tests reproduce the Yemen results** (333/333 preliminary severity, national Final PiN 22,325,198 from the recorded choices, the 305/11/17 split) plus the manual's rules as unit tests. If it cannot reproduce them, it does not ship.
4. **Review, evidence, outputs:** flag review and decision records, Evidence & Comments, the 10 pattern outputs with map looks, export.

Each stage ends with a CI live test and an honest "not hand-tested" until the owner has run it.

## 8. Differences between the two editions that affect the design

| Topic | 2023 | 2024 (followed) |
|---|---|---|
| Severity flags | 3 automated | **4 automated; 1 and 2 mandatory, 3 and 4 optional** |
| PiN column | "Final Joint Overall PiN" | "Final PiN"; decisions documented in "Evidence & Comments" |
| Workspace 3C | 11 questions | **10 questions** (re-ordered) |
| Distribution of PiN by severity | "not developed" | "not developed ... prioritized ... if feasible, in the 2025 cycle" (p.12) -- still absent, but may arrive |
| Flag handling | Boxes only | Annex 5 (rank and prioritise flags) and Annex 6 (Flag analysis dashboard) |
| Severity evidence | direct/indirect evidence | outcome and **proxy** outcome indicators; expert-judgement elicitation allowed; at least one life-threatening and one irreversible-harm indicator recommended |
| Scope | agreed in session | concludes with **HCT endorsement** |
| Sector severity inputs | scale alignment | also the **indicators and thresholds used** |

## 9. Risks

- Flag formulas read differently from the OCHA worksheet -> plausible but wrong flags. Mitigation: documented settings per ambiguity, Yemen reproduction, and a request for the formula-bearing worksheet.
- Edition drift (a newer edition after July 2024). Mitigation: the edition is stored with every result.
- Misuse as an official figure or a crisis ranking. Mitigation: the not-endorsed statement in every output and tool description.
- The "PiN per severity phase" component may be added by OCHA; the module will not pre-empt it.

## 10. What is needed from the owner

1. Review and merge this specification.
2. If available: the **OCHA analysis worksheet with live formulas** (or the JIAF Flags dashboard export) -- it settles section 6. The Yemen copy supplied has values only.
3. Confirmation that the July 2024 manual is the current edition.
4. Whether the supplied PDFs and Yemen workbooks may be stored in the repository (the PDFs show no licence terms, so until told otherwise they are only referenced; the Yemen files are published datasets but are not committed either).
