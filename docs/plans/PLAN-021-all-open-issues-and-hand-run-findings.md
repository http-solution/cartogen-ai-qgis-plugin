# PLAN-021: every open issue and every finding from the 1.18.0 hand run: fix it or close it

Status: planned

## Goal
The owner's instruction (2026-10-25): stop spending hand-test time and money; for every open issue and every finding, either plan the fix or close it. After this plan each one has a decision, a fix approach, and a CI test that proves it, and the owner is asked for one model-free check at the end, not one hand run per fix. Covers issues #72, #97, #120, #130, #148, #169, #223, #224, #362, #379, #380, #425 and the hand-run findings not already in PLAN-020.

## Scope
Decisions (a "close" needs the stated evidence; the owner has authorised fix-or-close, so a close with evidence is not held for another hand run):

| # | Decision | Evidence or fix | Proof |
|---|---|---|---|
| 148 | Close now | Hand-verified Pass (1.18.0 row OI-148): `Beside_the_arm` within at 279.9 m, `Inside_the_U` beyond at 369.8 m | the hand run |
| 130 | Close now | Hand-verified Pass (1.18.0 row OI-130): the fragment asked what to do, a bare "yes" in a new project ran nothing | the hand run |
| 169 | Close now | Umbrella: every one of its 32 children (#137 to #168) is closed once #148 is | the issue list |
| 120 | Fix gaps, then close | Labels and the black raster are verified (OI-128 pass, rc50). Not yet shown: scratch origin layers are saved or called temporary. Fix: the origin and result layers a tool creates are saved with the project or the reply says they are temporary | CI live test: run a point tool, save, reopen, layer present or reply says temporary |
| 97 | Close after one CI test | Export with 20 exchanges verified (40 messages, timestamps). Missing: the same after save and reopen | CI live test: 20 turns, save, reopen, export, 40 messages |
| 72 | Close after #97 | Umbrella of F01 to F25; its children are all closed except #97 | the issue list |
| 223 | Fix | `_background_processing.py`: release a bundle on layer removal, project close and a task that never delivers; Stop already verified | CI live test: start a task, remove the layer and close the project, the bundle store is empty |
| 224 | Fix | Root `__init__.py`: evict only this plugin's own modules, and only on reload; the in-place update and untick/re-tick already ran clean by hand | CI live test: import the plugin, simulate a reload, other plugins' modules are untouched, ours are fresh |
| 362 | Fix the three | I4 "animate the layer over time" routes to `export_temporal_animation_frames`; I6 elevation profile stops looping on `list_layout_items`; I9 "charts linked to maps" builds a layout chart, not an HTML dashboard | replay tests of the three prompts against the router and loop guard, plus the existing live layout render |
| 379 | Fix | Placement is fixed (CI). Open: the elevation-profile render is intermittently empty in CI. Add a render check with pixel assertions, find the cause from CI output, fix or make the tool report an empty profile instead of drawing axes only | CI live test that renders three charts and a profile and asserts non-blank, repeated until stable |
| 380 | Fix | Do not inject a task plan when the algorithm index strongly matches an operation-shaped request; measure the 385-prompt replay before and after (34 today); no golden routing row may be lost. "Sort the districts by population" already passes by hand | replay test with a target of 0 operation-shaped prompts matched, golden tables unchanged |
| 425 | Plan and build | Undo of `add_field`: remove the field only while it holds no values and no edits were committed after it; otherwise say so and offer to delete the column with a confirmation | CI live test: add a field, undo, field gone; add, fill, undo, refuses with a clear reply |

Hand-run findings, all fixed in the same build:
- Legend cut off, footer "may not fit" warning, bundle README and OI-224 row: PLAN-020, unchanged.
- Layout name: "create a print layout called Big Map" produced `Layout_Big_Map`. Fix: use the requested name exactly; the `Layout_` prefix stays only when no name was given. Check `_layout_names.py` so "draw into Test Layout" still finds it.
- Duplicate CartogenAI tab in Log Messages: cause not known (the extra tab appeared after installing rc40 and then 1.18.0 over it; the plugin logs with tags `CartogenAI`, `Providers`, `CredentialManager`, `ChatTabWidget`). Fix: a CI test that lists every tag the plugin logs under, and one tag only; if the tab is an artefact of the old install, say so in the update steps.
- A5 note "fetch_dem and run_steps failed" while contours were made: read the evidence folder's `steps.jsonl` of that request (it is in the returned bundle), find why those two tools were called, fix the routing or the description so a plain "draw contour lines" call uses the contour tool only.
- A3: the sector coverage chart was never opened. Covered by the CI render check: the chart image has bars for Health and Shelter only.
- A7 and A8 in the sheet depend on A6's SENSITIVE tag; the sheet states the order. Not a product change.
- A18 lineage by buffer then rename: add a CI live test (the merge-then-rename case is hand-verified); the owner's click is not needed.
Out: new features beyond the above; a release (the owner decides when and which version).

## Acceptance
1. Offline CI: pure logic for every item (legend fit, name rule, undo rule, router decisions, tag list).
2. CI live (QGIS 4.2.2): each proof column above, run on every push.
3. Ledger: one entry per fixed feature with its guard tests; `tools/ledger_guard.py` passes.
4. Hand check, once, model-free: a console script in the next bundle that exports the three layouts (legend, footer, names) and prints the footer heights. Nothing else is asked of the owner for these items. The owner's remaining list is only what CI cannot judge: how the legend and footer look in the exported PDF on the Windows fonts.

## Guard tests
Named as each item is written; each new test goes in the ledger entry of its feature.

## Rollback
One pull request per group (A: closures and comments, B: layouts and names, C: processing and reload, D: routing and prompts, E: undo). Each reverts alone. Layouts and projects already saved are not changed.

## Status log
- 2026-10-25: plan written after the owner's instruction to plan every fix or close. Closures of #148, #130 and #169 are done with this plan (comments posted). Everything else is planned, nothing built yet.
