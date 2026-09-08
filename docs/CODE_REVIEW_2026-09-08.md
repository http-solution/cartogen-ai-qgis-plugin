# Cartogen AI (`cartogen-ai`) — Full Code Review, 2026-09-08

Independent 5-dimension review (mockups/incomplete UI, bugs, uncompleted work, security
vulnerabilities, GDPR compliance) of **this repo** (`C:\Cartogen-AI-Core\cartogen-ai`), now
confirmed as the canonical QGIS-plugin checkout (see this repo's own `CLAUDE.md`, added
2026-09-08, and `cartogen-ai-community/docs/CODE_REVIEW_2026-09-08.md` for the ancestor-repo
review this one follows and deliberately does not duplicate).

**Baseline at review time:** `main` @ `9fcc939`, working tree clean (only harmless deleted
`scratch_test_3w_*.csv` scratch artifacts, untouched), 1217 tests, 1 known DNS-dependent
failure, 0 errors — independently re-verified earlier today before committing the
temporal-dashboard feature (`609ee10`).

**Scope note:** this review does **not** re-report `BUG-2026-09-08-1` (account.py HTTPS-claim
gap) or `BUG-2026-09-08-2` (GDPR account-feature scope gap) as new findings — both were already
found in `cartogen-ai-community`'s review earlier today and independently re-confirmed to apply
here unchanged (ported into this repo's own `docs/BUG_TRACKER.md`/`docs/IMPLEMENTATION_TRACKER.md`
as part of commit `15ccb7d`). It also does not re-report the pre-existing `BUG-2026-09-05-2`
(`calculate_service_area` degenerate-network failure), already open in this repo's tracker
before today. This document covers what's *new* in a fresh pass over `cartogen-ai`'s own,
larger, more-evolved codebase (the 27-point architecture review's 15 commits, the temporal
dashboard feature, and everything else that has landed here since the two repos diverged).

---

## 1. Mockups / incomplete UI scan

Grepped `src/cartogen_ai` for `TODO`/`FIXME`/`XXX`, `NotImplementedError`, and
placeholder/stub/mock/dummy/"coming soon" language, outside tests.

**Clean.** Every `TODO` hit is the literal string `"TODO"` used as one value in a real task-status
enum (`task_manager.py`, `tasks_tab_widget.py`) — not an unfinished code marker. Every
placeholder/stub hit is either a Qt `setPlaceholderText(...)` call on a real, wired-up input
field (expected UI affordance, not incomplete UI), or documentation prose talking *about* the
concept of placeholder data (rules telling the model never to invent one). The one genuine stub
in the codebase, `agent/providers/cartogen.py` (the Cartogen-Hosted gateway client), is exactly
as documented: its own module docstring says "STUB, NOT WIRED IN," `GATEWAY_BASE_URL` is a
placeholder domain that resolves to nothing live, and the Settings dialog's own tooltip already
tells the user this option isn't usable yet. This is disclosed, not a hidden mockup — no action
needed beyond what's already tracked (see GDPR §3.3 in `docs/GDPR_COMPLIANCE_REVIEW.docx`, which
already flags this correctly as "not currently a processor").

No new mockup or incomplete-UI findings.

---

## 2. Bug scan

Directly inspected (not assumed to match the community-line review, since this repo's code has
materially changed since the two diverged):

