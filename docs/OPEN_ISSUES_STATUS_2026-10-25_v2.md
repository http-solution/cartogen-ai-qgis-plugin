# Open issues, status on 2026-10-25 (after PLAN-021, with 1.18.1 built)

Supersedes `OPEN_ISSUES_STATUS_2026-10-25.md` (kept as written; the hand-test bundle builder of 1.18.0 reads it). Policy until today: no issue closed without a hand-verified pass or an owner decision. On 2026-10-25 the owner decided that every open issue is either fixed or closed; each closure carries a comment saying what was hand-verified and what was CI only.

## Closed on 2026-10-25 under that decision
| # | Issue | Closed on | Not hand-verified |
|---|---|---|---|
| 148 | bounding-box nearest neighbour | hand-verified pass (1.18.0 row OI-148) | none |
| 130 | fragment 'template: access_map' | hand-verified pass (1.18.0 row OI-130) | none |
| 169 | external audit tracker | all 32 children closed | none |
| 223 | abandoned processing bundles | code already there; live proof on real tasks (#437); Stop passed by hand | memory after Stop (row V2-stop) |
| 224 | bootstrap eviction | code already there; proof on real modules (#437); update in place passed by hand | toolbar count, log lines (row V1-update) |
| 97 | exported chat history | 20 exchanges exported by hand; save, reopen, export, delete in CI (#440) | export from the owner's reopened project |
| 120 | labels, scratch layers, black raster | `add_point_layer` keeps its layer or says it is temporary (#440); black raster passed by hand on rc50 | other tools that write temporary layers |
| 425 | undo of `add_field` | CI only (#439): removes an empty field, refuses a filled one | row V9-undo-field |
| 72 | rc7 smoke umbrella | all its children closed | none |
| 379 | layout charts and elevation profile | CI only (#441): items render, tools say whether they drew, profile rendered five times | the layout view on the owner's machine; the 'intermittent empty profile' was never reproduced |

## Still open
| # | Issue | State | Needs |
|---|---|---|---|
| 362 | animate, elevation profile, linked charts | router offers the right tools for all three; a repeating listing now stops with a message naming the next tool (#438) | rows V4-animate, V5-profile, V6-charts: the model's own answers |
| 380 | plain requests answered by a wrong task plan | replay of 385 prompts: 34, then 7, now 2 (both right) (#438); the contour request no longer starts a download | rows V3-contour, V7-merge, V8-raster |

## Owner decisions still open
Version and release of 1.18.1 (built, not published; plugins.qgis.org upload is the owner's), the Pages site unpublish step, and the two older owner tasks (JIAF validation blockers, HX4 credentialed integrations).
