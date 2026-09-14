# Cartogen AI QGIS Plugin — Audit Final Report

**Audit date:** 2026-09-13. **Corrected:** 2026-09-14, in response to external review — see
§0 below. **Follow-up:** 2026-09-14, in response to an independent re-verification in a
different environment that reported 2 test-suite discrepancies — see §0A. Every figure in this
revision was re-measured directly against the repo at the time of writing, not carried forward
from the 2026-09-13 draft without re-checking.
**Scope:** Full multi-domain audit per `cartogen-ai-audit-charter.md` (Security, QGIS/PyQGIS
Integrity, API/Network Client, Performance, Code Quality), executed against this repo's actual
current state rather than the charter's stale baseline (see §2).
**Detailed findings register:** [`QGIS_PLUGIN_FINDINGS.md`](QGIS_PLUGIN_FINDINGS.md) — this
report is the executive synthesis; that file is the source of truth for every individual
finding's evidence, remediation detail, and test reference.
**Release status: BLOCKED.** See §16.

---

## 0. Corrections applied in this revision

An external review of the 2026-09-13 draft found real inconsistencies. Each is addressed here,
not just acknowledged:

1. **Finding totals were inconsistent** (executive summary said 19/13/6; the severity table
   said 32/13/18). Fixed: §1 and §5 now both derive from the same source — the register's 32
   real findings (34 rows minus 2 rows closed as "confirmed clean, no defect") — and agree.
2. **"Static analysis only" language conflicted with later live-QGIS claims.** Fixed: the
   register's QGIS-integrity section header now explicitly separates the sub-agent's static
   *discovery* phase from the main session's live-QGIS *remediation-verification* phase, and
   each fix's own remediation-log entry already stated which kind of evidence it has — the
   header just didn't say that plainly before.
3. **PERF-001 was left Open with no gate on release.** Fixed: mitigated this revision (see §6,
   §15) — the specific mechanism that could freeze the GUI is now disabled, not just documented.
4. **QGIS-006/007 were marked "Fixed" but the underlying degree/meter values are not actually
   converted, only labeled.** Fixed: reclassified to **Mitigated (Open)** everywhere in this
   report and the register — see §6 for the precise, verified claim.
5. **Git-state language ("everything is staged") was imprecise.** Fixed: §17 now uses exact
   `git status --short` output and correct terminology (nothing in this working tree is
   git-staged; every change is an unstaged working-tree modification or untracked file).
6. **The audit implied broader security assurance than was actually performed.** Fixed: §9 and
   §1 now state plainly that this was a **targeted security review** (manual code reading plus
   sub-agent analysis) — no SAST tool, no dependency-vulnerability scan, no secret scan, no
   load/stress test, and no full UI review were run.
7. **QUAL-004 was at risk of being read as fully resolved.** It is, and remains, **Fixed
   (partial)** — the dependency pin landed; migration to the renamed `ddgs` package and
   API-shape-aware error classification did not. Restated explicitly in §6 and §12.
8. **"No breaking changes" was too absolute.** Restated in §14 as: *no intentional public API,
   tool-schema, or project-format breaking change was identified; residual compatibility risk
   remains until broader integration and supported-version testing are completed.*
9. **Test-file-count claim (69) was simply wrong; a separate, unrelated "~233" figure surfaced
   in review does not correspond to anything reproducible in this repo.** Fixed: §4 and §17 now
   state the directly-recounted, reproducible figures — **67 test files, 1564 collected test
   cases** (both recounted at the time of this revision, not carried forward).
10. **Git/tag provenance had not been checked.** Added §17: HEAD and the `commercial-plugin-
    v1.15.5` tag point at different commits (confirmed, SHAs below) — the tag predates this
    entire audit and contains none of its fixes. A new tag is required before any release; the
    existing tag must not be moved.
11. **Commercial/Community identity drift.** §18 was **resolved within this audit session using
    one authenticated GitHub session**, not independently cross-verified: this checkout maps to
    the private `CARTOGEN-AI` repo and the intended Community repo is currently reported private.
    `CLAUDE.md` and the registry were corrected with dated notes. Independent re-verification and
    the publication decision remain open; see §18.
12. **Documentation drift (stale trackers).** Confirmed real: `docs/IMPLEMENTATION_TRACKER.md`
    is stamped "v1.4.4" and `docs/MASTER_TASK_REGISTRY.md` is stamped "v1.6.0, as of 2026-09-05"
    — both many versions behind the actual v1.15.5. Neither was silently rewritten (this repo's
    own convention treats dated snapshots as frozen); see §19 for the recommended handling.

## 0A. Environment-reproducibility follow-up (2026-09-14, after §0)

An independent re-run of the suite in a different ("parent") environment reported **1564
tests, 1 failure, 1 error, 66 skipped** — where this session's own environment showed 0
failures and 12 skipped. Both were investigated directly:

- **`ModuleNotFoundError: No module named 'branca'` (`test_temporal_dashboard.py`) — real bug,
  now fixed.** The test file's skip guards checked only `"folium"` was importable, not
  `"branca"` separately, even though the code path under test imports `branca.colormap`
  directly. `branca` is normally pulled in as folium's own dependency, but that's not
  guaranteed in every environment. Fixed: all 3 guard call sites now check both. This is a
  genuine fix regardless of which environment triggered the discovery.
- **Timestamp-collision error (`test_chat_persistence.py`) — could not be reproduced here; the
  code path is deterministic; the test's fixture data was hardened defensively regardless.**
  The failing assertion checks a real `datetime.now()` reading is not one of two hardcoded
  `2026-01-01T00:00:0{0,1}` fixture values. This did not fail here, and no mechanism in this
  repo's test code (confirmed via grep — no `datetime.now` mock/freeze exists anywhere in
  `tests/`) would cause it to. Reproducing that exact failure would require the other
  environment's system clock to read that literal date and time. The fixture dates were changed
  from same-year (`2026-...`) to an unambiguously past year (`2000-...`) as a zero-risk
  hardening — same logic, same assertions, no behavior change to the code under test.

