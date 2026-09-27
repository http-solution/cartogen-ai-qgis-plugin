# `execute_pyqgis_script` — RestrictedPython as a defense-in-depth layer

**Status: scoping document, not a build plan with a start date.** `docs/IMPLEMENTATION_TRACKER.md`
§1.11 records process isolation (`docs/EXECUTE_PYQGIS_SCRIPT_ISOLATION_SCOPE_2026-09-24.md`) as the
decided real fix for this tool's sandbox. This document does **not** revisit that decision or
propose an alternative to it. It scopes a narrower question Alaa asked separately: whether
`RestrictedPython` (Zope Foundation, PyPI `RestrictedPython`, installed and tested live here at
**v8.5**, current as of this writing) is worth adding as a layer *underneath* the current
same-process AST-blocklist sandbox, on the same "defense in depth, not a replacement" basis
`system_tools.py`'s own `_SAFE_BUILTINS` comment already claims for itself. Nothing here has been
started; a go-ahead is a separate, later decision — same convention as the 2026-09-24 doc.

## 1. What was actually tested, not assumed

`pip install RestrictedPython` (v8.5) and its real `compile_restricted`/`safe_globals`/
`safer_getattr` were run directly against this exact codebase's own historical bypass reports
before writing any recommendation below. Three things confirmed live, not from documentation:

**(a) RestrictedPython's attribute guard does NOT catch this project's dominant bypass class.**
`safer_getattr` (the function substituted for every `.attr` access under `compile_restricted`)
blocks only: names starting with `_`, a small hardcoded `INSPECT_ATTRIBUTES` set (see (b)), and
`format`/`format_map` on strings/`Formatter`. It does **not** block by capability. Live-verified:

```python
from RestrictedPython import compile_restricted, safe_globals
src = 'import pathlib\npathlib.Path("/tmp/rp_test_pwn.txt").write_text("pwned")'
code = compile_restricted(src, '<test>', 'exec')
exec(code, dict(safe_globals))
# -> ImportError: __import__ not found
```

That specific probe was blocked, but only because `safe_globals`'s `__builtins__` has **no
`__import__` at all** — a blanket "no imports work unless you provide one" default, not a
capability check on `pathlib`. The 2026-09-04/09-05 bypass sweeps this project already ran and
fixed (`pathlib`, `dbm`, `logging`, `zipfile`, `io.open`, `tarfile`/`gzip`/`bz2`/`lzma`, `winreg`,
`linecache`/`filecmp`, `socketserver`/`poplib`/`imaplib`/`nntplib`/`xmlrpc`, `webbrowser`/`pydoc`,
`zipimport` — all plain, non-underscore method/attribute names) are **not** name patterns
`safer_getattr` would ever recognize. `_BLOCKED_MODULES` (the module-name denylist) remains
necessary regardless of whether RestrictedPython is adopted; nothing here replaces it.

