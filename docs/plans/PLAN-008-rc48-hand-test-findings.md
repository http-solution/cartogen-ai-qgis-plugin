# PLAN-008: fix what the rc48 hand test found

Status: in progress

## Goal
Turn the 16 failed and 18 partial rows of the rc48 hand test (`docs/HAND_TEST_RESULTS_rc48_2026-10-24.md`) into fixed, test-guarded behaviour, in the order that protects users first: data leaving the machine, wrong answers, then broken exports and layouts, then routing. Nothing is closed without a hand-verified pass.

## Scope
Batch 1 (this pull request, certain causes): `print_map` PDF crash (A22); `tidy_project_layers(apply=true)` must ask first (OI-120); sheet rows whose expectation was wrong (A25 re-run, A20 and A26 counts).
Batch 2 (needs evidence, one pull request each, test first):
1. **#150 leak** (OI-150): merge of a SENSITIVE layer, rename, rename, read sent data to the cloud model with no card. Needs the evidence folder of that run; then a CI test of the exact tool sequence through the egress gate, and the fix at whatever step loses the protection.
2. **#148** (OI-148): road distance for a facility on the U-shaped road. Needs evidence folder `20261023-201442_t3`; CI test on the fixture.
3. **#128** (OI-128): ramp reported, canvas grey. CI reproduction of the styling call on `yem_ppp_2020`.
4. **Layouts** (A12, A6, A16): chart items stacked at one spot and drawing empty grids, elevation profile without a curve, call count. Check placement defaults and data refresh in CI (render the layout to an image and compare against blank).
5. **Plain requests vs the task library** (B28, B32, B41 and 31 more): measured offline, 34 of 385 plain algorithm prompts match a mapping task at the confident score (for example 'Sort the districts by population' matches 'Map population distribution') and the injected plan steers the model away. Design to decide: when the algorithm topic index has a strong match for an operation-shaped request, do not inject a task plan. Must not lower the golden routing tables (`tests/test_tool_router_basics.py`, `tests/test_rc46_hand_test_fixes.py`); measured before and after with the 385-prompt replay.
6. **Loops and failing ids** (B7, B3, B15): loop guard for repeated identical calls; `grass:r.sunmask.datetime` fails when run, read the error and drop or fix the id.
Out: owner decisions (#95 default, #129 frame, #84 note, #145/#146), the upgrade gate (#224), and anything needing a model change.

## Acceptance
1. Batch 1: `tests/test_print_map_live.py` writes a real PDF in CI; the tidy live test sees PREVIEW_REQUIRED before the changes and applies only with confirmation (CI live).
2. Each Batch 2 item: a failing test first (offline where it can be, CI-live otherwise), then the fix, then the row in the next hand-test bundle. Hand-verified only after the owner's pass.

## Guard tests
`tests/test_print_map_live.py`, `tests/test_project_tidy_live.py` (batch 1); batch 2 adds its own, listed in the ledger entry when built.

## Rollback
One pull request per item; revert it.

## Status log
- 2026-10-24: rc48 results recorded (52 pass, 18 partial, 16 fail, 1 skip). Closed on hand-verified passes: #80, #81, #91, #94, #122, #123, #124. Batch 1 built on branch claude/rc48-results. Batch 2 waits on the evidence folders for OI-150, OI-148, OI-128 and OI-120 (they were not in the uploaded bundle) and on the owner's go for item 5, which changes routing behaviour.
- 2026-10-24 (item 2, #148, analysed offline, owner asleep; decision recorded as my recommendation, overrule it here): the road distances the tools gave for the U-road fixture were RIGHT (70 m and 200 m along the road). What is missing is the off-road leg: `Inside_the_U` is 300 m from the road (it sits between the two arms) and `Beside_the_arm` is 80 m. Counting the leg, the totals are 370 m (not reached within 300) and 280 m (reached). Both `classify_facilities_by_access` and `travel_time_matrix` document that they do not add the leg, but the answer never said so. Recommendation and order: (1) do NOT change the classification (the #80 flow that just passed hand testing depends on it); (2) add `access_leg_m` per destination to the `travel_time_matrix` result, computed the same way for both of its methods; (3) say in both tool descriptions to add the leg when the question is a total travel budget; (4) a CI test on the U-road fixture pins the four numbers (cost 70 and 200, leg 300 and 80); (5) the hand-test row text states the expected totals, not the shortcut.