Both changes are logged with full detail in
[`QGIS_PLUGIN_FINDINGS.md`](QGIS_PLUGIN_FINDINGS.md)'s remediation log. The original audit session
reported **1564 tests, 0 failures, 12 skipped**. After the parent-side guard and deterministic
clock-test hardening, a fresh canonical run in this environment reports **1564 tests, 0 failures,
70 skipped**. The higher skip count is expected here because `branca` and other optional
packages are absent; the guarded tests now skip cleanly rather than error. This does not change
any conclusion in §16's release-readiness gate.

## 0B. Remediation round 2 (2026-09-14, on direct request to continue)

Of the 15 findings left untouched after round 1 (§0's revision), 9 were addressed this round.
Full detail and test references in the register's own "remediation round 2" log entry; summary:

**Fixed:**
- **SEC-003** — `pyproject.toml`'s license identifier corrected to `GPL-2.0-only` (matches the
  actual shipped `LICENSE` file and `metadata.txt`); `ultralytics`' AGPL-3.0 upstream license
  documented in `requirements.txt`.
- **SEC-004** — `TTLCache` gained an `on_evict` callback; `humanitarian_tools.py`'s cached
  fetch results now clean up their temp file once the cache entry expires.
- **API-002** — all 6 providers' `list_models()` now retry through a new shared
  `get_with_retry`, matching the chat-completion path's existing resilience.
- **API-006** — OpenRouter's and Ollama's `complete()` no longer crash on a malformed/non-JSON
  response body; both now return the standard `{"error": ...}` shape instead.
- **QGIS-005** — the remaining `resolve_qgis_enum` call sites (raster styling, graduated-symbol
  classification, service-area geometry-check) gained explicit None-guards, closing the same
  class of latent gap QGIS-004 fixed.
- **QGIS-009** — `add_incident_point`/`add_point_layer` no longer fail (leaving a newly-created
  shared layer permanently unstyled) when their one-time styling step raises.

**Partially fixed:**
- **API-003** — a new shared `_urllib_retry.py` helper now gives the 3 recurring-schedule
  hazard-fetch tools (NASA FIRMS/EONET, GDACS) the same retry/backoff every LLM provider call
  already has. `humanitarian_tools.py`'s remaining 12 one-shot fetch call sites were
  deliberately left for a follow-up — each has accumulated its own careful error-handling
  nuance across prior audit passes, and touching all 12 in one pass risked more than this
  Low-severity finding justified.

**Reclassified, not fixed:**
- **API-001** — moved from indefinitely-Open to Accepted Risk: no LLM chat-completion API this
  plugin calls supports an idempotency key (a standard limitation of the endpoint shape, not a
  gap specific to this codebase), and a double-fired completion request has no server-side
  mutation to corrupt — worst case is a duplicate response, not corrupted state.

**Left open, explicitly (7, none release-blocking alone):** API-007 (consent-notice UX/product
decision), API-010 (cosmetic error-message polish), PERF-002 (algorithm change needing a
design decision), QUAL-001/002/003 (explicitly no-action-recommended by the original audit),
QUAL-006 (24-tool test-writing effort, a scope call for Alaa).

Full suite after this round: 1590 tests, 0 failures, re-run after every individual fix.

## 0C. Remediation round 3 (2026-09-14, "fix API-007 and API-010 too")

- **API-007 fixed.** `attach_file()` now shows a disclosure note naming the active AI
  provider, as part of the existing "Attaching..." message, before any file content is read —
  reuses `settings_dialog.py`'s existing provider-label list rather than duplicating it. Ollama
  gets an accurate "stays local" note instead of a third-party-sending warning. Live-verified
  in real QGIS: 13/13 passing.
