# Open issues, status on 2026-10-25 (after the rc50 partial hand run and the rc51 release)

Supersedes `OPEN_ISSUES_STATUS_2026-10-24.md` (kept as written). Policy: no issue is closed without a hand-verified PASS or an owner decision. The hand-test bundle builder reads the first column of the table below to choose which open-issue rows go into the next bundle.

## Closed on 2026-10-25 by the owner's decision (comment posted on each)
#93, #95, #84, #127, #129, #138, #145, #146 (accepted as they are; the evidence is in each comment) and #305, #233 (closed as not planned: optional residuals, and a superseded tracking list). The one gap #138 left, undo of `add_field`, is the new issue #425.

## Still open
| # | Issue | Last evidence | State | Needs |
|---|---|---|---|---|
| 72 | rc7 smoke findings (umbrella) | children closed one by one | umbrella | closes when the issues it lists are closed or decided |
| 97 | exported chat history missing messages | rc48 OI-97: all 20 exchanges exported with timestamps; the export came from the live chat, not a reopened project | mostly works | one re-run after save and reopen |
| 120 | placeholder labels, scratch layers, black raster | tidy now asks before it applies; duplicate detection now normalises the source (CI only) | fixed in CI, not hand-verified | re-run row OI-120 |
| 128 | population raster drawn grey | rc50 hand run, row OI-128: Pass (the raster came up with a colour ramp, renderer `singlebandpseudocolor`) | hand-verified pass | owner to confirm the close |
| 130 | fragment 'template: access_map' | rc48 inconclusive: the guard stood down because the last assistant message was a question | inconclusive | re-run in a new chat |
| 148 | bounding-box nearest neighbour | the access leg is now counted (CI only) | fixed in CI, not hand-verified | re-run row OI-148 |
| 150 | lineage ignores nested inputs | closed on GitHub on 2026-10-23 after the rc48 FAIL; fixed in rc49 (PLAN-008/009) and made to apply to layout exports in rc51 (PLAN-016 item 2); not hand-verified | closed, hand check owed | owner: the reworded OI-150 row (a cloud question about the renamed merge result). Reopen if it fails |
| 169 | external audit tracker (32 findings) | most children closed | umbrella | closes when its children are closed or decided |
| 223 | abandoned processing bundles | not exercised | not exercised | owner: a run long enough to press Stop |
| 224 | bootstrap namespace eviction | upgrade check skipped | open | clean-profile and upgrade gate (owner) |
| 362 | rc46 Part 4: animate, profile loop, linked charts | PLAN-008 (CI only) | open | hand rows |
| 379 | layout charts stack and draw empty; elevation profile | placed on free spots (CI only); the elevation-profile render is intermittent in CI and unexplained | fixed in CI, not hand-verified | rc49/rc50 rows; an evidence run for the profile |
| 380 | plain requests answered by an unrelated task plan | rc50 hand row 'sort the districts by population': Pass (one prompt of the 34 reported) | partly verified | the plain-language rows of the bundle |
| 425 | undo does not cover `add_field` | rc48 OI-147 observation; no plan | feature gap | owner decision whether to plan it |

## Not hand-verified since rc50
PLAN-016 (profile re-read at export, export gate following lineage, footer measured in the real font, contour tool descriptions) shipped in rc51, and the owner's disclaimer wording is on `main` for rc52. All of it is CI-checked only; the rc51 bundle rows P16 and the reworded OI-150 row are its hand checks.
