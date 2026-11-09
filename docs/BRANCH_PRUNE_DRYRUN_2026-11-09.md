# Remote branch prune: dry run, 2026-11-09 (HY-4)

Status: dry run only. **Nothing was deleted.** Deleting a remote branch cannot be undone from here, so the owner approves this list first.

## What was checked
- Remote branches as GitHub lists them: 57 (including `main` and this session's working branch). The "190-odd" in the master list is old: GitHub deleted the others when their pull requests merged.
- Open pull requests: 0, so no branch has an open PR.
- For each branch, its closed pull requests (480 read) and whether the branch tip is the head commit of its merged PR.

## 1. Safe to delete: merged, and the branch tip is the PR's head commit (40)

| Branch | PR | Last commit |
|---|---|---|
| `claude/130-replace-warning` | #199 | 2026-10-05 |
| `claude/auth-update-fix` | #113 | 2026-10-01 |
| `claude/cost-and-routing` | #227 | 2026-10-09 |
| `claude/gate-loop-fix` | #115 | 2026-10-01 |
| `claude/h1-h2-h4-tools` | #172 | 2026-10-04 |
| `claude/humanitarian-catalogue-styling` | #174 | 2026-10-04 |
| `claude/hx1-humanitarian-looks` | #183 | 2026-10-04 |
| `claude/hx1b-created-layer-looks` | #184 | 2026-10-04 |
| `claude/hx1c-sitrep` | #185 | 2026-10-04 |
| `claude/hx2-task-register` | #186 | 2026-10-04 |
| `claude/hx3a-allocation` | #187 | 2026-10-04 |
| `claude/hx3b-importers` | #188 | 2026-10-04 |
| `claude/hx3c-critical-links` | #189 | 2026-10-04 |
| `claude/hx5-stage1-plan` | #192 | 2026-10-04 |
| `claude/hx5-stage2-inputs` | #193 | 2026-10-04 |
| `claude/hx5-stage3-engine` | #194 | 2026-10-04 |
| `claude/hx5-stage4-review` | #195 | 2026-10-04 |
| `claude/issues-status-pass` | #198 | 2026-10-05 |
| `claude/rc10-release` | #111 | 2026-10-01 |
| `claude/rc11-release` | #118 | 2026-10-01 |
| `claude/rc13-release` | #190 | 2026-10-04 |
| `claude/rc14-release` | #196 | 2026-10-05 |
| `claude/rc15-release` | #200 | 2026-10-05 |
| `claude/rc8-audit-fixes` | #108 | 2026-10-01 |
| `claude/readme-rc13-link` | #191 | 2026-10-04 |
| `claude/readme-rc14-link` | #197 | 2026-10-05 |
| `claude/readme-rc15-link` | #201 | 2026-10-05 |
| `claude/results-cleanup` | #246, 117 | 2026-10-01 |
| `claude/routing-styling` | #245, 109 | 2026-10-01 |
| `claude/smoke-fixes` | #244, 114 | 2026-10-01 |
| `claude/smoke-fixes2` | #116 | 2026-10-01 |
| `claude/viz-gap-analysis` | #110 | 2026-10-01 |
| `claude/wp1-quick-corrections` | #240, 177 | 2026-10-04 |
| `claude/wp2-data-correctness` | #239, 178 | 2026-10-04 |
| `claude/wp3-blocked-roads` | #243, 179 | 2026-10-04 |
| `claude/wp4-processing-provider` | #241, 176 | 2026-10-04 |
| `claude/wp4-registry-diagnostic` | #236, 175 | 2026-10-04 |
| `claude/wp5-partial-edge` | #235, 180 | 2026-10-04 |
| `claude/wp6-lifecycle` | #234, 181 | 2026-10-04 |
| `claude/wp7-handover` | #238, 182 | 2026-10-04 |

## 2. Needs your decision (15): unmerged work, no PR, or commits after the merge

| Branch | State | Tip commit says | Last commit |
|---|---|---|---|
| `claude/adm-routing` | no pull request | Route ADM-code and governorate requests to the boundary download tools | 2026-10-14 |
| `claude/gdal-thread-investigation` | PR #287 closed, never merged | Investigation step 3: pass the raster as a project layer object / id,  | 2026-10-12 |
| `claude/h5-h6-tools` | PR #173 merged, but later commits exist on the branch | docs+feat(style): humanitarian tools catalogue, README section, and ma | 2026-10-04 |
| `claude/hand-test-sheet` | PR #351 closed, never merged | Add tools/build_hand_test_bundle.py: packages the plugin zip with the  | 2026-10-16 |
| `claude/issue-triage-plan` | no pull request | docs: record the owner's decisions and the complete fix plan (work pac | 2026-10-04 |
| `claude/pending-work-master-list` | no pull request | PLAN-023: programme plan from 1.18.2 to 1.30 with per-package tools, k | 2026-10-26 |
| `claude/persona-plan` | no pull request | docs: persona plan, correct status vocabulary (generic-only vs built)  | 2026-10-04 |
| `claude/pkg-h-probe` | PR #343 merged, but later commits exist on the branch | Record the QGIS capability probe results from CI (packages H and I sco | 2026-10-16 |
| `claude/plan-reality` | no pull request | Plan for full QGIS-by-prompt coverage from the current code, and corre | 2026-10-14 |
| `claude/plan015-log` | no pull request | PLAN-015: status log for the rc50 pre-release and bundle | 2026-10-24 |
| `claude/rc48-check-base` | no pull request | Release candidate 1.17.0-rc48: Excel and CAD export, export routing, w | 2026-10-23 |
| `claude/rc48-check-head` | PR #389 closed, never merged | TEMPORARY: run the OI-150/OI-128 faithful reproductions against the rc | 2026-10-24 |
| `claude/status-doc` | no pull request | Status document: what the roadmap packages did and how far each was te | 2026-10-16 |
| `claude/test-fixtures-script` | PR #451 closed, never merged | Add tools/make_test_fixtures.py for the hand-test package | 2026-10-26 |
| `claude/test-package-1-18-3` | no pull request | Fixture generator: add IPC and points fixtures for the 1.18.3 test pac | 2026-10-26 |

My recommendation for section 2: keep every branch with a stated plan (`claude/pending-work-master-list` holds PLAN-023's programme plan text) until you say, and delete the rest only after you have looked at the tip commit. The two merged branches with later commits (`claude/h5-h6-tools`, `claude/pkg-h-probe`) may hold work that never reached `main`.

## 3. Kept: `main` and `claude/eager-goldberg-aruysp` (this session's branch)

## How the deletion would run, once you approve a list
One `git push origin --delete <branch>` per branch, only for branches you approved, then re-list the remote and record the result here. A deleted branch's commits stay reachable through its merged pull request on GitHub.

## Execution status (added 2026-11-09, later)
The owner approved the plan ("go with HY-4"): delete the 40 merged branches (section 1) and the 4 section-2 branches whose closed pull request keeps the same commit; tag then delete the other 11 (`archive/<name>`). **Not executed.** The cloud session that wrote this has a git proxy that answers HTTP 403 to every push except its own branch: pushing an annotated tag and deleting one branch were each tried once and each was refused, nothing changed, and all 55 branches still exist. No retry or workaround was attempted.

`tools/prune_branches.py` does the whole plan from a clone with push rights: it re-checks every branch against the live remote, tags where the commits exist only on the branch and confirms the tag is on the remote before deleting, and stops at the first refusal. Its dry run against the live remote on 2026-11-09 reported 44 deletes, 11 tag-then-deletes and 0 skips, matching this document. Run `python tools/prune_branches.py` to see the plan and `python tools/prune_branches.py --execute` to apply it. Record the result here afterwards.
