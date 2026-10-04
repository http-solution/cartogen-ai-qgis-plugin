# JIAF 2 analysis-support module -- stage 1 plan and specification (2026-10-04)

**Status: plan and specification only. Nothing is built.** Source: the *JIAF 2.0 Technical Manual* PDF the owner supplied (cover: "Humanitarian Programme Cycle Steering Group, July 2023, Endorsed by IASC OPAG"; 62 pages; read in full except the long sector-by-sector Annex 2). Page numbers below are the manual's printed page numbers. Wording in quotation marks is the manual's.

What is **not** in the PDF: the Excel files. Annex 4 ("Example files to be used for sectoral reporting of PiN and Severity") is an empty page in the PDF, and Workspaces 3A/3B are "a single Microsoft Excel spreadsheet" the manual only links to (p.40, p.50). The calculation rules below come from the manual's text; the exact worksheet formulas, column layouts and rounding do not, so the worksheets are still needed as the test reference (section 8).

Note: the owner's earlier message mentioned a July **2024** Technical Manual; this PDF says July 2023. Which edition is current should be confirmed (section 8).

## 1. What we are and are not building

**Support for people who run the JIAF process -- not a replacement, not endorsed by OCHA or the IASC.** The manual is explicit that JIAF "utilizes both automated statistical analysis as well as structured, participatory, and consensus-building processes" and that "there are no adequate or reliable models to conduct this type of complex analysis with algorithmic and statistical approaches alone" (p.8). So the module does the parts the manual makes mechanical, and records the parts it makes human:

| The manual makes it mechanical (module computes) | The manual makes it a group decision (module records and checks) |
|---|---|
| Mosaic joint overall PiN: highest sectoral PiN per unit, national = sum of units (Box 16, p.40) | Whether a flagged unit uses the highest or the second-highest sectoral PiN (Step 3.4, p.42) |
| The six automated PiN flags, with recommended thresholds (Table 3A, p.34) | Each sector's own PiN and severity -- "JIAF 2.0 does not include guidance for sector-specific methods" (p.32) |
| Preliminary intersectoral severity from the overlap of sectoral severities (Box 17, p.40) | Final intersectoral severity of flagged units, by "convergence of evidence and consensus building" (Step 3.5, p.43) |
| The three automated severity flags (Table 3B1, p.35) | Context, shocks, scope, qualitative linkages (Modules 1 and 3C) |
| Some of the 11 pattern prompts (maps, bar graphs, a correlation) (Table 3C, p.39) | Thresholds and alignment explanations: each sector states its own (Workspaces 2A, 2B) |

Rules that follow from the manual and that the module keeps:

- **Never average sector scores and never sum sector PiNs across sectors.** "The JIAF Joint Overall PiN is not an average of the cluster PiNs" (p.40). Summation happens only across *units*, never across sectors.
- **Intersectoral severity is per unit only.** "There is no national or country-wide severity aggregation or classification" (Box 19, p.43). The module offers no national severity figure.
- **Do not compute the final severity of a flagged unit.** Table 3B2 "is only to be used to guide the classification of intersectoral severities of the areas flagged" (p.35); the agreed value is a recorded human decision.
- **No imputation, no invented thresholds.** Missing sector data is shown as missing; sector thresholds come from the sector.
- **No "JIAF-compliant" claims.** Tool names and results say "support for the JIAF 2.0 process"; the existing `calculate_severity_index` keeps its "JIAF-style exploratory analysis" wording.
- **Not for ranking crises.** "The results should not be used to prioritize one crisis over another" (p.9); severity phases "do not imply prioritization of humanitarian needs" (p.37). Output text says so.

## 2. What the manual specifies (the facts the engine is built on)

### Structure (pp.9-18)
Three modules and 11 steps: Module 1 Contributing factors and scope (steps 1.1-1.5, workspaces 1A-1C); Module 2 Interoperable sectoral needs (2.1-2.3, workspaces 2A-2B); Module 3 Intersectoral needs (3.1-3.6, workspaces 3A, 3B, 3C); then return to step 1 and finalize Module 1. Module 1 results are "initial" until the end ("initial/final" toggle, Box 7, p.21).