**(b) RestrictedPython's attribute guard DOES fully subsume this project's frame-walking blocklist,
and is more complete.** `system_tools.py`'s `_BLOCKED_DUNDER_ATTRS` set was built the hard way —
found live, one technique at a time, across the 2026-09-08/09-20/09-23 sweeps (`__class__`,
`__bases__`, `__subclasses__`, `__mro__`, `__globals__`, `__builtins__`, `__reduce__`,
`__reduce_ex__`, `__code__`, `__closure__`, `__getattribute__`, `__dict__`, `__traceback__`, plus
the non-dunder frame names `f_back`/`f_globals`/`f_locals`/`f_builtins`/`f_code`/`gi_frame`/
`cr_frame`/`ag_frame`/`tb_frame`/`tb_next` added 2026-09-08 specifically because they *aren't*
dunder-shaped and so weren't caught by a naive "starts with `__`" rule either). RestrictedPython
closes both halves of that, out of the box, verified live:

```python
# Every double-underscore name is rejected at COMPILE TIME, not exec time:
compile_restricted('e.__traceback__', '<t>', 'exec')
# -> SyntaxError: "__traceback__" is an invalid attribute name because it starts with "_"

# The non-dunder frame/traceback/generator/coroutine names this project found by hand are
# ALSO already enumerated upstream, in transformer.py's INSPECT_ATTRIBUTES:
compile_restricted('def w(f):\n  while f.f_back: f = f.f_back\n  return f.f_globals',
                    '<t>', 'exec')
# -> SyntaxError: "f_back" is a restricted name ... / "f_globals" is a restricted name ...
```

`INSPECT_ATTRIBUTES` (`RestrictedPython/transformer.py`) contains `tb_frame`, `tb_next`, `f_back`,
`f_builtins`, `f_code`, `f_generator`, `f_globals`, `f_locals`, `f_trace`, `co_code`, `gi_frame`,
`gi_code`, `gi_yieldfrom`, `cr_await`, `cr_frame`, `cr_code`, `cr_origin`, `ag_await`, `ag_frame`,
`ag_code` — a strict superset of this project's own 10-name hand list (missing `f_trace`,
`co_code`, `cr_await`, `cr_origin`, `ag_await`, none of which this project has been live-bitten by
yet, consistent with "closes the specific technique found this review, not a claim of
completeness" being this file's own stated pattern every time). And it's maintained upstream by a
project whose whole purpose is tracking exactly this attack surface, rather than by this project
re-discovering each variant independently through its own adversarial testing.

**(c) `format`/`format_map` hardening is redundant with existing code, not new.**
`_BLOCKED_DUNDER_ATTRS` already blocks `format`/`format_map` unconditionally (any object, any
call); `safer_getattr` only restricts them on `str`/`Formatter`. Adopting RestrictedPython would
not need to keep this project's blanket version *and* gain nothing narrower — no functional
difference either way, since blocking it unconditionally already covers the RestrictedPython-scoped
case.

## 2. What this narrows the recommendation to

RestrictedPython's real, verified value here is specific: it replaces the **frame/traceback/
generator/coroutine introspection half** of `_BLOCKED_DUNDER_ATTRS` (16 of its ~30 entries) with a
maintained-upstream mechanism that is provably at least as complete today and — the actual
argument for adopting it — gets more complete for free as RestrictedPython's own maintainers find
new variants, instead of this project needing another live adversarial sweep each time. It does
**not** touch, replace, or reduce the need for:

- `_BLOCKED_MODULES` (module-import denylist) — unaffected; see (a) above.
- `_BLOCKED_QT_NAMES` (dangerous Qt classes pulled from an otherwise-legitimate module) —
  unaffected; this is a "which names are safe to import from module X" question, not an
  attribute-access-after-import question.
- `os`/`sys`/`modules`/`write`/`authManager` in `_BLOCKED_DUNDER_ATTRS` — these are plain
  capability-bearing attribute names (not underscore-prefixed), the same class as (a); still need
  hand curation regardless.
- The `_validate_script_safety` AST walk itself, or `_SAFE_BUILTINS` — see §3 for why swapping the
  builtins dict is a bigger, separate decision from adopting the attribute guard.

## 3. Two integration shapes, with a recommendation

### Shape A — Adopt only `safer_getattr` + `INSPECT_ATTRIBUTES` as the `_getattr_` hook (recommended)

`execute_pyqgis_script`'s current mechanism is a **denylist checked before `exec()` runs**
(`_validate_script_safety`'s `ast.walk`), not a compile-time AST transform. Fully switching to
`compile_restricted` would mean compiling the script through RestrictedPython's own transformer
instead of `ast.parse` + plain `exec` — a bigger change (see Shape B) than this project needs to
get (b)'s benefit.

The narrower move: keep `_validate_script_safety` exactly as-is (it still needs to exist regardless,
per §2), but add `from RestrictedPython.Guards import safer_getattr, INSPECT_ATTRIBUTES` and:

1. Fold `INSPECT_ATTRIBUTES` into `_BLOCKED_DUNDER_ATTRS` directly (a set union — one line), so the
   existing `ast.Attribute` walk in `_validate_script_safety` starts catching the upstream-tracked
   superset immediately, with **zero change to the exec-time mechanism.** This alone captures most
   of (b)'s value with the least risk, and is a genuinely mechanical, low-risk fix in this project's
   own stated sense (CLAUDE.md: "an obviously dead branch — fix directly").
2. Separately (a real decision, not mechanical): replace the current plain-`getattr`-based runtime
   attribute access inside the exec environment with `safer_getattr`, so a NEW dunder name nobody
   has thought to block yet is caught automatically at exec time too, not just for the names already
   enumerated in step 1. This requires actually wiring `_getattr_` into the exec globals the way
   RestrictedPython expects (it substitutes `obj.attr` for `_getattr_(obj, 'attr')` at compile time
   via its own transformer — `execute_pyqgis_script` does not currently compile through that
   transformer, so this step needs either (i) adopting `compile_restricted` for real (Shape B), or
   (ii) writing a much smaller custom AST transform that only rewrites `ast.Attribute` nodes to call
   a guard function, reusing `safer_getattr` as that function without adopting the rest of
   RestrictedPython's transform. (ii) is untested here and is real, scoped work, not a one-liner —
   flagged, not sized.

**Recommendation: do step 1 now** (mechanical, verified, low-risk, closes real ground the current
list is missing today per §1(b)). **Defer step 2** pending a decision on whether (ii)'s custom
partial-transform is worth building, or whether it's cleaner to fold this into Shape B once/if
process isolation (§1.11's Path A) is actually built — a subprocess architecture is a natural point
to also switch the in-subprocess exec environment to real `compile_restricted`, since at that point
the subprocess boundary is already doing the heavy lifting and RestrictedPython becomes a genuine
defense-in-depth layer *underneath* it, exactly the shape §1.11's isolation doc already described
("the existing AST validator still runs — defense in depth, not replaced").

### Shape B — Adopt `compile_restricted` as the actual compile step (not recommended now)

Replace `ast.parse(script)` + `exec(compiled, restricted_globals)` with
`compile_restricted(script, '<script>', 'exec')` + `exec(code, safe_globals)` (or a
`system_tools.py`-specific globals dict built the same way, keeping `QgsProject`/`QgsVectorLayer`/
etc. injected as today). This gets `safer_getattr`/`INSPECT_ATTRIBUTES` automatically without a
custom transform, plus RestrictedPython's write-guard (`guarded_setattr`) and iteration guards for
free.

**Real costs, not yet resolved:**
- RestrictedPython's transform also restricts syntax this project's scripts may currently use
  without issue (e.g. `print` requires an explicitly-provided `_print_` in globals — confirmed live
  above; this project's own `_SAFE_BUILTINS` already includes real `print`, so scripts using it
  today would break under a naive Shape-B swap unless a `PrintCollector`-equivalent is wired in).
  A full compatibility pass against real model-generated scripts (not just the adversarial probes
  in §1) has not been done.
- `_SAFE_BUILTINS` (this project's own allowlist dict) and RestrictedPython's `safe_builtins` are
  two independently-built allowlists with real differences (e.g. this project's list includes
  `hasattr`, `format`, `super`, `classmethod`, `staticmethod`, `property`, none of which are in
  RestrictedPython's `safe_builtins`) — reconciling them is a real per-name review, not a drop-in
  swap, and a wrong call either direction either breaks legitimate scripts or reopens a name this
  project deliberately blocked.
- No import-allowlisting story exists yet for the `qgis.PyQt.QtCore`-style imports this tool's own
  prompt guidance actively tells the model to write (§2 of this doc) — `safe_globals` has no
  `__import__` at all, so Shape B as tested above blocks ALL imports, which is stricter than this
  tool needs. A working Shape B needs a custom `__import__` that allowlists by prefix
  (`qgis.`/`processing`/`PyQt`/a short safe-stdlib list) — unbuilt, unscoped in more detail than
  this paragraph.

**Recommendation: not now.** This is real, separable work with its own compatibility and
allowlist-design questions, better done once (or if) process isolation actually lands, per Shape
A's closing paragraph — building it twice (once now for the current in-process sandbox, again for
whatever the subprocess's own exec environment ends up being) is the outcome to avoid.

## 4. What this document is not

Not a claim that adopting either shape closes the "structurally unbounded" problem `_BLOCKED_MODULES`
and `_BLOCKED_QT_NAMES` still have — §1.11's own diagnosis of that stands unchanged, and process
isolation remains the decided fix for it. This document is scoped narrowly to one already-identified
sub-problem (frame/introspection attribute access) that has a real, verified, upstream-maintained
answer available today, cheaply, as defense in depth.

## 5. Next step, if there's a go-ahead

Shape A step 1 (fold `INSPECT_ATTRIBUTES` into `_BLOCKED_DUNDER_ATTRS`) is small enough to do and
verify in the same session as a go-ahead: add the import, union the sets, add a test asserting each
of RestrictedPython's names not already in this project's list (`f_trace`, `co_code`, `cr_await`,
`cr_origin`, `ag_await`) is now blocked, run the full suite, done. Shape A step 2 and Shape B both
need their own separate scoping pass first (the open questions in §3 are real, not rhetorical) —
not sized here.