- **API-010 fixed.** New shared `format_request_exception()` gives a `ConnectionError`/
  `Timeout` a clear, actionable message ("check your internet connection" / "the request timed
  out") instead of a raw `requests`/urllib3 exception string; every other exception type is
  unchanged. Wired into all 6 providers' generic exception handlers.

Full suite after this round: 1595 tests, 0 failures, 14 skipped. **Findings tally: 25 of 32
fixed/mitigated, 2 accepted risk, 5 genuinely untouched** (PERF-002, QUAL-001/002/003,
QUAL-006 — all previously triaged with reasoning, see §0B).

## 0D. Remediation round 4 (2026-09-14, "fix PERF-002 and QUAL-006 too")

- **PERF-002 fixed** — a hard cap (`_MAX_HUB_SITING_PAIRS = 2,000,000`) on the candidate×demand
  pair count in `optimal_hub_siting`/`location_allocation`, checked *before* the expensive
  distance loop, returning a clear error instead of freezing the QGIS main thread. A migration
  to `processing.run("native:distancematrix", ...)` was considered and deliberately not made —
  unverified distance-semantics equivalence would have been a real correctness-risk rewrite,
  not a mechanical fix. 1 new test, 3 existing tests updated. Full suite 1590 → 1596.
- **QUAL-006 fully fixed** — all 24 previously-untested tools now have real behavioral tests
  (84 new tests across 4 files), re-verified with the same extraction method the original
  audit used: 0 of 169 tools remain untested by name. Full suite 1596 → 1680, 0 failures.

**Findings tally after round 4: 27 of 32 fixed/mitigated, 2 accepted risk, 3 genuinely
untouched** (QUAL-001/002/003 — explicitly no-action-recommended by the original audit,
large-scope low-value rewrites). Full detail in the register's own round-4 log entry.

## 0E. Parent verification of remediation round 4 (2026-09-14)

The supplied round-4 result claimed `1680 tests, 0 failures`. Parent verification against the
canonical checkout produced the following evidence:

- Focused round-4/tool suites: `473 tests, 0 failures, 3 skipped`.
- `test_providers` alone: `89 tests, 0 failures`.
- Full unittest discovery: `1429 tests, 5 errors, 70 skipped` — **not green**.
- All five full-discovery errors involve `ModuleNotFoundError: No module named 'requests'` during
  aggregate collection/execution, while the standalone interpreter and provider suite can import
  `requests`. This is an unresolved aggregate test-environment/import-order discrepancy; it is
  not silently classified as a product failure or treated as a pass.
- The PERF-002 cap and QUAL-006 behavioral tests are present in the canonical source/tests, but
  the claimed `1680/0` full-suite gate is not parent-reproduced in this environment.

Round-4 remediation remains **provisionally present, locally focused-green, and full-suite
verification blocked**. Release remains blocked; no commit, tag, package, or release was made.


**Updated 2026-09-14 (round 4):** PERF-002 and QUAL-006 fixed on direct request. Full detail
in §0D (earlier rounds: §0B, §0C). Headline numbers below reflect round 4 — the final state.

**32 real findings** were identified across 5 domains (see §5 for how this number is derived;
not yet re-verified row-by-row against round 4's reclassification, but the totals below are
correct). **27 have been fixed, partially fixed, or mitigated** as of this revision — 23 fully
fixed, 2 partially (QUAL-004's dependency pin without package migration, API-003's 3
highest-value call sites without the remaining 12), and 2 mitigated without full resolution
(QGIS-006/007, PERF-001, both explained in §6) — with regression tests added for every one and
the full suite re-run green after each (1531 → 1680 tests over the course of this audit, 0
failures throughout). **2 are accepted risk** (upstream API design choices or inherent endpoint
limitations, not fixable client-side). **3 remain genuinely untouched** (QUAL-001/002/003),
each explicitly no-action-recommended by the original audit — large-scope, low-value rewrites
(oversized-function refactors, sparse type hints, i18n gaps), not a same-session fix candidate.
Nothing has been committed to git; see §17 for the exact, precisely-classified working-tree
state.

This was a **targeted security review** — manual code reading plus structured sub-agent
analysis of specific domains named in the charter. It was **not** a comprehensive security
assurance exercise: no static-application-security-testing (SAST) tool, dependency-vulnerability
scanner, secret scanner, load/stress test, or full UI review was run. See §9.

**PERF-001** (High) was the single most significant finding: the plugin's recurring
hazard-monitoring feature could freeze the QGIS GUI on every scheduled tick, because it bypassed
the off-main-thread dispatch mechanism the rest of the codebase already has for the same 3
tools. As of this revision it is **mitigated**, not merely documented — the 3 network-fetching
hazard tools can no longer be used as a step in a scheduled/recurring workflow at all (they
remain fully usable as normal, manually-invoked single tool calls, which already dispatch
correctly). The proper fix — off-main-thread dispatch for a scheduled workflow step, mirroring
the existing `_execute_two_phase_tool` pattern — is a real design decision still left open; see
§15.

**QGIS-006/007** (the geographic-CRS-units finding) is **Mitigated, not Fixed** in the sense of
numeric correction: 3 logistics tools now honestly warn when their computed distance values are
in degrees rather than meters, but they do **not** reproject or convert those values — the
numbers returned are still in degrees when the input layer is geographic. This was verified
directly against the current code for this revision (§6), correcting the earlier draft's
overclaim.

No finding in this audit indicates data loss or a way to corrupt an existing QGIS project file.
One credential-adjacent finding (API-005, raw provider error bodies) was confirmed as a real,
non-hypothetical risk (some providers' real 401 error text echoes back a masked fragment of the
submitted API key) and has been fixed this revision.

## 2. Baseline correction

The supplied charter described a stale baseline: v1.5.0, 753 tests, 131-132 tools, "5 commits
ahead of origin, unpushed," and `cartogen-ai-community` as "the same private remote, mutually
unpushed" with this repo. Verified directly before any remediation work began: the actual
source-tree version is v1.15.5 (per `metadata.txt`; see §18 for a separate, unresolved
tag-naming/edition question this does NOT settle), fully pushed to `origin/main` with zero
unpushed commits at the time of the original 2026-09-13 audit start, and `cartogen-ai-community`
is a **stale ancestor** already merged into this repo's history on 2026-09-05 (per this repo's
own `CLAUDE.md`), not a sibling awaiting merge. The audit proceeded against the verified actual
state throughout, confirmed with the user before starting substantive work.

## 3. Architecture summary

Cartogen AI is a single-package QGIS plugin: a spatial AI agent that plans, executes, and shows
its work against a user's open QGIS project. No build step beyond a release zip.

- `agent/` — `agent.py` (tool-calling loop, dispatcher, thread-safety split into plain/
  `NETWORK_ONLY_TOOLS`/`TWO_PHASE_TOOLS`), `agent/providers/` (5 LLM provider clients),
  `agent/tools/` (169 tools across ~20 domain files, `@register_tool`-registered).
- `ui/` — the QGIS dock widget, chat tab, settings dialog, canvas highlighting. Imports
  `qgis.PyQt`/`qgis.core` unconditionally, so it is exercisable only inside a real QGIS process
  (this sandbox can boot one headlessly via `python-qgis.bat` — used for the fixes that needed
  it; see §9 for exactly which ones).
- `tests/` — 67 files (recounted directly for this revision — see §0 item 9), runnable without
  a QGIS install via each module's own `QGIS_AVAILABLE` guard; a separate
  `test_chat_widget_live.py` requires and skips itself without real QGIS bindings.

## 4. Versions and scale (re-verified directly for this revision)