- **`TurnTransactionLog` / undo-last-operation** (`agent/transactions.py`, new from the 27-point
  review's point 20): clean, small, and unusually candid about its own scope in its module
  docstring — it explicitly enumerates what it does *not* cover (MODIFY-call rollback, DELETE-call
  rollback, cross-turn undo) rather than silently overclaiming completeness. No bug found; the
  documented gaps are a known, already-flagged design limitation, not a defect.
- **`tool_operations.py` classification** (156 tools, hand-reviewed READ/CREATE/MODIFY/DELETE/
  PUBLISH taxonomy): spot-checked the destructive-capable tools (`remove_layer`, `load_project`)
  — both correctly classified `DELETE`. No misclassification found in the sample checked.
- **Destructive-action confirmation gate**: unchanged from the already-verified
  `cartogen-ai-community` logic (byte-identical inherited code) — still gates on
  `confirmed=False -> PREVIEW_REQUIRED` consistently across `remove_layer` and
  `undo_last_operation`.
- **`docs/MASTER_TASK_REGISTRY.md` "not yet committed" staleness (documentation hygiene, not a
  code bug):** this file's own running log contains numerous "Not yet committed — awaiting
  Baron's go-ahead" annotations (auth-system diagnostic, points 4/5/6/9/12/13/17/21 of the
  27-point review, `TASK-0008`, the Section IV/V humanitarian-standards gaps, etc.) that are
  **stale** — `git log`/`git status` confirm all of that code is already committed (the working
  tree is fully clean) under commit hashes the registry's prose was never updated to cite. The
  registry document even flags one instance of this itself mid-file ("the 'not yet committed'
  language... was never updated after that commit landed"), but the pattern recurs beyond that
  one correction. This is not a code defect and nothing here is actually lost or at risk — but
  it is a real, recurring documentation-hygiene gap worth naming, because a future session (or
  Baron) reading this registry at face value would wrongly believe real work is still sitting
  uncommitted when it is not. **Recommendation:** a pass to reconcile every "not yet committed"
  claim in this file against `git log` and either strike the phrase or correct it, so the
  registry's own "how to keep this current" instructions are actually being followed for this
  specific claim type.

No new functional bugs found beyond the documentation-hygiene item above and the three bugs
already tracked (`BUG-2026-09-08-1`, `BUG-2026-09-08-2`, `BUG-2026-09-05-2`).

---

## 3. Uncompleted work cross-check

`git status`/`git diff --stat` confirm the working tree is clean (only the harmless deleted
`scratch_test_3w_*.csv` files, pre-existing, untouched). The temporal-dashboard feature — the one
genuinely uncommitted, Baron-approved piece of work found at the start of today's reconciliation
— is now committed (`609ee10`). No other uncommitted code exists in this repo as of this review.

`docs/MASTER_TASK_REGISTRY.md`'s own queue still names two standing, unanswered *design*
decisions from earlier in the project (not code defects, not new): whether
`optimize_delivery_route`'s straight-line fallback should be blocked/upgraded, and which
incident-reporting-code vocabulary to standardize on. Both remain open exactly as before — not
re-litigated here, just noted as still-pending per the existing queue.

**Correction, 2026-09-08, later (during "solve the pending tasks" pass):** the paragraph above is wrong -- verified against a closer read of `docs/MASTER_TASK_REGISTRY.md`'s own Level 2 queue (not just the older 2026-09-03 journal entry that first raised these two items) plus the live code directly: **both decisions were already made by Baron on 2026-09-04 and are already implemented and committed.** `optimize_delivery_route` builds a real road-snapped route via `native:shortestpathpointtopoint` when given `road_network_layer`, and otherwise returns an explicit warning instead of a silent straight line (confirmed present in `agent/tools/logistics_tools.py`). `add_incident_point`/`add_point_layer` support both ACLED-style (`event_type`/`sub_event_type`) and IMSMA/IMAS-style (`hazard_type`/`contamination_status`) controlled fields via `_validate_incident_coding()` (confirmed present in `agent/tools/humanitarian_tools.py`). There is nothing left pending here -- this was an analysis error in the paragraph above, not a real open item; left uncorrected in place would have wasted Baron's attention re-deciding something already decided.

---

## 4. Security review

### 4.1 New CRITICAL finding — `execute_pyqgis_script` sandbox bypass via frame/traceback introspection

**Severity: CRITICAL.** The sandbox already has three prior, self-documented hardening sweeps
(2026-08-21, 2026-09-04, 2026-09-05) that each found and closed a real, live-confirmed bypass —
and each one explicitly says "this closes what was found, not a claim of completeness." This
review found and **live-reproduced** a fourth bypass, in the same spirit, that the existing
denylist (`_BLOCKED_MODULES`, `_BLOCKED_CALLS`, `_BLOCKED_DUNDER_ATTRS`, `_BLOCKED_QT_NAMES` in
`agent/tools/system_tools.py`) does not cover:

**What it is.** A model-generated script passed to `execute_pyqgis_script` can reach the *real*,
unrestricted `builtins` module — and from there, real `open`/`__import__`/anything else — entirely
without importing any blocked module and without referencing any blocked name, by walking Python
exception-traceback frame objects:

```python
def run():
    try:
        raise ValueError("trigger")
    except ValueError as e:
        tb = e.__traceback__
        f = tb.tb_frame
        while f.f_back is not None:
            f = f.f_back
        real_builtins = f.f_globals.get("__builtins__")
        ns = real_builtins if isinstance(real_builtins, dict) else real_builtins.__dict__
        real_open = ns["open"]
        real_open("/some/real/path", "w").write("arbitrary file write")
```

None of `__traceback__`, `tb_frame`, `f_back`, `f_globals`, `__builtins__` (used here as a string
dict key, not an `ast.Attribute` node), or `__dict__` appear anywhere in `_BLOCKED_DUNDER_ATTRS` —
the AST walk in `_validate_script_safety` has no rule that would ever flag this script. Once
`real_builtins`/`ns` is obtained, the restricted `_SAFE_BUILTINS` dict that `exec()` installs as
the script's `__builtins__` is fully bypassed: the script now holds a reference to the actual,
unrestricted `builtins` module, from which real `open`, real `__import__` (and therefore
`os`/`subprocess`/anything else, regardless of `_BLOCKED_MODULES`), `eval`, `exec`, etc. are all
directly retrievable by dict key — none of that retrieval touches a single name this file's
denylist inspects, since it's dict-key indexing, not `ast.Name`/`ast.Attribute` access to the
literal identifiers `open`/`eval`/`__import__`.

**Verified, not assumed.** Reproduced live in this session against an exact copy of this file's
`_BLOCKED_MODULES`/`_BLOCKED_CALLS`/`_BLOCKED_DUNDER_ATTRS`/`_SAFE_BUILTINS`/
`_validate_script_safety`/exec pattern (same restricted-builtins-dict, same `exec(script,
local_env)` call shape `execute_pyqgis_script` itself uses): `_validate_script_safety(EXPLOIT)`
returns `None` (script accepted, not rejected), and running it through the same `exec()` pattern
this tool uses successfully wrote a real file to disk from inside the restricted execution
context — full proof-of-concept, not a theoretical concern. (An earlier variant of this technique
using a suspended generator's `gi_frame` was also tried and confirmed *not* to work — a
generator's frame's `f_back` is `None` while suspended, only valid while actively executing — so
this finding is specifically the exception-traceback variant, which does not have that
limitation: a caught exception's traceback retains valid `f_back` references up the entire call
stack that was active at the moment it was raised, including the caller of `exec()` itself and
everything above it.)

**Impact.** This is full, unrestricted arbitrary code execution in the QGIS process — not
"just" file read/write. Once `real_builtins`/`__import__` is reachable, the script can `import
os`/`subprocess` and do anything the QGIS process's own OS user can do: read/write/delete any
file the user can access, launch arbitrary processes, open network connections, etc. — exactly
the class of risk `_BLOCKED_MODULES` exists to prevent, reached by a path that check never
inspects. Given `execute_pyqgis_script` is exposed to LLM-generated code (the model decides what
script to run, from chat), this is reachable by anything that can influence the model's output —
directly if the model is ever tricked (prompt injection from untrusted map data, an attached
file, or a compromised/malicious LLM response) into emitting this pattern.

**Recommended fix (short-term, matches this file's existing denylist-sweep pattern exactly):**
extend `_BLOCKED_DUNDER_ATTRS` (or a new, purpose-named set checked the same way) to include
frame- and traceback-introspection attribute names: `f_back`, `f_globals`, `f_locals`,
`f_builtins`, `f_code`, `gi_frame`, `cr_frame`, `ag_frame`, `tb_frame`, `tb_next`, and
`__traceback__` itself. As with every prior sweep, closing this specific technique is not a claim
that the denylist is now complete — the same "any attribute name this list hasn't happened to
enumerate yet" shape can recur (e.g., is there a way to reach a frame object without an exception
or a generator at all? — worth a follow-up adversarial pass once this fix lands). This finding is
itself the concrete argument for treating `docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md`
point 19's standing tiered-execution-model / allowlist-architecture question as more urgent, not
less — a denylist over Python's introspection surface is intrinsically a chase, and this is the
fourth distinct technique family found chasing it (module-name gaps, Qt-class gaps, `.format()`
string-traversal, now frame/traceback attribute gaps).

**Not fixed in this review** — recorded in `docs/BUG_TRACKER.md` below, awaiting Baron's
go-ahead to change code, per Hermes Charter Rule 8.

### 4.2 Everything else — re-verified, not assumed

- **`SECURITY.md`'s other documented protections** (SSRF guard, read-only SQL enforcement,
  encrypted-by-default credential storage with plaintext-fallback warning, destructive-action
  confirmation gates): spot-checked against current code, unchanged from the already-verified
  `cartogen-ai-community` state — SECURITY.md's own file:line references still resolve to the
  described behavior.
