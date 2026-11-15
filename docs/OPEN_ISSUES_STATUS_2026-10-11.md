# Open GitHub issues: status at rc35 (2026-10-11)

A dated snapshot, not a result. **46 issues are open.** None was closed in this pass, because the rule is that an issue closes only on a
hand-verified pass and nothing after rc22 has been hand-tested. "State" below is what the repository notes say about the code
(`docs/ISSUE_VERIFICATION_CHECKLIST_2026-10-05.md`, `docs/IMPLEMENTATION_TRACKER.md`), plus what changed since; it was **not re-run today**.
Already closed on GitHub: #151, #152-#168 except #162, #220, #221, #228, #231 (an earlier list of mine called some of these open; it was out of date).

How to clear the list: run `docs/FULL_LIVE_TEST_rc34.md` on the rc35 build (its helper is `tools/live_test_pack.py`), then close each issue
whose rows pass and comment the evidence on it.

## Changed in this pass
- **#222 (A15, raster classification memory):** built. `unsupervised_classification` now reads, classifies and writes the raster in row blocks
  (about 4 million values per block); centres are fitted on a proportional random sample from a first pass, every cell is then assigned in
  a second pass. Memory no longer grows with the raster. The old limits (25 million cells, 60 million cell-band values) are gone; the new
  limit is time: a raster over 400 million cells is refused with a clip-it-first error. Checked: pure-numpy block logic offline
  (`tests/test_raster_numpy.py::TestBlockedClassification`), real GDAL read/write in CI (`tests/test_raster_numpy_live.py`, first run in CI).
  **Not measured:** run time on a large raster and real memory use; no cancel button inside this tool. Row H10 of the live-test pack was
  rewritten for the new behaviour.
- **#153 (automatic raster alignment):** no code change, and it is closed on GitHub. The checklist listed "automatic alignment" as still open;
  it exists as the opt-in `align_to_first` argument (tools refuse mismatched grids by default and warp onto the first raster's grid only
  when asked, saying which raster was the reference and the resampling). Warping silently without being asked would change the user's data
  without telling them, so the default stays "refuse and say how".

## Groups
| Group | Issues | State | What closes it |
|---|---|---|---|
| rc7 smoke findings | #72 (umbrella), #75, #79, #80, #81, #84, #86, #87, #88, #91, #93, #94, #95, #97 | Fixed in code, CI-checked (rc8 to rc12) | Hand rows in the live-test pack; #75 and #97 need a real model and a long session; #93 needs your decision on schema disclosure |
| rc11 smoke findings | #120 to #125, #127 to #132 | Fixed in code, CI-checked | #127, #128 never re-run in real QGIS; #132 never run on the real Yemen layer; #131 timing not measured live |
| Audit P1 | #137 to #150, umbrella #169 | Fixed in code and CI | Each issue's acceptance line by hand |
| Audit P2 | #162 | Fixed (WP4), CI-checked | Rows I9, I10 |
| Code audit | #222 | **Built today**, see above | A large-raster run by hand |
| | #223 | Fixed offline; the real QgsTask signal path is not live-tested | A live run |
| | #224 | Last-resort path narrowed; reload and upgrade behaviour not tested | The clean-profile and upgrade gate (GATE rows) |
| Tracking | #233 | rc23 fixes awaiting hand test, plus rc22 rows inconclusive or never run | The full pack |

## Open inside closed issues (no open issue tracks these)
#154 DEM vertical unit assumed to be metres; #159 score writes in `analysis_tools`; #160 raster-unit validation in zonal tools; #161 reprojecting
points into the admin CRS; #167 running tasks are not invalidated at unload; #166 the wheel has not been built in a clean environment.
Decide whether to reopen or file new issues for these.