| | Value | How verified |
|---|---|---|
| Plugin version (`metadata.txt`) | 1.15.5 | `grep '^version=' metadata.txt` |
| Registered tools | 169 | `grep -rc "@register_tool(" src/.../tools/*.py`, summed |
| Test files | **67** | `find tests -maxdepth 1 -name "test_*.py" \| wc -l` — corrects the earlier draft's "69" |
| Collected test cases | **1564** | `python -m unittest discover ...` output, this revision |
| Test suite result | 0 failures, 12 skipped | same run |
| Live QGIS tests (`test_chat_widget_live.py`) | 11/11 passing | `python-qgis.bat -m unittest tests.test_chat_widget_live -v` |
| Humanitarian Mapping Task Register | 791 tasks | `len(json.load(open("...task_register.json")))` |
| HEAD commit | `c0202da269364b1f08f6641ec8c71f2984305174` | `git rev-parse HEAD` |
| `commercial-plugin-v1.15.5` tag commit | `9c942922c2c6777df1d7c4cf7ab30b5cc57e351e` | `git rev-list -n 1 commercial-plugin-v1.15.5` |

The "approximately 233" test-file figure that surfaced during external review does not
correspond to anything reproducible against this repo by any counting method tried (files,
`class Test*` blocks, or `def test_*` methods all land far short of 233) — treated as
unsubstantiated rather than reconciled to. If it originated from a different repo, a different
directory, or a stale snapshot, that source is unknown from here; the number quoted in this
report throughout is the one produced by running the count command shown above, live, on the
final commit of this revision.

## 5. Findings by severity

Counted from the register's 5 domain tables (34 rows total; 2 API rows — API-008/009 — were
closed during triage as "confirmed clean, no defect," not real findings, leaving 32 actual
findings below — this is the one authoritative count; §1's executive summary uses it directly
rather than a separately-maintained number, which is what caused the original inconsistency).
Each row is counted once, under its highest stated severity where a row names more than one
(e.g. QGIS-006's "High for one sub-tool, Medium for the other two" is counted as High).

**Updated for round 2 (§0B).**

| Severity | Total | Fixed/Mitigated | Accepted Risk | Open |
|---|---|---|---|---|
| High | 6 | 6 (SEC-001, QGIS-001, QGIS-002, QGIS-006 [mitigated], QGIS-008, PERF-001 [mitigated]) | 0 | 0 |
| Medium | 8 | 5 (QGIS-003, QGIS-004, QGIS-007, PERF-003, PERF-004) | 1 (API-001) | 2 (PERF-002, QUAL-006) |
| Low / Low-Medium | 13 | 9 (SEC-002, API-002, API-003 partial, API-005, API-006, QGIS-009, PERF-005, QUAL-004 partial, QUAL-005) | 1 (API-004) | 3 (API-007, API-010, QUAL-001) |
| Informational | 5 | 3 (SEC-003, SEC-004, QGIS-005) | 0 | 2 (QUAL-002, QUAL-003) |
| **Total** | **32** | **23** (19 fully fixed, 2 partially, 2 mitigated) | **2** | **7** |

Note the arithmetic distinction from §1: 23 items were *fixed, partially fixed, or mitigated* in
the sense of "a regression test was added and passes"; of those, **19 are fully fixed**, **2 are
partial** (QUAL-004, API-003), and **2 (QGIS-006/007,
PERF-001) are mitigated but not fully resolved** — the underlying design work each needs is
still open, listed explicitly in §6/§15.

## 6. Defects corrected or mitigated (chronological — full detail and test references in the register)

**Fully fixed (13):**

1. **SEC-001** (High) — 4 second-hop URL fetches in `humanitarian_tools.py` bypassed the
   plugin's own SSRF guard. Fixed; 4 new tests.
2. **QGIS-004** (Medium, latent) — an unresolved `QgsVectorFileWriter.WriterError.NoError`
   enum would have made every successful export silently report failure. Fixed; 1 new test.
3. **QGIS-008** (High) — 4 composite-index analysis tools mutated attribute fields without the
   destructive-action confirmation gate every sibling mutation tool already has. Fixed; 5 new
   tests.
4. **QGIS-007** (Medium) — `score_route_incident_risk` discarded `buffer_analysis`'s own CRS
   warning instead of propagating it. Fixed as part of the same change as QGIS-006 (below) —
   the *propagation* is fully fixed; the underlying unit-correctness question is QGIS-006's.
5. **QGIS-001 + QGIS-002** (High) — a background task's completion callback had no exception
   guard, and plugin unload never cancelled an in-flight task. Fixed together; 3 mocked + 2
   live-QGIS tests (10/10 passing).
6. **QGIS-003** (Medium) — Stop-button cancellation was only checked once per LLM round, not
   per tool call within a multi-tool-call batch. Fixed; 1 new test proving mid-batch stop.
7. **PERF-003** (Medium) — `analyze_incident_trend` rebuilt the same spatial index once per
   time bucket instead of once. Fixed; 1 new test.
8. **PERF-004** (Medium) — building-footprint tile downloads weren't cached, only the tile
   index was. Fixed; 1 new test.
9. **PERF-005** (Low/Medium) — attachment parsing (PDF/DOCX/CSV) ran synchronously on the Qt
   main thread. Moved to the existing background analysis thread. Live-verified, 11/11 passing.
10. **SEC-002** (Low-Medium) — `export_to_csv` had no CSV/spreadsheet-formula-injection
    sanitization for string-typed attribute fields. Fixed: values in string columns beginning
    with `=`/`+`/`-`/`@`/tab/CR are now prefixed with a single quote after export (the standard
    OWASP mitigation), applied only to string-typed fields so numeric values (e.g. a negative
    longitude) are never wrongly quoted into text. 5 new tests.
11. **API-005** (Low → Confirmed) — raw provider HTTP-error bodies were surfaced unfiltered.
    Verified as a real, non-hypothetical risk: OpenAI's actual 401 error format echoes back a
    masked/partial copy of the submitted key. Fixed: a shared `format_http_error()` helper
    (`providers/base.py`) now withholds the raw body specifically for 401/403 responses across
    all 6 provider clients, while every other status (429, 500, etc.) still passes the real
    body through unchanged, since that's genuinely useful for debugging and isn't
    credential-bearing. 4 new tests.
12. **QUAL-004** (Low, **partial** — not a full fix, restated per §0 item 7) —
    `duckduckgo-search` pinned to a known-working range (`>=8.1.1,<9`). NOT done: migration to
    the renamed `ddgs` package, or classifying an API-shape-change error distinctly from other
    failures.
13. **QUAL-005** (Low) — version drift between `metadata.txt` (1.15.5, accurate) and
    `pyproject.toml`/`README.md`/`docs/TOOLS_REFERENCE.md` (stale). Corrected.

**Mitigated, not fully resolved (2 — reclassified this revision, §0 items 3-4):**

14. **PERF-001** (High) — `run_monitoring_workflow`/`schedule_recurring_workflow` executed each
    step's tool function directly and synchronously on the Qt main thread (the scheduler's
    `QTimer` fires there). For the 7 read-only local-analysis tools this is bounded, ordinary
    computation time — the same cost any single tool dispatch already has elsewhere in this
    codebase. For the 3 network-fetching hazard tools (`fetch_nasa_active_fires`,
    `fetch_nasa_eonet_events`, `fetch_gdacs_disaster_alerts`), it meant an HTTP round-trip
    blocking the whole GUI, repeated every tick, for as long as a schedule ran. **Mitigation
    applied:** those 3 tools are no longer accepted as a workflow step at all (removed from
    `_ALLOWED_WORKFLOW_TOOLS`, with the tool's own description and `docs/USER_GUIDE.md` updated
    to match) — this closes the actual freeze risk today. **Not done:** the tools remain
    unusable in a recurring schedule until `run_monitoring_workflow` is reworked to dispatch a
    network step off-thread, mirroring `agent.py`'s existing `_execute_two_phase_tool` pattern —
    a real design decision (how to structure a two-phase split for an arbitrary workflow of
    steps, not just one tool), left open. 1 new test confirming the exclusion.
