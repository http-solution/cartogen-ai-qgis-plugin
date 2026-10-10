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
- Local-file vector and raster layers are handed to the worker as COPIES in the temp directory (audit A06), so a script cannot
  modify the user's files; edits it makes to such a layer are discarded, not reconciled. Database/web-service layers have no file
  to copy; they are locked read-only in the scratch project (#220).
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
        # Widened 2026-09-28 after a live-reported worker timeout with zero
        # diagnostics (see _run_worker_handshake below): checking only
        # sys.prefix's own root misses real QGIS-for-Windows layouts where
        # sys.prefix is the QGIS install root itself and the bundled
        # interpreter sits one level down (OSGeo4W's apps\PythonXXX\, the
        # standalone installer's apps\Python3XX\) -- also checking
        # sys.base_prefix/sys.exec_prefix (can differ from sys.prefix under a
        # venv-like setup) and any single apps\Python3* child directory.
        bases = {prefix, Path(sys.base_prefix), Path(sys.exec_prefix)}
        candidates = []
        for base in bases:
            candidates.append(base)
            apps_dir = base / "apps"
            if apps_dir.is_dir():
                candidates.extend(sorted(apps_dir.glob("Python3*")))
        for base in candidates:
            for name in ("python.exe", "python3.exe"):
                candidate = base / name
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


# Basenames of the QGIS executable itself, across the installers this project
# supports -- never spawn one of these as the "worker interpreter". If
# find_python_interpreter() falls through to sys.executable and that turns out
# to BE the QGIS binary (the exact upstream bug this function exists to work
# around), spawning it as a worker doesn't error -- it silently launches a
# second, real QGIS process that never writes the JSON handshake this module
# waits for, hanging until the full job timeout kills it with no diagnostic at
# all. Live-reported, 2026-09-28: a real Windows session hit a 60s
# execute_pyqgis_script timeout with nothing in the logs to explain it -- this
# is the leading suspect. Checked by _run_worker_handshake below, which fails
# fast (a few seconds, not the full job timeout) with a clear message instead.
_QGIS_BINARY_BASENAMES = {"qgis-bin.exe", "qgis-bin", "qgis.exe", "qgis", "QGIS", "QGIS.exe"}


def _qgis_sys_path_entries():
    """Directories already on THIS process's own `sys.path` -- this plugin is
    running inside a real, already-initialized QGIS session, so if it can
    `import qgis.core` right now, whatever made that true is already sitting
    in this list. On a real Windows/macOS desktop install, QGIS's own C++
    bootstrap adds the `qgis` bindings (and PyQt, GDAL's Python bindings,
    etc.) to the EMBEDDED interpreter's `sys.path` directly -- it is not
    exported as an OS-level `PYTHONPATH` environment variable at all, so a
    bare subprocess spawned from the same on-disk interpreter binary does
    NOT inherit it via `os.environ` (confirmed by a live report, 2026-09-28:
    a *correctly resolved* real Python interpreter -- not the QGIS-binary
    misdetection `_QGIS_BINARY_BASENAMES` guards against -- still failed
    with `ModuleNotFoundError: No module named 'qgis'`). Reusing this
    process's resolved `sys.path` instead of reconstructing an install
    layout by guesswork (OSGeo4W vs. the standalone installer vs. Docker
    each differ) works however THIS install actually set itself up, since
    it's the exact same information QGIS itself already computed."""
    return [p for p in sys.path if p and os.path.isdir(p)]


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
    # Order matters: this plugin's own parent dir first (so `import cartogen_ai`
    # in the worker always resolves to THIS install, never a same-named package
    # elsewhere on the QGIS interpreter's own sys.path), then the live process's
    # resolved qgis/PyQt/GDAL bindings directories, then whatever PYTHONPATH the
    # environment already had (lowest precedence, kept rather than dropped).
    path_entries = []
    plugin_parent = _plugin_parent_dir()
    if plugin_parent:
        path_entries.append(plugin_parent)
    path_entries.extend(_qgis_sys_path_entries())
    existing = env.get("PYTHONPATH", "")
    if existing:
        path_entries.append(existing)
    if path_entries:
        # Dedupe while preserving order -- sys.path commonly repeats entries.
        seen = set()
        deduped = []
        for entry in path_entries:
            if entry not in seen:
                seen.add(entry)
                deduped.append(entry)
        env["PYTHONPATH"] = os.pathsep.join(deduped)
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


def _write_snapshot_of_live_project(live, snapshot_path):
    """Serializes the live project to `snapshot_path` WITHOUT changing which file the
    live project thinks it is.

    QgsProject.write(path) has Save As semantics: it re-points the project's file name
    at `path`. Live-confirmed on QGIS 4.2.2, 2026-09-30 (rc7 smoke test): after one
    isolated execute_pyqgis_script call the QGIS title bar read "*live_snapshot",
    QgsProject.instance().fileName() returned
    ".../Temp/cartogen_isolation_xxxx/live_snapshot.qgz", and every later tool that
    derives an output folder from the project home (export_layer, downloads) wrote into
    that temp folder -- which run_isolated_script deletes in its `finally`, taking the
    user's exports with it. A plain Ctrl+S would also have saved into that vanished
    folder instead of the user's project. This function's caller previously documented
    "never touches the live QgsProject singleton", which was wrong for exactly this
    reason. The file name and dirty flag are restored in a `finally` so a failed write
    cannot leave the project renamed either."""
    original_file_name = live.fileName()
    was_dirty = live.isDirty()
    try:
        live.write(snapshot_path)
    finally:
        live.setFileName(original_file_name)
        live.setDirty(was_dirty)


def _build_scratch_project(tempdir):
    """Snapshots the live project into a scratch copy where every MEMORY-provider
    layer's data is exported to a real GPKG file and swapped in, so the worker
    process actually receives its features. Leaves the live QgsProject singleton's layers
    untouched and restores its file name and dirty flag after serializing it (see
    _write_snapshot_of_live_project for why that restore is needed).

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
    _write_snapshot_of_live_project(live, snapshot_path)

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

    repointed = _copy_file_backed_layers(scratch, live, tempdir, set(memory_layer_ids))
    _lock_uncopyable_layers(scratch, set(memory_layer_ids) | set(repointed))

    scratch_path = os.path.join(tempdir, "scratch_project.qgz")
    scratch.write(scratch_path)
    return scratch_path, memory_layer_ids


def local_file_path(source):
    """The on-disk file a layer source string points at ("path" or "path|layername=x"), or None when it is not a local file
    (database, web service, virtual layer, vsicurl...). Pure apart from the existence check."""
    if not source:
        return None
    text = str(source).split("|", 1)[0]
    if "://" in text or text.startswith("/vsi") or text.lower().startswith(("dbname=", "pg:", "wfs:", "url=")):
        return None
    return text if os.path.isfile(text) else None


def _copy_file_backed_layers(scratch, live, tempdir, already_handled):
    """Rc20 audit A06: the scratch project used to reference the SAME files as the live project, so a script that opened an
    existing layer for editing wrote straight into the user's data (no undo, concurrent with the live layer's own handle). Every
    local-file vector layer is now exported to a GeoPackage in `tempdir` and every local-file raster copied there, and the
    scratch layer repointed at the copy: the worker can read everything and damage nothing. Layers backed by a database or web
    service are NOT copied (they have no file to copy) and remain writable by the script. Returns the ids repointed."""
    repointed = []
    for layer_id, layer in list(scratch.mapLayers().items()):
        if layer_id in already_handled:
            continue
        try:
            if not hasattr(layer, "providerType"):
                continue
            provider = layer.providerType()
            live_layer = live.mapLayer(layer_id) or layer
            path = local_file_path(live_layer.source())
            if path is None:
                continue
            if provider == "ogr":
                copy_path = os.path.join(tempdir, f"ro_{layer_id}.gpkg")
                _export_layer_to_gpkg(live_layer, copy_path)
                layer.setDataSource(copy_path, layer.name(), "ogr")
            elif provider == "gdal":
                copy_path = os.path.join(tempdir, f"ro_{layer_id}{os.path.splitext(path)[1]}")
                shutil.copy2(path, copy_path)
                layer.setDataSource(copy_path, layer.name(), "gdal")
            else:
                continue
            repointed.append(layer_id)
        except Exception as exc:   # a layer that cannot be copied stays as-is rather than failing the whole script run
            log_event("script_isolation", tag="Tools", status="copy_skipped", error=True, error_class=type(exc).__name__)
    return repointed


def _lock_uncopyable_layers(scratch, handled):
    """Marks every vector layer that is neither a copy nor a re-exported memory layer read-only in the scratch project (#220, A06).

    Database and web-service layers have no file to copy, so the worker reaches the real source. Read-only is written into the
    scratch project file, so startEditing() refuses in the worker and a script can read the layer but not change it. A script's own
    new layers are unaffected. Returns the ids locked. A layer that rejects the flag is left as it was and logged."""
    locked = []
    for layer_id, layer in list(scratch.mapLayers().items()):
        if layer_id in handled or not hasattr(layer, "setReadOnly") or not hasattr(layer, "providerType"):
            continue
        try:
            layer.setReadOnly(True)
            locked.append(layer_id)
        except Exception as exc:
            log_event("script_isolation", tag="Tools", status="lock_skipped", error=True, error_class=type(exc).__name__)
    return locked


# --- result adoption ---------------------------------------------------------------------------------------------------------
# GitHub #145 / #146 (audit F09, F10). The first reconcile (a) cloned each new layer, which kept the OGR source URI inside the
# worker's temporary directory that run_isolated_script deletes in its `finally`, so the live layer's data could vanish or leak a
# locked file; and (b) treated an equal feature COUNT as "no change", so a script that updated an attribute or a geometry
# reported success and the live layer kept its old value. Now new vector layers are copied into live-owned memory layers before
# the directory goes, new rasters are copied to a kept location, and a pre-existing memory layer is compared by schema and
# content and replaced atomically, with the original restored if any step fails.

KEPT_OUTPUT_DIR_NAME = "cartogen_script_outputs"


def source_is_under(source, directory):
    """True when a layer source string ("path" or "path|layername=x") points inside `directory`. Pure."""
    if not source or not directory:
        return False
    path = os.path.normcase(os.path.abspath(str(source).split("|", 1)[0]))
    root = os.path.normcase(os.path.abspath(directory))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:                    # different drives on Windows
        return False


def _normalize_value(value):
    """Comparable text for an attribute value; every NULL spelling is the same. Pure."""
    if value is None:
        return ""
    text = str(value)
    if text in ("NULL", "None"):
        return ""
    if isinstance(value, float):
        return repr(round(value, 9))
    return text


def content_signature(field_names, rows):
    """(field names, sorted rows) for comparing two copies of a layer; `rows` is an iterable of (attributes, wkb_hex).
    Feature ids are ignored (a GeoPackage round trip renumbers them). Pure."""
    normalized = sorted((tuple(_normalize_value(v) for v in attrs), wkb or "") for attrs, wkb in rows)
    return (tuple(field_names), normalized)


def _layer_signature(layer, skip_fields=()):
    skip = {n.lower() for n in skip_fields}
    keep = [i for i, fld in enumerate(layer.fields()) if fld.name().lower() not in skip]
    rows = []
    for f in layer.getFeatures():
        geom = f.geometry()
        wkb = bytes(geom.asWkb()).hex() if geom is not None and not geom.isEmpty() else ""
        attrs = f.attributes()
        rows.append(([attrs[i] for i in keep], wkb))
    return content_signature([layer.fields().at(i).name() for i in keep], rows)


def _same_content(live_layer, result_layer):
    """True when the two layers hold the same fields and features. The result copy has been through a GeoPackage, which adds its
    own `fid` primary-key column; that column is ignored when only one side has it (CI run 37163181576 showed an untouched memory
    layer reported as 'updated' because of it)."""
    live_names = {f.name().lower() for f in live_layer.fields()}
    result_names = {f.name().lower() for f in result_layer.fields()}
    skip = ("fid",) if ("fid" in live_names) != ("fid" in result_names) else ()
    return _layer_signature(live_layer, skip) == _layer_signature(result_layer, skip)


def _detach_vector_layer(layer):
    """A live-owned memory copy of a vector layer (fields, features, CRS, name, renderer), independent of the layer's source."""
    from qgis.core import QgsFeature, QgsVectorLayer, QgsWkbTypes
    geometry = QgsWkbTypes.displayString(layer.wkbType()) if layer.isSpatial() else "none"
    copy = QgsVectorLayer(geometry, layer.name(), "memory")
    if layer.isSpatial():
        copy.setCrs(layer.crs())
    provider = copy.dataProvider()
    if not provider.addAttributes(layer.fields().toList()):
        raise RuntimeError("could not copy the field definitions")
    copy.updateFields()
    features = []
    for src in layer.getFeatures():
        dst = QgsFeature(copy.fields())
        dst.setGeometry(src.geometry())
        dst.setAttributes(src.attributes())
        features.append(dst)
    ok, _added = provider.addFeatures(features)
    if not ok:
        raise RuntimeError("could not copy the features")
    copy.updateExtents()
    try:
        if layer.renderer() is not None:
            copy.setRenderer(layer.renderer().clone())
    except Exception:
        pass            # the data matters more than the symbology
    return copy


def _keep_raster(layer):
    """A raster layer whose file has been copied out of the scratch directory, or raises."""
    from qgis.core import QgsRasterLayer
    source = str(layer.source()).split("|", 1)[0]
    kept_dir = os.path.join(tempfile.gettempdir(), KEPT_OUTPUT_DIR_NAME, uuid.uuid4().hex)
    os.makedirs(kept_dir, exist_ok=True)
    target = os.path.join(kept_dir, os.path.basename(source))
    shutil.copy2(source, target)
    kept = QgsRasterLayer(target, layer.name())
    if not kept.isValid():
        raise RuntimeError("the copied raster is not valid")
    return kept


def _replace_memory_layer(live_layer, result_layer):
    """Replaces a live memory layer's schema and features with `result_layer`'s, restoring the original if any step fails.
    Raises RuntimeError if even the restore fails."""
    from qgis.core import QgsFeature
    provider = live_layer.dataProvider()
    original_fields = live_layer.fields().toList()
    original_features = list(live_layer.getFeatures())
    new_names = [f.name() for f in result_layer.fields()]
    schema_changed = new_names != [f.name() for f in original_fields]

    def load(fields, features):
        if not provider.truncate():
            raise RuntimeError("could not clear the layer")
        if schema_changed or fields is original_fields:
            current = list(range(live_layer.fields().count()))
            if current and not provider.deleteAttributes(current):
                raise RuntimeError("could not remove the old fields")
            if not provider.addAttributes(fields):
                raise RuntimeError("could not write the field definitions")
            live_layer.updateFields()
        rebuilt = []
        for src in features:
            dst = QgsFeature(live_layer.fields())
            dst.setGeometry(src.geometry())
            dst.setAttributes(src.attributes())
            rebuilt.append(dst)
        ok, _added = provider.addFeatures(rebuilt)
        if not ok:
            raise RuntimeError("could not write the features")

    new_features = list(result_layer.getFeatures())
    try:
        load(result_layer.fields().toList(), new_features)
    except Exception as first:
        try:
            load(original_fields, original_features)
        except Exception as second:
            raise RuntimeError(f"update failed ({first}) and the original could not be restored ({second})")
        raise RuntimeError(f"update failed and the original was restored: {first}")
    live_layer.updateExtents()
    live_layer.triggerRepaint()


def _reconcile_results(result_project_path, pre_call_layer_ids, memory_layer_ids):
    """Loads the worker's resulting project and applies two, and only two, kinds of change back to the LIVE project --
    everything else a script could theoretically do (remove/reorder layers, edit styles) is not reconciled; see this
    module's docstring for why that is the deliberate Phase 1 scope, not an oversight.

    1. A layer id present in the result but not in the pre-call live project is a new layer the script created. A vector layer
       whose data sits in the scratch directory becomes a memory copy owned by the live project; a raster is copied to a kept
       folder; a layer that points at a file outside the scratch directory (the script opened an existing file) is cloned as is.
    2. A pre-existing MEMORY layer whose schema or content differs from the exported copy (compared by values and geometry,
       not by feature count) has its live features replaced atomically.

    Returns (new_layer_names, updated_memory_layer_names, problems); `problems` lists anything that could not be applied, so
    the caller can say so instead of reporting a clean success."""
    live = QgsProject.instance()
    result_scratch = QgsProject()
    result_scratch.read(result_project_path)
    scratch_dir = os.path.dirname(result_project_path)

    new_layers_added, problems = [], []
    for layer_id, layer in result_scratch.mapLayers().items():
        if layer_id in pre_call_layer_ids:
            continue
        try:
            if source_is_under(layer.source(), scratch_dir):
                if hasattr(layer, "bandCount"):
                    adopted = _keep_raster(layer)
                else:
                    adopted = _detach_vector_layer(layer)
            else:
                adopted = layer.clone()
        except Exception as e:
            problems.append(f"new layer '{layer.name()}' could not be kept: {e}")
            continue
        live.addMapLayer(adopted)
        new_layers_added.append(adopted.name())

    memory_layers_updated = []
    for layer_id in memory_layer_ids:
        if layer_id not in pre_call_layer_ids:
            continue
        live_layer = live.mapLayer(layer_id)
        result_layer = result_scratch.mapLayer(layer_id)
        if live_layer is None or result_layer is None:
            continue
        try:
            if _same_content(live_layer, result_layer):
                continue
            _replace_memory_layer(live_layer, result_layer)
        except Exception as e:
            problems.append(f"changes to layer '{live_layer.name()}' were not applied: {e}")
            continue
        memory_layers_updated.append(live_layer.name())

    return new_layers_added, memory_layers_updated, problems


# Widened 20 -> 60, 2026-09-28: the 20s figure was sized off Docker's own cold-start
# measurement (~1.18s, see SECURITY.md 1b) -- a real desktop QGIS install can be much
# slower to cold-start a worker (more bundled plugins/providers to register, disk I/O
# contention with the already-running main QGIS process, antivirus scanning a freshly
# spawned python.exe). Live-reported, same day: a real Windows QGIS 4.2.2 session, on
# its FIRST execute_pyqgis_script call of the session (a true cold start, not a warm
# worker), got killed at 20s with EMPTY stderr -- no traceback, no crash evidence, just
# "didn't answer in time" -- consistent with a legitimately slow but otherwise healthy
# cold start, not a hang. The two failure modes this handshake exists to catch (a wrong
# interpreter lookup spawning the QGIS binary itself; a real crash) are covered
# independently of this timeout's value: the QGIS-binary case is caught by the
# _QGIS_BINARY_BASENAMES basename check above BEFORE this handshake ever starts
# waiting, and a genuine crash still shows up immediately via _kill_and_drain_stderr's
# captured stderr, not after a long wait. So there is no real downside to being more
# patient here, and 60 gives a real desktop install the same budget as one full job.
_WORKER_HANDSHAKE_TIMEOUT_SECONDS = 60


class _IsolationWorker:
    """Manages one persistent worker subprocess. Started lazily on first use and
    kept alive across calls -- Phase 0 benchmarking (scoping doc §8) measured a
    cold spawn-per-call at ~5s, almost entirely `import qgis.core`'s fixed cost,
    which is why this is a persistent worker rather than one process per call."""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()

    def _ensure_started(self):
        """Returns None on success, or an error dict if the worker could not be
        started/confirmed alive. Does a READY handshake (§
        _WORKER_HANDSHAKE_TIMEOUT_SECONDS) rather than relying on the first real
        job's timeout to notice a dead or wrong-binary worker -- see
        find_python_interpreter()'s docstring and _QGIS_BINARY_BASENAMES for the
        failure mode this specifically catches: a wrong interpreter lookup
        silently spawning the QGIS binary itself, which never answers and
        previously hung for the FULL job timeout (live-reported, 2026-09-28)
        with nothing in the logs to explain it. That specific failure mode is
        caught by the basename check below, BEFORE this handshake ever starts
        waiting -- so this handshake's own timeout doesn't need to be short to
        catch it; see _WORKER_HANDSHAKE_TIMEOUT_SECONDS's own comment for why
        it was later widened from a too-impatient 20s."""
        if self._proc is not None and self._proc.poll() is None:
            return None
        interpreter = find_python_interpreter()
        if Path(interpreter).name in _QGIS_BINARY_BASENAMES:
            return {
                "error": (
                    f"Refusing to start the isolation worker: interpreter lookup resolved to "
                    f"'{interpreter}', which looks like the QGIS application binary itself, not "
                    "a Python interpreter -- spawning it would hang rather than run a script. "
                    "This is the exact upstream QGIS bug find_python_interpreter() works around "
                    "(sys.executable is the QGIS binary inside a real desktop session); its "
                    "search did not find a real bundled interpreter on this install. Report this "
                    "install's QGIS version/OS so the lookup can be widened."
                )
            }
        env = _build_worker_environment()
        try:
            self._proc = subprocess.Popen(
                [interpreter, "-m", "cartogen_ai.core.agent.services._script_isolation_worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
                cwd=tempfile.gettempdir(),
                # Live-reported, 2026-09-28: a visible (blank) console window opened during
                # the isolation call on real Windows QGIS. stdin/stdout/stderr are already
                # fully redirected to pipes here, so nothing was ever meant to appear in
                # that window -- it's just Windows' default behavior of allocating a new
                # console for a spawned console-subsystem process (python.exe) when the
                # parent (QGIS, a GUI app) has none of its own to inherit. CREATE_NO_WINDOW
                # suppresses that allocation entirely; it doesn't exist on non-Windows
                # platforms, so getattr's default of 0 there is a deliberate no-op (0 is
                # the only creationflags value subprocess.Popen accepts on POSIX at all --
                # anything else raises ValueError there).
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as e:
            return {"error": f"Could not spawn the isolation worker via interpreter '{interpreter}': {e}"}

        ready_line = self._read_line_with_timeout(_WORKER_HANDSHAKE_TIMEOUT_SECONDS)
        if ready_line is None:
            stderr = self._kill_and_drain_stderr()
            return {
                "error": (
                    f"Isolation worker did not answer within {_WORKER_HANDSHAKE_TIMEOUT_SECONDS}s "
                    f"of starting (interpreter: '{interpreter}') -- it was killed rather than left "
                    f"to hang for the full per-job timeout. Worker stderr, if any: {stderr[:2000]}"
                )
            }
        try:
            ready = json.loads(ready_line)
        except json.JSONDecodeError:
            stderr = self._kill_and_drain_stderr()
            return {"error": f"Isolation worker's startup response was not valid JSON: {ready_line!r}. stderr: {stderr[:2000]}"}
        if not ready.get("ready"):
            stderr = self._kill_and_drain_stderr()
            return {"error": f"Isolation worker started but did not report ready: {ready}. stderr: {stderr[:2000]}"}
        return None

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

    def _kill_and_drain_stderr(self):
        """Kill the worker and return whatever it had written to stderr --
        in that order, deliberately: a still-running process's stderr pipe
        isn't at EOF yet, so reading it while the process is still alive
        just blocks (a real bug this fixed, 2026-09-28 -- see _drain_stderr's
        docstring). Killing first closes the write end from the OS's side,
        so the read below reaches EOF immediately instead of hanging."""
        proc = self._proc
        self._kill()
        return self._drain_stderr(proc)

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
            start_error = self._ensure_started()
            if start_error is not None:
                return start_error
            try:
                self._proc.stdin.write(json.dumps(job) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                stderr = self._kill_and_drain_stderr()
                return {"error": f"Isolation worker was not running when the job was sent (crashed?): {stderr[:2000]}"}

            line = self._read_line_with_timeout(timeout)
            if line is None:
                stderr = self._kill_and_drain_stderr()
                detail = f" Worker stderr: {stderr[:2000]}" if stderr.strip() else ""
                return {"error": f"Script exceeded the {timeout}s isolation timeout and the worker was terminated.{detail}"}
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                stderr = self._kill_and_drain_stderr()
                return {"error": f"Isolation worker produced an unreadable response (crashed?): {stderr[:2000]}"}

    def _drain_stderr(self, proc):
        """Best-effort read of everything `proc` wrote to stderr. Must be called
        AFTER the process has already been killed/exited (see
        _kill_and_drain_stderr) -- NOT implemented with select.select() on the
        pipe, which is a real, confirmed cross-platform bug fixed here
        2026-09-28: Windows' select() only supports sockets, not the plain
        pipes subprocess.PIPE gives on that platform, so the original
        select()-guarded version silently returned "" on every Windows call
        (caught by its own broad except Exception) -- stderr capture was
        never actually working there, exactly the gap that left a live-
        reported Windows timeout with zero diagnostic information. Reading
        AFTER kill (rather than before, via a background thread racing a
        still-open pipe) means a plain blocking .read() correctly reaches EOF
        immediately instead of hanging or needing another thread at all."""
        if proc is None or proc.stderr is None:
            return ""
        try:
            return proc.stderr.read() or ""
        except Exception:
            return ""

    def shutdown(self):
        with self._lock:
            self._kill()


_worker = _IsolationWorker()


def shutdown_worker():
    """Stop the isolation worker process, if one is running. Called when the plugin unloads (audit F31, #167)."""
    _worker.shutdown()


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

        new_layers, updated_memory_layers, problems = _reconcile_results(result_path, pre_call_layer_ids, memory_layer_ids)
        if new_layers or updated_memory_layers or problems:
            log_event(
                "isolated_script_reconciled",
                tag="ScriptIsolation",
                new_layers=len(new_layers),
                updated_memory_layers=len(updated_memory_layers),
                problems=len(problems),
            )
        reply = {"success": True, "result": response.get("result")}
        if problems:
            # Never a clean success when part of the script's work could not be brought back (#145 / #146).
            reply["warning"] = "Part of the script's changes could not be applied to your project: " + "; ".join(problems)
        return reply
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
