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
- **Some newly-written files on this FUSE-mounted tree cannot be deleted by any method**
  (`rm`, `mv`, Python `os.remove`, waiting ~15s and retrying — all fail with
  `Operation not permitted`, confirmed live), though the same files can be freely
  overwritten/truncated. `df -T`/`stat -f` confirm this working tree is mounted via `fuse`/
  `fuseblk` (a Windows-host bridge), which is almost certainly the actual cause — this is a
  mount-layer quirk, not anything in this repo's code. Same root cause as the
  `scratch_test_*` entry above, but on 2026-08-21 it also hit git's own internals: a `git
  commit` failed partway through (unable to unlink its own temp object files) and left an
  orphaned, empty `.git/HEAD.lock`, which then blocked every subsequent commit attempt for
  the rest of that session since the lock file itself couldn't be removed either. If this
  happens again: don't fight it by hand-editing git internals — leave the pending change
  uncommitted in the working tree (git's own object store integrity is unaffected; `git
  fsck` still comes back clean) and let a future session or the other environment sharing
  this tree pick up the commit once the lock clears.

Current baseline: **691 tests, 1 known failure + 6 known errors, 0 real defects.** If a full
suite run ever shows a *different* failure/error count or a *different* failing test name,
that's real signal — investigate it, don't assume it's this same known baseline.

## Fixed (recent)

| ID | Found | Fixed | Severity | Summary |
|---|---|---|---|---|
| BUG-2026-08-21-1 | 2026-08-21 | v1.2.33 | medium | `route_optimization_prototype.py`: `ox.graph_from_bbox` called with bbox tuple in the wrong element order for the installed osmnx version (2.0.7 wants `(west, south, east, north)`, script passed `(north, south, east, west)`). |
| BUG-2026-08-21-2 | 2026-08-21 | v1.2.33 | low | `route_optimization_prototype.py`: `ox.distance.nearest_nodes()` requires `scikit-learn` on an unprojected graph, which wasn't in the script's documented `pip install` line. |
| BUG-2026-08-21-3 | 2026-08-21 | v1.2.29 | medium | `agent/tools/vector_tools.py`: `calculate_area`/`calculate_length` mutated the live layer's attribute table in place via the same `_add_calculated_field` primitive as `field_calculator`, but weren't gated behind the `confirmed=True` preview/confirm flow `field_calculator` already required for that same class of operation — a real inconsistency in the destructive-action safety gate, not just a missing feature. Both now follow `field_calculator`'s exact `PREVIEW_REQUIRED` pattern (verified still present in current code: `agent/tools/vector_tools.py` lines 1375/1403, `confirmed: bool = False` + the `PREVIEW_REQUIRED` branch). |
| BUG-2026-08-21-4 | 2026-08-21 | v1.2.28 | medium | `agent/providers/gemini.py`: `grounded_search()`/`list_models()` sent the API key as a `params={"key": ...}` query param instead of the `x-goog-api-key` header. |
| BUG-2026-08-21-5 | 2026-08-21 | v1.2.34 | medium | `plugin_upload.py` (both trees): the v1.2.34 release zip silently shipped 7 stray repo-root files it should never have included (6 `scratch_test_*` test artifacts + a leftover `.git_commit_msg.txt`), because `EXCLUDE_FILES` only did exact-name matching and neither file was expected to exist at build time. Added `EXCLUDE_FILE_PATTERNS` (fnmatch-based) covering `scratch_test_*`/`.git_commit_msg*`; both v1.2.34 zips rebuilt and re-verified clean (86 entries each, contamination check passed). |

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
