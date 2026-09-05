# JIAF Multi-Sector Composite — Specification

**Status: DRAFT — not yet reviewed or approved, no code written.** Same spec-before-build discipline
as the Prompt Refinement Layer, SAM imagery extraction, and route risk-scoring specs. Unlike those,
this spec's grounding is a real external methodology (JIAF 2.0), researched directly from primary/
near-primary sources before writing anything down, not assumed from the gap-analysis review's own
framing.

---

## 1. Research grounding (sourced, checked before design)

`calculate_severity_index` already implements a JIAF/INFORM-style **single-sector** severity index:
min-max normalize indicators, weighted sum, 5-phase equal-interval classification (1 minimal - 5
catastrophic). The real gap: nothing combines several sectors' severity into one intersectoral
figure, so today a request like "what's the overall severity, combining health, WASH, and food
security" has to be answered by eyeballing separate per-sector runs.

Researched directly (WebSearch + a fetched Global Health Cluster brief, "Decoding JIAF 2.0", July
2024/2025 update -- not assumed from general knowledge) rather than guessed at, since inventing a
humanitarian methodology's rules would be exactly the kind of fabrication `agent/prompts.py` rule 12
exists to prevent, applied here to research, not just tool output:

- **Cross-sectoral severity** is officially a **5-phase** scale (1 minimal, 2 stressed, 3 severe, 4
  extreme, 5 catastrophic) — matching `_severity_class`'s existing equal-interval 1-5 classification
  exactly, confirming this codebase's existing convention is already JIAF-aligned, not a coincidence
  to paper over.
