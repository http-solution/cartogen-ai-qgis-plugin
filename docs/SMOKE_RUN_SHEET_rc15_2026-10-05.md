# Live smoke-test run sheet — rc15 (prepared 2026-10-05)

A blank sheet, not a result. Nothing here has been run. It orders the hand checks from `docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md`
(issue rows), `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md` (rows B*, C, E, I*) and `docs/RELEASE_SMOKE_TEST.md` (16 categories) into one
session. Close an issue only on a hand-verified pass; record each row (build, date, pass/fail, exact prompt, what you saw, screenshot/log line).

## Before you start
1. **Install** the `cartogen-ai-v1.16.0-rc15` pre-release asset (the attached zip, not "Source code (zip)"). Verify SHA-256
   `fe35f3720e634e6ecd75203fbc7f5f4db62ca27f4e9149449cb65ad0c07f0a87`. Restart QGIS (QGIS 4.2.2). Settings must show `1.16.0-rc15`.
2. **Data:** the Yemen/Sanaa project (roads with `oneway` F/T/B and `speed_kmh`, health facilities, `yem_ppp_2020`, an HDX admin layer). Save it
   first. For the synthetic rows use `docs/release_smoke_assets/inputs/smoke_start.qgz` (copy the whole bundle to a writable folder).
3. **One working provider** configured (a cloud one for the egress rows #149/#93; a local one is fine elsewhere).
4. **Open the QGIS log panel** (Log Messages > Python and Cartogen) and keep it visible; note any traceback.
5. **Make a dated results doc** (copy the table below) and fill as you go.

## Run order (stop and note if the gate fails)
| Step | Row | Prompt / action | Expected | Issues | Result |
|---|---|---|---|---|---|
| G | Gate | Start QGIS; open panel | Panel opens; key present; no traceback; version rc15 | — | |
| 1 | B1 | "Add a point at 4902068.0, 1799912.0." (3857 project) | Asks which CRS; places nothing | #119 | |
| 2 | B6 + #130 pt3 | Paste `template: access_map`. Then a one-hour service area, then the same origin at 5 km or `fastest` | No analysis for the fragment. Second run's reply says the earlier layer was replaced and lists what changed (silent for an identical re-run) | #130 | |
| 3 | B2 | Same service-area request three times | One origin layer; no new origin/result sets | #121 | |
| 4 | B7 | Service area beside a one-way street | Differs from the two-way result | #132 | |
| 5 | B3 | "Which health facilities are beyond one hour's travel from <point>?" (note the time) | Green/red layer kept; no re-style; well under a minute; 110 reachable | #122, #80 | |
| 6 | B9 | "Population within the one-hour service area" | Three labelled figures; convex hull marked an upper bound | #123, #81 | |
| 7 | B5 + #125 | Stage `load_project`/`remove_layer`, reply "yes"; type "confirm" while an egress card is pending | Hint only, no model call; egress approved only by the card click; project not replaced | #88, #125 | |
| 8 | B4 | Tall confirmation card, scroll up while it works | View does not jump; clock times on bubbles | #124 | |
| 9 | B8 | Download admin boundaries twice | One layer, labelled, pale fill, below lines/points | #127 | |
| 10 | B10 | Old project: "tidy the project layers", then apply | Lists duplicates/black raster/scratch; apply hides copies, restyles, saves scratch; deletes nothing | #120, #128 | |
| 11 | B11 | "Fastest route from A to B" (note the time) | Estimate labelled with speed basis; route above roads; well under 14 min | #131 | |
| 12 | B12 | Access-map print layout, PNG and PDF | Thin pale graticule; legend lists reach polygon; body panel fits; no stacked sets; reading guide says **blue** | #129, #165 | |
| 13 | B13 | HTML dashboard, basemap "none" and default; open in a browser | Saved in `<project>/outputs`; "showing N of M"; map fits; markers draw | #84 | |
| 14 | #139/#140 (I8) | Processing toolbox: hub siting on valid points; service-area algorithm on roads + facilities | Both run | #139, #140, #156, #157 | |
| 15 | #141 | `calculate_area`, project area unit km² then ha | `area_sqm` identical | #141 | |
| 16 | #143 | Leave a layer in edit mode with an edit; field-calculate | Your edit stays uncommitted; undo works | #143 | |
| 17 | #144 | Field-calculate a bad expression; text into an integer field | Error shown; layer unchanged | #144 | |
| 18 | I1–I3 | Per `RC12_..._PLAN` section I rows I1–I3 | See plan | #159–#161 | |
| 19 | I4–I7 | Rows I4–I7 (raster grid, profile, barriers, matrix) | See plan | #152–#155 | |
| 20 | I8–I11 | Rows I8–I11 | See plan | #156, #157, #162–#164 | |
| 21 | I12–I16 | Rows I12–I16 | See plan | #165–#167, #91, #93 | |
| 22 | #137, #138, #145–#150 | Section 3 "Hand check" cells of the verification checklist | See checklist | #137–#150 | |
| 23 | Long session | #75: after a service-area run ask "What population lives within one hour of this point, and what region is that in?" Note false positives/misses of the footnote. #97: export chat history after a ~45-minute session | Per checklist | #75, #97 | |
| 24 | Hydrology / JIAF | Plan section E (H1–H5); `record_jiaf_decisions`, `finalize_jiaf_results` with `write_fields` | See plan | — | |
| 25 | 16-category smoke | `RELEASE_SMOKE_TEST.md` checklist table | See table | smoke 16–18 | |
| 26 | C13/C14 | Clean-profile install; upgrade from the previous zip | Both work | — | |

## Not testable in this pass
- **#151** PostGIS read-only SQL needs a database.
- Known gaps: raster-unit validation, automatic raster alignment, DEM vertical unit, running-task invalidation at unload.
- **#89, #158, #168** are closable on CI evidence (your call). **#169** closes when #137–#168 are closed.

## Recording
After the session, give me the filled results (or just the failures with exact prompt, what you saw, and log lines). I will file defects,
update `docs/IMPLEMENTATION_TRACKER.md`/`BUG_TRACKER.md`, and prepare any fixes. I do not close issues.
