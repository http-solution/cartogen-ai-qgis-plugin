# Self-audit and harmonization, 2026-10-23

Written at the owner's request: check the project's instructions and skills, audit my own work against them, and make the pieces work together so that a finished job is not broken again and progress is on record. This is a living record: add dated lines, do not rewrite old ones.

## 1. Instruction sources and how they fit

| Source | What it governs | Decision |
|---|---|---|
| `CLAUDE.md` (repo root) | Structure, how to run tests, editions rule (no tier gating), version bumps, "flag, don't decide" | Kept. A "Working agreement" block was added (ledger, plans, guards, no issue closed without a hand-verified pass). |
| `.claude/CLAUDE.md`, `.claude/settings.json`, `.claude/skills/graphify` | graphify knowledge graph; hooks call `graphify hook-guard` before search/read | Kept. graphify is not installed in the cloud sandbox, so "run `graphify update .`" cannot be done there; `CLAUDE.md` now says so instead of leaving a rule that is silently skipped. |
| `CONTRIBUTING.md` sections 1 to 9 | Comments explain why; say shipped/roadmap/unverified; flag judgment calls; testing conventions; releasing; QGIS rules | Kept. Section 10 added: plan first, ledger always, regression test with every fix, specific hand-test claims, record after release. |
| `.github/PULL_REQUEST_TEMPLATE.md` | Why, how verified, before/after table, tool count, status, checklist | Kept; plan/ledger/guard boxes added. My PRs #363 to #367 used my own body text instead of this template (see 2.1). |
| User skill `humanitarian-gis-agent` (cloud skills) | How an agent answers humanitarian GIS questions: never fabricate, state CRS and method, label estimates, Do No Harm | Not a development process. It describes the behaviour the plugin should have; section 3 maps it onto the plugin's guards and lists the gaps. |
| Cloud skills `session-start-hook`, `code-review`, `simplify`, `run`, and the business-role skills | Generic | Not applicable to this repository's process; nothing changed. |
| Session rules (GitHub footer, no PR unless asked, no release without the owner) | How I act | Followed. Merges happened only after the owner's "merge when green"; PR #367 was merged on the same standing instruction. |

## 2. Where my own work departed from those sources, and what was done

| # | Departure | Evidence | Fix |
|---|---|---|---|
| 2.1 | PRs #363 to #367 did not use the PR template (no before/after table, no status boxes) | PR bodies | Template gained plan/ledger boxes; CONTRIBUTING 10.6 makes the template mandatory. Future PRs fill it. |
| 2.2 | `docs/BUG_TRACKER.md` was not updated for the defects found and fixed in rc47 (CLAUDE.md says to) | file unchanged until now | Seven entries added (BUG-2026-10-18-1 to -7). |
| 2.3 | `docs/TOOLS_REFERENCE.md` drifted after I changed a tool's parameters; nothing failed | found 2026-10-23 | Regenerated; `tests/test_tools_reference_in_sync.py`; ledger `tools-reference-sync`. |
| 2.4 | A CI-only lint failure (ISC004) passed locally because an older `ruff` was first on the PATH | PR #365, first CI run | `tools/local_ci.sh` checks the pinned ruff, runs mypy, runs the ledger guard. |
| 2.5 | `graphify update .` never run | CLAUDE.md rule | Not installed in the sandbox; stated in CLAUDE.md. Open for the owner's machine. |
| 2.6 | README test count is typed by hand and will drift | README status block | Residual risk. Release checklist (CONTRIBUTING 8) now says to take it from the last green offline run. |
| 2.7 | Bundle rows can disagree with their own prompts (the split-by-line expectation said x=2 for a line at x=1) | PR #366 | Partly guarded: `tests/test_rc46_hand_test_fixes.py` replays every tool-sheet prompt; expectation text is still not machine-checked. Residual risk. |
| 2.8 | I reported offline numbers (351 of 385 plain prompts found) that were tuned on the same prompts | rc47 notes | Already labelled as flattering the index in the changelog, the status doc and PR #364. No change needed; kept as a reminder to hold out prompts. |
| 2.9 | The hand-test bundles grew by copy (full, plain, lean, open-issue) so the same row could be asked twice | `dist/` | One builder (`tools/build_lean_bundle.py`) now makes one bundle: open-issue rows chosen from the open-issue table, then this release's rows; `tests/test_test_bundle.py` guards the selection. |

## 3. The humanitarian-gis-agent skill against the plugin

| Skill principle | Where the plugin does it (code or test) | Gap |
|---|---|---|
| Never fabricate coordinates | Point provenance flags (`agent_orchestrator._check_point_provenance`, `tests/test_coordinate_provenance.py`); ungrounded-record guard | The reply wording is a model behaviour; not hand-verified beyond rc40 row P1. |
| Do No Harm / protect sensitive data | Cloud egress gate with layer sensitivity (`tests/test_egress_gate.py`, `tests/test_sensitivity_egress_lock.py`) | #93 (field names visible to the cloud model) waits for the owner's decision. |
| Compute distances and areas in a projected CRS | Unit handling and CRS checks in the analysis tools (`tests/test_network_units_live.py`, `tests/test_point_assignment_crs_live.py`) | Replies do not always state the original, working and output CRS as the skill asks. Not enforced; open as a candidate improvement, not a defect. |
| Label estimates as estimates | Population exposure shows three labelled figures with the hull marked as an upper bound (#123) | Awaiting hand re-run. |
| Evidence-driven: facts, analysis, implications, limits | Not enforced by code | Not planned for the plugin; it is a style of report, not a tool behaviour. |

## 4. How the project now stays harmonized

1. `docs/plans/` says what each piece of work is for and when it is done; `tests/test_plans.py` checks the shape.
2. `docs/FEATURE_LEDGER.json` lists finished features with their source files, their guard tests and what was hand-verified; `tests/test_feature_ledger.py` fails if a guard or source disappears.
3. `tools/ledger_guard.py` and `tools/local_ci.sh --offline` run the guards locally with the CI tool versions before a push.
4. `docs/OPEN_ISSUES_STATUS_*.md` is the single list of what is open and what each issue needs; the test bundle reads it.
5. Trackers (`IMPLEMENTATION_TRACKER`, `BUG_TRACKER`, `STATUS_DONE_VS_TESTED`) are updated after every release (CONTRIBUTING 10.7).

## Status log
- 2026-10-23: audit written with the combined hand-test bundle. Items 2.5, 2.6 and 2.7 remain open risks; the rest are closed by the changes in the same pull request.
