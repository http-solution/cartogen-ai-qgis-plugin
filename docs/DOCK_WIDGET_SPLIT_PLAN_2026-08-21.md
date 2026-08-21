# dock_widget.py Split: What Was Done, What Wasn't, and Why (2026-08-21)

Tracks the `docs/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md` §3.2 recommendation to split
`ui/dock_widget.py` (1,428 lines as of this doc, up from the review's noted "1,365+") along its
tab boundary, plus extracting `_read_attached_file()` into its own module. This is the last of
the four review-finding tasks from that round.

## Why this file gets a plan doc instead of just a diff

Every other fix in this round (`gemini.py`'s auth header, the destructive-tools gate additions,
usage-visibility wiring) could be verified the normal way: real test runs, real diffs, a full
suite pass in both trees. `ui/dock_widget.py` cannot be verified that way at all. It imports
`qgis.PyQt`/`qgis.core` unconditionally at module level with no `QGIS_AVAILABLE`-style fallback
(confirmed via `grep` — no other file in `agent/` or `ui/` besides `settings_dialog.py` and
`canvas_highlight.py` does this), so it cannot even be `import`ed in this sandbox, only
syntax-checked with `py_compile`. There are zero existing tests for it (`tests/test_dock_widget*.py`
does not exist), and it's a live, stateful `QDockWidget` with cross-tab signal wiring, a shared
`agent`/`task_manager` reference, and background-thread callbacks feeding it via `pyqtSignal`s. A
broken signal connection or a missing attribute reference in a class-split refactor would not show
up in any test run here — it would show up the next time a real person opens the plugin in QGIS.
That asymmetry (this sandbox can silently ship a broken UI with a fully green test suite) is
exactly the risk the review flagged when it called this "the largest, riskiest single change in
the whole findings list."

## What was done this round (low-risk, verified)

`_read_attached_file()` (the file-attachment reader: PDF/DOCX/CSV/XLSX/image/plain-text parsing)
had zero Qt/QGIS dependencies despite living inside `dock_widget.py` — it only uses `os`,
`pypdf`, `python-docx`, `pandas`, and `base64`. Extracted verbatim into `ui/attachments.py` as
`read_attached_file()`, imported back into `dock_widget.py` as `_read_attached_file` (single call
site, `ui/dock_widget.py`'s `_handle_attach_file`/`_analyze_file`, unchanged). This is genuinely
low-risk: a pure function move with an import added, verified by:
- `py_compile` on both the new module and the edited `dock_widget.py`.
- `tests/test_attachments.py` — 10 new tests (plain text, unreadable bytes, missing file, PNG/JPG
  base64 encoding, CSV including the cp1252-fallback path, XLSX, a real generated PDF, a real
  generated DOCX) — the **first test coverage this function has ever had**, made possible
  specifically by moving it out of a QGIS-only file.
- Full suite: 691 tests passing in both trees (was 681), same pre-known sandbox baseline
  unchanged.

## What was NOT done: splitting `QgisAiAgentDockWidget` itself

The class itself was left as one file. Based on a direct read of the current structure (not
assumed), here's what a real split would need to account for:

- **Three tabs, not two.** `self.tab_widget.addTab(...)` is called for Chat, "📋 Tasks & Memory",
  and "❓ Help" — the review's "ChatTabWidget/TasksTabWidget" framing undercounts by one; Help
  would need its own home too (or to stay inline, which is itself a design call).
- **Shared signals crossing the proposed boundary.** `statusSignal`, `usageSignal`,
  `receiveMessageSignal`, `toolStepSignal`, and `planUpdatedSignal` are all defined on the one
  `QDockWidget` class and connected once in `__init__`. `usage_label`/`status_label` live in the
  Chat tab but are updated from code paths (`_after_successful_response`, `_analyze_file`) that
  also touch Task-Manager-tab state (`_on_live_plan_updated`, `_apply_memory_filter`) in the same
  method. Splitting into separate widget classes means deciding whether these signals stay on a
  parent container (most likely correct) or get duplicated/proxied per-tab — a real design
  decision, not a mechanical extraction.
- **One shared `agent` reference and one `task_manager` connection.** `_send_message`,
  `_analyze_file`, and the Tasks tab's plan rendering all read from the same `self._agent_provider()`
  call and the same `agent.task_manager.plan_updated` connection
  (`getattr(self, "_connected_task_manager", None) is not agent.task_manager` — a de-dup guard
  that would need to move or be reasoned about carefully if ownership splits across classes).
- **No way to visually confirm the result.** Even a mechanically careful split could get a layout
  detail wrong (a widget added to the wrong parent, a stretch factor lost, the `QScrollArea`
  wrapping the Tasks tab — see `tasks_scroll` — not reapplied identically) that only shows up as a
  visibly broken dock panel, not a Python exception.

## Recommendation

Do this split in (or immediately test it in) a real QGIS session, not blind in this sandbox — the
same reasoning already applied elsewhere this round (the Gemini auth-header fix was verified
against Google's real docs before shipping instead of guessed; the destructive-tools gate
additions were tested against the real gate mechanism). A rough shape, for whenever that happens:

1. Keep `QgisAiAgentDockWidget` as the outer `QDockWidget` owning the shared signals, the `agent`
   reference, and `self.tab_widget`.
2. Extract the Chat tab's widget construction and handlers (`_send_message`, `_analyze_file`,
   `_analyze_image`, `_refresh_usage_label`, `_after_successful_response`, chip handling) into a
   `ChatTabWidget(QWidget)` that takes the parent dock (or its signals) at construction time.
3. Extract the Tasks & Memory tab similarly into `TasksTabWidget(QWidget)`.
4. Leave Help inline or give it its own trivial `HelpTabWidget` — it has no live state, lowest risk
   either way.
5. Add `tests/test_dock_widget_construction.py` that at minimum imports the module inside a
   `QGIS_AVAILABLE`-guarded skip (matching every other test file's pattern) so CI at least catches
   an import-time error, even without a full QGIS environment to click through.
6. Run `docs/RELEASE_SMOKE_TEST.md`'s full checklist against the split result before shipping —
   this is precisely the kind of change that checklist exists for.

Not attempted as part of this round.
