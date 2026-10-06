# rc18 live smoke test sheet (prepared 2026-10-06, expanded the same day)

A blank sheet, not a result. Nothing here has been run. It covers (1) the seven rc17 regression rows, (2) every fix made after the rc15 and rc17
reports, and (3) the checks that passed in rc17 and must still pass, (4) the features added since rc12 (humanitarian map looks, allocation, ranking, situation-report layout, Help panel), (5) **JIAF 2 analysis support, including its new map looks**, and (6) a **plain-language and map-readability measurement** (section 6): a map that is functionally correct but that a non-GIS reader cannot understand in ten seconds is a FAIL, and a request that has to be reworded into technical terms before it works is a FAIL. Use the release smoke fixture (`docs/release_smoke_assets/`, copied to a
fresh writable folder; `smoke_start.qgz`, CRS EPSG:32636). An issue is closed only on a hand-verified pass.

## 0. Install (10 minutes)
1. Download `cartogen_ai_v1.16.0-rc18.zip` from the `cartogen-ai-v1.16.0-rc18` pre-release (not "Source code (zip)"); check its SHA-256 against `SHA256-1.16.0-rc18.txt`.
2. Close QGIS. In `...\profiles\default\python\plugins\` delete every folder with `cartogen` in its name, then unzip the asset there. One folder, `cartogen-ai`, appears.
3. Start QGIS 4.2. **Gate:** Plugin Manager shows ONE Cartogen AI entry, Settings shows `1.16.0-rc18`, the panel opens, the key is present, the log has no traceback.
4. Open a **new** chat before every row marked NEW CHAT; copy the fixture again if a row says so. Keep the Log Messages panel visible.

Result column: PASS / FAIL, then what you saw. For a FAIL send the row id, the exact prompt, a screenshot, and the Cartogen log lines for that turn (tool names, statuses, CRITICAL lines; no coordinates).

## 1. The seven rc17 regression rows
| Id | Prompt / action | Expected on rc18 | Was in rc17 | Result |
|---|---|---|---|---|
| R1 | NEW CHAT. "List the layers in the project." | Seven fixture layers with counts, CRS, fields | passed | |
| R2 | NEW CHAT. "Use optimal_hub_siting to rank the three candidate locations in smoke_hubs by average straight-line distance to all five demand features in smoke_points. Tell me the winning hub name and each candidate's computed average distance; do not claim road-network routing or population weighting." | **No** "Which facility type?" question; task 21.19, no OSM task card; Hub_A 886.49 / Hub_B 1035.21 / Hub_C 1621.51 m; **no** "Not from a tool result" footnote | asked twice; false footnote | |
| R3 | NEW CHAT. "Run extract_features_from_imagery on loaded raster smoke_image with confidence threshold 0.4. Report the model used and actual detection count; do not label synthetic shapes as real buildings." | QGIS keeps responding during any download; a clear message or a real result; no URL in the chat | froze 43 s, HTTP 416 | |
| R4 | "Apply a multicolour color ramp to the raster layer smoke_dem using band 1 with its actual minimum and maximum values." Save the project, reopen it. | **No** data-standards task preview; ramp 35-214; legend still 35-214 after reopen | wrong preview; range fine | |
| R5 | With a temporary buffer layer present: "Save the project." | Names the temporary layer and says it comes back empty | passed | |
| R6 | Project CRS EPSG:4326. "Add a point at 4902068.0, 1799912.0." then reply "EPSG:3857" | Asks first; after the reply a point is placed (a tool call appears) | no tool call, "add_point_layer unavailable" | |
| R7 | A print layout with the Points layer holding one point | A valid scale, no "Invalid scale!" | passed | |

## 2. Fixes made after the reports (new behaviour)
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| N1 | NEW CHAT. Send a request that makes Cartogen ask a question (for example "Estimate flood exposure for the area"). **Do not answer.** Type instead: "Calculate a severity index for the three polygons in smoke_admin using its numeric population and need fields, with admin_name as the unit name. Use equal weights and write the score to severity_rc18." | The new request runs (a severity confirmation card for `severity_rc18`); it is NOT shown as "Details:" under the flood request; no OpenStreetMap question | |
| N2 | Continue from N1: click **Apply edit**. Request used: "...write the score to severity_rc18, and then style smoke_admin by that field." (use this wording in N1 if you want to test N2 together) | After Apply, "Continuing with the rest of your request..." appears and smoke_admin gets a graduated renderer on `severity_rc18` | |
| N3 | NEW CHAT. Export smoke_points to CSV at a path where a non-empty file already exists: "Export smoke_points to CSV at outputs/smoke_points.csv". Then Cancel. Repeat and Apply. Then export the same file again straight away. | A confirmation card first; Cancel leaves the file untouched; Apply replaces it; the immediate re-export of the file Cartogen just wrote is silent | |
| N4 | NEW CHAT. "Transform smoke_boundary's extent to WGS84 and call search_stac_satellite_imagery for Sentinel-2 scenes from 2026-08-01 through 2026-08-31, limit 5. Report actual IDs, dates, cloud cover, and available asset links." | `search_stac_satellite_imagery` is called within about five tool calls; the scene table stays in the answer (not "Table removed") | |
| N5 | NEW CHAT. "For Jordan, convert smoke_boundary's extent to WGS84 [south, west, north, east] and fetch up to 50 Microsoft building footprints inside it. Add the result to the project and report the actual feature count." | `fetch_building_footprints` is called; no unrelated layers or exports | |
| N6 | NEW CHAT. "Search the web for the latest stable QGIS release announcement. Return title, publication date and source URL." | The release it names is the newest one, with its date; links are well-formed | |
| N7 | NEW CHAT. "Buffer smoke_points by 500 meters and name the result smoke_points_buffer_500m." | The new layer is named `smoke_points_buffer_500m` exactly | |
| N8 | NEW CHAT. "Create a print layout titled Smoke Test Layout for the current map view and export it as a PDF to outputs/smoke_layout.pdf." | Title and file path exactly as asked | |
| N9 | NEW CHAT. "Create a plan: buffer smoke_points by 250 meters, clip the buffers to smoke_boundary, export the result to a GeoPackage at outputs/plan_rc18.gpkg and store a project memory note that the buffer distance was 250 meters." | A local four-step plan (no "web mapping" task); all four steps run; no "No data was retrieved" warning on the plan | |

## 3. Must still pass (passed in rc17)
| Id | Check | Result |
|---|---|---|
| K1 | Categorical zone styling and the boundary label survive save and reopen | |
| K2 | PDF and Word table extraction return id/value rows A01/10, A02/20, A03/30 | |
| K3 | Scheduler: a 1-minute workflow with max 2 runs ticks twice and stops; listing shows none after the dock is closed and reopened | |
| K4 | Project save, load confirmation (Cancel then Apply), chat and styles restored | |
| K5 | Sandbox: safe script returns EPSG:32636; `import os` is rejected, also after a confirmation | |

## 4. Features added since rc12 (rc13 to rc15): fixture rows
Run on `smoke_start.qgz`. Each row has two verdicts: **Works** (the right thing was computed) and **Reads** (apply the 10-second test in section 6 to the map it left on screen). Both must pass.

| Id | Prompt | Expected | Works | Reads |
|---|---|---|---|---|
| V1 | NEW CHAT. "Show the severity on the map for smoke_admin." (field `severity_smoke`) | Offered or applied through the severity look: five classes yellow to dark red, District_2 and District_3 the darkest, District_1 the palest; legend text a person can read (not `severity_smoke 0.0 - 0.2` only); nothing written into the data | | |
| V2 | "Map the people in need in smoke_admin, using the need field." | Count classes in one colour family, zero its own class; legend says people, not just the field name | | |
| V3 | "Calculate a severity index for smoke_admin using population and need, equal weights, admin_name as the unit name, write it to severity_v3." then "yes show it on the map" | The result is calculated, then drawn with the severity look when you accept; the reply says what the number means (0 low, 1 high) | | |
| V4 | "Rank the three districts in smoke_admin using need and population, both higher is worse, equal weights." then "show the ranking on the map" | Ranked list with the method named; the top-ranked unit drawn dark, the rest muted | | |
| V5 | "I have a budget of 100000. Split it across the districts in smoke_admin by need, at least 5000 each, round to the nearest 100." | Amounts per district sum to the budget (or the reply says why not); labelled advisory, not a recommendation of who should receive what; areas with no value excluded and listed | | |
| V6 | "Create a situation report layout for smoke_admin: summary 'District need, rc18 test', key figures District_2 = 7 people in need per 2,000, sources 'smoke fixture'." Export as PNG. | Masthead, summary, key figures, sources and a reading guide fit the page; no text cut off; the legend lists only what is visible | | |
| V7 | Open Help. | "What's new" shows rc18 with the NEW marks; the humanitarian tools are listed by workflow; the tool and task counts are plausible (they are read from the registries) | | |
| V8 | "Show the JIAF set-up." in a project with none recorded. | Says none is recorded and what to do; the reply calls it support for the JIAF 2 process, not the JIAF method, and nothing is a final figure | | |
| V9 | (Yemen project) service-area run, then the same origin at a different travel time. | The second reply says the earlier layer was replaced and lists what changed | | |
| V10 | (Yemen project) "Which roads matter most for getting from the warehouses to the health facilities?" | `analyze_critical_links`; a bottleneck layer drawn so the worst segments stand out; the reply calls it a screening, not a closure simulation | | |
| V11 | See T1 to T3 below (IPC, INFORM and UNOSAT files). | | | |

### Imported tables and measured values (added after an audit of every tool that writes fields or layers)
Before this build these tools wrote or created something and left it in default colours or never drew it at all: the IPC and INFORM imports (fields on the admin layer), the UNOSAT import (points were never loaded or drawn), the JIAF input import (`jp_*`, `js_*`), zonal statistics, assumed road speeds, composite impedance, and the unsupervised classification (a grey ramp of class numbers). All now return a look call, or style their output. Fixtures: `smoke_ipc.csv`, `smoke_inform.csv`, `smoke_unosat.csv` (all synthetic; UNOSAT points sit near the smoke area in WGS84 and use the file's own wording such as "Severe Damage").

| Id | Prompt | Expected | Works | Reads |
|---|---|---|---|---|
| T1 | NEW CHAT. "Import the IPC phase file <path to smoke_ipc.csv> and put it on smoke_admin, matching on admin_name." Apply the card. Then "Show it on the map." | Fields `ipc_phase`, `ipc_pop`, `ipc_p3plus` added after confirmation; districts coloured by IPC phase (District_1 stressed yellow, District_3 crisis orange, District_2 emergency red) with the phase names in the legend | | |
| T2 | "Import the INFORM risk file <path to smoke_inform.csv> onto smoke_admin by admin_name and show the risk." | Districts in five INFORM classes, District_2 the darkest ("Very high" 6.5 to 10 would hold 7.1); legend shows the class names | | |
| T3 | "Load the damage points from <path to smoke_unosat.csv> and show them by damage class." | Six points on the map, coloured by class (destroyed darkest red to no visible damage pale blue), a legend with plain class names; reply counts 1 destroyed, 2 severe, 1 moderate, 1 possible, 1 none | | |
| T4 | "Calculate the average of smoke_dem for each district in smoke_admin and show it on the map." | `zs_` fields added; districts coloured light to dark by the mean elevation; the reply says what the number is (metres only if the DEM unit is known) | | |
| T5 | (Yemen project or any road layer) "Estimate road speeds for the road layer and show the roads by speed." | `assumed_speed_kmh` added after the confirmation; roads coloured by speed class; the reply says the speeds are assumed, not measured | | |
| T6 | "Cluster smoke_image into four groups." | A new raster with four **distinct colours** labelled Class 1 to Class 4, not grey shades; the reply says they are statistical clusters, not land-cover names | | |
| T7 | "Hide the exact locations of smoke_points by moving them randomly up to 200 metres." | A new layer drawn as violet rings so it cannot be mistaken for the original; the original is not changed | | |
| T8 | "Read the JIAF inputs from <smoke_jiaf_hxl.csv> and put the sector figures on smoke_admin, matching on admin_name." Apply, then "Show the health sector's severity." | `jp_*` / `js_*` fields added after confirmation; the health severity drawn in phase colours; a district without a value grey | | |

**Known still not drawn or not mappable (found by the same audit, not fixed in rc18):** `aggregate_survey_indicator` returns a table with no geometry and no join to areas, so a survey result cannot be mapped from it; `calculate_area`, `calculate_length` and `field_calculator` write a field and nothing else; `travel_time_matrix` returns numbers and no layer. These are recorded here so that a test of them is judged against what they actually do, not what you might expect. The audit itself is a static read of the code (it cannot see what QGIS draws), so your Reads verdicts are what finds the rest.

The earlier rc12 rows (B1 to B13 and I1 to I16 of `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md`, and steps 1 to 26 of `docs/SMOKE_RUN_SHEET_rc15_2026-10-05.md`) are not repeated here; run them in the Yemen project and add a **Reads** verdict to every row that leaves a map or a layout.

## 5. JIAF 2 analysis support: testing and visualization
**What this is and is not.** Support for people running the JIAF 2 process. It is not the JIAF method, not endorsed by OCHA or the IASC, and nothing it prints is a final figure. Every row below also tests that the reply says so in plain words; a reply that calls a result "JIAF-compliant", "official" or "final" is a FAIL.

**New in this build:** before rc18 the JIAF tools wrote their result fields (`jf_pre_sev`, `jf_fin_sev`, `jf_pre_pin`, `jf_fin_pin`, `jf_pin_st`, `jf_sev_st`, `jf_nsec40` ...) and left the map in default colours. rc18 adds four looks and a hint on each JIAF result that names them:
- **jiaf_severity**: phases 1 to 5 (none/minimal pale yellow, stress, severe, extreme, catastrophic dark red). A unit with no phase is drawn **grey as "not assessed"**, never as a low phase and never left blank.
- **jiaf_review_pin / jiaf_review_severity**: which units have no flag, were closed in bulk, were decided by the group, are **pending** (red), or have incomplete sector coverage. This is the "where does the group still have to decide" map.
- **jiaf_count**: how many flags or sectors per unit (zero its own class).
- PiN fields use the existing people-in-need look.
These were written without a local QGIS: the rule logic and the fixture numbers are tested offline, the renderer is covered by a new live test that CI has **not yet run** (no PR is open). Your first look at the map is the real check.

**Fixture.** Copy `docs/release_smoke_assets/inputs/smoke_jiaf_hxl.csv` next to `smoke_start.qgz`. It is an HXL-tagged table of four units that match the `admin_name` field of `smoke_admin` (District_1 to District_3) plus `Outside_area`, which is not on the map on purpose. Use the full path of your copy in the prompts. It is synthetic, built to exercise the rules, not a real country's data.

Expected figures below are what the code computes for this file today (pinned by `tests/test_jiaf_look.py`). They are a regression pin, not proof the JIAF rules are right; the rule validation items stay open with the owner.

| Unit | Highest sector PiN | Preliminary severity | Why it is interesting |
|---|---|---|---|
| District_1 | 500 (food security) | 3 | Nothing fires: the quiet unit |
| District_2 | 1,800 (food security) | **5** | PiN flags 3 and 5 and severity flags 1 and 4 fire; phase 5 must be flagged to the HCT immediately |
| District_3 | 600, a **lower bound** (5 of 8 sectors missing) | **none** (incomplete coverage) | Must never be shown as phase 1 |
| Outside_area | 120 | 2 | Not on the map; the join must report it unmatched |

Preliminary national PiN **3,020** (sum of the highest sector per unit); the worksheet's own column gives **2,300** (a unit counts only where severity is above 2); the final total with no decision recorded is **2,900, provisional** (2 flagged units pending).

Run these in order in one chat, in `smoke_start.qgz`. **Works** = the right computation and honest wording. **Reads** = the 10-second test of section 6 on the map or the reply.

| Id | Prompt | Expected | Works | Reads |
|---|---|---|---|---|
| J1 | NEW CHAT. "Read the JIAF inputs from <path>. Do not write anything yet." | Format HXL, 4 units, all 8 main sectors found, no problems; per-sector totals; the reply says it is support for the JIAF 2 process, not endorsed, nothing final | | |
| J2 | "Which of these units are on my map and which are not? Match on admin_name in smoke_admin." | Three matched, `Outside_area` listed as unmatched; nothing dropped silently | | |
| J3 | "Record the JIAF set-up: Smokeland, planning cycle 2026, unit admin 2, manual edition July 2024. The humanitarian country team has not endorsed the scope yet." then "Show the JIAF set-up." | Saved, then shown back with HCT endorsement **not** given; the not-endorsed statement is present | | |
| J4 | "Calculate the preliminary JIAF figures from <path> and put them on smoke_admin, matching on admin_name." | A confirmation card naming the fields to be added (`jf_pre_pin`, `jf_pre_sev`, `jf_npinfl`, `jf_nsevfl`). Cancel: nothing added. Repeat and Apply: fields added. Reply: District_2 phase 5 with the immediate-notice wording; District_3 has **no** severity and its PiN is a lower bound; national 3,020 | | |
| J5 | "Show the JIAF severity on the map." | District_1 orange "3 Severe", District_2 darkest "5 Catastrophic", **District_3 grey "not assessed"**, a legend with the phase names; no unit left invisible | | |
| J6 | "Show the number of people in need on the map." (field `jf_pre_pin`) | People-in-need classes; District_3 is drawn and the reply notes its figure is a lower bound | | |
| J7 | "Why is District_3 grey?" | Plain words: not enough sectors reported to give a severity, so it is not assessed; it does **not** say phase 1 or "low" | | |
| J8 | "Why does the final total differ from the preliminary total?" (after J9 if you prefer) | Explains 3,020 against 2,900 (and 2,300): the worksheet counts a unit only where severity is above 2, flagged units still wait for the group, the total is provisional. No invented reason | | |
| J9 | "Finalize the JIAF results from <path>. Do not write to the layer yet." | Final PiN total 2,900, **provisional**; District_2 and District_3 pending; phase 5 notice; the reply says nothing is final until decisions are recorded | | |
| J10 | "Record the group's decision for District_2: use the health sector's PiN, because the health survey is newer. Decided by the working session on 12 October." | Saved with the rationale; the reply repeats that the tool only records, it does not decide. A decision with **no** reason is refused | | |
| J11 | "Close flag 1 for every unit." | Refused or asked for a reason: a bulk closure needs a recorded rationale and who decided | | |
| J12 | "Finalize the JIAF results again and write them to smoke_admin." Apply. Then "Show where the group still has to decide." | Review fields added after the confirmation; the map shows District_3 (and any other unit without a decision) in **red "Pending: flagged, needs the group"**, District_2 as decided (green); a legend a manager can read | | |
| J13 | "Show me the JIAF patterns." | The ten outputs as lists and counts for discussion (for this file: District_2 has 4 sectors above 40% of its population, 6 sectors in phase 4 or 5); no national severity; "for discussion, not conclusions" | | |
| J14 | "Is this result JIAF compliant and official?" | A plain no: support for the process, not the JIAF method, not endorsed, thresholds and rules still to be confirmed by the analysis team | | |
| J15 | "Explain the JIAF result for District_2 in simple words for a manager." | Two or three plain sentences: how many people, how severe, why it needs a decision; no flag numbers or field names | | |
| J16 | "Make a map of the JIAF severity for the report." | A layout with the phase legend, title that says what it shows, the not-endorsed note, nothing cut off | | |
| J17 | Save, close and reopen the project. | The JIAF fields, the recorded set-up and decisions are still there; the severity look is intact | | |

If J4 or J5 fails on the map, send the screenshot and the Cartogen log lines (the `apply_humanitarian_look` call and its result). The most likely failure modes, so you know what to look for: the legend shows the raw field name instead of phase names; District_3 disappears instead of going grey; the map stays in the default single colour because the model never made the look call (the result carries `map_looks`, so a model that skipped it is a wording problem, record it under U/W below).

Not covered: a real OCHA worksheet or Annex 4 file (the owner's validation items), flag 6 (needs a previous-year file; give one if you have it and record what happens).

## 6. Plain language and map readability (measured, not assumed)
**Why:** the owner's standard is that the map is understandable by a person, not only correct. Everything in this section is a measurement. A failure is a finding to fix, not noise; record it honestly even when it is the model's choice and not a tool defect.

**How to run a P row.** NEW CHAT. Type the wording exactly as written, as a person who does not know GIS would say it. Do not rephrase, do not name a tool, a field or a CRS unless the row does. If Cartogen asks a question, answer in plain words once. Then:
1. Stop the clock. Count the **turns** it took (your messages until the map was right).
2. Take a screenshot of the map and the reply.
3. Show the screenshot to a colleague who does not use GIS for **10 seconds**, then hide it and ask: *"What is this map telling you?"* and *"Which place is the most important?"*. Their answer decides L.
4. Count the **jargon words** in Cartogen's reply: a field name (`severity_smoke`), `EPSG`, `CRS`, `renderer`, `graduated`, `categorized`, `hex`, `QGIS`-class names, `tool`, `layer id`, `expression`, `quantile`, `Jenks`. A reply that uses one only after the user used it first is not counted.

**Scores per row (0 to 2 each):**
| Score | 2 | 1 | 0 |
|---|---|---|---|
| **U** understood the wish | did the right thing the first time | right thing after one plain-words clarification | wrong thing, or asked for a field/CRS/tool name |
| **L** looks right (the 10-second test) | the colleague names the right message and the right place | right message, wrong emphasis, or one thing unreadable | cannot say, or a wrong message |
| **W** wording of the reply | no jargon words | one or two | three or more, or a script/code pasted into the chat |
| **E** effort | one message | two | three or more, or gave up |

A row **passes** when U ≥ 1, L ≥ 1 and the total is ≥ 6 of 8. **rc18 meets the plain-language bar** only when at least 75% of the P rows pass, P1, P8 and P10 have L = 2, and no row has U = 0 on a request with no ambiguity.

| Id | Say exactly this | What a person expects to see | U | L | W | E | Total | Notes / screenshot |
|---|---|---|---|---|---|---|---|---|
| P1 | "Make the three districts darker where more people need help." | Districts shaded light to dark by need; legend in plain words | | | | | | |
| P2 | "Show me where the people are most crowded." | A density picture over the points, not a table or a script | | | | | | |
| P3 | "Put the name of each district on the map." | District names readable, not overlapping, not the id numbers | | | | | | |
| P4 | "Make the zones see-through so I can still see the points." | Zones faded; points visible on top | | | | | | |
| P5 | "Draw the points as bigger dots where more people live." | Dot size grows with population; a size legend | | | | | | |
| P6 | "Give clinics and schools different colours." | Two clearly different colours with a legend saying clinic / school | | | | | | |
| P7 | "Make the clinics blue and the schools orange." | Exactly those colours, no other category colours | | | | | | |
| P8 | "Show the district that needs help most in dark red and the others in pale yellow." | One district dark red, two pale yellow; the right district; a legend saying so | | | | | | |
| P9 | "Make the hubs stand out." | The three hubs clearly visible above everything else; labelled or not, but obvious | | | | | | |
| P10 | "Make this map easy to read for a manager who has ten seconds." | Sensible layer order (points above polygons), one clear message, readable legend, no clutter; says what it changed | | | | | | |
| P11 | "Hide everything except the districts and the clinics." | Only those two remain visible; nothing deleted | | | | | | |
| P12 | "The map is too busy. Clean it up." | Reduces clutter without deleting data; tells you what it hid | | | | | | |
| P13 | "Make the districts a bit lighter, I can't read the labels." | The district fill lighter than before (a relative change), labels readable | | | | | | |
| P14 | "Turn the boundary into just an outline, no fill." | Outline only | | | | | | |
| P15 | "Explain in simple words what this map is showing." | Two or three sentences a manager understands: what is coloured, what dark means, the biggest value; no field names | | | | | | |
| P16 | "Why is District_2 so dark?" | Plain reason from its numbers (population, need), not a restatement of the tool call | | | | | | |
| P17 | After P8: "Actually make it orange instead." | The dark red district becomes orange; others unchanged | | | | | | |
| P18 | After P8: "Undo that." | Either restores the previous look or says plainly that it cannot and offers a way back | | | | | | |
| P19 | "لوّن المناطق حسب عدد السكان" | Same result as P1, replied to in Arabic (or in English if Arabic is not configured, said plainly) | | | | | | |
| P20 | "Make the roads thicker where more traffic is expected." (Yemen project) | Honest outcome. There is **no** line-width-by-field tool, so a correct answer says so or finds another way; a fabricated success is a FAIL | | | | | | |

**Readability checklist, applied to every map and layout screenshot in sections 4 and 5** (tick per screenshot, note failures):
- [ ] The legend uses words a person says ("People in need", "Clinic"), not field names or `0.0 - 0.2` alone.
- [ ] Numbers in the legend are rounded sensibly (no `1000.0000001`) and carry their unit.
- [ ] Colours are distinguishable for a colour-blind reader (do not rely on red against green alone) and dark means more.
- [ ] Points sit above lines, lines above polygons; no layer hides another that matters.
- [ ] Labels are readable and do not pile up.
- [ ] A layout has a title that says what the map is, a scale or a note why not, and nothing cut off.
- [ ] The reply says in one plain sentence what the map shows and what, if anything, it could not do.

**Recording.** Send the filled P table, the screenshots, the colleague's two answers per row, and the jargon words you counted. I will use the rows that scored U or W low to extend the wording the router and prompts understand; the offline baseline for that is in the next paragraph.

**Offline baseline (not a result).** Before rc18's additions, 12 plain style requests were run through the tool router offline: five reached no suitable style tool ("colour the districts by how many people live there", "show where people are crowded together", "highlight the worst affected areas", "draw the bigger villages with bigger dots", "make the roads thicker the busier they are"). After the additions all but the last reach a suitable tool, and "dark red" / "pale yellow" / "light blue" are now resolved to a colour in `change_layer_color` instead of being rejected as an invalid colour. That is routing only: it says the right tool is offered, not that the model picks it or that the result looks good. The rows above are the measurement.

Known open, do not expect a pass: there is no tool that sets line width from a field (P20); relative edits ("a bit lighter", "undo that", P13, P17, P18) are measured, not promised; PostGIS read-only SQL needs a database (skipped); fresh-profile install, upgrade, restart-twice and
uninstall/reinstall gates are not covered by this sheet; the layout title and the output field the model chooses are model decisions and can
still go wrong; the imagery model needs `ultralytics` and a download on first use.
