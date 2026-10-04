# JIAF 2 analysis-support module -- stage 1 plan (2026-10-04)

**Status: plan only. Nothing is built, and the official manual has NOT been read.** Every statement about JIAF 2 below is marked:

- **[search]** -- from web-search result snippets on 2026-10-04 (secondhand, one or two sentences each, not the manual). Treat as a lead to check.
- **[owner]** -- stated by the project owner in the HX5 proposal.
- **[unknown]** -- must come from the manual and worksheets before any code is written.

Why the manual was not read: the session's network policy blocked unocha.org, reliefweb.int, interagencystandingcommittee.org, fscluster.org, healthcluster.who.int and knowledge.base.unocha.org. Search only returned titles and short summaries.

## 1. What we are and are not building

JIAF is OCHA's / the IASC's inter-agency method. This module **supports analysts who run the JIAF process; it does not replace it, does not decide severity, and does not carry OCHA's or the IASC's endorsement.** The existing `calculate_severity_index` stays what it is -- a weighted min-max index -- and is renamed in its description to "JIAF-style exploratory analysis" so nobody mistakes it for the method **[owner]**.

## 2. What the method looks like (to be confirmed against the manual)

- JIAF 2 (the IASC Technical Manual, July 2024) gives a method to calculate people in need (PiN) and severity, introduced for the 2024 planning cycle **[search]**.
- The analysis flow has three modules: initial analysis, sectoral analysis, final (intersectoral) analysis **[search]**.
- The joint overall PiN uses the "mosaic method": for each unit of analysis, the highest sectoral PiN, at the lowest level with reliable data -- sectoral PiNs are **not summed** and sector severity scores are **not averaged** **[search], [owner]**.
- In the intersectoral step sectors present results, discuss flags, agree the joint PiN for flagged areas and jointly analyse intersectoral severity for flagged areas **[search]**. If that is right, intersectoral severity is an **analyst judgement on flagged areas, not a formula** -- so the module must record and check that judgement, not compute it.
- Sector specialists supply thresholds and indicator-to-phase rules **[owner]**; we never invent them.

## 3. The analyst's workflow the module will follow

Written in the order an analyst works. Stage numbers are the build stages (section 5).

| Step | What the analyst does | What the module does | Stage |
|---|---|---|---|
| 1. Set up | Names the country, planning cycle, unit of analysis (admin level), and the manual version used. | Stores it with the project; every output repeats it. | 2 |
| 2. Bring in sector inputs | Loads each sector's assessment results as a file (population and PiN / severity-phase figures per unit) -- importing what sectors already produced comes first. | Reads CSV/Excel, maps columns (explicit mapping, nothing guessed), joins to the admin layer by P-code, as `import_humanitarian_table` does. | 2 |
| 3. Check the inputs | Reads the validation report. | Checks against the manual's rules (valid phases, shares sum to the population, PiN not above population, units match, missing data listed -- never filled). | 2 |
| 4. Sectoral results | Confirms each sector's PiN and severity per unit. | Shows them side by side; flags units where the sector's own numbers disagree with each other. | 3 |
| 5. Joint overall PiN | Reviews the result. | Mosaic: highest sectoral PiN per unit; says which sector set each unit's figure; checked against the official worksheets. | 3 |
| 6. Flags and intersectoral severity | Reviews flagged units, records the agreed severity and why. | Lists flags; stores the agreed value, who agreed it, the evidence and the date. It does not compute severity. | 4 |
| 7. Map and share | Maps the result and exports tables. | Humanitarian map looks, an evidence table and an export of every figure with its source and manual version. | 4 |

## 4. Information needed from the manual and worksheets (extraction checklist)

Nothing in stage 2 is written until these are answered from the primary documents:

1. Exact module and step definitions, and what each step must produce.
2. The severity scale: names and definitions of phases 1-5, and which phases count toward PiN. **[unknown]** -- a "phase 3 and above" rule is commonly quoted but is not confirmed here.
3. How a sector's PiN is derived and what the sector submits (population in each phase? PiN directly? how uncertainty is stated).
4. The mosaic method in full: unit level, how overlapping or duplicate units are handled, which population denominator is used, tie handling.
5. The flag rules for the intersectoral step, and what the agreed severity is recorded as.
6. The official worksheets: file names, sheet and column layout, any formulas. These become the test reference -- the calculation engine must reproduce their results on their own examples.
7. Version and date of the manual, and whether a newer one exists (the FSC guidance and cluster notes show sector-specific variants).
8. Terms of use for quoting or redistributing the manual and worksheets (decides whether they can live in the repo or are only referenced).

## 5. Build stages

1. **This document, then the specification** -- the checklist above answered with page references, plus an input validator pinned to the manual. No calculation yet.
2. **Inputs and validation** -- set-up record, sector-input import (reuses the `import_humanitarian_table` pattern), validator. Imports existing sector assessments first.
3. **Calculation engine** -- sectoral view and mosaic joint PiN, **tested to reproduce the official worksheets** on their own examples. If it cannot reproduce them, it does not ship.
4. **Analyst review, evidence and export** -- flags, recorded agreed severity, evidence table, map look, export with manual version.

Each stage ships as its own PR, labelled "support for the JIAF process, not endorsed by OCHA/IASC", with a live test in CI and an honest "not hand-tested" until the owner has run it.

## 6. Rules this module keeps

- Nothing is imputed: a missing value is shown as missing and kept out of a result.
- No threshold, weight or indicator rule is invented; the sector supplies it and the output repeats it.
- A figure always says which sector and which input set it came from.
- The tool names and descriptions never say "JIAF-compliant" or imply OCHA/IASC approval.

## 7. What is needed from the owner to start stage 1

Any one of these:

- Attach the JIAF 2 Technical Manual (July 2024) PDF and the official Excel worksheets to the session or the repo, **or**
- allow these hosts under the cloud environment's Network access (Custom, keep the package-manager defaults): `www.unocha.org`, `reliefweb.int`, `interagencystandingcommittee.org`, `knowledge.base.unocha.org`, `fscluster.org`, `healthcluster.who.int`.

Also needed:

- Which sectors' inputs the owner actually has (and in what file form) -- a real example of each is the best test material.
- The unit of analysis for the first country (admin 1 or 2), and which planning cycle.
- A decision on whether the manual and worksheets may be stored in the repo (section 4, item 8).