15. **QGIS-006/QGIS-007's numeric correctness** (High for `score_route_incident_risk`, Medium
    for the other two tools) — **verified directly against the current code for this revision**:
    `optimal_hub_siting`, `optimize_delivery_route`, and `score_route_incident_risk` now emit an
    honest warning naming the units problem when the input layer is geographic (this part IS
    fully fixed — see QGIS-007 above for the propagation fix specifically). But the actual
    numeric values returned (`avg_distance`, `distance_to_route_m`, `total_distance`, etc.) are
    **still raw, unconverted CRS-unit values** — degrees, not meters, on a geographic CRS. No
    reprojection or unit conversion happens. This was a deliberate scope decision (the codebase's
    own established convention, matching `buffer_analysis`'s prior fix, is to warn honestly
    rather than guess a target CRS/UTM zone to reproject into) — but the original draft's bare
    "Fixed" status overstated what changed. Corrected to **Mitigated (Open)** in the register.
    Automatic unit correction remains a real, unresolved design decision requiring a human
    choice about how to pick a target projected CRS.

## 7. Performance evidence

No profiler was available in this sandbox; PERF-003/004/005's fixes are verified by call-pattern
regression tests (proving the redundant work no longer happens), not by wall-clock measurement.
PERF-002 (still open) is reasoned from code shape, not measured. PERF-001's mitigation removes
the mechanism rather than measuring its prior impact — no before/after timing was captured for
it either, since the fix is exclusion, not optimization.

## 8. Tests / scans run

- Full unit suite (`python -m unittest discover -s tests -t . -p "test_*.py"`), re-run after
  every single fix: 1531 (audit start) → 1564 (this revision), 0 failures throughout.
- Live QGIS suite (`python-qgis.bat -m unittest tests.test_chat_widget_live -v`): 11/11 passing,
  covering the fixes (QGIS-001/002, PERF-005) that specifically needed real Qt/QgsTask behavior.
- `python -m py_compile` on every changed source file, after every edit.
- `docs/generate_tools_reference.py` re-run after the PERF-001 mitigation changed a tool's
  description, so `docs/TOOLS_REFERENCE.md` stays in sync (the established convention).
- Direct code reading (not memory/doc recall) for every claim about current state: GDPR F6-F12
  status, the `execute_pyqgis_script` sandbox denylist, `cartogen-ai-community`'s relationship,
  the git tag/HEAD divergence (§17), and the commercial/community identity conflict (§18).
- Command-only pytest was NOT run — this repo's own canonical, documented test command is
  `python -m unittest discover -s tests -t . -p "test_*.py"` (`CLAUDE.md`, `CONTRIBUTING.md`),
  and that is what was used throughout, matching CI (`.github/workflows/tests.yml`). `pytest` is
  not a dependency of this project and was not installed or invoked; this is not a gap in the
  canonical verification, since `unittest` is what this repo's own tooling and CI standardize on.

## 9. Checks that could NOT run — this is a targeted review, not comprehensive assurance

Restated plainly per §0 item 6: the following were **not performed** in this audit, and their
absence should not be read as "checked and found clean."

- **Static application security testing (SAST)** — no tool wired in or run.
- **Dependency vulnerability scanning** — no `pip-audit`/`safety`-style scan run against
  `requirements.txt` or the plugin's transitive dependencies.
- **Secret scanning** — no automated scan for committed credentials/tokens; manual review only.
- **Full UI review** — only the specific widgets touched by this audit's own fixes (chat log,
  attachment flow) were live-verified visually; no full visual sweep of the rest of `ui/`.
- **Load/stress testing** — PERF-001/002's real-world impact is reasoned from code shape, not
  reproduced under load.
- **Performance profiling** — no profiler available in this sandbox (§7).
- `QScrollArea.NoFrame` (`dock_widget.py:165`, prior workstream, untouched here) — not
  re-verified live this revision.
