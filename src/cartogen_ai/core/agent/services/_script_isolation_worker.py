"""
Persistent worker process for `execute_pyqgis_script` isolation
(see script_isolation.py's module docstring for the full design).

Spawned as `<interpreter> -m cartogen_ai.core.agent.services._script_isolation_worker`
by `_IsolationWorker` in script_isolation.py, with `cartogen_ai`'s own package
parent already on PYTHONPATH. Reads one newline-delimited JSON job per line
from stdin, writes one newline-delimited JSON response per line to stdout,
and loops until stdin closes (the parent process exiting closes it).

This file is trusted, plugin-authored bootstrap code, not the untrusted
model-generated script -- it runs BEFORE the untrusted script does, to set up
the very sandbox (`_validate_script_safety` + `_SAFE_BUILTINS`, imported from
system_tools.py rather than duplicated here) the untrusted script then runs
inside. Importing `cartogen_ai` here does not reopen the "cartogen_ai is a
blocked import" rule in system_tools.py's `_BLOCKED_MODULES` -- that rule
blocks the untrusted SCRIPT from importing it, and is enforced by
`_validate_script_safety` against the script's own source text below, exactly
as it is in-process today.
"""
import contextlib
import io
import json
import os
import sys
import traceback

# A script's print() output is returned to the model, capped so one chatty loop cannot flood the reply.
_MAX_CAPTURED_OUTPUT = 4000


def _init_qgis():
    from qgis.core import QgsApplication

    qgs = QgsApplication([], False)
    qgs.initQgis()
    return qgs


def _run_job(job, local_env_factory):
    from qgis.core import QgsProject

    from cartogen_ai.core.agent.tools.system_tools import _validate_script_safety, _SAFE_BUILTINS

    script = job["script"]
    project_path = job["project_path"]
    result_project_path = job["result_project_path"]

    safety_error = _validate_script_safety(script)
    if safety_error:
        return {"error": f"Script rejected for safety: {safety_error}"}

    project = QgsProject.instance()
    if not project.read(project_path):
        return {"error": f"Isolation worker could not load the serialized project at {project_path}."}

    local_env = local_env_factory()
    local_env["__builtins__"] = _SAFE_BUILTINS
    local_env["__name__"] = "execute_pyqgis_script"

    # print() is an allowed builtin and writes to sys.stdout, which is this worker's reply channel to the parent: one printed line made the
    # parent fail to parse the reply and kill the worker ("unreadable response (crashed?)", DEF-12). The script's output is captured instead
    # and handed back as `printed`, so the model also gets to see it.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            exec(script, local_env)  # noqa: S102  # nosec B102 (this is the isolated worker process; the script runs with restricted builtins after the static safety check)
            if "run" not in local_env:
                return {"error": "Script must define a 'run()' function.", **_printed(captured)}
            result = local_env["run"]()
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc(), **_printed(captured)}

    try:
        # Same fix as script_isolation.py's _build_scratch_project, applied on
        # the way OUT: QgsProject.write() doesn't persist a memory layer's
        # feature data, so a NEW memory layer the script just created (the
        # dominant pattern this tool's own local_env encourages -- create a
        # layer, add features, addMapLayer) would round-trip back to the
        # parent with 0 features unless it's export-and-swapped first, exactly
        # like a pre-existing memory layer is on the way in.
        from cartogen_ai.core.agent.services.script_isolation import _export_layer_to_gpkg

        result_dir = os.path.dirname(result_project_path)
        for layer_id, layer in list(project.mapLayers().items()):
            if hasattr(layer, "providerType") and layer.providerType() == "memory":
                gpkg_path = os.path.join(result_dir, f"out_{layer_id}.gpkg")
                _export_layer_to_gpkg(layer, gpkg_path)
                layer.setDataSource(gpkg_path, layer.name(), "ogr")
        project.write(result_project_path)
    except Exception as e:
        return {"error": f"Script ran but the isolated project could not be saved back: {e}"}

    return {"success": True, "result": result, **_printed(captured)}


def _printed(captured):
    text = captured.getvalue()
    if not text:
        return {}
    return {"printed": text[:_MAX_CAPTURED_OUTPUT] + ("... [truncated]" if len(text) > _MAX_CAPTURED_OUTPUT else "")}


def _encode_response(response):
    """One JSON line for the parent. A script may return a set, a date, a QGIS object: str() those rather than raise, because an
    exception here used to end the worker's loop and the parent then reported a crash (DEF-12). Never raises."""
    try:
        return json.dumps(response, default=str)
    except Exception as e:
        return json.dumps({"error": f"The script ran, but its result could not be sent back as JSON ({type(e).__name__}: {e}). "
                                    "Return plain numbers, text, lists and dicts from run()."})


def serve(lines, out, run_job):
    """The job loop, apart from QGIS so it can be tested: one JSON job per input line, one JSON reply line per job on `out`. A job that
    raises, or whose reply cannot be encoded, yields an error reply and the loop goes on."""
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except json.JSONDecodeError as e:
            out.write(json.dumps({"error": f"Worker received unreadable job: {e}"}) + "\n")
            out.flush()
            continue
        try:
            response = run_job(job)
        except Exception as e:
            response = {"error": f"Isolation worker crashed running the job: {e}", "traceback": traceback.format_exc()}
        out.write(_encode_response(response) + "\n")
        out.flush()


def main():
    from qgis.core import (
        QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature,
        QgsGeometry, QgsPointXY, QgsField, QgsApplication,
    )
    from qgis.PyQt.QtCore import QVariant

    def local_env_factory():
        return {
            "QgsProject": QgsProject,
            "QgsVectorLayer": QgsVectorLayer,
            "QgsRasterLayer": QgsRasterLayer,
            "QgsFeature": QgsFeature,
            "QgsGeometry": QgsGeometry,
            "QgsPointXY": QgsPointXY,
            "QgsField": QgsField,
            "QgsApplication": QgsApplication,
            "QVariant": QVariant,
        }

    try:
        qgs = _init_qgis()
    except Exception as e:
        # No handshake sent -- the parent's startup-handshake timeout
        # (script_isolation.py's _IsolationWorker._ensure_started) will fire
        # and report this via stderr, still far faster than the old full
        # per-job timeout with no explanation at all (live-reported, 2026-09-28).
        sys.stderr.write(f"Isolation worker failed to initialize QGIS: {e}\n{traceback.format_exc()}\n")
        sys.stderr.flush()
        sys.exit(1)

    # The startup handshake script_isolation.py's _ensure_started() waits for
    # -- confirms the worker is a real, responsive Python process running this
    # module, not (for example) the QGIS application binary itself silently
    # spawned by a wrong interpreter-lookup result, which would otherwise sit
    # here forever with no output at all.
    # Replies go to the real stdout; anything else in this process that writes to sys.stdout (a library, a stray print) is discarded
    # rather than mixed into the reply stream. Not sent to stderr: the parent only reads that pipe after killing the worker, so a
    # chatty library could fill the pipe and block the worker.
    protocol_out = sys.stdout
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115 -- must stay open for the life of the process
    protocol_out.write(json.dumps({"ready": True}) + "\n")
    protocol_out.flush()

    try:
        serve(sys.stdin, protocol_out, lambda job: _run_job(job, local_env_factory))
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    main()
