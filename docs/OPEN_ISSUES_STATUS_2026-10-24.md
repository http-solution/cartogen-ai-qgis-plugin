# Open issues, status on 2026-10-24 (rc48 hand test)

Source: the rc48 hand test (`docs/HAND_TEST_RESULTS_rc48_2026-10-24.md`, 87 rows run by the owner on 2026-10-23 and 24) and the earlier comments. Policy: no issue is closed without a hand-verified PASS (or an owner decision). 21 open; #80, #81, #91, #94, #122, #123 and #124 were closed on a hand-verified pass.

| # | Issue | Last evidence | State | Needs |
|---|---|---|---|---|
| 72 | rc7 smoke findings (umbrella) | rc40: 42 Pass, 14 Fail, 11 Skip; 19 children closed | umbrella | children below |
| 84 | HTML dashboard | rc48 OI-84: full path in the project folder, popups, no basemap; the offline note is only in the chat reply | partial | owner to accept (note in the file) |
| 93 | field names of a SENSITIVE layer reach the cloud | rc40: card now states it | owner decision on the disclosure | owner |
| 95 | project memory wrote coordinates | rc48 OI-95: no raw coordinates; the dialog shows 'Saved with the project: ON' (the F25 option B default) and lists layer ids | owner decision | owner: keep ON or switch the default to OFF |
| 97 | exported chat history missing messages | rc48 OI-97: all 20 exchanges exported with timestamps; export came from the live chat, not a reopened project | mostly works | one re-run after save and reopen |
| 120, 128 | placeholder labels; black population raster | rc48: #120 tidy reported then applied in one turn (fixed: apply now asks); duplicate detection unproven. #128 reply says a ramp was applied but the canvas is grey | open | #120: re-run after the fix. #128 (2026-10-24 PLAN-008): the raster tool renders in colour in CI; the grey canvas came from a task-library plan taking over a plain request, fixed in #385 (not hand-tested); re-run row OI-128; #128: CI reproduction of the styling call |
| 127 | HDX boundaries opaque and duplicated | rc48 OI-127: download works, second send replaced the layer, no labels | partial | owner decision on labels |
| 129 | print layout problems | rc48 OI-129: title and graticule fine; main frame still follows the DEM extent, legend lists extra layers | partly open | owner decision on frame extent |
| 130 | fragment 'template: access_map' | rc48 OI-130: started a template plan, but in a chat whose last assistant message was a question (the guard then stands down) | inconclusive | re-run in a new chat |
| 138 | snapshots touch GUI objects off-thread | rc48 OI-147: project switch during a run was clean, no 'wrong thread' lines; undo of add_field not covered | mostly works | owner to accept; add_field undo is a feature gap |
| 145, 146 | script outputs / same-count edits lost | rc48 OI-145: 'import os' is blocked by design; the reply does not say a file-layer edit went to a copy | limitation | owner decision on file-layer edits |
| 148 | bounding-box nearest neighbour | rc48 OI-148: the tool was used but Inside_the_U was reported 69.96 m from the start (expected about 1.2 km along the road) | **fixed in CI, not hand-verified** | PLAN-008: the road distances were right; the off-road leg was missing and is now reported (CI test on the U-road fixture). Re-run OI-148 in the next hand test |
| 150 | lineage ignores nested inputs | rc48 OI-150: a merged and renamed output of a SENSITIVE layer was read by the cloud model with no card | **fixed in CI, not hand-verified; stays open** | PLAN-008: a caller-named output was counted as an input so its lineage tag was lost; fixed and guarded by tests/test_egress_flow_live.py (merge, rename, rename, read). Re-run OI-150, then close |
| 169 | external audit tracker | 32 findings; many closed, rest listed above | umbrella | children |
| 223 | abandoned processing bundles | rc48 OI-223: runs finished before Stop; no Task Manager panel in this build | not exercised | owner: a run long enough to press Stop |
| 224 | bootstrap namespace eviction | rc40: upgrade check skipped | open | clean-profile/upgrade gate (owner) |
| 233 | rc23 hand verification list | tracking list | tracking | hand test |
| 305 | rc40 residuals (6 calls, HTTP 500) | optional | optional | owner |
| 362 | rc46 Part 4: animate, profile loop, linked charts | rc48 A16: profile took 6 model calls, `list_layout_items` twice; A17 explained instead of exporting; A12 charts stacked and empty | open | PLAN-008 |

Closed since 2026-10-18: #358 to #361 (rc46 hand-test defects, fixed in rc47 with regression tests; hand verification is rows A1, A4, A5, A14 of the rc47 lean bundle).

PLAN-008 also merged (2026-10-24, all CI only, none hand-tested): #379 layout charts and profile now draw and are placed on free spots (PR 384); #380 task library stands down when a strong algorithm fits (PR 385); B3, B7, B15 guards (PR 386). #379 and #380 stay open until the rc49 hand test passes their rows.
