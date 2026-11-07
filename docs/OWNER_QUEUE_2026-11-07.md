# Full review and owner queue, 2026-11-07

A dated snapshot (not edited later). It reads the master task list (101 rows), the live-results record, the open issues and the round-2 evidence as of `main` at 58d69b4. Where a number comes from a keyword count of row notes, it says so.

## 1. Where the project stands

| Fact | Value | Source |
|---|---|---|
| Open pull requests | 0 | GitHub |
| Open issues | #362, #380, #510 and the rerun checklist #576 | GitHub |
| Offline tests | 6,093 run; 54 errors that also occur on a clean `main` here (no `requests` module in this sandbox) | local run |
| Features seen live | 69 working, 18 partly, 1 failing, 52 not seen (of 140 testable) | `docs/LIVE_RESULTS.json` |
| Features whose code changed since the live baseline and need a live recheck | 52 | `tools/live_results.py --gate` |
| Master-list rows | In progress 47, Blocked 19, Waiting on you 14, Decision needed 11, Closed 10 | `docs/MASTER_TASK_LIST_2026-10-27.csv` |

**The main finding.** About three quarters of the 47 "In progress" rows (37 by a keyword count of their notes: "CI only", "hand test", "live run", "rerun", "awaiting") are built and merged and wait for a live run or an owner look, not for code. The bottleneck is verification, not building.

## 2. What round 2 and the follow-up changed

Seen working live (agent-run, evidence read): undo of a filled field refuses at once (P2); "animate over time" calls the animation tool (P3); A1 pages are no longer empty (P1); the mesh case reaches `native:meshrasterize`; the egress card and result checks work (W11, W2).

Found and fixed in code (CI only, not yet seen live): table outputs got a false "geometry invalid" failure (DEF-28); `generate_situation_dashboard` failed on a label list (DEF-29); the A1 legend was cut while its check said it fits, because `adjustBoxSize()` does nothing on that item (DEF-27, cause confirmed on real QGIS 4.2.2 by a CI probe); the Help line now names the PyQt build when it differs from the running Qt (W13).

Still open and not fixed: why the evidence collector's log files are empty (DEF-9, 28 of 28 empty); the A1 legend and Qt line have not been looked at by a person.

## 3. Owner queue, in the order I recommend

| # | What | Why it matters | My recommendation |
|---|---|---|---|
| 1 | **Run the round-2 package** (GitHub #576): A1 (look at the legend pages), C1 step 6, E4 step 7, W13 (About screenshot), A2, B5 (20 exchanges), D1, B3 | Confirms or rejects ten built fixes; unblocks closing DEF-23, 24, 25, 27, 28, 29 | Do this first, by the same agent route as round 2 (it worked), with `FAILURE_PROTOCOL.md`. About 2 hours. |
| 2 | **OWN-16**: look at the Connections window and CLI setup on your Windows machine | Only a person can judge it; it is the last P0 hand check and blocks closing LEAD-8 and LEAD-9 | Do the first three boxes (window readable, Codex page, path paste) now; leave the browser sign-in until you actually use the CLI. About 20 minutes. |
| 3 | **Issue #362** | I4, I6 and I9 were each seen working by an agent run | Close it with a note "agent-verified on one model; reopen if another model fails". Keep #380 open: the mesh case is confirmed, B28 and B32 were not rerun and the routing change is not done. |
| 4 | **OWN-15**: rerun the nine model-choice rows with the Claude provider | Separates model-choice failures (DEF-17) from plugin faults (DEF-10, 11, 12) | Yes, one session, before 1.18.6. |
| 5 | **Release 1.18.6** | Held. The release gate lists 52 features needing a recheck, so it would fail today | Release only after items 1, 2 and 4. For the gate: run the FULL 45-row package once on the release candidate, then stamp `rechecked_at`. Rechecking features one by one is slower and easier to get wrong. |
| 6 | **OWN-11**: clean-profile install and in-place upgrade test of the exact release zip | The only test of what a new user gets | Before 1.18.6, on the final zip. |
| 7 | **OWN-13**: the open secret-scanning alert | A security item | Open it and read what it matched before dismissing. The 2026-10-09 scan found no secrets and CI gitleaks passes, so a false positive is likely, but I cannot see the alert from here. |
| 8 | **HY-4**: prune about 190 remote branches | Irreversible | Approve a dry run first: I list every branch with its PR state, you approve the list, then I delete only branches whose PR is merged or closed. Never the open ones. |
| 9 | **HU-5** layer piling (63 `addMapLayer` sites) | Items 1 and 2 of the row are already done | Mark the row's first two items done. For the third, choose "mark superseded" (tag older results), the least risky: replacing deletes user layers, grouping needs UI work. |
| 10 | **AR-3**, **DEF-6** | Both measured or seen working | Close both. AR-3: no length bias measured (test pins it). DEF-6: cell-size suggestion seen working live in row D5. |
| 11 | **OWN-6, OWN-7**: the PLAN-022 and PLAN-023 question lists | Block planning, not shipping | Accept the written defaults unless you object. I did not re-read the question lists in this pass; say so and I will walk you through them in about 15 minutes. |
| 12 | **OWN-1, OWN-3, OWN-4** | Older asks | Retire OWN-1 (superseded by round 2) and OWN-4 (done by agent runs, see #362 above). Keep OWN-3 until the A5, A7, C5, D3, D4, S5 rows are rerun. |
| 13 | Defer | No risk from waiting | OWN-9 (JIAF material), OWN-10 (credentials), OWN-14 (samples), OWN-12 (plugins.qgis.org upload, after 1.18.6 passes), LEAD-10 (Antigravity: run `tools/agy_probe.py` only if you still want it), AR-1 and AR-6 (large reworks, after 1.18.6), PR-R3, R8 to R11 (roadmap releases out of order: finish verification debt first). |

## 4. What I can do next without you

1. After the round-2 results arrive: record them, stamp `rechecked_at`, refresh the dashboard and GitHub, close rows only on your say.
2. LEAD-4 items 3 and 4 (schema-argument drift for composite tools): real engineering, testable offline.
3. DEF-8: review the 504 broad-except handlers (record only today).
4. HY-3: pin the Windows runner. Needs your confirmation first: it renames a check that branch protection may require by name.

## 5. Risks I see

- **One person and one model carry the verification.** Every "seen working" result is an agent on one machine with one model (Gemini flash). A second model (OWN-15) and a person's look (items 1 and 2) are the cheapest way to lower that risk.
- **The dashboard can be overwritten by a refresh that reads `main` before a data PR merges.** This happened on 2026-11-07. Merge a data PR first, refresh after.
- **Several fixes exist only as CI-run code.** Round 2 found three defects (DEF-27, 28, 29) in code that had passed CI, which is the real reason for the live runs.
- **The evidence collector still cannot capture the QGIS log (DEF-9).** Failures are diagnosed from `steps.jsonl` and the saved project instead, which works but loses the log text.
