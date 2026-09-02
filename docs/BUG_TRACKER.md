# Cartogen AI — Bug Tracker

Lightweight, in-repo, git-versioned bug tracker. Created 2026-08-21 as part of setting up
ongoing implementation tracking — this is the first version, not a backfill of every bug ever
found (those are already recorded, resolved, in `CHANGELOG.md`'s per-version entries).

**Scope.** This file tracks real, currently-open code defects only — something that behaves
incorrectly against its own documented/intended behavior. It does NOT track: product/design
decisions awaiting a call (see `docs/IMPLEMENTATION_TRACKER.md`), unbuilt features or specs,
or this sandbox's inherent inability to run live QGIS (a standing environmental limitation,
not a bug — see `docs/RELEASE_SMOKE_TEST.md`).

**Format.** One entry per bug: ID, found date, severity, status, description, repro, fix status.
Severity is `critical` (data loss / security / crash) / `high` (wrong result, no workaround) /
`medium` (wrong result, has a workaround) / `low` (cosmetic, wording, non-blocking). Status is
`open` / `fixed-unverified` (fixed in code, not yet re-tested) / `fixed-verified` (fixed and
confirmed via a real test run or live check) / `wontfix` (with rationale).

---

## Open bugs

**None currently known.** Every real code defect found during this project's review history
(across all rounds through v1.2.33) was fixed in the same session it was found, verified via
a real test run or direct execution, and recorded in `CHANGELOG.md` — see that file for the
full fix history (e.g. the gemini.py header-auth fix in v1.2.28, the two real bugs found and
fixed in `route_optimization_prototype.py` in v1.2.33). None of that history is duplicated
here; this file starts tracking forward from today.

## Known non-bugs (do not re-file these)

Recorded here specifically so a future session doesn't rediscover these and mistake them for
new regressions — both are stable, understood, environment-specific artifacts, not code defects:

- **`test_is_safe_url_accepts_public_host` (1 failure)** — `tests/test_new_tools.py`. Fails
  because this sandbox's DNS/network egress can't resolve a public hostname the way a real
  deployment environment can. Not a code defect; the SSRF-guard logic itself is not in
  question here.
- **6 errors in `tests/test_reporting_tools.py`** — all `PermissionError` on `os.remove()`
  cleanup for files named `scratch_test_*.csv/.docx/.pdf` written to the repo root. This
  sandbox specifically cannot delete files matching that pattern once written (confirmed
  live, not assumed). Not a code defect — new tests should use `tempfile.mkdtemp()` /
  `shutil.rmtree()` instead of the `scratch_test_*` naming convention (see
  `tests/test_attachments.py` for the pattern that avoids this).
- **Files on this FUSE-mounted tree cannot be `rm`/`os.remove`'d** (confirmed live, repeatedly,
  `Operation not permitted`), though they can be freely overwritten/truncated. `df -T`/`stat -f`
  confirm this working tree is mounted via `fuse`/`fuseblk` (a Windows-host bridge), which is
  almost certainly the actual cause — a mount-layer quirk, not anything in this repo's code. Same
  root cause as the `scratch_test_*` entry above, but on 2026-08-21 it also hit git's own
  internals: a `git commit` failed partway through (unable to unlink its own temp object files)
  and left an orphaned, empty `.git/HEAD.lock`, which then blocked every subsequent commit attempt
  for the rest of that session since the lock file itself couldn't be removed either. If this
  happens again: don't fight it by hand-editing git internals directly against the real
  `.git/index` — use a scratch copy of the index (`GIT_INDEX_FILE=/tmp/scratch_index git add -A`
  etc., then `write-tree`/`commit-tree`/update the ref by hand, then copy the scratch index back
  over the real one) — see the commits from 2026-08-21 in this repo's history for the exact
  sequence used.
  **Correction, same day, later:** the above was true as originally investigated, but incomplete
  — it was written after only testing `rm` and a *cross-filesystem* `mv` (moving a file to a
  different mounted folder), both of which do fail. A **same-filesystem** `mv`/rename (moving a
  file to a new path still inside this same mounted tree) was not tested until fixing
  BUG-2026-08-21-6, and it **works**: `mv agent _legacy_stubs/agent_dir_test` succeeded outright.
  The actual restriction is on unlink (removing a path with nothing replacing it), not on rename —
  cross-filesystem `mv` fails for the same reason `rm` does, since without a hard-link-style
  rename available it has to fall back to copy-then-delete-source, and the delete half is exactly
  the unlink this mount blocks. Earlier work in this repo's history (`agent`/`ui`/
  `QGIS_AI_Agent_*.md` handling from before this correction) used the more conservative
  "overwrite content with a stub, `.gitignore` it, `git rm --cached` it" pattern instead of a true
  move, because that's what the incomplete finding above supported at the time — that work is not
  wrong, just more conservative than it needed to be. See `docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md`
  §3 for where this correction mattered in practice.