### Sector inputs (Module 2, pp.26-32)
- Sectors: CCCM, Education, Food Security, Health, Nutrition, Shelter/NFI, WASH, Protection (plus the AoRs Child Protection, GBV, HLP, Mine Action). "For the purpose of joint overall PiN and Intersectoral severity estimations, the overarching protection severity and PiN will be used"; AoR figures travel alongside for display only (p.26, p.32).
- Each sector reports, **per unit of analysis**, one **PiN** and one **severity phase 1-5**, in "the standard Microsoft Excel file" (Step 2.3, p.32). Unit of analysis: typically admin level 2, but any agreed unit, and optionally population groups (Step 1.5, p.24).
- Sector severity scale (absolute, 1-5): 1 Minor or no sectoral deprivation; 2 Borderline/stressed; 3 Elevated; 4 Extreme; 5 Sectoral collapse (p.29). "Not all countries will have areas in all five severity phases."
- **Not developed in JIAF 2.0:** "the distribution of population among intersectoral severity phases" (p.13). So there is no "share of population in each phase" input or output; an importer must not invent one.
- Workspace 2A (PiN alignment, Yes/No per sector against five principles, with an explanation when No) and 2B (severity, Aligned/Adapted, with an explanation when Adapted) are self-assessments recorded per sector (pp.30-32).
- IASC PiN definition and the five joint-overall-PiN principles (scope; deprivation within affected; not masked by assistance; independent of responding actor; current and expected needs) are in Table 2A (p.28). Per-sector PiN definitions are listed there too.

### Joint overall PiN -- the Mosaic Method (Box 16 p.40; Step 3.4 pp.42-43)
1. For each unit (admin unit or population group), take the **highest sectoral PiN**.
2. The national PiN is "the sum of all subnational PiNs" (the final per-unit values).
3. Flags (below) identify units to discuss. For each flagged unit the group decides to use the highest sectoral PiN (flag resolved) or, by agreement, the second highest. Decision tree: Diagram 22, p.43; if no consensus, elevate to the Humanitarian Coordinator / request interagency support.
4. Decisions go in a new column "Final Joint Overall PiN"; the country total is the sum of that column.
5. "If adjustments are not done, the JIAF analysis group may decide to use the second highest PiN" (Box 13, p.34). Also "attention will be paid for the Joint Overall PiN estimation not to aggregate sectoral PiNs whose misalignments are significant" (p.13).

### PiN flags (Table 3A, p.34) -- recommended thresholds, adaptable per country
1. Number of sectors with missing or zero PiN: **1 or 2**.
2. % difference between the 1st and 2nd highest PiN: **30%**.
3. % difference between the 1st and 3rd highest PiN: **50%**.
4. Highest sector PiN targets sub-population group(s): **50%**.
5. PiN greater than **90%** of total affected population.
6. Change from last year: **100%**.
7. Manual flag (explanation at country level).

"A flag does not necessarily imply that the data is erroneous, just that it needs to be verified" (Box 13).

### Preliminary intersectoral severity (Box 17, p.40; Table 3B2 "Overlap of sectoral needs", p.38)
- Phase 1: fewer than 4 sectors in stressed (phase 2) or worse
- Phase 2: at least 4 sectors in phase 2 or worse
- Phase 3: at least 4 sectors in phase 3 or worse
- Phase 4: at least 4 sectors in phase 4 or worse
- Phase 5: at least 2 sectors in phase 5 **and** at least 2 other sectors in phase 4 or worse
Intersectoral phases are named 1 Minimal, 2 Stressed, 3 Severe, 4 Extreme, 5 Catastrophic -- "not the same as the sectoral severity phases" (p.35).

