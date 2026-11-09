# Analysis of the nine "Decision needed" rows, 2026-11-09

Written at the owner's request after the master list was re-read. It is a decision aid: nothing here has been applied except the status fixes listed at the end. Facts are from the repository, GitHub, PLAN-023 and PLAN-060; where a statement is my judgement it says so.

**Headline.** Of the nine rows, only four are real decisions (HY-4, HU-5 part 3, AR-3, and the sequencing call on the roadmap releases). One (AR-1) was a blocked row mislabelled as a decision, one (PR-R8) cannot start whatever is decided, and HU-5 is mostly already done. The roadmap releases share one answer: hold them until the live recheck of 1.18.6.

## 1. HY-4: prune remote branches

**Facts.** 55 remote branches (not 190). Section 1 of `docs/BRANCH_PRUNE_DRYRUN_2026-11-09.md` lists 40 merged branches at their PR head; section 2 lists 15 that need a decision. Checked on 2026-11-09 with `git ls-remote`:
- **4 branches whose PR was closed without merging** (`gdal-thread-investigation` #287, `hand-test-sheet` #351, `rc48-check-head` #389, `test-fixtures-script` #451): the branch tip equals `refs/pull/N/head`, so GitHub already keeps every commit. Deleting the branch loses nothing.
- **2 branches merged but with later commits** (`h5-h6-tools` #173, `pkg-h-probe` #343): the branch tip differs from the PR head, so the later commits exist only on the branch.
- **9 branches with no PR at all** (`adm-routing`, `issue-triage-plan`, `pending-work-master-list`, `persona-plan`, `plan-reality`, `plan015-log`, `rc48-check-base`, `status-doc`, `test-package-1-18-3`): their commits exist only on the branch.
- Not proven: whether the content of the 11 branches in the last two groups already landed on `main` by another route. This checkout is shallow, so no merge-base exists and a diff cannot say. `PLAN-023` (the content of `pending-work-master-list`) is on `main`, and `persona-plan`'s tip file is identical on `main`.

**Options.** (a) Keep all 15: costs nothing but leaves 17 branches among the 2 live ones. (b) Delete all 15: loses the commits of the last 11. (c) Tag then delete: push a tag `archive/<name>` at each tip, then delete the branch; every commit stays reachable and any branch can be recreated from its tag.

**Recommendation (mine): (c).** Approve section 1 (40 branches) as it stands. For section 2, tag and delete the 4 closed-PR branches without tags (nothing is lost) and tag-then-delete the other 11. Result: 2 branches left, no history lost, fully reversible. Say "go" and I run it one branch at a time and record the result.

## 2. PR-R3, PR-R9, PR-R10, PR-R11: start a roadmap release now?

**Facts (PLAN-023 S2, sizes are my own estimates in agent build days, not measured).** R3 indices, time series, STAC: 10. R9 geometry editing: 9. R10 attributes and raster rows: 9. R11 Processing models and algorithm waves: 11. About 39 days for the four. None needs owner input. The plan's own order rule: a release starts only when the previous release's hand rows are returned and its failures fixed; R1 must come first.

**Evidence on risk.** The dashboard shows 67 features needing a live recheck, 51 never seen live. Round 3 found 16 defects (DEF-23 to DEF-38) in code CI had passed; the first real Codex run found three faults CI could not see. Release 1.18.6 is not yet cut. Starting any of the four now stacks about 39 days of CI-only code on a 1.18.6 that has not had its live pass.

**Options.** (a) Start one now, out of order. (b) Hold all until 1.18.6 passes live, then follow the order rule. (c) Decline some.

**Recommendation (mine): (b).** After 1.18.6: R1 first (it is unblocked, see below), then the order among R3, R9, R10, R11 is yours. My judgement, not measured: R3 and R11 touch more of what field users ask for; R9 and R10 are lower-risk, self-contained editing and attribute work. Nothing needs declining yet.

## 3. PR-R8: standards and publication

Not a decision. PLAN-023 S2 says R8 needs R1 (the catalogue) and R7 (the portals), and R7 needs R3, R5 and OWN-10. It cannot start whatever is decided. Status fixed to Blocked and its Depends column now says PR-R1, PR-R7.

## 4. AR-1: agent pipeline redesign

Not a decision yet. Its own row says "only after RM-A shows what a gate buys", and RM-A is still open: the gate is built and its 7 live tests passed in CI (PLAN-031), but its hand test and the CRS/stale checks, switched on tool by tool, need a real run. The code it would change is large (`agent_orchestrator.py` 2,275 lines; `core/agent` 12,243 lines). Status fixed to Blocked on RM-A. **Recommendation (mine):** decide after the RM-A hand test returns, using what the gate caught.

## 5. AR-3: task-matcher bias toward short task definitions

**Facts (PLAN-060, measured 2026-11-05).** Of 792 task titles, 613 find their own task; 165 find none (the fragment guard, by design); 13 lose to an identical keyword set; 1 loses to a task with fewer strong keywords; none lose to a task with more. Of 385 plain prompts, 2 still get a directive, both right. No length bias is measurable and `tests/test_task_matcher_length_fairness.py` pins it.

**Options.** Close as "no measurable bias", or change the shared scoring (a routing change). **Recommendation: close.** One thing this does not settle: 165 of 792 titles (21 %) find no task by design; if that guard is judged too strict, it is a different question and a new row.

## 6. HU-5: smaller carry-overs

Three parts, read 2026-11-05:
1. Task-runner callbacks at unload: built (2026-10-06, `plugin_epoch`); only a live look (OI-224) is missing. Fold it into the 1.18.6 recheck package.
2. `find_region` naming the wrong country: resolved 2026-09-28; the row text is stale.
3. Output layers piling up in long sessions: 63 `addMapLayer` call sites in 26 files; only `calculate_service_area` replaces a same-named layer. The real decision:

| Option | Effect | Risk |
|---|---|---|
| Replace (as service area does) | one layer per name | silently destroys the user's earlier result |
| Group | outputs tidied under a group | changes the layer tree users already rely on |
| Mark superseded | older output renamed or flagged, nothing deleted or moved | lowest; needs one shared helper at the call sites |

**Recommendation (mine): mark superseded**, behind a setting, through one helper used first by the tools most often re-run, not all 63 sites at once.

## 7. PR-R1 (not one of the nine, found while checking)

Listed Blocked on OWN-7, which was closed on 2026-11-09 (defaults accepted). It is unblocked and first in line. What remains is sequencing: before or after the 1.18.6 live pass. **Recommendation: after**, for the same reason as section 2. Status moved to Decision needed.

## Status changes made with this analysis

| Row | From | To | Why |
|---|---|---|---|
| HT-3 | Blocked | Not started | its only dependency OWN-3 is closed; eval rows are buildable, measuring needs live model calls |
| HT-5 | Blocked | Waiting on you | its only dependency OWN-1 is closed; it is a hand re-check |
| PR-R1 | Blocked | Decision needed | its only dependency OWN-7 is closed |
| PR-R8 | Decision needed | Blocked | needs R1 and R7 (PLAN-023) |
| AR-1 | Decision needed | Blocked | waits on RM-A |