Current baseline (as originally recorded above): **691 tests, 1 known failure + 6 known errors,
0 real defects**, specific to the FUSE-mounted sandbox described above. If a full suite run in
that same environment ever shows a *different* failure/error count or a *different* failing
test name, that's real signal — investigate it, don't assume it's this same known baseline.

**2026-08-22, different environment (native Windows filesystem, not FUSE-mounted, `folium`
0.20.0 installed):** `python -m unittest discover -s tests -t . -p "test_*.py"` gives **691
tests, 0 failures, 0 errors, 1 skipped, in 13.874s.** Neither the `test_is_safe_url_accepts_public_host`
DNS-egress failure nor the 6 `PermissionError`-on-cleanup errors reproduce here — consistent
with both being properties of the old FUSE mount, not of the code. This does not supersede the
baseline above (that one is still accurate for that sandbox); it's a second, separately-tracked
baseline for whoever is running tests on a normal local machine, so a clean run there isn't
mistaken for something broken having been silently fixed.

## Fixed (recent)

| ID | Found | Fixed | Severity | Summary |
|---|---|---|---|---|
| BUG-2026-08-21-1 | 2026-08-21 | v1.2.33 | medium | `route_optimization_prototype.py`: `ox.graph_from_bbox` called with bbox tuple in the wrong element order for the installed osmnx version (2.0.7 wants `(west, south, east, north)`, script passed `(north, south, east, west)`). |
| BUG-2026-08-21-2 | 2026-08-21 | v1.2.33 | low | `route_optimization_prototype.py`: `ox.distance.nearest_nodes()` requires `scikit-learn` on an unprojected graph, which wasn't in the script's documented `pip install` line. |
| BUG-2026-08-21-3 | 2026-08-21 | v1.2.29 | medium | `agent/tools/vector_tools.py`: `calculate_area`/`calculate_length` mutated the live layer's attribute table in place via the same `_add_calculated_field` primitive as `field_calculator`, but weren't gated behind the `confirmed=True` preview/confirm flow `field_calculator` already required for that same class of operation — a real inconsistency in the destructive-action safety gate, not just a missing feature. Both now follow `field_calculator`'s exact `PREVIEW_REQUIRED` pattern (verified still present in current code: `agent/tools/vector_tools.py` lines 1375/1403, `confirmed: bool = False` + the `PREVIEW_REQUIRED` branch). |
| BUG-2026-08-21-4 | 2026-08-21 | v1.2.28 | medium | `agent/providers/gemini.py`: `grounded_search()`/`list_models()` sent the API key as a `params={"key": ...}` query param instead of the `x-goog-api-key` header. |
| BUG-2026-08-21-5 | 2026-08-21 | v1.2.34 | medium | `plugin_upload.py` (both trees): the v1.2.34 release zip silently shipped 7 stray repo-root files it should never have included (6 `scratch_test_*` test artifacts + a leftover `.git_commit_msg.txt`), because `EXCLUDE_FILES` only did exact-name matching and neither file was expected to exist at build time. Added `EXCLUDE_FILE_PATTERNS` (fnmatch-based) covering `scratch_test_*`/`.git_commit_msg*`; both v1.2.34 zips rebuilt and re-verified clean (86 entries each, contamination check passed). |
| BUG-2026-08-21-6 | 2026-08-21 | v1.4.1 | high | `cartogen_ai.py` (repo root, this repo only — introduced by the same-day namespace-package restructure, not present before it): its filename collided with the new `cartogen_ai.core` namespace package under `src/`. Since both the repo root and `src/` end up on `sys.path`, and a regular module anywhere on `sys.path` always wins over a namespace-package portion regardless of path order, every `from cartogen_ai.core.agent... import X` resolved to this file instead — confirmed via `python -m unittest discover`, which failed 31 tests with `ModuleNotFoundError: No module named 'qgis'` (this file's own unconditional `qgis.PyQt` import executing where the namespace package was expected). Fixed by renaming the file to `plugin_main.py` (pure rename, no behavior change) and updating `__init__.py`'s `classFactory()` to import from it; see `docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md` §3.1 for the full writeup. Re-verified: full `py_compile` and `python -m unittest discover` both clean after the fix (see that run's output for the exact pass count). |

| BUG-2026-09-02-1 | 2026-09-02 | unreleased (uncommitted) | high | Cross-checked the codebase against QGIS's own official Qt5/Qt6 plugin-migration documentation (`plugins.qgis.org/docs/migrate-qgis4`, `github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6`) ahead of a QGIS 4.2 demo. Found 5 unscoped-enum/removed-API usages that the wiki explicitly names as Qt6-breaking (QGIS 4 uses real Qt6/PyQt6, which requires scoped enum access): `Qt.UserRole` (6x, `ui/tasks_tab_widget.py`) needs `Qt.ItemDataRole.UserRole`; `QMessageBox.Yes`/`.No` (4x each, same file) need `QMessageBox.StandardButton.Yes`/`.No`; `QgsMapLayer.RasterLayer` (1x, `agent/tools/styling_tools.py`) needs `QgsMapLayer.LayerType.RasterLayer`; `QgsWkbTypes.PolygonGeometry`/`PointGeometry`/`LineGeometry` (11x across `agent/tools/logistics_tools.py`, `raster_tools.py`, `styling_tools.py`, `vector_tools.py`) need the `QgsWkbTypes.GeometryType.*` form; and `.exec_()` (1x, `ui/dock_widget.py`, removed outright in PyQt6, not just deprecated) needs `.exec()`. All replacements use the exact dual-compatible form the QGIS wiki documents, so QGIS 3.x (Qt5) support is unaffected. Fixed by scoping every flat reference; re-verified with `python -m py_compile` (clean) and the full suite (699 tests, same known 1-failure/6-error/14-skip sandbox baseline as before the change, 0 new failures) — but the `Qt.UserRole`/`QMessageBox.*` fix in `tasks_tab_widget.py` and the `.exec_()` fix in `dock_widget.py` have **zero automated test coverage** (these Qt-widget files import `qgis.PyQt`/`qgis.core` unconditionally and cannot be imported outside a real QGIS process, matching this project's existing convention for `dock_widget.py`'s tab-widget split) — status `fixed-unverified` for those two files specifically pending a real QGIS session check; `fixed-verified` for the `QgsMapLayer`/`QgsWkbTypes` fixes in `agent/tools/`, which the suite exercises via 3 updated stale mocks in `tests/test_styling_tools.py` (2 occurrences) and `tests/test_vector_tools_extended.py` (2 occurrences) that still set the pre-fix flat mock attribute. Also separately noted, NOT fixed: `QVariant.Double`/`.String`/`.Bool` used in several `QgsField()` constructor calls (`analysis_tools.py`, `imagery_extraction.py`, `vector_tools.py`) are deprecated since QGIS 3.38 in favor of `QMetaType.Type.*`, per `qgis.org/pyqgis/master/core/QgsField.html`'s own deprecation note — confirmed this still works without error on Qt6 (just prints a deprecation warning), so left as a lower-priority modernization item, not blocking today's demo. |
| BUG-2026-09-02-2 | 2026-09-02 | unreleased (uncommitted) | critical | Live QGIS 4.2 test (run by the user right after BUG-2026-09-02-1's fix was packaged) failed opening the dock panel at all: `AttributeError: type object 'Qt' has no attribute 'RightDockWidgetArea'`. This exposed that BUG-2026-09-02-1's sweep was NOT exhaustive -- it only checked the specific patterns named in QGIS's migration wiki, not every flat `Qt.*` enum access in the codebase. A full grep for every `Qt.<Attr>` usage surfaced 5 more real Qt6-breaking flat accesses, all fixed with the same scoped form: `Qt.RightDockWidgetArea`/`Qt.LeftDockWidgetArea` -> `Qt.DockWidgetArea.*` (`ui/dock_widget.py:48`, the confirmed crash site, hit on every dock-panel open); `Qt.RichText` -> `Qt.TextFormat.RichText` (`ui/tasks_tab_widget.py:231`); `Qt.Key_Return`/`Qt.Key_Enter` -> `Qt.Key.*` and `Qt.ShiftModifier` -> `Qt.KeyboardModifier.ShiftModifier` (`ui/chat_tab_widget.py:36`, the chat input's Enter-to-send handler); `Qt.BlockingQueuedConnection` -> `Qt.ConnectionType.BlockingQueuedConnection` (`agent/agent.py:95-96`, the tool-dispatch cross-thread connection every tool call goes through -- also updated that file's `QGIS_AVAILABLE=False` test-stub `Qt` class to expose both the flat and nested attribute so the existing mocked test path keeps working). All five are zero-automated-test-coverage call sites (three import `qgis.PyQt` unconditionally with no fallback; `agent.py`'s stub path never exercises the real `qgis.PyQt.Qt` object) -- status `fixed-unverified-pending-retest`: applied and syntax-checked, full suite re-verified clean (699 tests, 1 known failure, 0 errors -- better than the previously documented 6-error baseline, because delete permission granted earlier in this session let scratch-file cleanup succeed), zip rebuilt, but NOT yet re-confirmed inside a live QGIS 4.2 session. Given one exhaustive-looking sweep already missed 5 real breaks, treat BUG-2026-09-02-1 and this entry together as `needs a real QGIS 4.2 smoke test before the plugin is trusted for the 2026-09-02 presentation`, per `docs/RELEASE_SMOKE_TEST.md`. |
| BUG-2026-09-02-3 | 2026-09-02 | unreleased (uncommitted) | critical | Second live QGIS 4.2 crash the same afternoon, right after BUG-2026-09-02-2's fix: `AttributeError: type object 'QScrollArea' has no attribute 'NoFrame'`. Two prior sweeps both scoped their search to the `Qt` class itself (`Qt.<Attr>`); neither checked flat enum access on *other* Qt widget classes. Widened the sweep to every `Q<Class>.<Attr>` pattern across the whole plugin and cross-checked each one against what it actually is (static method vs. real flat enum member vs. a false-positive text match inside a comment/docstring -- `QFont.Italic` and `QgsLegendStyle.Item` in `agent/tools/layout_tools.py`'s comments are the latter, not code, left alone). Found and fixed 5 more real Qt6-breaking flat accesses: `QScrollArea.NoFrame` -> `QScrollArea.Shape.NoFrame` (`ui/dock_widget.py:114,121`, the confirmed crash, hit on every dock-panel open right after BUG-2026-09-02-2's dock-area fix); `QDialogButtonBox.Ok`/`.Cancel` -> `QDialogButtonBox.StandardButton.*` (`ui/settings_dialog.py:271`, the Settings dialog's OK/Cancel row) and `.Close` (`ui/account_dialog.py:76`); `QLineEdit.Password` -> `QLineEdit.EchoMode.Password` (API-key fields in `ui/settings_dialog.py:183` and `ui/account_dialog.py:44,48`); and 8 occurrences of `QPalette.Window`/`.AlternateBase`/`.Base`/`.WindowText`/`.Highlight`/`.HighlightedText`/`.Mid` -> `QPalette.ColorRole.*` plus `QPalette.Disabled` -> `QPalette.ColorGroup.Disabled`, in the live-theme-palette extraction duplicated identically in `ui/theme.py` and `ui/settings_dialog.py:_extract_theme_palette()` (feeds every dock/dialog stylesheet and the chat bubble colors -- would have broken theming on first dock-widget paint). `ui/account_dialog.py` and the `_extract_theme_palette` duplicate in `ui/settings_dialog.py` are part of the separate, pre-existing, not-yet-committed 'account' feature this session has no other context on -- fixed the Qt6 break there too since it ships in the packaged zip regardless of git commit state, but left everything else in those two spots untouched. All test-suite-invisible for the same reason as BUG-2026-09-02-1/-2 (unconditional `qgis.PyQt` imports); full suite re-verified clean (699 tests, same 1 known failure, 0 errors) and zip rebuilt. Separately: while widening the sweep, also found ~15 flat enum accesses on QGIS's own native classes (not generic Qt/PyQt6 widget classes) -- `QgsGraduatedSymbolRenderer.EqualInterval/Jenks/Quantile`, `QgsColorRampShader.Interpolated`, `QgsContrastEnhancement.StretchToMinimumMaximum`, `QgsTask.CanCancel`, `QgsUnitTypes.DistanceKilometers/LayoutMillimeters`, `QgsVectorFileWriter.NoError`, `QgsZonalStatistics.Mean/Sum`, `QgsRasterBandStats.Max/Min`, `QgsTextBackgroundSettings.ShapeRectangle` -- spread across `agent/tools/{layout,raster,vector,monitoring}_tools.py`. Spot-checked a sample against the live `qgis.org/pyqgis/master` docs rather than guessing: results were inconsistent -- `QgsVectorFileWriter.NoError` is explicitly documented as valid in BOTH flat and scoped form (no fix needed), while others' docs only show the scoped form without confirming whether flat access still works. Unlike the pure-PyQt6 cases above (verified hard breaks via QGIS's own Qt5/Qt6 migration wiki), QGIS's own enum modernization has been gradual and inconsistent, so a blanket scoped-rewrite here risks introducing new AttributeErrors by guessing wrong rather than fixing real ones. Deliberately NOT touched pending real verification -- these only fire when the agent actually invokes the specific tool that touches them (graduated-symbol styling, layout export, raster contrast stretch, color ramp shading, zonal statistics, unit conversion, vector file export, cancellable background tasks), not on every session like the three dock/panel/theme bugs above, so flagged as a known risk for whichever of those specific tools get demoed today rather than blocking the whole plugin. |
| BUG-2026-09-02-4 | 2026-09-02 | unreleased (uncommitted) | high | Live user feedback from an expert test session, three distinct issues: chat text unreadable in QGIS dark theme, the agent not visualizing mappable results or guessing a stale year instead of asking, and (confirmed via a live screenshot) markdown tables rendering illegibly. Root cause for the color issues: `ui/chat_formatting.py`'s `derive_bubble_colors()` already correctly derived bubble background/text from the live QGIS theme, but `render_markdown()` -- which renders the actual message content inside that bubble (code blocks, inline code, tables, blockquotes, `<hr>`) -- was completely disconnected from it, hardcoded to fixed light-theme colors (`#e8e8e8` code background with no explicit foreground, `#666`/`#999`/`#ddd`/`#ccc` borders and blockquote text). In dark theme this collapsed to near-invisible contrast -- confirmed live via a screenshot where Gemini had wrapped table cell values (layer names) in backtick code formatting, rendering as a near-white block (inherited near-white bubble text on a hardcoded light-grey `#e8e8e8` background) in an otherwise-readable dark-themed table. Fixed by threading the same theme-derived `colors` dict `_add_message` already builds through `render_markdown(text, colors)` and `_render_table(...)`, replacing every hardcoded color with `colors['text']`/`colors['subtle']`/`colors['border']` and a theme-derived code-chip background (`_blend_hex(agent_bg, text, 0.15)`); reproduced the exact reported table scenario against both the old and new code as a regression check (old: bare `#e8e8e8` background, no text color, i.e. exactly the reported white block; new: theme-derived `#313d5b`-class background with explicit matching text color) rather than trusting the fix without reproducing the failure first. Defaults to the same static light-theme fallback `derive_bubble_colors()` itself falls back to, so a bare `render_markdown(text)` call is unaffected. Fully unit-testable (this file deliberately has zero qgis/PyQt imports) -- added `test_dark_theme_colors_flow_into_code_and_table_and_blockquote` plus a default-fallback regression test; full suite re-verified clean (701 tests, same 1 known sandbox failure, 0 errors). For the middleware behavior issues (no fix verifiable from this sandbox -- these are LLM behavior, not code logic): added system-prompt rule 40 (default to creating a real map layer for mappable results instead of only describing them in chat text) and rule 41 (never silently fill in a guessed year/date for a tool parameter the user didn't mention -- `fetch_fts_funding_data`/`fetch_worldpop_population` already support omitting the year to auto-select the most recent; the bug was the model guessing a stale year itself instead of leaving it blank). Added 3 matching cases to `tests/manual_prompt_rule_evals.py` per this repo's own convention (a live-user-discovered failure mode becomes a rule, and the rule becomes a manual eval case) -- these need a real LLM+QGIS session to actually confirm the model's behavior changed, same limitation as every other prompt rule in this file. |
| BUG-2026-08-21-7 | 2026-08-21 | v1.4.1 | high | Two compounding issues found while re-verifying the suite after BUG-2026-08-21-6's fix, both specific to this repo's namespace-package restructure: (1) 15 `from agent...`/`import agent...`/`import ui...` statements survived the earlier bulk import-rewrite across `tests/test_providers.py`, `test_new_tools.py`, `test_export_tools.py`, `test_chat_persistence.py`, and `tests/manual_prompt_rule_evals.py` — all *function-local* imports (inside a test body or context manager), which the original rewrite pass (scoped to module-top-level import lines) didn't reach; each failed with `ModuleNotFoundError: No module named 'agent'`. Rewritten to `cartogen_ai.core.agent...`/`cartogen_ai.core.ui...`, matching the top-level rewrite already done elsewhere. (2) Separately, and more subtly: `python -m unittest discover -s tests -p "test_*.py"` — the exact command documented in `CLAUDE.md`, `README.md`, `CONTRIBUTING.md`, `.github/workflows/tests.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, and `SECURITY.md` before this fix — silently never executes `tests/__init__.py`'s `src/`-on-`sys.path` bootstrap, because without an explicit `-t`/`--top-level-directory`, `discover()` treats `-s tests` as *also* the top-level directory and imports each `test_*.py` as a bare top-level module rather than as a member of the `tests` package, so `tests/__init__.py` never runs as a package initializer. The fix is `-t .` (repository root as the true top-level directory): `python -m unittest discover -s tests -t . -p "test_*.py"`. Without it, every test importing `cartogen_ai.core.*` fails with `ModuleNotFoundError: No module named 'cartogen_ai'` even though the exact same import works fine outside unittest (e.g. via plain `python3 -c "..."`) — confirmed by direct comparison. All 6 documentation/CI locations updated to the `-t .` form. Re-verified after both fixes: `691 tests, 1 known failure + 6 known errors` — back to the pre-restructure baseline exactly. |

Full history before this file existed: see `CHANGELOG.md`, every version from v1.0.0 forward.

## Note on version numbering (added after a version mismatch was flagged)

The **source tree** (`metadata.txt`) is at v1.2.34 as of this line, but the **last packaged
release zip** in `dist/` is still `qgis_ai_assistant_v1.2.33.zip` — v1.2.34 was a docs-only bump
(creating this file and `IMPLEMENTATION_TRACKER.md`) and was never rebuilt into a zip. If you're
looking at an installed plugin or a shipped zip rather than this source tree directly, "v1.2.33"
is the accurate, currently-installable version — that's not a discrepancy in this file, it's
just source-vs-package lag. All bugs listed above were fixed at or before v1.2.33, so this
tracker's content is identical either way; nothing here is gated on the 1.2.34 bump specifically.

**Update (later same day):** the root tree's install-package name changed from `qgis_ai_assistant`
to `cartogen_ai_core` as part of a full internal rebrand (see `CHANGELOG.md`) — the zip filenames
above (`qgis_ai_assistant_v1.2.33.zip`, and the v1.2.34 zip built earlier that day) are frozen
historical artifacts under the old name, left as-is rather than renamed after the fact. Any zip
built from this point forward will be named `cartogen_ai_core_v*.zip` instead.

**Repo note:** the "Update (later same day)" paragraph above and the zip-name history further up
this file describe the old `qgis_ai_assistant`/`cartogen_ai_core` repo's own rebrand, carried over
here verbatim as accurate history — not a description of this repo. This repo's build produces
`cartogen_ai_v*.zip` (see `plugin_upload.py`'s `PLUGIN_NAME`), and it's a single tree, so there's
no second copy to propagate this file to.

## How to file a new bug

Add a row above (in "Open bugs," converting the "None currently known" line to a real table
once the first one is filed) with: ID (`BUG-YYYY-MM-DD-N`), what's wrong, how you know (a
failing test, a stack trace, a live QGIS session's actual behavior — not a hypothetical),
severity, and current status.
