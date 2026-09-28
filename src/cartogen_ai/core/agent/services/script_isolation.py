# -*- coding: utf-8 -*-
"""
Process-isolation boundary for `execute_pyqgis_script`
(IMPLEMENTATION_TRACKER.md §1.11; docs/EXECUTE_PYQGIS_SCRIPT_ISOLATION_SCOPE_2026-09-24.md,
Path A, Phase 1 -- go-ahead given 2026-09-28).

Every prior fix to that tool's sandbox closed one specific "capability reachable through an
allowed name" bypass -- a denylist that structurally can't be proven complete (see that file's
own `_BLOCKED_MODULES`/`_BLOCKED_DUNDER_ATTRS` comments for the history). This module changes
the *category* of fix: the script runs in a separate OS process holding its own `QgsApplication`,
which never has this plugin's in-memory credential objects, conversation history, or Python
object graph at all -- not just names blocked from an exec() scope in the same process.

`_validate_script_safety`'s AST checks and `_SAFE_BUILTINS` still run inside the worker (defense
in depth, not replaced by this boundary -- a script that somehow found a new denylist bypass
would still only be attacking a disposable subprocess with a temp-file copy of the project, not
this plugin's live process).

Scope of what this covers, per the scoping doc's Phase 1: the existing `local_env` surface
exactly as-is (QgsProject/QgsVectorLayer/QgsRasterLayer/QgsFeature/QgsGeometry/QgsPointXY/
QgsField/QgsApplication/QVariant), vector/geometry scripts. Raster-heavy serialization cost was
explicitly deferred to a later phase in the scoping doc; this module does not special-case
raster layers beyond letting them serialize into the project file unconditionally.

Known, documented limitations (not silently claimed as fixed):
- A script that mutates an EXISTING file-backed (non-memory) layer writes to the same file the
  live process still has open -- the isolation boundary does not solve concurrent-access
  semantics for that case, only credential/process isolation. No different from the same file
  being edited by an external program while QGIS has it open.
- Layer removal/reordering/style edits made by a script are not reconciled back into the live
  project -- only new layers (added) and existing MEMORY layers' feature data (since that's the
  one case where the pre-serialize export step already builds a mapping to reconcile) are synced
  back. This matches what `local_env` actually gives a script to do (see §2 of the scoping doc:
  no iface/canvas/selection access, so the realistic pattern is "read some layers, add a new
  computed one" or "add features to an existing memory layer this turn already created").
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

try:
    from qgis.core import QgsProject, QgsVectorFileWriter, QgsCoordinateTransformContext
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False

from ...logger import log_event

# A hung script (infinite loop, a blocking network call some future bypass reaches)
# needs a hard process-level kill -- the in-process version never needed this since
# the whole plugin already provides no way to interrupt exec() from outside, and a
# stuck in-process call meant reloading the plugin. In its own process, a timeout
# is both possible and necessary: the worker itself has no per-job timeout, so
# without one a hung script would hang the isolation call, and by extension the
# tool-dispatch thread, forever.
_JOB_TIMEOUT_SECONDS = 60
# A crashed/never-starting worker must not hang the caller either.
_WORKER_START_TIMEOUT_SECONDS = 30


def find_python_interpreter():
    """Locate a spawnable Python interpreter from inside a running QGIS process.

    Adapted from QPIP's (opengisch/qpip, MIT-licensed) `python_command()`, which
    exists for the identical sub-problem: "spawn a real Python process from inside
    a running QGIS session." `sys.executable` cannot be trusted directly -- inside a
    real QGIS desktop session on Windows it is the QGIS binary itself
    (`qgis-bin.exe`), not a Python interpreter. This is a known, currently-unfixed
    upstream QGIS bug (qgis/QGIS#45646; an attempted fix, qgis/QGIS#67318, was
    closed unmerged 2026-09-18) -- see IMPLEMENTATION_TRACKER.md §1.11's
    2026-09-27 update for the research trail. Not independently live-verified by
    this project on a real QGIS desktop install on Windows/macOS (no such install
    in this sandbox) -- adopted on the strength of the upstream bug report and
    QPIP's own production code, same caveat that update recorded. The Linux
    branch (`sys.executable` used directly) IS live-verified here, against the
    real `qgis/qgis` Docker image this repo's CI itself pins.
    """
    prefix = Path(sys.prefix)
    if (prefix / "conda-meta").exists():
        return "python"
    if sys.platform.startswith("win"):
        for name in ("python.exe", "python3.exe"):
            candidate = prefix / name
            if candidate.exists():
                return str(candidate)
        return sys.executable
    if sys.platform == "darwin":
        for base in (prefix, prefix / "bin", Path(sys.executable).parent):
            for name in ("python3", "python"):
                candidate = base / name
                if candidate.exists():
                    return str(candidate)
        return sys.executable
    # Linux: sys.executable is already correct here (the upstream bug is
    # Windows/macOS-specific) -- live-confirmed against qgis/qgis's Docker image.
    return sys.executable


def _build_worker_environment():
    """A curated, minimal environment for the worker subprocess -- per the scoping
    doc's §3 recommendation ("environment variables stripped to the minimum QGIS
    needs to start"). This plugin does not itself put credentials in environment
    variables (confirmed: infrastructure/auth.py reads only QgsAuthManager/session
    memory), so the concrete benefit here is narrower than the scoping doc's
    illustrative example implied -- but a separate process with a curated, smaller
    environment is still meaningfully less surface than inheriting this plugin's
    entire process environment unfiltered, and costs nothing to do."""
    keep_prefixes = ("QGIS_", "GDAL_", "PROJ_", "QT_", "LC_", "XDG_")
    keep_exact = {"PATH", "HOME", "USERPROFILE", "LANG", "TEMP", "TMP", "TMPDIR", "PYTHONPATH", "DISPLAY"}
    env = {
        key: value
        for key, value in os.environ.items()
        if key in keep_exact or key.startswith(keep_prefixes)
    }
    plugin_parent = _plugin_parent_dir()
    if plugin_parent:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = plugin_parent if not existing else os.pathsep.join([plugin_parent, existing])
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def _plugin_parent_dir():
    """The directory that must be on the worker's sys.path/PYTHONPATH for
    `import cartogen_ai` to work there -- the worker needs it to reuse
    `_validate_script_safety`/`_SAFE_BUILTINS` rather than duplicating that
    denylist in a second file that would silently drift out of sync."""
    try:
        import cartogen_ai
    except ImportError:
        return None
    # cartogen_ai has no top-level __init__.py (a namespace package), so
    # __file__ is None -- __path__[0] is the actual on-disk package directory
    # in both layouts (installed as a QGIS plugin folder, or this repo's src/).
    package_dir = Path(list(cartogen_ai.__path__)[0]).resolve()
    return str(package_dir.parent)


def _export_layer_to_gpkg(layer, path):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"
    QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsCoordinateTransformContext(), options
    )


def _build_scratch_project(tempdir):
    """Snapshots the live project into a scratch copy where every MEMORY-provider
    layer's data is exported to a real GPKG file and swapped in, so the worker
    process actually receives its features. Never touches the live QgsProject
    singleton or its layer objects.

    QGIS writes a memory layer's definition into a project file but not its
    feature data -- live-confirmed, 2026-09-24 Phase 0 benchmark (see the scoping
    doc's §8): a live memory layer with 1,000 and with 50,000 features both
    serialized without error, and a fresh process loading that project saw 0
    features on each. This plugin's own tools produce memory layers constantly
    (`run_allowlisted_processing_algorithm` forces `memory:` outputs by design),
    so this is the dominant real case, not an edge case.

    Returns (scratch_project_path, memory_layer_ids) -- the second so the caller
    knows which layer ids to reconcile feature changes back for after the run.
    """
    live = QgsProject.instance()
    snapshot_path = os.path.join(tempdir, "live_snapshot.qgz")
    live.write(snapshot_path)

    scratch = QgsProject()
    scratch.read(snapshot_path)

    memory_layer_ids = []
    for layer_id, layer in list(scratch.mapLayers().items()):
        if getattr(layer, "type", None) is None:
            continue
        if hasattr(layer, "providerType") and layer.providerType() == "memory":
            # Export the LIVE layer's features, not this scratch-reloaded copy's --
            # `scratch.read(snapshot_path)` already loaded this layer with 0
            # features (the exact gap this function exists to close: QGIS writes
            # a memory layer's definition into a project file but not its data),
            # so exporting `layer` itself here would just re-serialize the empty
            # copy. The live singleton still holds the real data, keyed by the
            # same layer id QGIS preserves across write/read.
            live_layer = live.mapLayer(layer_id)
            gpkg_path = os.path.join(tempdir, f"mem_{layer_id}.gpkg")
            _export_layer_to_gpkg(live_layer if live_layer is not None else layer, gpkg_path)
            layer.setDataSource(gpkg_path, layer.name(), "ogr")
            memory_layer_ids.append(layer_id)

    scratch_path = os.path.join(tempdir, "scratch_project.qgz")
    scratch.write(scratch_path)
    return scratch_path, memory_layer_ids


def _reconcile_results(result_project_path, pre_call_layer_ids, memory_layer_ids):
    """Loads the worker's resulting project and applies two, and only two, kinds
    of change back to the LIVE project -- everything else a script could
    theoretically do (remove/reorder layers, edit styles) is not reconciled; see
    this module's docstring for why that's the deliberate Phase 1 scope, not an
    oversight.

    1. Any layer id present in the result but not in the pre-call live project is
       a genuinely new layer the script created -- cloned and added to the live
       project (a clone carries no reference back to the scratch QgsProject it
       came from, so it's safe to move into a different QgsProject instance).
    2. Any pre-existing MEMORY layer whose exported-GPKG feature count changed
       has its live in-memory features replaced with the GPKG's current content
       -- the one case a script plausibly mutates data on a layer that already
       existed before the call (e.g. adding features to a layer produced earlier
       in the same turn).
    """
    live = QgsProject.instance()
    result_scratch = QgsProject()
    result_scratch.read(result_project_path)

    new_layers_added = []
    for layer_id, layer in result_scratch.mapLayers().items():
        if layer_id in pre_call_layer_ids:
            continue
        clone = layer.clone()
        live.addMapLayer(clone)
        new_layers_added.append(clone.name())

    memory_layers_updated = []
    for layer_id in memory_layer_ids:
        if layer_id not in pre_call_layer_ids:
            continue
        live_layer = live.mapLayer(layer_id)
        result_layer = result_scratch.mapLayer(layer_id)
        if live_layer is None or result_layer is None:
            continue
        if result_layer.featureCount() == live_layer.featureCount():
            continue
        provider = live_layer.dataProvider()
        provider.truncate()
        new_features = list(result_layer.getFeatures())
        if new_features:
            provider.addFeatures(new_features)
        live_layer.updateExtents()
        live_layer.triggerRepaint()
        memory_layers_updated.append(live_layer.name())

    return new_layers_added, memory_layers_updated


class _IsolationWorker:
    """Manages one persistent worker subprocess. Started lazily on first use and
    kept alive across calls -- Phase 0 benchmarking (scoping doc §8) measured a
    cold spawn-per-call at ~5s, almost entirely `import qgis.core`'s fixed cost,
    which is why this is a persistent worker rather than one process per call."""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        if self._proc is not None and self._proc.poll() is None:
            return
        interpreter = find_python_interpreter()
        env = _build_worker_environment()
        self._proc = subprocess.Popen(
            [interpreter, "-m", "cartogen_ai.core.agent.services._script_isolation_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
            cwd=tempfile.gettempdir(),
        )

    def _read_line_with_timeout(self, timeout):
        box = {}

        def _reader():
            box["line"] = self._proc.stdout.readline()

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            return None
        return box.get("line") or None

    def _kill(self):
        if self._proc is None:
            return
        try:
            self._proc.kill()
            self._proc.wait(timeout=5)
        except Exception:
            pass
        self._proc = None

    def submit(self, job, timeout=None):
        # Not a plain `timeout=_JOB_TIMEOUT_SECONDS` default: a default argument
        # is bound once at function-definition time, so a later
        # `si._JOB_TIMEOUT_SECONDS = ...` override (used by
        # tests/manual_isolation_bench/phase1_recovery_check.py to force a
        # short timeout) would silently have no effect. Reading the module
        # global inside the call body picks up the current value every time.
        if timeout is None:
            timeout = _JOB_TIMEOUT_SECONDS
        with self._lock:
            self._ensure_started()
            try:
                self._proc.stdin.write(json.dumps(job) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                stderr = self._drain_stderr()
                self._kill()
                return {"error": f"Isolation worker was not running when the job was sent (crashed?): {stderr[:2000]}"}

            line = self._read_line_with_timeout(timeout)
            if line is None:
                self._kill()
                return {"error": f"Script exceeded the {timeout}s isolation timeout and the worker was terminated."}
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                stderr = self._drain_stderr()
                self._kill()
                return {"error": f"Isolation worker produced an unreadable response (crashed?): {stderr[:2000]}"}

    def _drain_stderr(self):
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            self._proc.stderr.flush()
        except Exception:
            pass
        try:
            import select
            data = ""
            while select.select([self._proc.stderr], [], [], 0)[0]:
                chunk = self._proc.stderr.readline()
                if not chunk:
                    break
                data += chunk
            return data
        except Exception:
            return ""

    def shutdown(self):
        with self._lock:
            self._kill()


_worker = _IsolationWorker()


def run_isolated_script(script: str) -> dict:
    """The public entry point `execute_pyqgis_script` calls when running inside
    real QGIS. Serializes the live project (with memory layers made real), hands
    the script to the persistent worker, reconciles the result back into the live
    project, and returns the same {"success"/"result"} or {"error"/"traceback"}
    shape the in-process path always has -- callers (agent_orchestrator.py's
    generic before/after live-layer-id diff, used for undo tracking) don't need
    to know isolation happened at all."""
    live = QgsProject.instance()
    pre_call_layer_ids = set(live.mapLayers().keys())

    tempdir = tempfile.mkdtemp(prefix="cartogen_isolation_")
    try:
        scratch_path, memory_layer_ids = _build_scratch_project(tempdir)
        result_path = os.path.join(tempdir, f"result_{uuid.uuid4().hex}.qgz")

        response = _worker.submit({
            "script": script,
            "project_path": scratch_path,
            "result_project_path": result_path,
        })

        if response.get("error"):
            return response

        if not os.path.exists(result_path):
            return {"error": "Isolation worker reported success but wrote no result project -- treat as a failure."}

        new_layers, updated_memory_layers = _reconcile_results(result_path, pre_call_layer_ids, memory_layer_ids)
        if new_layers or updated_memory_layers:
            log_event(
                "isolated_script_reconciled",
                tag="ScriptIsolation",
                new_layers=len(new_layers),
                updated_memory_layers=len(updated_memory_layers),
            )
        return {"success": True, "result": response.get("result")}
    finally:
        shutil.rmtree(tempdir, ignore_errors=True)


def has_uncommitted_edits():
    """Refuses the call outright rather than silently committing or discarding
    in-progress edits -- per IMPLEMENTATION_TRACKER.md §1.11's 2026-09-27
    recommendation, matching this project's existing fail-loudly convention
    elsewhere (buffer_analysis's only_selected guard, the egress gate's
    block-by-default). Returns the list of editable layer names, empty if none."""
    live = QgsProject.instance()
    return [
        layer.name()
        for layer in live.mapLayers().values()
        if hasattr(layer, "isEditable") and layer.isEditable()
    ]