### Severity flags (Table 3B1, p.35) -- "should not be changed at the country level"
1. Any sector is in severity phase 5.
2. One outcome indicator is +2/-2 compared with the preliminary classification.
3. Two or more outcome indicators are +1/-1 compared with the preliminary classification.
4. More than 4 sectors are in phase 4 and the preliminary intersectoral severity is phase 4.
5. Manual flag.
An unflagged unit's preliminary severity is accepted ("the available evidence converged", p.43). A flagged unit needs the group's analysis of the evidence using Table 3B2 as a guide.

### Outcome indicators (Table 3B2, p.38)
Life-threatening conditions: crude death rate (per 10,000 per day: below 0.5 in phases 1-2, then 0.5-0.99, 1.0-1.99 and 2 or more in phases 3, 4, 5), under-5 death rate, global acute malnutrition (WHZ, MUAC), epidemic-prone diseases (no numeric thresholds); irreversible harm: livelihood coping strategies (>=20% of households at stress/crisis/emergency/collapse levels), human-rights/IHL violations (sporadic, repeated, widespread, systematic). Several thresholds are relative to a "baseline". Because of that, the **analyst assigns the indicative phase to each indicator value** ("Each data should then be aligned to the indicative phase they reflect", p.41); the module takes that phase as input and does not derive it.

### Patterns (Table 3C and Workspace 3C, pp.39-41)
Eleven questions with specified visual aids: Joint Overall PiN map (absolute and %); map of the number of sectors with >40% of the administrative population in need; sectoral PiN maps and bar graphs; intersectoral severity map and list (default phases 4-5); number of sectors in phase 4-5; sectoral severity maps; overlap of severity and PiN; sectors by units with high PiN and high severity; **correlation coefficient of PiN between sectors (list pairs above 0.7)**; PiN trend vs previous year; PiN by vulnerable group. Thresholds "can be set at country level".

### Disaggregated PiN (Box 21, p.45)
Either the group is a unit of analysis, or post-analysis extrapolation: Joint overall PiN x percentage of the population in the group -- with the stated caveat that this is by population share, not by difference in need.

### Limits and cautions the manual states (pp.8-13)
Reflects "current and expected needs for the coming year" with no scenarios or projections; outputs are "only as robust as the evidence used"; avoid "excessive disaggregation"; sector PiNs may not be fully aligned and must be documented; JIAF 2.0 findings can be quickly outdated.

## 3. The analyst's workflow in QGIS

Written in the manual's own step order so an analyst can follow the manual with the module open.

| Manual step | The analyst | The module | Build stage |
|---|---|---|---|
| 1.5 Scope | Records the unit of analysis (admin level), areas covered, population groups, and the manual edition. | Stores a project "analysis set-up" (country, cycle, unit, edition); every result repeats it. | 2 |
| 2.1 Alignment (2A, 2B) | Notes for each sector: PiN aligned Yes/No, severity Aligned/Adapted, with the explanation. | Stores these self-assessments; a No/Adapted shows beside that sector's figures. | 2 |
| 2.3 Sector inputs | Loads each sector's file (PiN + severity phase per unit). | Reads CSV/Excel with explicit column mapping, joins to the admin layer by P-code, validates (phase integer 1-5; PiN a non-negative number and not above the unit's population/affected population; unit keys match the scope; duplicates and missing values listed, not filled). | 2 |
| 3.1 Prepare | Reviews the computed workspace. | Computes mosaic joint PiN, the six PiN flags, preliminary severity and the three severity flags per unit; shows which sector set each unit's PiN. | 3 |
| 3.2-3.3 Review flags | Reads flagged units; sectors justify or correct their figures. | Lists flags with their reason; revised sector figures are stored as a new version beside the original (the manual leaves the revision method to the country, p.42). | 4 |
| 3.4 Joint overall PiN | Group decides highest vs second highest for flagged units. | Records the decision, who agreed, date and note; writes "Final Joint Overall PiN"; national total = sum. | 4 |
| 3.5 Intersectoral severity | Group classifies flagged units from the evidence. | Takes the analyst-assigned indicator phases, shows flags 2-3 against them, and records the **agreed** phase with evidence (direct or indirect) and a note. Never computes it. | 4 |
| 3.6 Patterns | Answers the 11 questions. | Draws the specified maps and graphs with the existing humanitarian map looks; lists units above the country-set thresholds. | 4 |
| 3.6+ Export | Shares results. | Exports tables with source sector, edition, flags, decisions and the not-endorsed statement. | 4 |

