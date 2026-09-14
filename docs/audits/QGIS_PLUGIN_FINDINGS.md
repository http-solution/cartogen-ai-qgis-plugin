# Cartogen AI QGIS Plugin — Full Audit Findings Register

Started 2026-09-13, per the audit charter `cartogen-ai-audit-charter.md` (external file, not
committed to this repo). **The charter's own baseline facts were stale** (described the repo at
v1.5.0/753 tests/131-132 tools/5 unpushed commits) — corrected against actual current state
(v1.15.5, 1531+ tests, 169 tools, fully pushed to `origin/main`) before this audit began. See
`docs/audits/QGIS_PLUGIN_AUDIT.md` for the architecture summary and full methodology.

**GDPR F6–F12 reconciliation** (charter's own requested item): all already closed against the
current `cartogen-ai` code, independently re-verified by reading the actual implementation, not
assumed from the prior review doc. F6 (undisclosed project memory) — fixed 2026-09-11, opt-in
setting (`memory.py:106-114`). F7+F8 (no export/consolidated view) — fixed together, "💾 Export
My Data" button (`tasks_tab_widget.py:160-169`, `agent/data_export.py`). F9 (erasure can't reach
distributed copies) — documented, not a code fix (`SECURITY.md:407-411`). F10 (plaintext
credential fallback) — already adequately mitigated, re-confirmed still true
(`auth.py`/`settings_dialog.py:515,519`). F11/F12 — organizational, not code items, N/A.