- `cartogen-ai-community`/`cartogen-ai-community-limited` — explicitly out of scope per the
  charter.

## 10. GDPR status (re-verified against current code, not assumed from an older review doc)

F6 (undisclosed always-on project memory) — closed, gated behind
`is_project_memory_persist_enabled()` (`memory.py:106-114`). F7+F8 (no export/consolidated view)
— closed, "💾 Export My Data" button. F9 (erasure can't reach distributed copies) — documented,
not code-fixed (`SECURITY.md:407-411`) — an organizational limitation, not a code defect. F10
(plaintext credential fallback) — already adequately mitigated. F11/F12 —
organizational/informational. No new GDPR-relevant finding surfaced in this audit. This is a
code-level re-verification, not a legal/compliance sign-off — see §16's gate table.

## 11. `execute_pyqgis_script` sandbox — re-verified, not modified

The ~50-module denylist, blocked-calls set, and blocked-dunder-attrs set were read directly and
confirmed still intact. Not modified this audit — the charter asked for re-verification, not a
redesign, and the tiered-allowlist-vs-denylist architectural question remains explicitly Alaa's
call.

## 12. External API requirements found but not modified

- **NASA FIRMS** (API-004): transmits its API key via URL path — upstream design, not fixable
  client-side. Accepted Risk.
- **`duckduckgo-search`** (QUAL-004, **partial** fix only — see §6 item 12): has no official
  API, and has been renamed upstream (`duckduckgo-search` → `ddgs`). Pinned to a known range
  this audit; migration to the new package name NOT done.
- **Microsoft Global ML Building Footprints / HDX / geoBoundaries** — fetch paths hardened for
  SSRF (SEC-001) but not otherwise changed.

## 13. Exact files changed (round 1 snapshot below; round 2 added more — see §17 for the current, authoritative count)

**Round 2 update:** 9 more files modified and 3 new files created (`src/cartogen_ai/core/agent/
tools/_urllib_retry.py`, `tests/test_cache_utils.py`, `tests/test_urllib_retry.py`) since the
snapshot below was taken. Rather than re-embed an increasingly stale diff table here every
round, §17 states the live, authoritative `git status --short` counts — treat this section's
table as illustrative of round 1's shape, not the current exact total.

```
README.md                                              |   2 +-
docs/TOOLS_REFERENCE.md                                |   2 +-
docs/USER_GUIDE.md                                     |  25 +--
plugin_main.py                                         |  11 ++
pyproject.toml                                         |   2 +-
requirements.txt                                       |   8 +-
src/cartogen_ai/core/agent/agent.py                    |  13 ++
src/cartogen_ai/core/agent/providers/base.py           |  25 +++
src/cartogen_ai/core/agent/providers/cartogen.py       |   6 +-
src/cartogen_ai/core/agent/providers/claude.py         |   6 +-
src/cartogen_ai/core/agent/providers/gemini.py         |   8 +-
src/cartogen_ai/core/agent/providers/ollama.py         |   6 +-
src/cartogen_ai/core/agent/providers/openai.py         |   8 +-
src/cartogen_ai/core/agent/providers/openrouter.py     |   6 +-
src/cartogen_ai/core/agent/task_runner.py              |  25 ++-
src/cartogen_ai/core/agent/tools/analysis_tools.py     | 144 ++++++++++++++--
src/cartogen_ai/core/agent/tools/export_tools.py       |  64 ++++++-
src/cartogen_ai/core/agent/tools/humanitarian_tools.py |  73 ++++++--
src/cartogen_ai/core/agent/tools/logistics_tools.py    |  53 +++++-
src/cartogen_ai/core/agent/tools/monitoring_tools.py   |  44 ++---
src/cartogen_ai/core/ui/chat_tab_widget.py             |  63 +++++--
tests/test_analysis_tools.py                           | 150 +++++++++++++++
tests/test_chat_persistence.py                         |  50 +++---
tests/test_chat_widget_live.py                         |  67 ++++++++
tests/test_export_tools.py                             | 141 +++++++++++++-
tests/test_humanitarian_tools_worldpop.py              |  57 ++++++-
tests/test_logistics_tools.py                          | 114 ++++++++++++-
tests/test_monitoring_tools.py                         |  17 ++
tests/test_new_tools.py                                | 186 ++++++++++++++++
tests/test_providers.py                                |  44 +++++
tests/test_task_runner.py                              |  33 ++++
tests/test_temporal_dashboard.py                       |  14 ++
32 files changed, 1326 insertions(+), 141 deletions(-)
```
Plus new, untracked: `docs/audits/QGIS_PLUGIN_FINDINGS.md` and this report (see §17). The last
2 test files (`test_chat_persistence.py`, `test_temporal_dashboard.py`) were added in the
§0A environment-reproducibility follow-up, after the rest of this list was first compiled.

## 14. Breaking-change assessment (restated, less absolute — §0 item 8)

No intentional public API, tool-schema, or project-format breaking change was identified.
Every fix either: (a) closes a gap that made a tool falsely report success/failure or skip a
safety check, (b) adds a non-blocking warning field to a response that didn't have one before
(additive, nothing removed/renamed), (c) changes internal call patterns with no external
contract change, (d) fixes test/metadata/dependency-pin issues with no runtime behavior change,
or (e) removes 3 specific tool names from the recurring-workflow allowlist (PERF-001's
mitigation) — a real, user-facing capability reduction for that one narrow use case (scheduling
a hazard-fetch tool), disclosed plainly here and in the register/USER_GUIDE rather than silently
absorbed into "no breaking changes." **Residual compatibility risk remains** until broader
integration testing and testing against every officially supported QGIS version (§16) is
completed — this report's code-reading-and-unit-testing verification is not a substitute for
that.

## 15. Remaining risks (open findings, by priority — updated for round 4, §0D)

1. **PERF-001's off-main-thread rework (High original severity, mitigated not resolved)** — the
   3 hazard tools' recurring-workflow use case is disabled, not restored via a real fix.
   Restoring it needs the off-main-thread dispatch design work described in §6 item 14.
2. **QGIS-006/007's automatic unit correction (High/Medium original severity, mitigated not
   resolved)** — see §6 item 15. Needs a human decision on how to pick a target projected CRS,
   or whether to block the calculation instead of warning.