- **`account.py`/`account_dialog.py` HTTPS-claim gap** (`BUG-2026-09-08-1`): confirmed unchanged
  (`scheme not in {"http", "https"}`, `DEFAULT_ACCOUNT_BASE_URL = "http://localhost:3000"`) —
  already tracked, not re-reported as new.
- **Sandbox's own prior sweeps** (module-name blocklist, Qt-class blocklist, `.format()` string-
  traversal block): all still present and, as far as this review's own testing went, still
  effective against the specific techniques each one closed — this review did not find a way to
  reopen any of them.

No other new security findings.

---

## 5. GDPR compliance review

`docs/GDPR_COMPLIANCE_REVIEW.docx` in this repo is, byte-for-byte in content (confirmed by full
text extraction and comparison), **the same document** as `cartogen-ai-community`'s copy —
dated 2026-09-01, reviewed against commit `01d853f`/v1.4.4, never updated for anything that has
landed in either repo since (including this repo's own 15-commit architecture-review pass and
the temporal-dashboard feature). Findings F1-F13, verified against current `cartogen-ai` code:

- **F1 (CRITICAL, global-memory notes had no deletion path): confirmed fixed here.**
  `memory.py`'s `clear_global_notes()` exists (present via two paths — a native fix, commit
  `99079e3`, and the community-line fix merged in via `764afce` — both landed, no conflict),
  and `tasks_tab_widget.py` wires a "Clear Global Memory" button to it, explicitly citing the
  review's own R4 recommendation in a code comment.