**`execute_pyqgis_script` sandbox re-verification** (charter's own requested item): the 4
bypasses named in the charter (`pathlib`, `dbm`, `logging`, `zipfile`) are still denylisted in
`system_tools.py`, and the sandbox has been hardened further since (now ~50 blocked modules
including `winreg`/`io`/`tarfile`/etc., plus a frame-traceback-walking escape fixed 2026-09-08,
`BUG_TRACKER.md`'s `NEW-2026-09-08-1`). Holds.

Status legend: **Open** (found, not yet fixed) · **Fixed** (code changed, tests updated, suite
green — not yet committed, per this audit's "no git commits, Alaa commits himself" rule) ·
**Accepted Risk** (real, deliberately not fixed — reason given) · **Needs Verification** (needs
a live QGIS session this sandbox can't run).

---

## Security (audited by a dedicated sub-agent, cross-checked directly)

| ID | Component | Severity | Confidence | Status |
|---|---|---|---|---|
| SEC-001 | `humanitarian_tools.py` — 4 second-hop URL fetches bypassing the plugin's own SSRF guard | High | Confirmed | **Fixed** |
| SEC-002 | `export_tools.py::export_to_csv` — no spreadsheet formula-injection sanitization | Low-Medium | Confirmed/Probable | **Fixed** (2026-09-14) |
| SEC-003 | `pyproject.toml`/`metadata.txt` license-field mismatch; `ultralytics` (optional dep) is AGPL-3.0, undocumented | Low/Informational | Confirmed metadata gap | **Fixed** (2026-09-14) |
| SEC-004 | `humanitarian_tools.py` — downloaded temp files never cleaned up (resource leak, not a vuln) | Informational | Confirmed | **Fixed** (2026-09-14) |

**SEC-001 detail.** `_is_safe_url`/`_build_safe_opener` (`vector_tools.py`, adversarially
tested against loopback/private/link-local/metadata addresses and unsafe redirects) existed
but was only applied at the `add_layer_from_path` fetch layer. Four functions in
`humanitarian_tools.py` do a **second, unvalidated fetch** using a URL taken directly from a
**first, external API response's own body** — genuinely third-party-controlled content, not a
hardcoded endpoint: `fetch_geoboundaries_network_phase` (`gjDownloadURL`),
`fetch_hdx_admin_boundaries_network_phase` (HDX resource `url`),
`fetch_building_footprints_network_phase` (Microsoft tile index `Url`, per-row in a loop),
`fetch_worldpop_population_network_phase` (`files[0]`). Fixed by importing and applying
`_is_safe_url`/`_build_safe_opener` at all 4 sites — each now returns a clean
`{"error": "Refusing to fetch ...: <reason>"}` instead of fetching an unvalidated URL. Also
fixed a sibling instance of the (already-known, same-day-fixed-elsewhere) malformed-JSON crash
class in `fetch_geoboundaries_network_phase` (`isinstance(data, dict)` guard — this specific
function had been missed when the sibling bug was fixed earlier the same day in
`hazard_monitoring_tools.py`/the rest of `humanitarian_tools.py`).
Evidence: `humanitarian_tools.py` — SSRF guard applied at lines ~275-285 (geoboundaries),
~397-403 (HDX zip), ~696-702 (building-footprint tiles), ~893-899 (WorldPop). 4 new regression
tests (`test_new_tools.py`, `test_humanitarian_tools_worldpop.py`) confirm each site now
refuses a `169.254.169.254`/`127.0.0.1` URL cleanly instead of fetching it; 6 existing tests
updated for the new call path (`_build_safe_opener().open(...)` instead of bare
`urllib.request.urlopen(...)`). Full suite 1531 → 1535, 0 failures.
Breaking risk: **None** — pure hardening, no legitimate URL from any of these 4 real external
APIs is a private/loopback/metadata address, so no real-world call is newly rejected.

---

## API / Network client (audited by a dedicated sub-agent)

| ID | Component | Severity | Confidence | Status |
|---|---|---|---|---|
| API-001 | `providers/base.py::post_with_retry` — retries non-idempotent POST on timeout, no idempotency key | Medium | Probable | Accepted Risk (2026-09-14) |
| API-002 | All 6 providers' `list_models()` bypasses `post_with_retry` | Low | Confirmed | **Fixed** (2026-09-14) |
| API-003 | Humanitarian/hazard `urllib` fetch tools have zero retry/backoff (unlike the 5 LLM providers) | Low | Confirmed | **Fixed (partial)** (2026-09-14) |
| API-004 | NASA FIRMS API key transmitted via URL path (upstream API's own design, not fixable client-side) | Low | Confirmed | Accepted Risk |
| API-005 | Raw provider HTTP-error bodies (`e.response.text`) surfaced unfiltered into chat/history | Low | Needs Verification → Confirmed (2026-09-14: OpenAI's real 401 body echoes a masked/partial key) | **Fixed** (2026-09-14) |
| API-006 | Inconsistent malformed-response error quality — OpenRouter has a narrow `except`, OpenAI/Gemini/Cartogen don't | Low | Confirmed | **Fixed** (2026-09-14) |
| API-007 | No inline consent notice at the moment of file attachment (image/file content → LLM) | Low-Medium | Confirmed | **Fixed** (2026-09-14) |
| API-008 | Sweep for siblings of the v1.15.5 `extract_openai_style_usage` crash | Informational | Confirmed clean | Closed (no action) |
| API-009 | Duplicate-submission/billing risk beyond API-001 | Informational | Confirmed clean | Closed (no action) |
| API-010 | Offline/DNS-failure messages are bounded (no raw traceback) but not maximally actionable | Low | Confirmed | **Fixed** (2026-09-14) |

Confirmed clean and worth stating: TLS enforced everywhere in scope (only expected exception:
Ollama's local `http://localhost`); no credential ever appears in a log/print/exception
message; the 429-specific backoff genuinely engages for a sustained limit (~60s total patience,
10s/20s/30s); Stop-button cancellation is honestly documented as "between calls, not mid-call,"
matching what the code actually does — no misrepresentation found.

---

## QGIS / PyQGIS integrity

**Discovery phase** (below): audited by a dedicated sub-agent via static code analysis only —
that sub-agent had no live QGIS session, so several findings below are explicitly marked Needs
Verification for that reason. **Remediation phase** (2026-09-13, see the remediation log at the
bottom of this file): a real QGIS install (`python-qgis.bat`) WAS available in the main session
and was used to live-verify specific fixes (QGIS-001/002, and later PERF-005) end to end, not
just via mocks — noted per-fix in the remediation log. These are two different phases of the
same audit; a fix's own remediation-log entry states plainly whether it was live-verified or
only unit-tested against mocks. Don't read the static-only note above as describing this whole
file's evidence quality — check each finding's own entry.

| ID | Component | Severity | Confidence | Status |
|---|---|---|---|---|
| QGIS-001 | `task_runner.py::AgentQgsTask.finished()` has no exception guard (unlike `.run()`) | High | Confirmed code gap / Needs Verification for live crash behavior | **Fixed** |
| QGIS-002 | `plugin_main.py::unload()` never cancels an in-flight `AgentQgsTask` | High | Confirmed | **Fixed** |
| QGIS-003 | Stop-button cancellation checked once per LLM round, not per tool call within a multi-tool-call batch | Medium | Confirmed | **Fixed** |
| QGIS-004 | `export_tools.py` — `_VFW_NO_ERROR` `None`-fallback would make every export silently report failure if the enum ever fails to resolve | Medium (latent) | Confirmed logic bug | **Fixed** |
| QGIS-005 | Other `resolve_qgis_enum` call sites are `None`-safe only by incidental outer `try/except`, not by design | Low/Informational | Confirmed | **Fixed** (2026-09-14) |
| QGIS-006 | CRS-unit-mismatch bug class (fixed in `buffer_analysis`, architecture review point 3) not propagated to `optimal_hub_siting`, `optimize_delivery_route`, `score_route_incident_risk` | High (for `score_route_incident_risk`), Medium (other 2) | Confirmed | **Mitigated (Open)** — see 2026-09-14 correction below |
| QGIS-007 | `score_route_incident_risk` discards `buffer_analysis`'s own CRS warning | Medium | Confirmed | **Fixed** |
| QGIS-008 | Destructive-action preview/confirm gate (established by BUG-2026-08-21-3) not applied to 4 composite-index tools that mutate attribute tables the same way | High | Confirmed | **Fixed** |
| QGIS-009 | `add_incident_point` can leave a shared "Incidents" layer permanently unstyled on a rare styling failure | Low | Confirmed code path; trigger condition currently unreachable | **Fixed** (2026-09-14) |

**QGIS-004 detail (fixed).** `export_tools.py`'s `_VFW_NO_ERROR = resolve_qgis_enum(...)` could
be `None` if a future QGIS build resolved neither the scoped nor flat form of
`QgsVectorFileWriter.WriterError.NoError`. `if error != _VFW_NO_ERROR` would then be `error !=
None`, which is **always True** for a real (non-`None`) error code from a successful export —
meaning every successful export would silently report itself as failed. This doesn't crash, so
nothing would have caught it; the wrong answer would just ship. Fixed with an explicit
`is None` guard returning a clear error naming the resolution failure, instead of comparing
against a possibly-`None` sentinel. Today inert (the enum currently resolves fine on both
QGIS 3.x and 4.x) — this closes a real correctness gap conditional on future QGIS API drift,
not a currently-observable bug.

Confirmed clean and worth stating: `ui/`'s Qt6 flat-enum crash fixes (already tracked in
`BUG_TRACKER.md`) hold; every `NETWORK_ONLY_TOOLS` function genuinely touches no
`QgsProject`/`QgsVectorLayer`/`iface` object, confirming the main-thread-dispatch bypass is
safe; `BlockingQueuedConnection` reentrancy correctly short-circuits when already on the
dispatcher thread, no deadlock pattern found; Arabic/RTL filename handling uses Python's
Unicode-aware `str.isalnum()`, not an ASCII-only regex, and no byte-level UTF-8 slicing
anti-pattern exists anywhere in `agent/`/`ui/`; renderer/geometry-type matching in
`styling_tools.py` is consistently correct across all 10 call sites checked; the atlas-export
`beginRender()`/`endRender()` pair is correctly wrapped in `try/finally`.

---

## Performance (Section 7 of the charter, audited by a dedicated sub-agent, static analysis only)

| ID | Component | Severity | Confidence | Status |
|---|---|---|---|---|
| PERF-001 | `run_monitoring_workflow`/`schedule_recurring_workflow` bypass the two-phase off-main-thread dispatch the 3 individual hazard tools already get — every step's `urllib.request.urlopen` runs synchronously on the Qt main thread, and the recurring scheduler fires it inline from its `QTimer` slot | High | Confirmed (architectural trace); duration itself Needs Verification | **Mitigated** (2026-09-14) — see correction below |
| PERF-002 | `optimal_hub_siting`/`location_allocation` compute a full candidate×demand `QgsGeometry.distance()` cross product in pure Python, no upper bound on input size | Medium | Probable (reasoned from shape, not measured) | **Fixed** (2026-09-14) |
| PERF-003 | `analyze_incident_trend` rebuilds the same `QgsSpatialIndex`/feature-id map once per time bucket (`num_periods` is unbounded) instead of once for the whole call | Medium | Confirmed | **Fixed** |
| PERF-004 | `fetch_building_footprints_network_phase` caches the small tile-index CSV via `_LOOKUP_CACHE` but not the actual per-quadkey tile downloads — repeat calls re-fetch multi-MB tiles | Medium | Confirmed | **Fixed** |
| PERF-005 | `attach_file()`/`read_attached_file` parse PDF/DOCX attachments synchronously on the Qt main thread, no `QgsTask`/background hop (unlike the network-fetch tools) | Low/Medium | Needs Verification (no profiler; depends on real attachment sizes) | **Fixed** |

Confirmed already in good shape (no finding): no heavy optional dependency is imported at module
scope anywhere under `agent/tools/` (all local-imported inside the function that needs them), so
plugin/QGIS startup isn't paying for pandas/docx/openpyxl/matplotlib/pdfplumber/folium up front;
`task_register.json` (791 tasks) is parsed once via a memoized module global, and `task_matcher
.classify()` only runs once per message send (not per keystroke — no `textChanged`-driven call
exists); `vector_tools.py`/`raster_tools.py` route essentially everything through native
`processing.run(...)` algorithms rather than per-feature Python loops; `QgsSpatialIndex` is
already used correctly elsewhere (`diagnose_topology`, `obfuscate_sensitive_points`,
`_count_points_in_polygons`'s own bbox-then-contains pattern — PERF-003 is a call-frequency bug
in that same function, not a missing-index bug); only 4 call sites construct a
`QgsCoordinateTransform` anywhere in `agent/`/`ui/`, each once per call, no CRS-in-a-loop
pattern; `_trim_history` genuinely caps conversation history at 20 messages,
`memory.py`'s `_in_memory_actions` is capped at 50, and `chat_tab_widget.py`'s highlight-expiry
timers are self-cleaning — no unbounded in-memory growth found; `hazard_monitoring_tools.py`
deliberately has no TTL cache on its 3 fetch tools (documented intentional — live data must
reflect the latest fetch, distinct from `humanitarian_tools.py`'s static reference data), not a
gap; `scheduler.py`'s `_MIN_INTERVAL_MINUTES = 1` + max-concurrent-schedules cap are already in
place with their own prior-review comments.

---

## Code Quality (Section 8 of the charter, audited by a dedicated sub-agent, static analysis only)

| ID | Component | Severity | Confidence | Status |
|---|---|---|---|---|
| QUAL-001 | 5 oversized functions with real multi-concern complexity (`_build_temporal_dashboard_html` 465 lines, `_execute_two_phase_tool` 176 lines/10 near-identical dispatch blocks, `create_print_layout` 232 lines, `calculate_service_area` 186 lines/depth 5, `agent.run` 161 lines) | Low | High | Open (informational; only `_build_temporal_dashboard_html` and `_execute_two_phase_tool` flagged as worth a refactor if touched again — `calculate_service_area`'s depth is a documented hard case, not a defect) |
| QUAL-002 | Type-hint coverage is consistently sparse in `agent/tools/` (13%) and `ui/` (1%) vs. core dispatch code (28%, `tool_router.py` 100%) — a stable codebase-wide convention, not an old-code-never-updated pattern (newest tool file is 0% too) | Informational | High | Open (informational; retrofitting 169 tool signatures explicitly not recommended as a large low-value rewrite) |
| QUAL-003 | i18n (`self.tr(...)`) used in only 1 of 14 `ui/` files (`onboarding_dialog.py`); 66+ hardcoded UI strings elsewhere not translation-wrapped | Informational | High | Open (informational) |
| QUAL-004 | `duckduckgo-search` (unpinned, per `requirements.txt`'s documented rationale) has no official API, a documented history of breaking on upstream response-format changes, and has been renamed upstream (`duckduckgo-search` → `ddgs`); `search_web`'s only failure handling is a generic `ImportError` catch, not a narrower degrade-on-API-change path | Low | Medium | **Fixed (partial)** |
| QUAL-005 | Version drift: `metadata.txt` says `1.15.5` (actual), `pyproject.toml` and `README.md` both still say `1.15.0` — `pyproject.toml`'s own adjacent comment already flagged this exact drift risk | Low | Confirmed | **Fixed** |
| QUAL-006 | 24 of 169 tools have zero behavioral test coverage by name (structural coverage only, via the generic `TOOL_REGISTRY` iteration tests) — mostly raster/classification tools (`slope_analysis`, `aspect_analysis`, `supervised_classification`, `unsupervised_classification`, `band_composite`, `pan_sharpening`, `mosaic_rasters`, `raster_clip`, `zonal_statistics`) plus 15 vector/layer-management tools | Medium | High | **Fixed** (2026-09-14) |

Confirmed already in good shape (no finding, re-verified rather than assumed): `grep`-verified
**zero** bare `except:` and **zero** real TODO/FIXME/XXX/HACK comments anywhere in `src/`
(CLAUDE.md's claim holds exactly); import direction is clean in both directions
(`agent/`/`agent/tools/` never imports from `ui/`, `ui/` correctly imports from `agent/`, no
circular import); AST-swept all 145 non-tool top-level functions/classes in `agent/`+`ui/` and
found zero dead code (every one referenced elsewhere); `_find_layer_by_name`'s 18-file
duplication is confirmed intentional, matching `CONTRIBUTING.md`'s own documented
per-tools-file self-containment convention, not flagged as a defect.

---

## Remediation log (chronological, this audit)

- **2026-09-13**: SEC-001 fixed (SSRF guard applied to 4 second-hop fetches + 1 sibling
  malformed-JSON crash fixed in `fetch_geoboundaries_network_phase`). 4 new regression tests, 6
  existing tests updated for the new call path. Full suite 1531 → 1535, 0 failures.
- **2026-09-13**: QGIS-004 fixed (`_VFW_NO_ERROR` `None`-fallback correctness gap in
  `export_tools.py`). 1 new regression test. Full suite 1535 → 1536, 0 failures.
- **2026-09-13**: QGIS-008 fixed (`confirmed`/`PREVIEW_REQUIRED` gate added to
  `calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`,
  `calculate_damage_exposure_severity`'s `output_field` write path — matching the exact
  established `field_calculator`/`calculate_area`/`calculate_length` pattern from
  BUG-2026-08-21-3, gated on `output_field` being requested specifically so the ordinary
  read-only analysis path stays ungated). Reuses the existing dispatcher-level schema-filtering
  protection (a model can't self-confirm by injecting `confirmed: True` — only a real UI
  confirm click can, since `confirmed` isn't in any of these tools' declared JSON schema). 5
  new regression tests (one per tool's gate, plus one confirming the schema-filtering
  protection). Full suite 1536 → 1541, 0 failures.

- **2026-09-13**: QGIS-006 + QGIS-007 fixed together (the same underlying geographic-CRS
  issue). `score_route_incident_risk` now propagates `buffer_analysis`'s own CRS warning
  (previously discarded — only `"error" in buffer_result` was checked) and extends it to
  explicitly cover `distance_to_route_m` (mislabeled as meters, actually degrees on a
  geographic CRS — the most safety-relevant instance, since this tool scores incident
  proximity to a route for humanitarian/security decisions). `optimal_hub_siting` and
  `optimize_delivery_route`'s straight-line fallback both gained the same honest,
  non-blocking warning `buffer_analysis` already uses (no guessed reprojection). 6 new
  regression tests. Full suite 1541 → 1545, 0 failures.

- **2026-09-13**: QGIS-001 + QGIS-002 fixed together (the same underlying task-lifecycle gap).
  `task_runner.py::AgentQgsTask.finished()`'s `on_complete` callback invocation is now wrapped
  in `try/except`, matching `.run()`'s own existing guard — a UI-side failure there (e.g. a
  destroyed dock widget) can no longer propagate uncaught into QGIS's own task-manager
  machinery. `chat_tab_widget.py` gained a new public `cancel_active_task()` (the cancel-only
  core of the existing `_stop_current_task`, now shared by both), and `plugin_main.py::unload()`
  calls it before tearing down the dock widget — closing the actual root cause (an in-flight
  task kept running against a dock widget scheduled for deletion) rather than only catching
  the crash it could cause. 3 new tests in `test_task_runner.py` (mocked), 2 new tests in
  `test_chat_widget_live.py` (real QgsTask via `python-qgis.bat`, live-verified: 10/10 passing).
  Full suite 1545 → 1550, 0 failures.

- **2026-09-13**: QGIS-003 fixed. `agent.py::run()`'s tool-call loop now checks `should_stop()`
  a second time, at the top of the per-call loop body (in addition to the existing top-of-round
  check) — a multi-tool-call batch in one LLM response (buffer → clip → export style requests)
  can now be interrupted between individual tool calls, not just between whole LLM rounds.
  `chat_tab_widget.py::_stop_current_task`'s docstring updated to match what the Stop button
  now actually guarantees. 1 new regression test (`OneRoundTwoToolsClient` returning 2
  `tool_calls` in a single response; stopper allows the round + first tool call, then fires
  before the second — asserts the second tool was never dispatched). Full suite 1550 → 1551,
  0 failures.

- **2026-09-13**: Performance (PERF-001–005) and Code Quality (QUAL-001–006) sections completed
  by 2 dedicated sub-agents (static analysis, charter Sections 7-8). QUAL-005 (version drift:
  `pyproject.toml`/`README.md` still said 1.15.0 against `metadata.txt`'s actual 1.15.5) fixed
  immediately as a mechanical, low-risk correction per `CLAUDE.md`'s own "fix directly" category
  — both bumped to 1.15.5. All other PERF-*/QUAL-* findings left Open/Informational for Alaa's
  triage: none are safe same-session fixes (PERF-001 needs a new off-main-thread dispatch class
  mirroring `_execute_two_phase_tool`'s existing pattern — a real, reviewable design change, not
  mechanical; PERF-002/003/004 are real but not demonstrated to be user-visible at typical input
  sizes; QUAL-001/002/003 are explicitly informational/no-action-recommended by the auditing
  agent itself; QUAL-004 and QUAL-006 are scoped decisions — a dependency pin and a test-writing
  effort — better left to Alaa's prioritization than done silently in bulk).

- **2026-09-13**: PERF-003 fixed. `analyze_incident_trend` was calling
  `_count_points_in_polygons(zones, ...)` once per time bucket, rebuilding the same
  `QgsSpatialIndex` + feature-id map against the unchanged `zones` layer every time —
  O(periods × zones) of redundant index construction for a fine-grained or long-range
  analysis. Split into `_build_polygon_index` (index + feature-id map) and
  `_count_points_in_polygons_indexed` (the actual per-call counting), with
  `_count_points_in_polygons` kept as a thin single-call convenience wrapper around both
  for its one remaining caller (`calculate_damage_exposure_severity`, unaffected).
  `analyze_incident_trend` now builds the index once and reuses it across every bucket.
  1 new regression test (mocks both helpers, asserts the index-builder is called exactly
  once regardless of bucket count while the counter is called once per bucket — `qgis.core`
  isn't importable in this sandbox, so this verifies the call pattern, which is exactly
  what the performance bug was, rather than the real QGIS index behavior). Full suite
  1551 → 1552, 0 failures.

- **2026-09-13**: PERF-004 fixed. `fetch_building_footprints_network_phase` already cached
  the small tile-index CSV via `_LOOKUP_CACHE`, but not the actual per-quadkey tile
  downloads (multi-MB, gzipped) — a repeated call for the same/overlapping bbox within the
  cache's 1800s TTL re-downloaded and re-decompressed the same tiles every time. Now cached
  by tile URL under the same `_LOOKUP_CACHE` instance/TTL. 1 new regression test (2 calls
  with the same bbox; confirms the safe opener's `.open()` is invoked only once). Exposed a
  latent test-isolation gap while adding it: 2 existing tests (`..._happy_path` and
  `..._handles_request_failure_gracefully`) didn't clear the shared
  `("building_footprints_links",)` cache key at their own start, unlike the established
  SEC-001 test's convention — harmless before this fix (that cache only ever held a CSV
  string), but a real risk now that a *successful* run also populates a second, per-tile
  cache entry other tests could silently inherit. Both now clear the shared key explicitly,
  matching the existing convention. Full suite 1552 → 1554, 0 failures.

- **2026-09-13**: PERF-005 fixed. `attach_file()`'s call to `read_attached_file` (pypdf/
  python-docx/pandas parsing) ran synchronously on the Qt main thread, before the
  background analysis thread was even started — a large PDF/DOCX/table-heavy attachment
  could freeze the whole GUI while it parsed. `read_attached_file` has zero Qt/QGIS
  dependency (documented in its own module docstring), so the parsing call moved into a
  new `_read_and_analyze_file`, which now runs entirely on the background thread
  `attach_file()` already spawns for the LLM analysis step — logic otherwise unchanged
  (success/failure handling, `_attached_paths` bookkeeping, and the signals emitted back to
  the chat log all identical to before, just executed off the main thread). Live-verified
  via `python-qgis.bat` (a real background thread reading a real temp file end-to-end
  through to the chat log): 1 new test, 11/11 passing in `test_chat_widget_live.py`.

- **2026-09-13**: QUAL-004 partially addressed. `duckduckgo-search` pinned to `>=8.1.1,<9`
  in `requirements.txt` (8.1.1 is the version `search_web` is actually tested against; the
  upper bound avoids an untested future major-version jump silently changing `DDGS`'s API
  shape) — this is the mechanical, low-risk half of the finding. Not changed: `search_web`'s
  exception handling already has a generic `except Exception` catch-all (so an API-shape
  break surfaces as a clear `{"error": "Search failed: ..."}`, not an uncaught crash — the
  audit's phrasing overstated this part); narrowing it further to detect specifically an
  API-shape change vs. a network/rate-limit error would mean guessing at `duckduckgo-search`'s
  internal exception types without evidence, which isn't a mechanical fix — left open for
  Alaa's call if it's worth pursuing.

- **2026-09-13**: PERF-001, PERF-002, QUAL-001, QUAL-002, QUAL-003, and the rest of QUAL-006
  deliberately left open — each needs a real design decision (a new off-main-thread dispatch
  class for PERF-001; an algorithm change with correctness risk for PERF-002; large-scope,
  explicitly-not-recommended rewrites for QUAL-001/002/003; a 24-tool test-writing effort for
  QUAL-006) rather than a same-session mechanical fix. Flagged for Alaa's triage/prioritization.

### 2026-09-14 — corrections and additional fixes from external review

- **PERF-001 mitigated (not fully resolved).** `run_monitoring_workflow` calls each workflow
  step's tool function directly, synchronously, on the Qt main thread (the scheduler's
  `QTimer` fires there). For the 7 read-only local-analysis tools this is bounded, ordinary
  compute time; for the 3 network-fetching hazard tools
  (`fetch_nasa_active_fires`/`fetch_nasa_eonet_events`/`fetch_gdacs_disaster_alerts`), it meant
  an HTTP round-trip blocking the whole GUI, every tick, for as long as a schedule ran.
  Mitigation: removed those 3 tools from `_ALLOWED_WORKFLOW_TOOLS`
  (`monitoring_tools.py`) — they remain fully usable as normal, manually-invoked single tool
  calls (already dispatched correctly via `agent.py`'s `TWO_PHASE_TOOLS`), just not schedulable.
  Tool description and `docs/USER_GUIDE.md` updated to match; `docs/TOOLS_REFERENCE.md`
  regenerated. 1 new regression test. The real fix (off-main-thread dispatch for a workflow's
  network steps, mirroring `_execute_two_phase_tool`) remains open — a real design decision.
  Full suite 1555 tests, 0 failures at this point.

- **SEC-002 fixed.** `export_to_csv` had no CSV/spreadsheet-formula-injection sanitization.
  Added `_sanitize_csv_formula_injection` (`export_tools.py`): after a successful CSV export,
  any STRING-typed field's value beginning with `=`/`+`/`-`/`@`/tab/CR gets a leading single
  quote (the standard OWASP mitigation) — numeric/date/bool fields are never touched, so a
  legitimate negative number (e.g. longitude) is never wrongly quoted into text. 5 new tests.
  Full suite 1560 tests, 0 failures.

- **API-005 fixed**, and its Confidence upgraded from "Needs Verification" to Confirmed: raw
  provider HTTP-error bodies were surfaced unfiltered into chat/conversation history.
  Verified this is a real, non-hypothetical risk (OpenAI's actual 401 error format echoes back
  a masked/partial copy of the submitted key). Added a shared `format_http_error()` helper
  (`providers/base.py`), used by all 6 provider clients: withholds the raw body specifically
  for 401/403 responses; every other status (429, 500, etc.) still passes the real body
  through, since that's genuinely useful for debugging and isn't credential-bearing. 4 new
  tests. Full suite 1564 tests, 0 failures.

- **QGIS-006/QGIS-007 reclassified from "Fixed" to "Mitigated (Open)".** Verified directly
  against the current code: `optimal_hub_siting`, `optimize_delivery_route`, and
  `score_route_incident_risk` correctly warn when their input layer is geographic (this part —
  and QGIS-007's warning-propagation fix specifically — IS fully correct), but the actual
  returned distance values (`avg_distance`, `distance_to_route_m`, `total_distance`, etc.) are
  still raw, unconverted CRS-unit values — degrees, not meters. No reprojection or unit
  conversion happens; this was a deliberate scope choice (matching `buffer_analysis`'s
  established "warn honestly, don't guess a target CRS" convention) that the original "Fixed"
  status overstated. No code change this entry — a status/documentation correction only.
  Automatic unit correction remains open, needing a human decision on target-CRS selection.

- **Documentation/report corrections** (no code change): reconciled the Final Report's finding
  totals to this register's authoritative 32-finding count; clarified the QGIS-integrity
  section's static-review-vs-live-verification phases (see this file's own section header
  above); corrected the test-file count (67, not 69) and re-measured the test-case count
  (1564 at time of writing); replaced "everything is staged" with precise `git status --short`
  classification (nothing is git-staged; all changes are unstaged modifications or untracked
  files); restated "no breaking changes" as "no *intentional* breaking change identified;
  residual compatibility risk remains until broader integration/supported-version testing";
  added git tag/HEAD divergence verification (the `commercial-plugin-v1.15.5` tag points at a
  different, pre-audit commit — confirmed, SHAs in the Final Report); flagged (not resolved) a
  commercial/community identity conflict between `CLAUDE.md` and `docs/MASTER_TASK_REGISTRY.md`;
  confirmed 2 genuinely stale trackers (`IMPLEMENTATION_TRACKER.md` v1.4.4,
  `MASTER_TASK_REGISTRY.md` v1.6.0) without silently rewriting them, per this repo's own
  frozen-snapshot convention. Full detail in the Final Report's own §0 corrections list.

### 2026-09-14 — environment-reproducibility follow-up (external re-verification and parent repair)

A fresh test run in a different ("parent") environment first reported 1 failure + 1 error where
the audit session showed 0 failures. The parent then reproduced and repaired both test-harness
issues directly. The focused regression set now passes **70 tests, 0 failures, 23 skipped**;
the full canonical suite passes **1564 tests, 0 failures, 70 skipped** in the current parent
environment.

- **`ModuleNotFoundError: No module named 'branca'` in `test_temporal_dashboard.py` — real test
  guard bug, fixed.** The temporal color-resolution class had no `branca` guard even though the
  production path imports `branca.colormap`; its setup now checks both `folium` and `branca`.
  The other temporal test classes retain the same paired guards.
- **Timestamp-collision assertion in `test_chat_persistence.py` — environment-sensitive test,
  hardened.** This runtime can return the same `datetime.now()` value for consecutive rapid calls.
  The test now controls `_now_iso()` with two deterministic timestamps and documents that it is
  testing fresh-save timestamp assignment, not host-clock advancement or timer resolution. The
  production timestamp implementation was not changed.
- A search found other `2026-01-01` values in unrelated date-range, incident, monitoring,
  remote-sensing, and export fixtures; they are not timestamp-collision fixtures and were left
  unchanged. The chat-persistence timestamp fixtures use `2000-01-01`.

The skip-count difference is environment-dependent optional-package availability. In the current
parent environment the missing optional packages are now handled as skips rather than errors.
This test-infrastructure repair does not clear the QGIS release gate: the working tree remains
dirty, the audit fixes remain uncommitted, the existing tag points to a pre-audit commit, and
interactive, licensing, CRS, security-scan, privacy/legal, and package provenance gates remain
open.
Full suite after both fixes: 1564 tests, 0 failures, 70 skipped (current parent environment).

### 2026-09-14 — remediation round 2 ("proceed with the remaining open findings")

Continued triaging the 15 findings still untouched after round 1. 9 more fixed/mitigated this
round; full suite grew 1564 → 1590, 0 failures throughout (re-run after every single fix, not
just at the end).

- **SEC-003 fixed.** `pyproject.toml`'s license SPDX identifier said `GPL-2.0-or-later`, which
  matched neither the actual shipped `LICENSE` file (plain GPLv2) nor `metadata.txt`'s own
  `license=GNU GPL v2` field. Corrected to `GPL-2.0-only` — a metadata-accuracy fix, not a
  change to the actual license terms (already GPLv2). Also documented `ultralytics`' AGPL-3.0
  upstream license directly in `requirements.txt` next to its entry (it's an optional,
  never-bundled dependency the user installs separately) — flagged for whoever owns this
  project's licensing decisions, not resolved unilaterally.
- **SEC-004 fixed.** Cached fetch results in `humanitarian_tools.py` (geoBoundaries/HDX/
  WorldPop) carry a real temp-file `local_path`, deliberately kept alive while the cache entry
  is live so a repeat call within the TTL window reuses the file — but nothing ever deleted it
  once the entry expired. `TTLCache` (`_cache_utils.py`) gained an optional `on_evict(key,
  value)` callback, fired on natural expiry or overwrite; `humanitarian_tools.py` wires a new
  `_cleanup_cached_local_path` into its `_LOOKUP_CACHE` instance. Backward-compatible (every
  other `TTLCache` caller omits the new parameter, unaffected). 13 new tests
  (`test_cache_utils.py` + `test_new_tools.py`).
- **API-002 fixed.** All 6 providers' `list_models()` used a bare `requests.get(...)` with no
  retry, unlike the chat-completion path (`post_with_retry` since 2026-09-12). `providers/
  base.py`'s retry loop refactored into a shared `_request_with_retry` helper behind both
  `post_with_retry` (unchanged behavior) and a new `get_with_retry`; all 6 `list_models()`
  functions now route through it. 2 new regression tests proving retry actually engages.
- **API-006 fixed.** OpenRouter's and Ollama's `complete()` both called `response.json()`
  inside a try block whose `except` clauses only caught `requests.exceptions.*` — a malformed/
  non-JSON body raised `json.JSONDecodeError` uncaught, crashing the turn instead of returning
  the normal `{"error": ...}` shape every other failure mode uses. OpenAI/Gemini/Claude/
  Cartogen already wrapped this in a broad `except Exception`, so only these 2 had the gap.
  Both now catch `ValueError` around the JSON-decode step specifically. 2 new regression tests
  proving each would have crashed before the fix.
- **QGIS-005 fixed.** The other `resolve_qgis_enum` call sites (`raster_tools.py`'s 4
  raster-styling enums used together in `apply_raster_stretch`, `styling_tools.py`'s
  classification-mode enum used in both `apply_graduated_style` call sites,
  `logistics_tools.py`'s `InvalidGeometryCheck` enum in `calculate_service_area`) were only
  None-safe by whatever each function's own broad `except Exception` happened to do with the
  resulting raw Python exception — not by an explicit check, same class of gap QGIS-004 fixed
  for `_VFW_NO_ERROR`. Each now has an explicit `if ... is None: return {"error": "Could not
  resolve ... in this QGIS version."}` guard, placed after cheaper validation so existing error
  precedence/ordering in each function is preserved. Today inert (every one of these enums
  resolves fine on both QGIS 3.x/4.x) — closes a correctness gap conditional on future QGIS API
  drift. 1 new regression test (`raster_tools.py`, mocking `_RBS_MIN=None`).
- **QGIS-009 fixed.** `_style_incident_layer`/`_style_named_point_layer` ran unguarded
  immediately after a brand-new shared layer (`Incidents`, or an `add_point_layer`-created
  layer) was added to the project — a styling failure (e.g. an unresolved enum, same class as
  QGIS-005 above) would raise past that point, meaning the actual point/feature the caller
  asked for never got added, even though the layer now exists in the project. Since styling
  only ever runs on first creation, every later call reusing that same layer would never retry
  it either — "permanently unstyled." Both call sites now wrap the styling call in `try/
  except`, printing a warning rather than blocking the tool's actual job (styling is cosmetic).
  2 new regression tests proving `add_incident_point`/`add_point_layer` still succeed when
  styling raises.
- **API-003 partially fixed.** Humanitarian/hazard `urllib` fetch tools had zero retry/backoff
  at all, unlike every LLM provider call. New shared `_urllib_retry.py` module
  (`urlopen_with_retry`, mirroring `providers/base.py`'s retry design: short exponential
  backoff, retries 429/5xx, never retries a permanent 4xx) wired into all 3
  `hazard_monitoring_tools.py` fetches (NASA FIRMS/EONET, GDACS) — these are the
  recurring-schedule-designed tools, the highest-value subset to fix first. 5 new tests for the
  helper + 1 integration test proving the retry actually engages for a real fetch tool. **Not
  done:** `humanitarian_tools.py`'s 12 remaining `urllib`/SSRF-opener call sites (geoBoundaries,
  HDX, building footprints, WorldPop, OSM) — left open deliberately: each has its own
  carefully-reasoned error-handling nuance (404-as-no-coverage, SSRF validation ordering,
  cache-key collision avoidance) built up over several audit passes, and touching all 12 in one
  pass risked more than the Low-severity finding justified in this session. A follow-up can
  wire the same `_urllib_retry.urlopen_with_retry` helper into them the same way.
- **API-001 reclassified from Open to Accepted Risk, not fixed.** `post_with_retry` retries a
  timed-out/5xx POST with no idempotency key — genuinely true, but there is no code fix
  available: none of the 5 LLM chat-completion APIs this plugin calls support an idempotency-
  key mechanism (confirmed by design — this is standard for LLM completion endpoints, not a
  gap specific to this codebase), and a chat-completion call has no server-side data-mutation
  side effect for a double-execution to corrupt — worst case is a duplicate response/double
  billing on a rare double-fire, not corrupted state. Leaving Open indefinitely with no path to
  "Fixed" was itself inaccurate bookkeeping; reclassified with this reasoning stated plainly.

**Left open, explicitly triaged (7 remaining, none release-blocking on their own):** API-007
(consent-notice UX/product decision — not mine to implement without direction on placement/
wording), API-010 (offline/DNS-error message polish — cosmetic, real but low value relative to
touching all 6 providers again), PERF-002 (algorithm change with correctness risk — needs a
native `processing.run` migration, a real design decision), QUAL-001/002/003 (explicitly
no-action-recommended by the auditing sub-agent itself — large-scope, low-value rewrites),
QUAL-006 (24-tool test-writing effort — real but sizable, a scope/priority call for Alaa on
which subset matters most).

### 2026-09-14 — remediation round 3 ("fix API-007 and API-010 too")

- **API-007 fixed.** No inline notice existed at the moment of file attachment telling the
  user their file's content (including raw image bytes, for an image) was about to be sent to
  whichever AI provider is currently configured. `chat_tab_widget.py::attach_file()` now shows
  a disclosure line naming the active provider (reusing `settings_dialog.py`'s existing
  `PROVIDERS` list as the single source of truth for display names, rather than duplicating
  it) as part of the existing "📎 Attaching..." message — before any file content is read or
  sent. Ollama gets a distinct, accurate note ("stays local... nothing is sent to a third
  party") rather than a generic third-party-sending warning that would be false for it.
  Live-verified via `python-qgis.bat` (13/13 passing, including 2 new tests exercising both
  the hosted-provider and local-Ollama wording against a real `QgsSettings` instance).
- **API-010 fixed.** Every provider's generic exception fallback surfaced whatever
  `requests`' own exception `__str__` produced — bounded (no raw traceback), but for the most
  common real case (no internet connection, DNS failure) that text is genuinely unhelpful
  (`"HTTPSConnectionPool(host=...): Max retries exceeded... Failed to establish a new
  connection: [Errno 11001] getaddrinfo failed"`). New shared `format_request_exception()`
  (`providers/base.py`) detects `requests.exceptions.ConnectionError`/`Timeout` specifically
  and gives a clear, actionable message ("could not reach the server -- check your internet
  connection" / "the request timed out"); every other exception type (a malformed-response
  `KeyError`/`ValueError`, etc.) passes through unchanged — this only replaces the one
  genuinely common, genuinely unhelpful case. Wired into all 6 providers' `complete()`/
  `list_models()`/`grounded_search()` generic exception handlers; Ollama's existing "(is Ollama
  running?)" hint is preserved, now appended to the clearer base message rather than replaced.
  3 new unit tests for the helper itself, full existing provider test suite (86 tests)
  re-verified green with no wording-dependent assertions broken.

Full suite after both fixes: 1595 tests, 0 failures, 14 skipped (2 more skips than round 2 —
the 2 new live-only API-007 tests, which only run under `python-qgis.bat`; live-verified
separately, 13/13 passing).

**Findings tally after round 3: 25 of 32 findings fixed/mitigated, 2 accepted risk, 5
genuinely untouched** (PERF-002, QUAL-001, QUAL-002, QUAL-003, QUAL-006 — all previously
triaged with reasoning; see the round-2 entry above).

### 2026-09-14 — remediation round 4 ("fix PERF-002 and QUAL-006 too")

- **PERF-002 fixed.** `optimal_hub_siting`/`location_allocation` compute a candidate×demand
  `QgsGeometry.distance()` cross product in pure Python with no upper bound. A genuine
  algorithm migration to `processing.run("native:distancematrix", ...)` was considered and
  deliberately NOT made — it would need live-QGIS verification that its distance semantics
  exactly match `QgsGeometry.distance()` (planar, not ellipsoidal) across every existing
  test's CRS assumptions, a real correctness-risk rewrite this audit's own conventions say
  not to make without that evidence. Instead: a hard cap on the candidate×demand pair count
  (`_MAX_HUB_SITING_PAIRS = 2,000,000`, a conservative estimate not a live-measured
  benchmark), matching the same "protective bound against unbounded, unattended cost"
  pattern already established in `scheduler.py`. Both tools now check
  `candidates.featureCount() × len(demand_geoms)` before the expensive loop and return a
  clear error naming the actual pair count if it's exceeded, instead of freezing the QGIS
  main thread. 1 new regression test proving the cap engages *before* iterating candidate
  features (not after). 3 existing tests updated to mock `.featureCount()` (previously
  unset, now required by the new check). Full suite 1590 → 1596, 0 failures.
- **QUAL-006 fully fixed.** All 24 of 169 tools with zero behavioral test coverage now have
  real tests — re-verified directly (the same extraction + grep method the original audit
  used) that 0 tools remain untested by name. 84 new tests added across 4 files:
  - **9 raster/classification tools** (`slope_analysis`, `aspect_analysis`,
    `zonal_statistics`, `raster_clip`, `unsupervised_classification`,
    `supervised_classification`, `mosaic_rasters`, `band_composite`, `pan_sharpening`,
    `tests/test_raster_tools.py`): the shared `_run_raster_and_add` helper 6 of these route
    through (never tested before, despite already backing `calculate_ndvi`/`ndwi`/`ndre`
    too) got its own thorough success/failure-path test suite; each tool's own test then
    only needs to prove its OWN wiring (which algorithm, which params) by mocking that
    helper directly — the same "test the shared mechanism once, test each caller's wiring
    separately" split `_run_and_add`'s existing test class already established for the
    vector side.
  - **15 vector/layer-management tools**: `rename_layer`/`toggle_visibility`,
    `intersect_layers`/`union_layers`, `dissolve_layer`/`merge_layers`,
    `reproject_layer`/`fix_geometries`, `select_by_attribute`/`get_feature_count`/
    `open_attribute_table`, `verify_crs_compatibility` (`tests/test_vector_tools_extended.py`,
    same "test the shared `_run_and_add` once, mock it per-tool" split); `load_workflow_preset`
    (`tests/test_new_tools.py` — also documents a real behavioral quirk found while writing
    the test: unlike most tools, this one has no explicit `QGIS_AVAILABLE` gate, so outside
    QGIS it returns "preset not found" rather than "QGIS not available"); `inspect_canvas_visually`
    (`tests/test_multimodal_remote_sensing.py`); `apply_heatmap_style`
    (`tests/test_styling_tools.py`, including a test documenting the tool's actual behavior of
    silently ignoring an unknown `field` name rather than erroring).

  Full suite 1596 → 1680, 0 failures throughout (re-run after each file's tests were added,
  not just once at the end).

### 2026-09-14 — parent verification of remediation round 4

- **Result:** Focused round-4/tool suites passed `473 tests, 0 failures, 3 skipped`; standalone provider tests passed `89/0`.
- **Blocker:** Canonical full discovery returned `1429 tests, 5 errors, 70 skipped`; every error was a `requests` import failure during aggregate collection/execution. The standalone interpreter and provider-only suite can import `requests`, so the aggregate import-order/environment discrepancy remains unresolved.
- **Status:** PERF-002 and QUAL-006 source/tests are present and focused-green, but the supplied `1680/0` full-suite claim is not parent-reproduced. Keep full-suite verification and release blocked until the environment discrepancy is resolved and the exact suite passes.

**Findings tally after round 4: 27 of 32 findings fixed/mitigated, 2 accepted risk, 3 genuinely untouched** (QUAL-001/002/003 — all explicitly no-action-recommended by the
original audit sub-agent; large-scope, low-value rewrites, deliberately not attempted).

**None of the above committed to git** — 34+ tracked files remain modified and the two audit
 documents remain untracked for Alaa's review.