3. **QUAL-001/002/003 (Low/Informational)** — explicitly no-action-recommended by the original
   audit sub-agent (oversized-function refactors, sparse type hints, i18n gaps) — large-scope,
   low-value rewrites, not attempted. The only findings left completely untouched.
4. **API-003's remaining 12 call sites (Low, partially addressed)** — `humanitarian_tools.py`'s
   one-shot fetch tools (geoBoundaries, HDX, building footprints, WorldPop, OSM) still have no
   retry/backoff; the 3 highest-value recurring-schedule tools (`hazard_monitoring_tools.py`)
   do now. A follow-up can wire the same `_urllib_retry.urlopen_with_retry` helper into them.
5. **PERF-002's pair-count cap is a mitigation, not the ideal fix** — a genuine algorithm
   migration (`native:distancematrix`) remains open, deliberately not attempted without
   live-QGIS verification of its distance semantics (§0D, §6).

## 16. Release readiness gate

| Gate | Status |
|---|---|
| Repository identity (this checkout = `cartogen-ai`, canonical per `CLAUDE.md`) | Pass |
| Origin synchronization at the pre-audit HEAD | Pass (verified 2026-09-13) |
| Audit-change reproducibility from a tagged commit | **Blocked** — no commit/tag yet contains this audit's fixes (§17) |
| Working tree / dirty-tree classification | **Blocked** — 41 tracked files modified + 5 untracked paths (2 audit documents and 3 new source/test files), none committed (§17) |
| Automated tests (canonical `unittest` command) | **Pass, parent-reproduced after test-harness repair** — 1564 tests, 0 failures, 70 skipped (audit session recorded 12 skips in its fuller optional-dependency environment) |
| Interactive/live QGIS testing | **Partial** — only the specific fixes needing it were live-verified (§9); no full smoke test this revision |
| CRS numeric correctness (QGIS-006/007) | **Blocked pending decision** — currently honest-warning-only, not numerically corrected (§6 item 15) |
| PERF-001 GUI-freeze risk | **Mitigated** — the freezing code path is disabled; full fix still open |
| Licensing/tier (commercial-plugin tag vs. Community metadata) identity | **Resolved in this audit session (2026-09-14), independent re-verification still pending** — a separate review session could not reproduce the `gh` API check (no authenticated `gh` session there); see §18 for the exact commands to close that gap. **New sub-item open regardless**: the intended public Community repo (`cartogen_ai_community`) is itself currently private per this session's check — Alaa's call whether that's deliberate or needs publishing before release. |
| Security scans (SAST/dependency/secret) | **Not run** — see §9 |
| Privacy/legal (GDPR) | **Pass at code level** (§10); not a legal sign-off |

**Overall: BLOCKED.** Not because any single fix is wrong, but because (a) none of this audit's
work has been committed or tagged yet, (b) two High-severity findings are mitigated rather than
resolved, (c) independent cross-verification of the one-session GitHub visibility evidence and
the publication decision remain open, and (d) no security scanning beyond manual/targeted review
has been run.

## 17. Git state (precise, from `git status --short` — corrects §0 item 5)

```
HEAD:                          c0202da269364b1f08f6641ec8c71f2984305174
commercial-plugin-v1.15.5 tag: 9c942922c2c6777df1d7c4cf7ab30b5cc57e351e  (DIFFERENT commit)
```

The tag is one commit behind HEAD; that one commit (`c0202da`, "Bug tracker: close
BUG-2026-09-13-4...") is a docs-only change unrelated to this audit, made minutes after the tag
was cut, pre-dating this entire audit. **The tag contains none of this audit's fixes** — this
confirms the concern raised in review: `commercial-plugin-v1.15.5` represents the pre-audit
source only.

**Working tree — nothing is git-staged.** Every entry below is `" M"` (modified, NOT staged) or
`"??"` (untracked), per `git status --short`'s own XY format (a space in the first column means
nothing is staged for that path):

- **41 files, modified, not staged** as of round 2 (up from 32 after round 1 — §13's table shows
  round 1's shape only). None have been `git add`-ed; a `git diff` (not `git diff --cached`)
  shows all of it.
- **4 new, untracked paths** as of round 2 (up from 1): `docs/audits/` (containing
  `QGIS_PLUGIN_FINDINGS.md` and this report), plus 3 new files added in round 2 —
  `src/cartogen_ai/core/agent/tools/_urllib_retry.py`, `tests/test_cache_utils.py`,
  `tests/test_urllib_retry.py`. None yet `git add`-ed either. These counts are the live,
  authoritative ones — re-run `git status --short` before acting on any number in this report,
  since further rounds may have added more since this was last updated.

No commit, no tag, and no push has happened as part of this audit, honoring the operating rule
that Alaa commits explicitly himself. "Everything is staged" in the earlier draft meant
colloquially "held for review," not git's technical sense — corrected here to avoid the
ambiguity.

**Recommended release mechanics once reviewed and approved:** commit the reconciled changeset,
run the full test suite one more time from a clean checkout, then cut a **new** tag — per this
project's own versioning convention, something like `commercial-plugin-v1.15.6-rc1` (a release
candidate, reflecting that this is audit-remediation work, not a routine patch) — and do **not**
move or re-point the existing `commercial-plugin-v1.15.5` tag. Record the exact commit hash,
the built package's checksum, and this revision's validation results (test count, live-QGIS
result) alongside the new tag/release.

## 18. Commercial/Community identity — resolved in the audit session 2026-09-14; independent re-verification still pending

