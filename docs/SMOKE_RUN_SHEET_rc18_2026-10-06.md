# rc18 live smoke test sheet (prepared 2026-10-06, expanded the same day)

A blank sheet, not a result. Nothing here has been run. It covers (1) the seven rc17 regression rows, (2) every fix made after the rc15 and rc17
reports, and (3) the checks that passed in rc17 and must still pass, (4) the features added since rc12 (humanitarian map looks, allocation, ranking, situation-report layout, JIAF 2 support, Help panel), and (5) a **plain-language and map-readability measurement** (section 5): a map that is functionally correct but that a non-GIS reader cannot understand in ten seconds is a FAIL, and a request that has to be reworded into technical terms before it works is a FAIL. Use the release smoke fixture (`docs/release_smoke_assets/`, copied to a
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
Run on `smoke_start.qgz`. Each row has two verdicts: **Works** (the right thing was computed) and **Reads** (apply the 10-second test in section 5 to the map it left on screen). Both must pass.

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
| V11 | (any IPC / INFORM / UNOSAT file you have) "Import this IPC file and join it to the admin layer." | The column mapping used is shown; unmatched P-codes are listed, not dropped silently; the result is drawn with a readable look | | |

The earlier rc12 rows (B1 to B13 and I1 to I16 of `docs/RC12_LIVE_TEST_AND_AUDIT_PLAN_2026-10-04.md`, and steps 1 to 26 of `docs/SMOKE_RUN_SHEET_rc15_2026-10-05.md`) are not repeated here; run them in the Yemen project and add a **Reads** verdict to every row that leaves a map or a layout.

## 5. Plain language and map readability (measured, not assumed)
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
