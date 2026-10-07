# rc21 live smoke test sheet (prepared 2026-10-07)

A blank sheet, not a result. rc21 fixes three things the rc20 hand test found (see the `v1.16.0-rc21` block in `metadata.txt`). **The rc20 sheet (`docs/SMOKE_RUN_SHEET_rc20_2026-10-06.md`) stays the master for rows D1-D14, the rc19 sheet for A1-A12, and the rc18 sheet for rows V, T, J, P and the fixtures.** Install and gate steps are the same as rc18 section 0. Nothing in rc21 has been hand-tested. If a prerequisite is missing write "not run: <reason>", never an inferred pass.

## F. New in rc21 (the rc20 failures, re-tested)
| Id | Prompt / action | Expected | Result |
|---|---|---|---|
| F1 | Ask the agent to colour a polygon layer by a numeric field whose values run about 5 to 15, with manual breaks `[100]` (or "classes at 100") | An error that names the data range (5 to 15). **No** inverted "100 - 15" class and no legend entry for it (#165) | |
| F2 | Same layer, manual breaks inside the range (`[8, 11]`) | Three classes with sensible labels, legend matches the map | |
| F3 | Rotate the map canvas to about 30 degrees (View > Rotate map, or the rotation box in the status bar). Ask for a print layout of the current view; export the PDF | The layout's map is rotated and the north arrow is rotated with it, pointing to the top of the page's true north. It is not upright at 0 degrees (#165) | |
| F4 | With the map not rotated, create the same layout | The arrow is upright (no regression) | |
| F5 | NEW CHAT. Send exactly: `template: access_map` | The agent asks what you want. **No** print layout is created, no layer is added or changed (#130). It may call a read-only tool such as get_layers | |
| F6 | NEW CHAT. Ask "Which CRS should I use?" style question yourself: send "Add a point at 4902068.0, 1799912.0" in an EPSG:4326 project, answer the CRS question with `EPSG:3857` | The point is placed (no regression from the fragment gate) | |
| F7 | Reply `yes` to a task card, then separately reply with a plain layer name such as `smoke_hubs` to a question | Both work as before | |

## G. Carry-over
Run D1-D14 (rc20 sheet), A1-A12 (rc19 sheet) and V, T, J, P (rc18 sheet) on rc21; run the gates (fresh-profile install, upgrade from the previous zip, restart twice, uninstall and reinstall).

Known open, do not expect a pass: model-added plans and arrange steps (N3/N9), geography suggested from project memory in prose (N1), PostGIS connections that authenticate through a QGIS auth configuration (not tested), the legend-by-role and attribution items listed in #165.
