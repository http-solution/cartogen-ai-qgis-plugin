# Security

This document describes Cartogen AI's threat model, the protections actually
implemented in the codebase, what was adversarially tested (with real, confirmed
findings — not just a list of intentions), and the limitations that are honestly
still open. It is written to be checked against the code, not trusted on its own —
file:line references are given throughout so any claim here can be verified directly.

<details>
<summary><strong>Table of contents</strong></summary>

- [Threat model](#threat-model)
- [Protections](#protections)
  - [1. PyQGIS script execution sandbox](#1-pyqgis-script-execution-sandbox)
  - [1a. Allow-listed Processing algorithm runner — a Tier 2 alternative to the sandbox](#1a-allow-listed-processing-algorithm-runner--a-tier-2-alternative-to-the-sandbox)
  - [2. Read-only SQL enforcement](#2-read-only-sql-enforcement)
  - [3. SSRF guard on fetched URLs](#3-ssrf-guard-on-fetched-urls)
  - [4. Credential storage](#4-credential-storage)
  - [5. Destructive-action confirmation gate](#5-destructive-action-confirmation-gate)
  - [6. Prompt-injection guidance](#6-prompt-injection-guidance)
  - [7. Chat history persistence is opt-in](#7-chat-history-persistence-is-opt-in)
  - [8. Recurring monitoring scheduler](#8-recurring-monitoring-scheduler)
  - [9. Prompt Refinement Layer — external-call awareness](#9-prompt-refinement-layer--external-call-awareness)
- [Testing performed](#testing-performed)
- [Data protection (recommendation, not yet assessed)](#data-protection-recommendation-not-yet-assessed)
  - [International transfer mechanisms, by provider](#international-transfer-mechanisms-by-provider-f3-researched-2026-09-01)
  - [Remediation, 2026-09-01](#remediation-2026-09-01-the-reviews-4-high-findings)
  - [Remediation, 2026-09-11](#remediation-2026-09-11-f6f7f8-part-of-the-v170-securitylogistics-release)
- [Known limitations (accepted risk, not fixed)](#known-limitations-accepted-risk-not-fixed)
- [Licensing note](#licensing-note)

</details>

## Threat model

The plugin runs an LLM in a tool-calling loop against a real QGIS project. Two things
in that loop are **untrusted input**, not just data:

1. **The LLM's own output.** A cloud provider response, a prompt-injected instruction
   hidden inside fetched web/OSM/HDX content, or simply a model mistake can all result
   in a tool call with attacker-influenced arguments — a script to execute, a URL to
   fetch, a SQL query to run.
2. **Content fetched from the internet** (`search_web`, `fetch_osm_features`,
   `search_hdx_datasets`, `fetch_geoboundaries`, `fetch_fts_funding_data`,
   `fetch_nasa_eonet_events`, `fetch_gdacs_disaster_alerts`) that gets
   fed back into the model's context and could contain text written to look like
   instructions.

The user running QGIS is trusted (they can already run arbitrary Python in the QGIS
Python console with no plugin involved at all). The protections below exist for the
case where the *model* — not the user — ends up driving a dangerous action, whether
through prompt injection, hallucination, or a compromised/malicious model provider.

## Protections

### 1. PyQGIS script execution sandbox
`agent/tools/system_tools.py` — `execute_pyqgis_script` runs model-generated Python
directly in the QGIS process. Two independent layers:

- **Static AST validation** (`_validate_script_safety`) rejects the script *before* it
  runs if it imports a blocked module, references a blocked builtin (even without
  calling it — `x = eval; x(...)` is caught the same as `eval(...)`), or accesses a
  blocked attribute name (the classic `().__class__.__bases__[0].__subclasses__()`
  escape chain, and `.format`/`.format_map` — see Testing below for why those two
  methods specifically are blocked). This also covers specific dangerous **classes**
  imported from an otherwise-legitimate module (`_BLOCKED_QT_NAMES`) — blocking a
  module wholesale doesn't work for `qgis.PyQt.QtCore`, since `QVariant`/`QColor`/
  signals from that same module are required for normal PyQGIS scripts, but
  `QFile`/`QDir`/`QDirIterator`/`QProcess`/`QNetworkAccessManager`/`QSettings`/
  `QLibrary`/`QPluginLoader`/`QDesktopServices` living in that same module family
  provide file read, filesystem browsing, process launch, raw network I/O, registry
  access, dynamic-library loading, and local-executable launch respectively — checked
  at the `ImportFrom` alias itself (not just later usage), so `from
  qgis.PyQt.QtCore import QFile as F` is caught too, not just a literal `QFile(...)`
  call.
- **Restricted execution builtins** (`_SAFE_BUILTINS`) — even if a future AST bypass
  is found, the script's `__builtins__` is a curated allowlist (~50 safe names), not
  the real Python builtins, so `eval`/`open`/`getattr`/etc. simply aren't resolvable
  names inside the script's scope regardless of the AST layer.

Blocked modules (`_BLOCKED_MODULES`): `os`, `subprocess`, `shutil`, `sys`, `socket`,
`ctypes`, `importlib`, `pty`, `multiprocessing`, `pip`, `urllib`, `requests`, `http`,
`ftplib`, `smtplib`, `pickle`, `codecs`, `base64`, `sqlite3`, `tempfile`, `platform`,
`threading`, `asyncio`, `pdb`, `code`, `marshal`, `shelve`, `builtins`, `gc`,
`inspect`, `types`, `copyreg`, `runpy`, `pathlib`, `dbm`, `logging`, `zipfile` (the last
four added 2026-09-04 after live-reproducing that each writes a real file to disk via a
plain method call -- `Path.write_text()`, `dbm.open(path, 'c')`,
`logging.FileHandler(path)`, `zipfile.ZipFile(path, 'w')` -- none of which is the `open`
builtin name already blocked above, so none tripped this list before that date), plus
`io`, `tarfile`, `gzip`, `bz2`, `lzma`, `winreg`, `linecache`, `filecmp`,
`socketserver`, `poplib`, `imaplib`, `nntplib`, `xmlrpc`, `webbrowser`, `pydoc`,
`zipimport`, `venv`, `mmap` (added 2026-09-05 in a second, broader sweep using the same
live-reproduction technique: `io.open` is the same function object as the builtin
`open`, just reached by attribute instead of bare name; `tarfile`/`gzip`/`bz2`/`lzma`
are the same archive/compression-writer file-write shape as `zipfile` above;
`winreg.CreateKey`/`SetValueEx` wrote a real registry key; `linecache.getline` read a
real file with no `open` name involved, confirming arbitrary file *read* has the same
blind spot as write; `socketserver`/`poplib`/`imaplib`/`nntplib`/`xmlrpc` are the same
network-client category as `ftplib`/`smtplib` above; `webbrowser`/`pydoc` can launch an
external program the same way `QDesktopServices` below can; `zipimport` loads code from
a zip file the same way `importlib`/`runpy` above can).

Blocked Qt classes regardless of which allowed submodule they're imported from
(`_BLOCKED_QT_NAMES`): `QFile`, `QSaveFile`, `QTemporaryFile`, `QDir`,
`QDirIterator`, `QFileInfo`, `QFileSystemWatcher`, `QProcess`,
`QProcessEnvironment`, `QNetworkAccessManager`, `QNetworkRequest`, `QNetworkReply`,
`QTcpSocket`, `QUdpSocket`, `QLocalSocket`, `QSslSocket`, `QSettings`, `QLibrary`,
`QPluginLoader`, `QDesktopServices`.

This is **defense in depth against known techniques, not a formally proven sandbox**.
Executing arbitrary attacker-influenced Python via `exec()` inside the host process is
inherently a harder security boundary than OS-level process isolation would be; a
determined attacker with unlimited creativity may find another gap. Treat this as
raising the bar significantly, not as an absolute guarantee — see Limitations below.

### 1a. Allow-listed Processing algorithm runner — a Tier 2 alternative to the sandbox

`agent/tools/processing_allowlist_tools.py` — `run_allowlisted_processing_algorithm`,
added 2026-09-11 as part of the v1.7.0 release, is a real slice of the tiered
allow-list architecture point 19 of
`docs/QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md` describes (declarative tools
/ allow-listed Processing algorithms / approved internal functions / PyQGIS as a rare
last resort), sitting between this codebase's ~150 declarative tools and
`execute_pyqgis_script`'s sandbox above. It runs exactly one Processing algorithm from
a hard-coded allow-list (`agent/tools/_processing_allowlist.py`, 36 algorithm ids,
every one derived from this codebase's own existing `processing.run()` call sites, not
a new judgment call about what's "safe") with a caller-supplied flat params dict —
**it never executes Python code at all**, so there is no `eval`/`exec`/denylist
surface to sandbox in the first place. Three narrower protections on top of the
allow-list itself:

- An unlisted `alg_id` is rejected before `processing.run()` is ever called.
- Any params key matching `OUTPUT`/`OUTPUT_LINES` (case-insensitive) is forced to
  `"memory:"` regardless of what value is supplied — confirmed live that a caller
  could otherwise direct output to an arbitrary file path — and one is injected if
  omitted entirely (confirmed live that Processing does not default a missing
  `OUTPUT` itself, it fails outright).
- Only JSON-primitive param values are ever accepted (strings, numbers, booleans) —
  a string matching a currently-loaded layer's name is resolved to that layer object,
  everything else passes through literally; there is no path for a nested object or
  code to reach `processing.run()`.

`execute_pyqgis_script`'s own description now names this tool as the preferred path
when a single Processing algorithm covers the task, without changing that tool's own
sandbox in any way — this is a new, narrower, safer option offered alongside it, not
a replacement. The larger tiered-allow-list question point 19 also raises (restructuring
away from the denylist sandbox entirely) remains open, unresolved by this addition.

### 2. Read-only SQL enforcement
`agent/tools/db_and_workflow_tools.py` — `execute_read_only_sql` has two layers:

- A keyword blocklist (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`,
  `CREATE`, `GRANT`, `REVOKE`, `INTO`, `COPY`, `PROGRAM`, `EXECUTE`, `CALL`, `DO`,
  `MERGE`, `VACUUM`, `ANALYZE`, `LO_EXPORT`, `LO_IMPORT`, `PG_READ_FILE`,
  `PG_READ_BINARY_FILE`, `PG_LS_DIR`, plus a substring check for `DBLINK` and its
  function family), and a stacked-statement guard (rejects more than one `;`-separated
  statement).
- A DB-level layer (`_enforce_db_read_only`) that opens a real PostGIS connection,
  sets the session to `READ ONLY`, and **fails closed**: if that `SET` can't be
  confirmed, the query is refused rather than silently running without the guarantee.

### 3. SSRF guard on fetched URLs
`agent/tools/vector_tools.py` — `_is_safe_url` resolves the hostname and rejects
loopback, private, link-local (including the `169.254.169.254` cloud metadata
endpoint), reserved, and multicast addresses before `add_layer_from_path` or the
two-phase URL-download path fetches anything. Applies to both IPv4 and IPv6.

**Every redirect hop is re-validated, not just the initial URL.** Confirmed live
(a local test HTTP server, not a mock) that Python's default
`HTTPRedirectHandler` follows a `3xx` response unconditionally — a URL that
passed `_is_safe_url` at call time could `302` to a completely different,
unvalidated address (e.g. the metadata endpoint) and the original code fetched
it anyway, since the check only ran once, before the request. `_prefetch_url_to_temp`
now uses a custom opener (`_SafeRedirectHandler`) that re-runs `_is_safe_url` on
every redirect target before following it. The response body is also streamed
and capped at `_MAX_DOWNLOAD_BYTES` (200MB) rather than read in one unbounded
`response.read()` call.

### 4. Credential storage
`agent/auth.py` — API keys go through `QgsAuthManager` (encrypted) first; if that's
unavailable, `save_credential` falls back to plaintext `QgsSettings` and flags it
(`CredentialManager.used_plaintext_fallback`) so `ui/settings_dialog.py` can warn the
user instead of it happening silently. No credential value is ever written to a log
or console print — only exception messages are, and only in `except` blocks.

### 5. Destructive-action confirmation gate
`agent/agent.py` — `remove_layer`, `load_project`, `field_calculator`, `calculate_area`, and
`calculate_length` require a `confirmed` flag that the dispatcher's schema filtering strips
from any LLM-supplied tool-call arguments (`_real_execute_tool`'s `filtered_args`). The only
real path to `confirmed=True` is a UI button click in `ui/dock_widget.py`, not anything the
model can inject into its own tool call.

`calculate_area`/`calculate_length` were added to this list in v1.2.28 — both call the same
`_add_calculated_field` primitive as `field_calculator` (an in-place edit of the live,
already-loaded layer's attribute table via `startEditing()`/`commitChanges()`), so leaving
them ungated was an inconsistency, not a deliberate distinction. See
`docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md` for the full audit this fix came out of,
including four tools this gate deliberately does *not* cover
(`calculate_severity_index`, `calculate_presence_gap`, `calculate_population_in_need`,
`calculate_damage_exposure_severity`) — **decided 2026-08-22**: leave ungated. They're
idempotent (re-running just recomputes the same field), lower real-harm than a
geometry-mutating op, and the extra confirmation click isn't worth the friction for this
category. See `docs/IMPLEMENTATION_TRACKER.md` §4 for the record of this decision.
`execute_pyqgis_script` has a different protection model entirely (sandbox, not a
confirmation dialog — see Limitations below).

### 6. Prompt-injection guidance
`agent/prompts.py`, rule 16 — instructs the model to treat content returned by
`search_web`/`gemini_grounded_search`/`openai_grounded_search`/`fetch_osm_features`/
`search_hdx_datasets`/`fetch_geoboundaries`/`fetch_fts_funding_data`/`fetch_nasa_eonet_events`/
`fetch_gdacs_disaster_alerts` as data, never as instructions to follow. This is a prompt-level
mitigation, not a code-enforced one — see Limitations. (`fetch_worldpop_population` and
`fetch_nasa_active_fires` return only numeric/coded fields to the model — no free-text
description/title fields — so neither is a text-injection vector the same way.)

### 7. Chat history persistence is opt-in
`agent/chat_persistence.py` — the AI conversation is only written into the active
project's `.qgz` file if the user has explicitly turned on "Save chat history in the
project file" in Settings (default: **off**). A project file is a shareable artifact
— emailed, committed, uploaded — and previously the conversation was always saved
into it with no way to opt out, which risked carrying sensitive content (humanitarian
incident/security details, internal notes discussed in chat) along with the map file
itself, silently. Turning the setting off does not retroactively remove history
already saved in a project from before it was disabled.

### 8. Recurring monitoring scheduler
`agent/scheduler.py`, `agent/tools/monitoring_tools.py` — `schedule_recurring_workflow`
re-runs a saved sequence of tool calls on a `QTimer` at a user/model-chosen interval,
unattended, for as long as QGIS stays open. Three controls:
- **Tool allowlist.** `_load_steps()` rejects any preset step naming a tool outside
  `_ALLOWED_WORKFLOW_TOOLS` before it's ever scheduled — 7 read-only analysis tools (no
  geometry edits, no file writes), plus (v1.9.0) 3 idempotent live-hazard-data refresh tools
  (`fetch_nasa_active_fires`/`fetch_nasa_eonet_events`/`fetch_gdacs_disaster_alerts`) that DO
  write, but only ever replace their own auto-managed layer's features with the latest fetch
  from a fixed external source — never a user-authored layer, and never an unbounded or
  escalating effect across repeated runs the way an arbitrary geometry edit could be.
- **Minimum interval floor.** `WorkflowScheduler.start()` rejects `interval_minutes`
  below 1 — previously only `<= 0` was rejected, so e.g. `0.001` became a ~60ms `QTimer`
  re-running full geoprocessing (zonal statistics, severity scoring) on the main Qt
  thread on every fire: a self-inflicted denial-of-service against the user's own QGIS
  session from a single miscalibrated or prompt-injected call.
- **Concurrent-schedule cap.** `WorkflowScheduler.start()` also rejects a *new*
  `preset_name` once 5 schedules are already active (replacing an already-active
  schedule under the same name is exempt) — previously nothing stopped an unbounded
  number of independent `QTimer`s from accumulating.

**Accepted risk (escalation of an existing one):** if a monitoring workflow includes
`calculate_presence_gap`, its `presence_file_path` argument is a local file path that
gets re-read, unattended, on every tick for as long as the schedule runs. This is the
same "Local file access is intentionally broad" risk already accepted below, now
recurring automatically rather than a one-shot explicit call — not a new vulnerability
class, but worth stating rather than leaving implicit.

### 9. Prompt Refinement Layer — external-call awareness
`agent/prompt_refiner.py` — when enabled (default **off**), `refine()` sends the user's
raw message to the same already-configured provider a second time before the real
turn runs. Same credentials, same trust boundary as the rest of the plugin, not a new
vulnerability class — but enabling this feature doubles how many times a given message
leaves the machine to an external provider. There is no hosted, private-data-enclave
option in this codebase — every request goes directly from your machine to whichever
provider you've configured.

## Testing performed

The unit test suite (`tests/`) includes targeted security tests for every protection
above. Beyond those, an adversarial pass was done against the running code (not
theoretical review) — each finding below was *confirmed exploitable* before being
fixed, not assumed:

| # | Attempted bypass | Result before fix | Fixed by |
|---|---|---|---|
| 1 | `import builtins; builtins.open(path).read()` | **Confirmed: full arbitrary local file read**, verified by actually reading `C:\Windows\System32\drivers\etc\hosts` | Added `builtins` to blocked modules |
| 2 | `"{0.__class__.__bases__}".format(x)` / `.format_map()` | **Confirmed: reaches dunder attributes invisibly to the AST walk** (they're text inside a string literal, not real `Attribute` nodes) | Block `.format`/`.format_map` as attribute access |
| 3 | `import gc; gc.get_objects()` | **Confirmed: enumerates the live object graph**, a known technique for locating already-imported dangerous classes without importing them directly | Added `gc` to blocked modules |
| 4 | `import inspect; inspect.currentframe()` | **Confirmed: reaches other frames' globals** | Added `inspect` to blocked modules |
| 5 | `SELECT lo_export(...)`, `pg_read_file(...)`, `dblink(...)` | **Confirmed: none of the DML/DDL keywords catch these**, and the DB-level read-only transaction doesn't block them either since they're not table mutations — `lo_export`/`pg_read_file` can read server-side files, `dblink` can run SQL against a different server, all from a plain `SELECT` | Added to the SQL keyword/substring blocklist |
| 6 | Decimal/hex/octal IP notation (`http://2130706433/`, `0x7f000001`, `017700000001`) | Tested — **fails closed** (neither `ipaddress.ip_address()` nor DNS resolution accept these forms, so the fetch is refused) | No fix needed; confirmed already safe |
| 7 | URL userinfo/fragment confusion (`http://trusted.com@127.0.0.1/`) | Tested — **not exploitable**, `urlparse().hostname` correctly extracts the real target | No fix needed; confirmed already safe |
| 8 | `().__class__.__base__` (singular, vs. the blocked plural `__bases__`) | Tested — **not exploitable**, blocked upstream by the `.__class__` check the chain always starts with | No fix needed; confirmed already safe |
| 9 | `from qgis.PyQt.QtCore import QDirIterator` to walk the filesystem | **Confirmed in live production use** (not synthetic testing) — a real agent session used this to browse well outside the QGIS install, returning real paths from unrelated personal project folders. `qgis.PyQt.QtCore` must stay importable (`QVariant`/`QColor`/signals live there), so a whole-module block wasn't an option | Added `_BLOCKED_QT_NAMES`: `QFile`/`QDir`/`QDirIterator`/`QProcess`/`QNetworkAccessManager`/`QSettings`/`QLibrary`/`QPluginLoader`/`QDesktopServices` and others, blocked by name regardless of which allowed Qt submodule they come from |
| 10 | `from qgis.PyQt.QtCore import QFile as F` (aliased import) | Tested while fixing #9 — **confirmed the usage-only version of the fix missed this**, since the script never writes the literal string "QFile" again after the import line | Check the `ImportFrom` alias's real name directly, not just later `Name`/`Attribute` references |
| 11 | `add_layer_from_path` with a URL that `302`-redirects to an internal/private address after passing `_is_safe_url` | **Confirmed exploitable** with a real local HTTP server (not a mock): the URL validated and the URL actually fetched differed, because the default redirect handler follows `3xx` unconditionally and the SSRF check only ran once, before the request | Custom redirect handler (`_SafeRedirectHandler`) re-validates every hop; verified the same live-server test now raises instead of fetching |

A side effect of fixing #1–#4 (restricting builtins) broke legitimate `class`
statements inside scripts (`__build_class__`/`__name__` weren't available) — found
during this same testing pass and restored, since defining a plain class carries no
security risk beyond what `type()` (already permitted) already allows.

Run `python -m unittest discover -s tests -t . -p "test_*.py" -v` to see all of the above
as passing, permanent regression tests (search for `# Confirmed live` / `# A1:` / `# A2:`
/ `# A3:` / `# A4:` comments in `tests/test_new_tools.py`, `tests/test_auth_and_deps.py`).

## Data protection (recommendation, not yet assessed)

**GDPR alignment has not been formally assessed and is recommended before any EU/DG ECHO
deployment handling real beneficiary or operational data.** When a cloud provider
(OpenRouter, Gemini, OpenAI, or Claude — see `docs/USER_GUIDE.md`) is selected, the chat
message text and any layer/attribute content the model is given via tool calls (e.g.
`get_layers`, attribute-table reads, population/incident/assessment data described back in
chat) leaves the user's machine and is processed by that provider, most of which are
US-based. In a humanitarian GIS context this can include personal or special-category data
(names, household identifiers, security-incident details, vulnerability/protection data)
under GDPR Art. 9. Recommended, not yet done:

- A formal GDPR alignment review covering lawful basis (Art. 6), special-category data
  (Art. 9) where JIAF/CVA/protection-related tools are used, cross-border transfer
  mechanisms (Art. 44-49) for each cloud provider, and a Data Protection Impact Assessment
  (Art. 35) if processing is judged high-risk.
- Documenting, per provider, what data-processing agreement/SCCs (if any) apply — this is
  outside what a QGIS plugin's own code can control or verify.
- A user-facing recommendation (in `docs/USER_GUIDE.md` and/or the in-app Help tab) to
  prefer the local Ollama provider, or to redact/aggregate personal and special-category
  data before it reaches chat, when working with real beneficiary data rather than test
  data.
- No data minimization or redaction is currently built into the plugin's tool-calling path
  — this is a genuine gap, not an oversight to silently "fix" here, since deciding what
  counts as personal/special-category humanitarian data is a legal judgment call per
  `CONTRIBUTING.md` §3, not an engineering one.

**Full review, 2026-09-01: `docs/GDPR_COMPLIANCE_REVIEW.docx`.** A code-level review against
each GDPR article, with file:line evidence for every claim -- not a substitute for real legal/DPO
sign-off (see its own disclaimer), but a concrete starting point. Its single CRITICAL finding:
`agent/memory.py`'s `SpatialMemoryManager.store_global_note()` writes agent notes into
`QgsSettings` (machine-wide, every project, indefinitely) and **no code path anywhere deletes
them** -- confirmed by a full-codebase search for `clear_global_notes`. Unlike project-scoped
memory (has a "Clear Project Memory" button) and chat history (opt-in, has a toggle), global
memory is always-on with no user-facing control at all. If it ever captures personal or
special-category data, there is currently no way to honour an Art. 17 erasure request for it.
Not fixed here -- flagged for a decision per `CONTRIBUTING.md` §3, tracked below.

### International transfer mechanisms, by provider (F3, researched 2026-09-01)

The review's F3 finding was that no transfer mechanism was documented for any provider.
Researched from each provider's own current published terms (not assumed); this is a
fast-changing area and an org doing a real assessment should re-verify against the live
pages before relying on it, not just cite this table.

- **OpenAI** -- DPA uses Standard Contractual Clauses (+ UK Addendum for UK data),
  self-serve/click-through, effective 2026-01-01. API data is not used for model training
  by default (since March 2023). Source: `https://openai.com/policies/data-processing-addendum/`.
- **Google / Gemini** -- Google LLC is EU-US/Swiss-US/UK Data Privacy Framework-certified
  (effective 2025-08-23) and separately offers SCCs via its Cloud DPA. **Important
  split specific to the Gemini API this plugin calls** (`generativelanguage.googleapis.com`):
  on the **free tier**, Google states it may use prompts/responses to improve its products
  and that human reviewers may read them; on the **paid tier**, Google states prompts and
  responses are *not* used to improve its products, and processing falls under the Cloud
  Data Processing Addendum. Enabling billing on the key used with this plugin is the
  difference between these two regimes. Sources: `https://ai.google.dev/gemini-api/terms`,
  `https://cloud.google.com/terms/data-processing-addendum`.
- **Anthropic / Claude** -- DPA (built on SCCs) is automatically incorporated into the
  Commercial/API Terms of Service on acceptance; no separate signature needed for a
  self-serve API account. If Claude is reached through a third-party platform instead of
  Anthropic directly, that platform's own terms govern instead.
  Source: `https://support.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa`.
- **OpenRouter** -- publishes a DPA via its Trust Portal, but by OpenRouter's own account
  it is only mutually signed/enforceable for **Enterprise-tier** accounts; a self-serve
  account can review it for information only, which means it is likely **not a binding
  contract** for a typical BYOK humanitarian-org deployment -- the sharpest gap of the
  four. Separately, OpenRouter's own account Privacy settings has independent toggles for
  whether *free* vs. *paid* model routing may go to an upstream provider that trains on
  the data, which is why `settings_dialog.py`'s OpenRouter key tooltip now tells the user
  to check that setting. Sources: `https://trust.openrouter.ai/`,
  `https://openrouter.zendesk.com/hc/en-us/articles/47828437697051`,
  `https://openrouter.ai/docs/guides/privacy/provider-logging`.

None of the above is legal advice or a substitute for the org's own DPO/counsel
confirming a transfer mechanism actually covers the org's specific processing --
it is what each provider currently publishes, so the org's review does not start from
zero.

### Remediation, 2026-09-01 (the review's 4 High findings)

- **F2 (no privacy notice anywhere in the product) -- addressed.** The Settings dialog
  now shows a static, provider-agnostic notice above the provider dropdown explaining
  what is sent and to whom (Ollama excepted), and `docs/USER_GUIDE.md`'s "What happens to
  your message before it is sent" section has a matching "Where it goes" paragraph.
- **F3 (no documented transfer mechanism for any provider) -- documented above.**
- **F4 (no DPA/sub-processor visibility surfaced to the deploying org) -- addressed.**
  Each cloud provider's Settings page now shows a link to that provider's Data Processing
  Addendum (or, for OpenRouter, its Trust Portal, labelled to flag the Enterprise-only
  caveat above) right in the dialog, next to the existing "get a key" link.
- **F5 (DPIA not done, but the processing pattern plausibly meets the EDPB's mandatory
  criteria) -- screening aid added, not a completed DPIA.** See
  `docs/DPIA_SCREENING_WORKSHEET.docx`: it pre-fills the factual, code-verifiable parts
  (EDPB WP248's nine criteria mapped against this plugin's actual tools and data flows)
  and leaves the risk determination and sign-off to the deploying org's DPO, which is a
  legal judgment call this repository cannot make on the org's behalf.

None of this closes the review's CRITICAL finding (global memory has no erasure path) or
its Medium/Low/Informational findings -- those remain open, tracked in
`docs/IMPLEMENTATION_TRACKER.md` §1.4.

### Remediation, 2026-09-11 (F6/F7/F8, part of the v1.7.0 security/logistics release)

- **F6 (project memory always-on, undisclosed, duplicated to a sidecar file) --
  addressed.** Extended the same opt-in pattern chat history already had
  (`Settings > Save chat history in the project file`) to project-scoped memory notes:
  a new `Settings > Save project notes/memory in the project file and sidecar database`
  toggle, default OFF, gates writes to the sidecar `.sqlite` file and the embedded
  `QgsProject` custom property. The in-memory cache used within a session is unaffected
  (never leaves the running process).
- **F7 (no structured data export) and F8 (no consolidated access view) -- addressed
  together, per the review's own recommendation.** New "💾 Export My Data" button (Tasks
  & Notes panel, next to Clear Project/Global Memory) and a matching `export_stored_data`
  agent tool assemble project memory, global memory, and chat history (if enabled) into
  one JSON file.
- **F9 (erasure can't reach previously-distributed file copies) -- documented, not a code
  fix.** This is an inherent property of local-file architecture: "Clear Project Memory"
  and the chat-history opt-out act on the live project state going forward only. An
  org's erasure process must separately account for any `.qgz`/sidecar `.sqlite` copies
  already saved, emailed, or committed to version control before the clear action.
- **F10 (plaintext credential fallback)** was already reviewed as adequately mitigated
  (explicit warning, tested) -- no further action.

Full detail: `docs/IMPLEMENTATION_TRACKER.md` §1.4.

Tracked in `docs/IMPLEMENTATION_TRACKER.md` §1.4.

### DPIA determination and deployment constraints, 2026-09-24

**Section 6 of `docs/DPIA_SCREENING_WORKSHEET.docx` was completed 2026-09-24 with a formal
determination: a DPIA is required under Art. 35(1), approved subject to the deployment
constraints below — not an unconditional go-ahead.** This is a policy record, not new code;
none of it is technically enforced yet (see `docs/IMPLEMENTATION_TRACKER.md` §1.4 for that
distinction and why enforcement wasn't built alongside this).

- **Ollama-only for protection/incident/displacement data.** Any workflow touching
  protection, security-incident, or displacement attributes must use the local Ollama
  provider. Cloud LLM providers (OpenRouter, Gemini, OpenAI, Claude) are restricted to
  anonymized, aggregated, or macro-level geospatial planning data only. Raw PII or exact/
  household-level GPS coordinates must not enter a cloud provider's context window unless
  local inference is used.
- **Hosted-Account feature (F14) restricted.** Must not be used with real
  beneficiary-adjacent data unless the configured `base_url` is confirmed to point to the
  organization's own self-hosted infrastructure, or an Art. 28 DPA is executed with
  whoever operates it first.
- **File-sharing SOP (extends F9).** Field teams must purge local project/global memory
  before committing a `.qgz` file to a shared drive or version control — F9's documented
  erasure limitation (above) means a clear action never reaches a copy already shared.

**The Ollama-only constraint now has an optional, OFF-by-default technical control (added
2026-09-24, partial).** Settings → "Cloud data protection" (Off / Warn only / Block), plus a strict
checkbox. When on and a **non-local** provider is selected, a tool call that touches a layer tagged
`RESTRICTED`/`SENSITIVE` — or an untagged layer derived from one — is blocked before it runs (or, in
warn mode, runs and reports it). Strict mode also treats *untagged* layers as protected. "Local"
means the provider endpoint is `localhost` or a private/loopback/link-local IP literal; a hostname is
treated as non-local because it is not resolved (address a LAN Ollama server by IP). While the gate is
on, the model cannot lower a protected layer's tag itself — that needs the user's confirmation in the
UI. Design and reasoning: `docs/OLLAMA_ENFORCEMENT_GATE_SCOPE_2026-09-24.md`.

**What it does not do — read before relying on it.**
- **It prevents accidents, not a determined user.** The setting lives in the user's own
  `QgsSettings`, which they can change.
- **What is gated:** tool calls (checked before they run) and file attachments. Every registered
  tool that reads feature values names its layer in its arguments, so the pre-run check sees it —
  `tests/test_egress_gate_coverage.py` keeps that true for future tools (it inspects each tool's own
  body, not helpers it calls). `execute_pyqgis_script` is blocked on a cloud provider whenever any
  protected layer exists (it names layers inside its own source). An attached file has no tag, so it
  is treated like an untagged layer: gated **only in strict mode**.
- **What is not gated:** text the user types or pastes, and the model repeating in its own prose what
  it saw earlier — including after switching provider, since the assistant's replies are kept in
  history (tool results are not). The prompt refiner sends only the user's own text, which the main
  request sends anyway.
- **It depends on layers being tagged.** Without strict mode an untagged layer is not protected;
  with strict mode every layer must be classified first. No automatic classification exists.
- **Derived-layer inheritance follows names.** Lineage records a layer's sources by *name*, so
  renaming or removing a protected source layer breaks inheritance for the untagged layers derived
  from it. Tag derived layers explicitly, or use strict mode.
- **Several decisions in the scope doc (§7) are still open** — who classifies layers, history
  on a provider switch, where the policy setting should live. The defaults chosen here (Off;
  strict off) are the reversible ones.
- **Decision 1 (default mode), answered 2026-09-28:** the code default stays **Off** for a
  general Community install — a fresh install should not have its behavior silently changed
  before anyone has looked at this setting. For a deployment that has completed the DPIA
  sign-off above for protection/incident/displacement data, the recommended setting is
  **Block, non-strict** — surfaced as guidance text directly under the Settings dropdown
  (`ui/settings_dialog.py`) rather than auto-switched, since this plugin has no way to detect
  on its own whether a given install's DPIA is actually complete — that is an organizational
  fact, not a technical one it can observe. Non-strict (not strict-by-default even for a
  DPIA-complete deployment) because strict mode requires every layer to be classified first,
  which this plugin has no automatic-classification path for yet; recommending strict-by-default
  would trade a real-but-solvable-by-tagging gap for guaranteed friction on day one.
- **Decision 2 (override policy), answered 2026-09-28: yes, a block is overridable, but only
  through the exact same UI Confirm-button path destructive actions already use — never a
  model-supplied argument.** A blocked call with known layers (`egress_gate.preview_required()`)
  is now handed to `agent_orchestrator.py`'s existing `PREVIEW_REQUIRED` machinery instead of a
  flat `EGRESS_BLOCKED` result: the model sees a rationale naming the exact tool and layers
  involved and tells the user, and only a real click on the existing Confirm affordance (chat's
  inline safety-gate card, the Activity tab's Confirm button, or a typed "Confirm" reply — all
  the same code path) sets `user_confirmed=True`, which the dispatcher's own schema-filtering
  guarantees the model can never inject itself (`_real_execute_tool`'s `filtered_args` comment:
  "prevents model self-approval via injected parameters"). No new free-text justification field
  was added — the deliberate click on a card naming exactly what's involved already is the audit
  record, the same standard `remove_layer`/`field_calculator` confirmations already meet without
  a note. Both the block and a confirmed override are logged (`egress_blocked`/
  `egress_override_confirmed`, metadata-only per `logger.py`'s convention), and an overridden
  call's result carries an `egress_override_note` naming the layers, so the chat transcript
  itself records what happened. **Deliberately excluded from this override path:** a check-failure
  block (`egress_gate.check_failed_decision`, raised when the gate's own machinery errors) has no
  known layers to show the user, so it stays a hard, non-overridable block — there is nothing
  concrete to confirm.
- **Decision 4 (`execute_pyqgis_script` on cloud), answered 2026-09-28: keep the existing
  whole-project rule, don't widen it.** `WHOLE_PROJECT_TOOLS` already treats every layer in the
  project as "touched" for this tool (its script names layers as string literals, invisible to
  the argument scan), so it's judged by the exact same PROTECTED-levels standard as every other
  tool — RESTRICTED/SENSITIVE, or untagged in strict mode — not by a broader "any non-PUBLIC
  layer" rule. Confirmed live (and now covered by a new regression test,
  `test_execute_pyqgis_script_is_allowed_with_only_internal_layers`,
  `tests/test_egress_gate.py`): a project made entirely of INTERNAL-tagged working layers does
  NOT block this tool on a cloud provider, since INTERNAL is an explicit owner declaration
  (`OPEN_LEVELS`) that the data may leave the machine — the same declaration every other tool
  already respects. Widening the rule to block on any non-PUBLIC layer would make this tool
  nearly unusable on cloud even for ordinary INTERNAL working layers, for no real security gain
  over the existing rule.
- **Decision 5 (history on a provider switch), answered 2026-09-28: accepted as out of scope,
  not built.** The scope doc's original premise (a provider switch re-sends earlier *tool
  results*) was already found wrong and corrected 2026-09-24 — conversation history stores only
  the user's own typed messages and the assistant's prose, never tool results. The residual this
  decision is actually about — the model repeating in its own prose, after a switch, something
  it saw from a protected layer earlier in the session — is already the documented "What is not
  gated" gap above, present whether or not a provider switch happens at all (the model could
  just as easily repeat it on the SAME provider). Gating it specifically on a provider switch
  would add real complexity (detecting the switch, deciding what in history might be
  "contaminated," and how) to close only a narrow slice of a gap that's already open more
  broadly — not judged worth building for that narrow a win.
- **Decision 6 (where the policy setting lives), answered 2026-09-28: user `QgsSettings` stays
  the mechanism for Community; a managed org-level config is out of scope for this codebase for
  now.** A managed config a local user can't override is squarely an Enterprise/Pro-tier
  deployment feature — real engineering work `docs/IMPLEMENTATION_TRACKER.md` §1.3's Path C
  decision (2026-09-24: stay GPL v2, gate tiers at runtime rather than a source split) already
  named as unblocked-but-not-started, not something to build ahead of that tier work actually
  resuming. Today's `QgsSettings` default already states plainly what it is and isn't
  ("prevents accidents, not a determined user") — that limitation is accepted, not treated as
  a defect to rush a fix for.

The plugin still does not restrict *which provider* a user selects, and does not disable the
Hosted-Account dialog under any condition — both remain deliberately-scoped-out follow-ups. See
`docs/IMPLEMENTATION_TRACKER.md` §1.4's 2026-09-24 entries.

## Known limitations (accepted risk, not fixed)

- **DNS rebinding (TOCTOU) on the SSRF guard.** `_is_safe_url` resolves the hostname,
  then `_prefetch_url_to_temp` immediately fetches it — but these are two separate DNS
  lookups. A sophisticated, purpose-built DNS-rebinding attack (attacker-controlled
  resolver returning a public IP on the first lookup and a private IP moments later on
  the second) could theoretically slip through. A full fix requires resolving once and
  pinning the connection to that specific IP at the socket level, which for HTTPS also
  requires careful handling of TLS SNI/certificate-hostname verification — judged
  higher-risk to implement hastily (a broken pinning attempt could itself become a
  security or reliability regression) than the narrow, attacker-must-control-DNS
  scenario it defends against. Revisit if this plugin starts fetching URLs from a less
  trusted source than an LLM's own tool-call arguments.
- **Local file access is intentionally broad.** `add_layer_from_path`,
  `load_tabular_data_as_layer`, `extract_pdf_tables`, `extract_word_tables`, and
  `calculate_presence_gap` (`presence_file_path`) will read any local file path the
  model names, and `georeference_image` writes its output to a model-named path — this is core functionality (loading/exporting the
  user's own files), not a bug, but it does mean a prompt-injected instruction that
  gets the model to read a local file and describe its contents back in chat (or to
  write output somewhere unexpected) is not prevented by this plugin. Reading is
  information disclosure through the model's own answer, not a tool exploiting the
  plugin; writing is bounded by normal OS file permissions, same as any other local
  file-creating tool (`save_project`, `export_layer`, `generate_chart`, etc.).
- **`execute_pyqgis_script`'s sandbox blocks specific dangerous names, not file I/O
  capability in general.** The objects the script IS allowed to use (`QgsProject`,
  `QgsVectorLayer`, `QgsRasterLayer`, and PyQGIS/GDAL/OGR generally) can themselves
  read or write files — e.g. `QgsVectorLayer('/etc/passwd', 'x', 'ogr')` or
  `QgsProject.instance().write(path)` — since blocking `QFile`/`os`/etc. (Protections
  § 1) doesn't remove file capability that legitimate PyQGIS objects carry by design.
  This is accepted, not fixed: any sandbox exposing real PyQGIS functionality
  necessarily exposes what PyQGIS itself can do, and PyQGIS scripts are expected to
  read/write project data as their normal job. Treat `execute_pyqgis_script` as
  "arbitrary-file-I/O-capable, with the interpreter-escape and process/network vectors
  specifically closed" — not as a fully contained sandbox.
- **Prompt-injection guidance (rule 16) is not code-enforced.** It's an instruction to
  the model, which a sufficiently adversarial prompt-injection payload might still
  override — there is no code-level filter on what fetched content is allowed to
  contain.
- **This is not a formal sandbox.** See "Protections § 1" above — `exec()`-based
  script restriction is inherently a best-effort blocklist approach, not a provable
  security boundary the way OS-level process isolation would be.
- **`extract_features_from_imagery`'s model weights download is unpinned and
  unverified.** `FastSAM("FastSAM-s.pt")` delegates entirely to the `ultralytics`
  package's own first-use download logic (from Ultralytics' own release CDN) — this
  plugin does not pin a specific weights-file hash, verify a checksum, or control which
  URL the download actually comes from. A compromised or MITM'd download of that
  package/CDN could deliver a malicious weights file that executes arbitrary code on
  load (a known general risk class with pickle-based/unsafe model-loading formats).
  Not fixed here: this plugin has no mechanism to intercept or verify a download
  performed inside a third-party dependency, and it doesn't attempt to vendor or pin
  the weights file itself. Consistent with the § 3 SSRF guard's scope (only URLs this
  plugin's own code fetches directly), this is an accepted, out-of-scope-for-this-code
  risk of the optional `ultralytics` dependency, not something the tool call itself
  introduces.

## Licensing note

This plugin is GNU GPL v2 (see `LICENSE`), consistent with PyQGIS (`qgis.core`,
`qgis.gui`, `qgis.utils`), which it imports at runtime. A proprietary license was
considered and deliberately not used, specifically to avoid the unresolved legal
question of whether a proprietary license would be compatible with importing GPL v2
PyQGIS code — monetization is services-based instead (support, hosting, custom
integration), not code licensing.