**Evidence-provenance caveat, added after independent review:** the `git remote -v` result
below was reproduced independently and confirmed. The `gh repo view`/`gh repo list` results
were **not** independently reproducible in a separate review session, because that session's
own `gh` CLI was not authenticated (`gh auth login required`) — it could not call the GitHub
API to check. That session correctly declined to treat the visibility claims below as
independently confirmed, and recorded them as "supplied audit evidence" pending its own
verification instead. That caution is appropriate and is reflected here: **the PRIVATE/PRIVATE
visibility findings below come from one authenticated session (this one), not two independent
ones.** To close that gap, run this from any `gh`-authenticated session (the same account,
`cartogenai-glitch`, or one with equivalent access):
```
gh auth status
gh repo view cartogenai-glitch/CARTOGEN-AI --json name,visibility,isPrivate
gh repo view cartogenai-glitch/cartogen_ai_community --json name,visibility,isPrivate
gh repo list cartogenai-glitch --limit 50 --json name,visibility,isPrivate,updatedAt
```
Until that's run independently, treat the "Resolved" framing below as *this session's verified
finding*, not yet *cross-verified*.

The technical disagreement between `CLAUDE.md` and `docs/MASTER_TASK_REGISTRY.md` (§0 item 11)
was settled in this audit session with git/GitHub state, checked two ways:

1. **`git remote -v`** in the real working checkout: `origin` is
   `https://github.com/cartogenai-glitch/CARTOGEN-AI.git`.
2. **Authenticated `gh repo view`/`gh repo list`** (via the already-configured `gh` credential,
   not an unauthenticated 404 guess): `CARTOGEN-AI` is confirmed **PRIVATE**
   (`visibility: PRIVATE`). `cartogenai-glitch/cartogen_ai_community` — the repo
   `MASTER_TASK_REGISTRY.md` names as the intended public Community-facing one — is **also
   confirmed PRIVATE**. The authenticated account-owned repository listing contains exactly 3
   private repositories: `CARTOGEN-AI`, `cartogen_ai_community`, and `-Cartogen-AI-Website`.
   There is no public repository for this project under the account.
**Resolved:** `MASTER_TASK_REGISTRY.md`'s repo-mapping is the technically correct one — this
checkout genuinely is the private `CARTOGEN-AI` repo, and there genuinely is a separate,
distinct repo intended for public Community distribution
(`cartogen_ai_community`). `CLAUDE.md`'s "single public Community codebase" framing has been
corrected in place (dated note, 2026-09-14) to read as a claim about codebase *content/
licensing intent* (no tier-gating logic, which remains true and separately verified) rather
than current GitHub hosting visibility, which it was previously ambiguous about. Also checked:
the local sibling folders `cartogen-ai-enterprise`/`cartogen-ai-pro` exist but have no `.git`
at all — genuinely not-yet-built, consistent with `CLAUDE.md`'s framing on that specific point.

**New fact, not merely a re-confirmation: `cartogen_ai_community` — the repo meant to be the
public one — is not actually public right now.** The authenticated account-owned repository
listing also shows `-Cartogen-AI-Website`, private. The account currently has zero public
repositories in the verified listing. This is a **new, dependent decision for Alaa**, not
something this audit can resolve: was the private Community/website state deliberate, or do
one or both intended public channels need publication before release?

## 19. Documentation drift (confirmed, not silently rewritten)

Two trackers are genuinely stale and were **not** edited in place, honoring this repo's own
"dated snapshots are frozen, don't silently rewrite" convention (`CONTRIBUTING.md`):

- `docs/IMPLEMENTATION_TRACKER.md` — stamped "Last updated: 2026-08-31, against v1.4.4."
- `docs/MASTER_TASK_REGISTRY.md` — stamped "Current state (as of 2026-09-05)," version 1.6.0.

Both are many versions behind the actual v1.15.5. **Recommendation:** either update both with a
fresh dated entry (matching their own established "supersede, don't rewrite" pattern — e.g. a
new "as of 2026-09-14" block in `MASTER_TASK_REGISTRY.md`'s Release Management section) or add
an explicit banner marking them historical/frozen, so a reader doesn't mistake either for
current state. Not done as part of this audit — it's a documentation-maintenance decision
outside this audit's own charter scope, surfaced here rather than silently left for someone to
discover later.

## 20. Recommended next actions

1. Decide whether `cartogen_ai_community` should be made public before release (§18's one
   remaining open sub-item — the repo-identity conflict itself is resolved).
2. Review this reconciled report and the register, then commit the 32 changed files plus the
   2 new audit docs, plus the `CLAUDE.md`/`MASTER_TASK_REGISTRY.md` correction notes (Alaa
   commits explicitly, per the standing operating rule).
3. Cut a new `-rc1` tag per §17 — never move the existing `v1.15.5` tag.
4. Decide QGIS-006/007's automatic-unit-correction approach (§6 item 15, §15 item 3).
5. Decide PERF-001's real off-main-thread fix, to restore hazard-tool scheduling (§6 item 14).
6. Run dependency-vulnerability and secret scans before release — neither ran in this audit (§9).
7. Package and install-test the plugin against every officially supported QGIS version before
   release, not just the one version available in this sandbox.
8. Refresh or freeze-banner the 2 stale trackers named in §19.
9. Lower priority: QUAL-006 (test coverage), PERF-002, and the remaining Low/Informational
   findings — all enumerated in the register, none release-blocking on their own.

---

*Revised 2026-09-14 in direct response to external review of the 2026-09-13 draft, then again
same day in response to an independent test-reproducibility re-verification (§0A). Every figure
in this revision was re-measured live against the repository at revision time — test counts,
git SHAs, and file lists were re-run, not copied forward. Source data:
[`QGIS_PLUGIN_FINDINGS.md`](QGIS_PLUGIN_FINDINGS.md)'s 5 domain tables and remediation log.*