- **Mosaic Method** (JIAF's own named term, not a term I chose): "a method for estimating the overall
  PiN by taking the **highest sectoral PiN figure** for each geographic unit of analysis. The overall
  PiN is determined by adding up all subnational PiN figures once the flags have been resolved."
  This is a **maximum across sectors**, not a sum or weighted average — summing sector PiN figures
  directly would double-count the same people needing help in multiple sectors simultaneously, which
  is exactly the problem the Mosaic Method exists to avoid.
- **Cross-sectoral severity itself is NOT purely a formula.** JIAF 2.0's process explicitly includes
  "**Convergence of Evidence**" (verifying that multiple sources point to the same conclusion) and
  Module 3 "**validation workshops**" where "flags are discussed and a final consensus is reached."
  Earlier, less-precise search results describing "the highest figure... used as the *preliminary*
  PiN/Severity" (emphasis added on a word this session's own research surfaced, not invented) are
  consistent with this: a maximum-across-sectors figure is the **starting point** analysts work from
  in a human consensus process, not JIAF's own final, official output. **This is the single most
  important finding for scoping this tool**: a fully-automated "final JIAF severity number" is not
  something JIAF itself claims to produce without human analysts — building this tool to output one
  would overclaim what the real methodology does.
- **2026 HPC cycle update** (dated, current as of this spec — not evergreen, cite the update's own
  date if this is ever revisited): "Overall PiN including only areas in intersectoral severity Phase
  3 and above" — a change from the 2025 cycle, which included all areas in scope regardless of
  severity. Building this in as the current default, not the old one, since it's what the *current*
  cycle actually specifies.

**Not found, and not guessed at:** the exact rule (if any beyond human consensus) for how an
intersectoral severity *class* is adjusted when several sectors are simultaneously severe (the
"compounding effect of overlapping sectoral needs" JIAF 2.0's own materials name but don't reduce to
a formula in any source this research reached). §2 scopes the tool to NOT attempt this — see below.

## 2. Non-goals

- **Not a replacement for JIAF's actual Module 3 process.** This tool computes the maximum-across-
  sectors starting point the Mosaic Method itself describes — it does not, and cannot, replicate the
  "Convergence of Evidence" human consensus/validation-workshop step, which is explicitly a
  qualitative process involving multiple named actors (national clusters, OCHA, global clusters),
  not a computation. Output must be labeled a **preliminary, Mosaic-Method-based estimate**, never
  presented as an official/validated JIAF figure — this is the load-bearing scope decision in this
  entire spec.
- **Not attempting the undocumented "compounding" adjustment.** §1 found real language describing a
  compounding effect of overlapping sectoral needs but no publicly-reachable formula for it. Building
  a guessed-at compounding rule would be inventing methodology, not implementing it — explicitly out
  of scope until (if ever) a primary source spells out the actual rule.
- **Not a new indicator-normalization method.** Reuses `_compute_severity_index`'s existing min-max/
  weighted-sum math for anything that still needs normalizing — this composite operates on
  **already-computed** per-sector severity classes/PiN figures (from running `calculate_severity_index`/
  `calculate_population_in_need` once per sector beforehand), not raw indicators directly.
- **Not sector-specific.** Generic over however many sectors the user has already scored — doesn't
  hardcode "health/WASH/food security," matching how `calculate_severity_index` itself is indicator-
  agnostic rather than domain-specific.

## 3. Proposed tool: `calculate_intersectoral_severity`

```
calculate_intersectoral_severity(
    admin_layer: str,
    unit_name_field: str,
    sector_severity_fields: dict,   # {"health": "health_severity_class", "wash": "wash_severity_class", ...}
    sector_pin_fields: dict = None, # {"health": "health_pin", "wash": "wash_pin", ...} -- optional
    min_severity_phase_for_pin: int = 3,
    output_field: str = None,
)
```

Prerequisite (not this tool's job, the existing tools' job, unchanged): the user has already run
`calculate_severity_index` once per sector with `output_field` set to a distinct field per sector
(e.g. `health_severity_class`, `wash_severity_class`) on the *same* `admin_layer`, and optionally
`calculate_population_in_need` once per sector similarly, writing each sector's population figure to
its own field.

Pipeline:
1. For each admin unit, `intersectoral_severity_class` = **max** of the given `sector_severity_fields`
   values for that unit — the Mosaic-Method-adjacent preliminary severity, per §1. Also report
   `driving_sector` (which sector produced the max) — useful diagnostic context a real analyst would
   want, and cheap to compute alongside the max itself.
2. If `sector_pin_fields` given, `overall_pin` per unit = **max** of the given PiN fields for that
   unit (the literal Mosaic Method, not a sum) — units missing a value for a given sector are simply
   not compared against that sector for the max, not treated as zero (an already-established pattern
   in this codebase: missing data is excluded, never imputed).
3. Apply the 2026 HPC default: units with `intersectoral_severity_class` below
   `min_severity_phase_for_pin` are excluded from the summed total PiN (their per-unit `overall_pin`
   is still reported, just not counted in the total) — configurable via the parameter in case a
   country context or future cycle reverts this, not hardcoded as unconditional.
4. Sum `overall_pin` across included units for a total intersectoral PiN figure.
5. If `output_field`, write each unit's `intersectoral_severity_class` back to the layer (mirroring
   `_write_scores_to_layer`'s existing pattern) for `apply_categorized_style`/`apply_graduated_style`.

Return shape mirrors `calculate_severity_index`/`calculate_population_in_need`'s existing
conventions: per-unit results (worst-first, capped via the existing `_cap_entries`/50-entry
convention), a `total_intersectoral_pin`, `sectors_included`, and a **mandatory** field in the
response itself (not just the tool description) stating this is a preliminary Mosaic-Method estimate
— e.g. `"methodology_note"` — so the field is available to quote back to the user even if the model
somehow doesn't relay the tool description's own framing.

## 4. Failure modes and fallbacks

- **Fewer than 2 sectors given**: an error — a single-sector "composite" is just
  `calculate_severity_index` again, not a genuine intersectoral calculation, worth rejecting rather
  than silently no-op-ing.
- **A named field doesn't exist on `admin_layer`**: a clear error naming exactly which
  sector/field is missing, matching every other tool's field-validation convention in this codebase.
- **A unit has no value for any given sector** (all sectors missing for that unit): excluded from
  results entirely, matching `_compute_severity_index`'s own "excluded, never imputed" rule for
  missing data — reported in an `excluded_units` list, not silently dropped.
- **`min_severity_phase_for_pin` outside 1-5**: a clear validation error.

## 5. What can and can't be verified before shipping

**Can verify without QGIS:** the max-selection and PiN-summation logic is pure Python once field
values are extracted — same testable/QGIS-dependent split as every other analysis tool in this
codebase (`_compute_severity_index` vs. `calculate_severity_index`).

**Cannot verify:** whether this tool's output would actually match a real JIAF Module 3 outcome for
a real crisis — by design, per §2, it never claims to; there is no "verification" that would make
sense here beyond confirming the max/sum arithmetic itself is correct, since the real JIAF process's
final output requires human workshops this tool explicitly doesn't attempt to replace.

## 6. Prompt guidance (new rule, once built)

A new rule stating: `calculate_intersectoral_severity`'s output is a **preliminary, Mosaic-Method-
based estimate**, not an official or validated JIAF severity/PiN figure — always state this plainly
when presenting results, matching rule 20's "present as a projection, not a certain fact" framing
applied here to a different kind of uncertainty (methodological incompleteness, not statistical
confidence). Never describe this tool's output as "the JIAF severity for this crisis" without that
qualifier.

## 7. Relationship to other roadmap docs

- Extends `calculate_severity_index`/`calculate_population_in_need`
  (`docs/HUMANITARIAN_GIS_FEATURE_REVIEW.md`) rather than duplicating their math — this tool
  operates on their *outputs*, not raw indicators.
- Same anti-fabrication discipline `agent/prompts.py` rule 12 already applies to LLM-generated text
  and (per rule 34) this codebase's own imagery-extraction output, now applied to *methodology
  research itself*: where JIAF 2.0's real rule wasn't found in reachable sources (the compounding
  adjustment, §1), this spec says so plainly and scopes it out, rather than inventing a plausible-
  sounding formula to fill the gap.
