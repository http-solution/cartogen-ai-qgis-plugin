# Security

This document describes Cartogen AI's threat model, the protections actually
implemented in the codebase, what was adversarially tested (with real, confirmed
findings — not just a list of intentions), and the limitations that are honestly
still open. It is written to be checked against the code, not trusted on its own —
file:line references are given throughout so any claim here can be verified directly.

## Threat model

The plugin runs an LLM in a tool-calling loop against a real QGIS project. Two things
in that loop are **untrusted input**, not just data:

1. **The LLM's own output.** A cloud provider response, a prompt-injected instruction
   hidden inside fetched web/OSM/HDX content, or simply a model mistake can all result
   in a tool call with attacker-influenced arguments — a script to execute, a URL to
   fetch, a SQL query to run.
2. **Content fetched from the internet** (`search_web`, `fetch_osm_features`,
   `search_hdx_datasets`, `fetch_geoboundaries`, `fetch_fts_funding_data`) that gets
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
`inspect`, `types`, `copyreg`, `runpy`.

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
`search_hdx_datasets`/`fetch_geoboundaries`/`fetch_fts_funding_data` as data, never as
instructions to follow. This is a prompt-level mitigation, not a code-enforced one —
see Limitations. (`fetch_worldpop_population` returns only numeric/binary raster data
to the model, no free-text fields, so it isn't a text-injection vector the same way.)

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
  `_ALLOWED_WORKFLOW_TOOLS` (7 read-only analysis tools — no geometry edits, no file
  writes) before it's ever scheduled.
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
leaves the machine to an external provider, which matters for any "private data
enclave" claim (see `docs/PRODUCT_TIERS.md`'s Enterprise tier, honestly marked as not
built).

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
