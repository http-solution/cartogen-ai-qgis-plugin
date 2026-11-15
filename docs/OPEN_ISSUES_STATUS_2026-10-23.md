# Open issues, status on 2026-10-23 (rc47)

Source: the last comment on each issue (most are from the rc40 hand test, 2026-10-14) and the rc41 to rc47 changelog. **rc41 to rc47 were shipped after
those comments and none of this list was re-run on them.** Policy: no issue is closed without a hand-verified PASS (or an owner decision). 28 open.

| # | Issue | Last evidence | State | Needs |
|---|---|---|---|---|
| 72 | rc7 smoke findings (umbrella) | rc40: 42 Pass, 14 Fail, 11 Skip; 19 children closed | umbrella | children below |
| 80 | beyond-one-hour task took 44 min | rc40: now about 1 min, but `classify_facilities_by_access` was not chosen, no green/red layer | speed fixed; tool choice unproven | hand re-run |
| 122 | access layer styling / hint | same run as #80 | unproven | hand re-run |
| 81, 123 | population figure was a convex hull | rc40: three labelled figures shown | works; row corrected | hand re-run with the corrected row |
| 84 | HTML dashboard | rc40: saved under the project, full path, Leaflet map, offline warning; "sample" note not possible | works; expectation removed | owner to accept |
| 91, 94 | whole-country WorldPop download / large-download confirmation | rc40: skipped (asked for a country code) | unproven | hand re-run (row now says country YEM) |
| 93 | field names of a SENSITIVE layer reach the cloud | rc40: card now states it | owner decision on the disclosure | owner |
| 95 | project memory wrote coordinates | rc40: no raw coordinates stored; notes are in-session unless the setting is on | not reproduced | owner to accept, then close |
| 97 | exported chat history missing messages | rc40: 16 of 20; likely typed while a reply ran | status line now says the message is kept in the box | hand re-run |
| 120, 128 | placeholder labels; black population raster | rc40: product correct (#120); root cause fixed (#128) | fixed in code | hand re-run |
| 124 | egress override card rough | rc40: card clean; text findings, part wrong row | partly fixed | hand re-run |
| 127 | HDX boundaries opaque and duplicated | rc40: HDX has no Jordan; geoBoundaries failed on that machine (#305) | unproven | re-run with Yemen |
| 129 | print layout problems | rc40: layout good; frame follows the canvas, legend listed stacked old layers | partly open | owner decision on frame extent |
| 130 | fragment "template: access_map" | rc40: not the described bug | not reproduced | owner to accept; rc47 also widened the verb list |
| 138 | snapshots touch GUI objects off-thread | rc40: project switch passed; the edit/undo row was not run | unproven | hand run with the log saved |
| 145, 146 | script outputs / same-count edits lost | rc40: confirmed; reply now says "NOT applied" and flags temporary layers | limitation made visible | owner decision on file-layer edits |
| 148 | bounding-box nearest neighbour | rc40: model never called the tool | tool fixed in code; routing widened | hand re-run |
| 150 | lineage ignores nested inputs | rc40: skipped (cloud card stopped the merge) | unproven | hand re-run |
| 169 | external audit tracker | 32 findings; many closed, rest listed above | umbrella | children |
| 223 | abandoned processing bundles | rc40: Stop latency found; polled every 250 ms since | partly fixed | live session |
| 224 | bootstrap namespace eviction | rc40: upgrade check skipped | open | clean-profile/upgrade gate (owner) |
| 233 | rc23 hand verification list | tracking list | tracking | hand test |
| 305 | rc40 residuals (6 calls, HTTP 500) | optional | optional | owner |
| 362 | rc46 Part 4: animate, profile loop, linked charts | rc47 fixes: `along_layer` (loop), wording for animate/produce/linked charts | fixed in code, CI only | rows A15 to A17 of the rc47 lean bundle |

Closed since 2026-10-18: #358 to #361 (rc46 hand-test defects, fixed in rc47 with regression tests; hand verification is rows A1, A4, A5, A14 of the rc47 lean bundle).