Module 1 (context, shocks) is free text in the manual; the module offers only a notes field and keeps no model of it.

## 4. Open ambiguities the text leaves (to settle against the Excel worksheets)

1. Flag 1: "1 or 2" sectors with missing or zero PiN -- flagged when the count is 1 or 2 (and not when 3 or more?) or when it reaches that value? Exact rule unknown.
2. Flags 2-3: "% difference" -- relative to which value, and flagged at >= or >? Rounding?
3. Flag 4: how the "targets a sub-population group" input is supplied (a yes/no per sector per unit?).
4. Flag 6: "change from last year 100%" -- comparison basis and handling when last year is zero/missing.
5. Flag 5: the "total affected population" field per unit.
6. Flag 4 of severity ("More than 4 sectors in phase 4") versus the preliminary rule "at least 4": strictly more than 4 as written -- confirm.
7. Whether a unit with fewer than the usual 8 reporting sectors changes the overlap counts (the manual says nothing).
8. The standard sector-input file's columns and any identifiers (P-codes?).

The module will implement the manual's wording exactly where it is clear, and for the above points will not guess: it will ask the owner/worksheet (section 8) and record the chosen reading as a documented setting.

## 5. Build stages (each its own PR; each labelled "support for the JIAF 2.0 process, not endorsed")

1. **This specification.** Done when the owner has reviewed it and supplied the worksheets (section 8).
2. **Inputs and validation:** analysis set-up record, sector alignment records, sector-input importer (same pattern as `import_humanitarian_table`: explicit mapping, P-code join, nothing guessed) and validator.
3. **Calculation engine:** mosaic joint PiN, PiN flags, preliminary severity, severity flags -- pure Python, tested offline **against the official worksheets' own examples** (and the manual's rules as unit tests). If it cannot reproduce them, it does not ship.
4. **Analyst review and outputs:** flag review and decision records, evidence, the 11 pattern outputs with map looks, export.

Each stage ends with a live test in CI and an honest "not hand-tested" until the owner has run it.

## 6. What this changes in the current tool set

- `calculate_severity_index` stays a weighted min-max index; its description will say "JIAF-style exploratory analysis, not the JIAF method" (stage 2 PR).
- `calculate_population_in_need` and `calculate_presence_gap` are not JIAF steps and are untouched.
- No tool will output a "% of population in each severity phase" figure (the manual says that component is not yet developed, p.13).

## 7. Risks

- Reading the flag rules differently from the official worksheet would produce a plausible but wrong flag. Mitigation: worksheet-reproduction test and a documented reading per ambiguity.
- Edition drift (2023 vs 2024). Mitigation: store the edition with every result; confirm the current one.
- Misuse as a ranking of crises, or as an official figure. Mitigation: the statements above in every output and in the tool descriptions.

## 8. What is needed from the owner to start stage 2

1. The official **Excel files**: the standard sector-input template (Annex 4) and the "Overall PiN and Joint Intersectoral Severity worksheet" (Workspaces 3A and 3B), ideally with a filled example. These answer section 4 and become the test reference.
2. Confirmation of the **edition**: is this July 2023 manual the one to follow, or is there a July 2024 manual to use instead (and, if so, the PDF)?
3. A real example of **sector inputs** from a country (even anonymised) to test the importer on.
4. First country/unit of analysis and planning cycle, if there is one.
5. Whether the PDF and worksheets may be stored in the repository (the manual's text shows no licence terms; until told otherwise they are only referenced, not committed).
