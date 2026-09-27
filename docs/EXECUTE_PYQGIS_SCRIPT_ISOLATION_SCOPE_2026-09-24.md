# `execute_pyqgis_script` process isolation — architecture scope

**Status: scoping document, not a build plan with a start date.** IMPLEMENTATION_TRACKER.md
§1.11 recorded process isolation as the decided real fix for this tool's sandbox, explicitly
deferred pending scope (2026-09-23). This document is that scoping pass — Alaa asked to have it
scoped, not built; nothing here has been started. A go-ahead on Phase 1 below is a separate,
later decision.

## 1. The problem, restated precisely

Every fix to date (`os`/`sys`/`cartogen_ai` blocks, `QgsProject.write()`/`authManager()` blocks,
the `type.__dict__` and frame-walking closures, the 2026-09-04/09-05 sweeps that found 24 more
bypasses across two sessions) closes one specific instance of the same shape of gap: "any
capability-bearing object reachable through an allowed name." That surface is structurally
unbounded for a denylist to enumerate — `SECURITY.md` itself has said so since before this
tool existed. Process isolation changes the *category* of fix: instead of trying to prove a
list of forbidden names is complete, the script runs somewhere that never has the dangerous
capability in the first place (no filesystem access outside a designated scratch area, no
network, no reference to this plugin's in-memory credential objects), regardless of what Python
trick a future session finds.

## 2. What the tool actually exposes today (narrows the design space)

Read directly from `system_tools.py`'s `execute_pyqgis_script`, not assumed:

```python
local_env = {
    'QgsProject': QgsProject, 'QgsVectorLayer': QgsVectorLayer,
    'QgsRasterLayer': QgsRasterLayer, 'QgsFeature': QgsFeature,
    'QgsGeometry': QgsGeometry, 'QgsPointXY': QgsPointXY,
    'QgsField': QgsField, 'QgsApplication': QgsApplication, 'QVariant': QVariant,
}
```

**No `iface`, no canvas, no active selection, no map-tool state.** A script today can only ever
reach `QgsProject.instance()` (the live project singleton) and construct plain geometry/vector
objects — it cannot read the active layer, the current canvas extent, or what's selected. This
matters directly for scoping: a fresh subprocess loading a *serialized copy* of the project loses
nothing a script could touch today **except one thing** — genuinely unsaved edits sitting in an
open `layer.startEditing()` session that haven't been committed yet. That is the one real fidelity
gap any isolation design has to either accept, work around, or explicitly flag to the model/user.

## 3. Three architecture paths, with a recommendation

### Path A — Serialize, run in a fresh subprocess, reload results (recommended)

1. Before dispatch, write the live project to a temp `.qgz` (or a narrower temp `.gpkg` covering
   only the layers the script's own source actually references, if the AST validator is extended
   to extract layer names — an optimization, not required for a first cut).
2. Launch a subprocess: a separate Python interpreter with its own `QgsApplication` (headless,
   `GUI=False` is sufficient here since no widget/canvas access is needed at all — see §2), no
   inherited file handles, a locked-down working directory (a fresh temp dir, deleted after),
   environment variables stripped to the minimum QGIS needs to start (no inherited
   `QGIS_AUTH_DB_URI` pointing at the real credential store, no plugin's own env vars).
3. The subprocess loads the temp project, runs the validated script (the existing AST
   `_validate_script_safety` check still runs — defense in depth, not replaced), captures
   `run()`'s return value and any layers it added/modified, writes them back to the temp project
   file, and exits.
4. The main process reloads the temp project's resulting layers into the live one (matching by
   name, same "new layer detected by diffing the live project's layer-id set" technique
   `transactions.py` already uses for undo tracking — reuse that, don't build a second mechanism).

**Cost:** real latency (full project serialize/deserialize + a second QGIS process cold-starting
per call). **Measured 2026-09-24 (Phase 0, see §8): ~5.0 s per call, not the 1-3 s originally
guessed here** — cold-spawn-per-call is likely too slow for interactive use as first written;
§8 recommends a persistent worker instead. **Fidelity gap:** the one named in §2 —
unsaved mid-edit-session state. **What it actually buys:** the subprocess genuinely has no
Python-level path to this plugin's `infrastructure/auth.py` credential objects (they're a
different process's memory entirely, not just an import block), no ability to reach this session's
live conversation history, and OS-level file/network restrictions on the subprocess (see Path C)
become meaningful instead of relying on a Python-level denylist alone.

### Path B — Curated proxy API (not recommended as "process isolation" — a different tool)

Give the subprocess a narrow, JSON-serializable data contract (e.g. "here are this layer's
features as GeoJSON, return features") instead of the real PyQGIS API surface. Real isolation,
but it stops being `execute_pyqgis_script` in any meaningful sense — it's a new, much narrower
geoprocessing tool that happens to also be isolated. Flagged here for completeness since it came
up in the earlier lay-out of this item, but **out of scope for this document**: it doesn't solve
"isolate the existing tool," it replaces it with a different one, which is a separate product
decision (would it deprecate `execute_pyqgis_script` entirely, or exist alongside it?) that
Path A doesn't force.

### Path C — OS-level sandboxing of the subprocess (a layer on top of A, not an alternative to it)

Once Path A's subprocess boundary exists, harden it further: on Windows (this project's primary
dev/target platform) that means an AppContainer/restricted-token process or a Job Object capping
filesystem/network/handle access; there is no Linux-equivalent seccomp story to reuse here since
Windows lacks that primitive. **This is real, separate scoping work with weaker, less-standard
Windows primitives than Linux offers** — flagged as a Phase 2+ hardening step, not something
Phase 1 should block on. Path A's subprocess boundary (separate memory space, stripped
environment, temp working directory) is a meaningful improvement over today's in-process denylist
on its own, even before any OS-level hardening lands on top of it.

**Recommendation: Path A first, Path C as a later hardening pass, Path B rejected as
out-of-scope (it's a different feature, not this one isolated).**

## 4. Phased plan (if/when this gets a go-ahead — not started)

**Phase 0 — benchmark, before committing to the design.** Measure real subprocess-cold-start +
project-serialize/deserialize overhead against a representative project (the existing
`docs/release_smoke_assets/inputs/smoke_start.qgz` fixture is a reasonable stand-in). If this
number is large enough to meaningfully change how the model is told to use the tool (e.g. "avoid
calling this in a tight loop"), that's a real product-facing cost worth knowing before Phase 1
starts, not discovered after.

**Phase 1 — the subprocess boundary itself, GEOMETRY/VECTOR scripts only.** Build the
serialize → subprocess → reload cycle for the existing `local_env` surface (§2) exactly as-is, no
new capabilities. Existing AST validator stays in place inside the subprocess (defense in depth).
Existing test suite (`test_new_tools.py`'s ~42 `execute_pyqgis_script` tests) needs a real design
decision here: do they keep mocking at the current level (fast, no subprocess spawned, tests the
validator/dispatch logic) with a *separate*, smaller set of real-subprocess integration tests
(slow, live-QGIS-only, matching this project's `qgis-live-tests` CI job convention), or does the
whole suite move to spawning real subprocesses (much slower CI, more faithful)? **This is a real
open question for whoever scopes the actual implementation, not decided here.**

**Phase 2 — raster support**, if Phase 1's fixture-based benchmark shows raster layers (larger,
slower to serialize) are common enough in real usage to justify the extra complexity of a
raster-aware temp-project builder (vs. just including whatever's already in the project
unconditionally, which is simpler but slower for large rasters).

**Phase 3 (optional, separate go-ahead) — Path C's OS-level hardening** on top of the now-working
Phase 1/2 subprocess boundary.

## 5. What changes, concretely (for whoever scopes the real implementation)

- `system_tools.py`: `execute_pyqgis_script` itself — the dispatch logic changes from
  `exec(script, local_env)` in-process to serialize → subprocess → reload. `_validate_script_safety`
  stays, unchanged, running inside the subprocess.
- New module (name TBD, e.g. `agent/services/script_isolation.py`): the actual subprocess
  management — spawn, temp-file lifecycle, timeout/kill handling (a hung script needs a hard
  process-level timeout, which this project doesn't currently need for the in-process version but
  absolutely needs once it's a separate process that could hang independently of the main QGIS
  event loop).
- `transactions.py`: the "diff live project layer-ids before/after" technique needs to run against
  the *reloaded* result, not the original in-process call — check this integrates cleanly with
  how `_real_execute_tool` currently wraps the call.
- Tests: per Phase 1's open question above.
- `SECURITY.md`: a new subsection once this ships, matching every prior sandbox-fix's convention
  of file:line evidence and a stated threat model — this doc is the scoping input for that, not
  a replacement for it.

## 6. Risks and open questions, stated plainly

- **Real latency cost, unmeasured.** Phase 0 exists specifically because this document cannot
  respons­ibly claim a number without running it against real QGIS.
- **Windows process-spawn reliability inside a QGIS plugin process** — spawning and reliably
  reaping a child process from inside a Qt application's event loop, on Windows specifically,
  has its own known rough edges (blocking the main thread while waiting, handle leaks on a
  killed/hung child) that this document flags but does not resolve.
- **The unsaved-mid-edit-session fidelity gap (§2)** needs an explicit decision: silently commit
  edits before serializing (surprising), block the call with an error telling the user to save
  first (safe, adds friction), or accept the gap and document it (matches this project's existing
  "document known limitations" pattern for F9's local-file erasure gap).
- **Test suite migration cost** (§4 Phase 1) is real engineering time, not a footnote.

## 7. What this document is not

Not a commitment to build this on any timeline. Not a claim that Path A is definitely the final
answer — it's the recommended starting point given what's actually exposed today (§2), open to
revision once Phase 0's real numbers exist. `execute_read_only_sql`'s separate, still-unverified
DB-level-enforcement question (§1.11's other open item) is untouched by this document — different
tool, different mechanism, needs a live PostGIS connection this sandbox still doesn't have.

## 8. Phase 0 results, 2026-09-24 (measured, not estimated)

Benchmark harness ran against real QGIS 4.2.2 via `python-qgis.bat` (Python 3.12.14), using
`docs/release_smoke_assets/inputs/smoke_start.qgz` (7 file-backed layers, small — see limits
below). The "child" was a real fresh headless `QgsApplication(GUI=False)` process that loaded a
serialized project copy, ran a trivial script, and exited. 8 iterations per scenario.

**Scenario 1 — cold subprocess per call (Path A as first written):**

| Phase | median | range |
|---|---|---|
| Serialize live project to `.qgz` | 0.053 s | 0.044-0.063 |
| Child spawn, end-to-end wall clock | **5.00 s** | 4.92-5.40 |
| — of which `from qgis.core import ...` | **3.48 s** | 3.42-3.93 |
| — of which `QgsApplication.initQgis()` | 0.35 s | 0.32-0.76 |
| — of which project read | 0.53 s | 0.44-0.66 |
| — of which the script itself | 0.002 s | — |
| Reload one result layer into live project | 0.030 s | 0.028-0.034 |
| **Total added overhead per call** | **5.09 s** | 5.00-5.50 |

In-process baseline (the real `execute_pyqgis_script`, trivial script, 50 runs): under 1 ms.
So cold-spawn-per-call adds roughly **five seconds to a call that costs effectively nothing
today**. `import qgis.core` alone is ~70% of it — fixed cost of any fresh QGIS process, not
something project size or script complexity changes.

**Scenario 2 — the memory-layer fidelity question. Confirmed a real gap, not a hypothetical:**
a live memory (scratch) layer with 1,000 features and another with 50,000 both serialized into
the `.qgz` without error, and the child loaded them as valid layers with **0 features**. QGIS
writes a memory layer's definition into a project file but not its data. This plugin's tools
produce memory layers constantly (`run_allowlisted_processing_algorithm` forces `memory:`
outputs by design, and most vector tools go through the same path), so a plain
serialize-the-project design would hand the isolated script a project whose scratch layers are
silently empty — the most likely-to-be-referenced layers, since they are the results of the
turn's earlier steps. Workaround cost measured: exporting a memory layer to a GPKG so its data
actually reaches the child took 0.15 s (1,000 features) and 0.53 s (50,000 features) per layer,
per call.

### What this changes in the recommendation

1. **Cold-spawn-per-call is not viable as written.** ~5 s per call is a large, visible cost for
   a tool a turn may call several times. Path A's boundary is still the right shape, but the
   child should be a **persistent worker**: started once (lazily, on first use), holding an
   initialized `QgsApplication`, receiving jobs over a pipe/socket. The 3.5 s import and 0.35 s
   init are then paid once per session. **Derived, not separately measured:** per-call cost
   would be roughly serialize (0.05) + project read (0.5) + reload (0.03) + IPC, i.e. on the
   order of ~0.6 s — a real prototype must confirm that before anyone relies on it. A persistent
   worker also brings new problems this document had not weighed: keeping the child's project
   state from leaking between calls, detecting/restarting a hung or crashed worker, and shutdown
   cleanup when QGIS closes.
2. **Memory layers must be handled explicitly in the serialize step** (export to a temp GPKG and
   repoint the layer, or pass their features another way). The design cannot be "write the
   project file and hand it over." The per-layer export cost above is added to every call in
   which scratch layers exist, and it grows with feature count.
3. **The unsaved-edit-session gap (§2) is now one of two known fidelity gaps, and the smaller
   one.** The memory-layer gap affects far more real calls.

### Limits of this benchmark — not to be over-read

- **Small, file-backed fixture.** Serialize (0.05 s) and project-read (0.5 s) will grow with
  layer count and with vector/raster size; a real analyst's project is likely larger. Only the
  spawn/import numbers are project-independent.
- **Run under `python-qgis.bat`, not inside a live QGIS desktop process.** Here
  `sys.executable` is `python3.exe`. **Inside a running QGIS desktop it is normally the QGIS
  executable itself (`qgis-bin.exe`), not a Python interpreter** — so the plugin cannot simply
  spawn `sys.executable` as the benchmark did. Locating the bundled Python interpreter reliably
  across QGIS 3.28 LTR and 4.x, on Windows, is an **unverified, real implementation risk**
  this benchmark could not test.
- **Warm OS file cache** across the 8 iterations; the first-ever spawn after boot may be slower.
- **No antivirus/EDR variation.** Endpoint scanning of freshly-spawned processes and DLL loads
  can add real latency on managed machines like a humanitarian org's laptops; not measured.
- **Trivial script.** Script time is not the bottleneck being measured here.

Harness committed at `tests/manual_isolation_bench/` (manual, live-QGIS-only, not collected by
`unittest`; run `python-qgis.bat tests/manual_isolation_bench/bench.py`). If Phase 1 is approved,
rerun it as part of that work against a larger real project.

## 9. Update, 2026-09-27 — the interpreter-location risk (§8) is resolved; not a guess

Alaa asked to scope this item further. §8's benchmark flagged one specific unverified risk as
blocking confidence in Path A: inside a real QGIS desktop session, `sys.executable` is the QGIS
binary itself (`qgis-bin.exe` on Windows), not a spawnable Python interpreter, and locating the
real one portably was untested here. Researched rather than guessed (no live QGIS desktop in this
sandbox to test against directly, but this is a documented, independently-confirmed problem with
real production solutions, not something that needs a live QGIS session to resolve):

- **Confirmed as a known, currently-unfixed upstream QGIS bug**, not specific to this plugin:
  [qgis/QGIS#45646](https://github.com/qgis/QGIS/issues/45646) ("`sys.executable` returns wrong
  value"). An upstream fix was attempted —
  [qgis/QGIS#67318](https://github.com/qgis/QGIS/pull/67318), adding a `qgis.utils.python_executable()`
  helper with per-platform lookup logic (checking paths next to `sys.prefix`/`sys.base_prefix`/
  `sys.exec_prefix`: OSGeo4W's `apps\PythonXXX` layout and conda-forge on Windows, a
  `PYTHONHOME`-setting wrapper next to the app bundle on macOS, `/bin/pythonX.Y` on Linux, where
  `sys.executable` is reportedly already correct) — but **that PR was closed without merging on
  2026-09-18** (auto-closed after 10 days of inactivity), so **no official helper exists in any
  shipped QGIS version, including the 4.2.2 this project targets.** A plugin doing its own process
  isolation cannot rely on QGIS to solve this; it has to carry its own lookup.
- **A real, shipped, MIT-licensed QGIS plugin already solves exactly this** for exactly this
  reason: [QPIP](https://github.com/opengisch/qpip) (`opengisch/qpip`, published on the official
  QGIS plugin repository, used to install pip dependencies for other plugins — a different problem
  than this tool's, but the identical sub-problem of "spawn a real Python process from inside a
  running QGIS") carries a `python_command()` method that cites the same upstream bug in its own
  source comment and does exactly the platform-specific lookup this project would need: on
  Windows, check `Path(sys.prefix) / "python.exe"` then `"python3.exe"` before falling back to
  `sys.executable`; on macOS, check `sys.prefix`, `sys.prefix / "bin"`, and
  `Path(sys.executable).parent` for `"python"`/`"python3"` (citing a second, separate report of the
  same bug on macOS,
  [opengisch/qpip#34](https://github.com/opengisch/qpip/issues/34#issuecomment-2995221985)) before
  falling back to `sys.executable`; on Linux, `sys.executable` is used directly (already correct
  there, matching the upstream PR's own claim). A conda install is detected first via
  `(Path(sys.prefix) / "conda-meta").exists()` and just uses the `"python"` shortcut on PATH.

**This resolves §8's "unverified, real implementation risk" as an engineering unknown** — there is
a concrete, working, real-world-proven algorithm to adopt (essentially QPIP's `python_command()`
almost verbatim, MIT-licensed so directly reusable), not a research gap Phase 1 would have to
solve from scratch. It does NOT change the Phase 0 latency numbers (§8) or the persistent-worker
recommendation derived from them, and it is still **not live-tested inside a real QGIS desktop
session by this project** — the algorithm is adopted on the strength of an independently-confirmed
upstream bug report plus a real shipped plugin's production code, not this project's own live
verification, so Phase 1 (if it goes ahead) should still confirm it against a real QGIS 4.2.2
desktop install on Windows before relying on it, not just trust this document.

**Also addressed here: a concrete recommendation for §6's unsaved-mid-edit-session fidelity gap**,
narrowing that open question from three options to one, for Alaa to accept or override rather than
deciding from a blank menu. Recommend the "block with an error" option: if the live project has any
layer in an active edit session (`layer.isEditable()` true, changes uncommitted) when
`execute_pyqgis_script` is called, refuse before serializing and tell the model/user to commit or
discard those edits first. This matches this project's own established convention elsewhere
(`buffer_analysis`'s `only_selected` fail-loudly-if-nothing-selected guard, the egress gate's
block-rather-than-guess default) of refusing outright rather than silently doing something the
caller didn't ask for — silently auto-committing a script author's in-progress edits is the kind of
surprising, hard-to-reverse behavior this codebase avoids elsewhere, and the alternative
(documenting the gap and shipping it silently) means a script could act on stale data with no
signal to the model that anything was omitted.

**Still fully open, unchanged by this update:** the Phase 1 go-ahead itself — this document
narrows two of the named open risks, it does not create new grounds for a yes. `execute_read_only_sql`'s
still-unverified DB-level enforcement (needs a live PostGIS connection, still unavailable in this
sandbox) is untouched by this update, same as every prior pass.