- **F6 (project memory always-on, undisclosed, duplicated to a shareable sidecar file):
  confirmed still open** — `store_project_note()` still writes unconditionally to three
  locations (in-memory cache, sidecar SQLite, `.qgz` custom property) with no opt-in setting.
- **F7 (no structured JSON export for chat history/memory notes): confirmed still open** — no
  export path for either found in `export_tools.py` or `memory.py`.
- **F2 (no in-app privacy notice): confirmed still open** — no GDPR-relevant privacy-disclosure
  text found anywhere in `docs/` or `src/` outside the review document itself; the few
  "privacy"-matching hits in `settings_dialog.py`/`vector_tools.py`/`prompt_refiner.py` are
  unrelated to a data-use notice.
- **F3/F4/F5/F8/F9/F10/F11/F12/F13**: not independently re-verified line-by-line this pass (all
  are either organizational/documentation items outside code, or unchanged conditions already
  covered above) — no evidence found of any of these being newly closed or newly broken since
  the review document was written.
- **The two already-ported findings** (`BUG-2026-09-08-1`/`-2`, the account-feature HTTPS and
  GDPR-scope gaps): re-confirmed to apply, not re-reported as new here.

No new GDPR findings beyond what's already tracked. The one actionable observation: this
document itself is now over a week stale relative to both repos' own code (it still describes
`cartogen-ai-community` by name and an old commit), and neither repo's tracker currently has an
open item to refresh it — worth Baron's attention alongside the standing account-feature
decision, since the account feature and this document's staleness are really the same underlying
gap (GDPR review coverage not keeping pace with what's shipped).

---

## 6. Findings summary and fix plan

| ID | Severity | Dimension | Status | One-line description |
|---|---|---|---|---|
| **NEW-2026-09-08-1** | **CRITICAL** | Security | **New, open** | `execute_pyqgis_script` sandbox fully bypassable via exception-traceback frame-walking (`__traceback__`/`tb_frame`/`f_back`/`f_globals`) to reach real, unrestricted builtins — live PoC confirmed, arbitrary code execution. |
| BUG-2026-09-08-1 | High | Security | Open (already tracked) | `account.py`/`account_dialog.py` HTTPS-claim gap — plain `http` accepted despite UI claiming HTTPS-only. |
| BUG-2026-09-08-2 | High | GDPR | Open (already tracked) | Hosted-Account feature never assessed by `docs/GDPR_COMPLIANCE_REVIEW.docx`. |
| BUG-2026-09-05-2 | Medium | Bug | Open (pre-existing) | `calculate_service_area` fails on degenerate 1-2 segment synthetic networks. |
| **NEW-2026-09-08-2** | Low | Docs hygiene | New, open | `MASTER_TASK_REGISTRY.md` has multiple stale "not yet committed" claims for already-committed work. |

**Fix plan, in priority order:**

1. **NEW-2026-09-08-1 (sandbox bypass) — fix first, before anything else touches
   `execute_pyqgis_script`.** Add the frame/traceback attribute names listed in §4.1 to the
   denylist; add a regression test asserting the exact PoC script in this document is rejected
   or, if accepted by the AST check, fails to actually escape at `exec()` time. Given this is a
   full-RCE-class gap in a tool already exposed to LLM-generated code, this should not wait for a
   convenient batch of other changes.
2. **BUG-2026-09-08-1 (HTTPS-claim gap)** — reject non-`https` schemes in
   `normalize_account_base_url()` except for `localhost`/`127.0.0.1`; add a regression test.
   (Same fix already planned in the community-line review; applies identically here.)
3. **BUG-2026-09-08-2 / GDPR doc staleness** — Baron's decision needed: extend
   `docs/GDPR_COMPLIANCE_REVIEW.docx` to cover the Hosted-Account feature explicitly (email/
   password/session-cookie flow), or defer/disable that feature until it's covered. Worth doing
   in the same pass as refreshing the document's stale commit/repo references (§5).
4. **BUG-2026-09-05-2** — pre-existing, medium severity, low real-world likelihood (needs a
   1-2 segment degenerate network); no change to its priority from this review.
5. **NEW-2026-09-08-2 (registry staleness)** — mechanical documentation cleanup, no urgency;
   fold into the next general documentation pass.

None of the above is fixed in this review — all await Baron's explicit go-ahead per Hermes
Charter Rule 8.
