"""Evidence collector for the Cartogen AI live smoke test. Runs in the QGIS Python console; makes NO model calls.

    exec(open(r"<PACKAGE>\\tools\\collect_evidence.py", encoding="utf-8").read())
    setup(r"<PACKAGE>\\results")        # once per session: sets the output folder, starts capturing the CartogenAI log
    snap("N1")                          # after each row: log text, screenshots, layer table, project state
    snap("N1", note="what I saw")       # optional one-line note, also written to the row's folder

snap(row) writes results/evidence/<row>/ :
    log_cartogenai.txt   every CartogenAI Log Messages line captured since setup() (all tabs also go to log_all.txt)
    window.png           the whole QGIS window
    canvas.png           the map canvas only
    layers.json/.txt     every layer: name, type, provider, CRS, feature count, fields, extent, filter, edit mode, renderer, visibility
    project.json         project path, CRS, plugin version, QGIS version, python and OS
    plugin_evidence/     the plugin's own evidence folders written since the previous snap (arguments, results and timings of every tool call)
    tools_called.txt     tool names in order, from those folders' steps.jsonl
    note.txt             the note, if given
and copies the log to results/logs/<row>.log and the window shot to results/screens/<row>.png, the names the results CSV refers to.

Status: first real run 2026-10-28 on QGIS 4.2.3: screenshots, layer tables and project state worked; the log files came out EMPTY for every row
(DEF-9), so snap() no longer depends on the log signal for what a row did. It now also copies every plugin evidence folder written since the
previous snap (the plugin's own "save an evidence folder for each request" setting) into plugin_evidence/ and writes tools_called.txt from its
steps.jsonl, which matches folders to rows by time instead of by guessing. The log signal now uses the explicit three-argument overload; whether that
fixes the empty log is NOT verified. Every step is wrapped so a failure goes to snap_errors.txt and the rest still runs.
"""
import contextlib
import datetime
import json
import os
import platform
import shutil
import traceback

_STATE = {"out": None, "lines": [], "connected": False, "last": 0.0}


def _err(text):
    out = _STATE["out"] or os.getcwd()
    with open(os.path.join(out, "snap_errors.txt"), "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now().isoformat()} {text}\n")
    print("collect_evidence:", text)


def _on_message(message, tag, level):
    _STATE["lines"].append((datetime.datetime.now().strftime("%H:%M:%S"), tag, int(level), message))


def setup(out_dir):
    from qgis.core import QgsApplication
    os.makedirs(os.path.join(out_dir, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "logs"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "screens"), exist_ok=True)
    _STATE["out"] = out_dir
    if not _STATE["connected"]:
        from qgis.core import Qgis
        signal = QgsApplication.messageLog().messageReceived
        try:
            signal[str, str, Qgis.MessageLevel].connect(_on_message)  # the overload that carries the text; a bare .connect may bind the bool one
        except Exception:
            signal.connect(_on_message)
        _STATE["connected"] = True
    _STATE["last"] = datetime.datetime.now().timestamp()
    print(f"collect_evidence: ready, writing to {out_dir}. Log capture starts now; call snap('<row>') after each row.")


def _layers():
    from qgis.core import QgsMapLayer, QgsProject, QgsRasterLayer, QgsVectorLayer
    root = QgsProject.instance().layerTreeRoot()
    rows = []
    for layer in QgsProject.instance().mapLayers().values():
        item = {"name": layer.name(), "id": layer.id(), "crs": layer.crs().authid(), "source": layer.source()[:300]}
        node = root.findLayer(layer.id())
        item["visible"] = bool(node.isVisible()) if node else None
        try:
            ext = layer.extent()
            item["extent"] = [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()]
        except Exception:
            item["extent"] = None
        if isinstance(layer, QgsVectorLayer):
            item.update(type="vector", geometry=layer.geometryType().name if hasattr(layer.geometryType(), "name") else str(layer.geometryType()),
                        features=layer.featureCount(), fields=[f.name() for f in layer.fields()], filter=layer.subsetString(),
                        editing=layer.isEditable(), renderer=layer.renderer().type() if layer.renderer() else None)
        elif isinstance(layer, QgsRasterLayer):
            item.update(type="raster", width=layer.width(), height=layer.height(), bands=layer.bandCount(),
                        renderer=layer.renderer().type() if layer.renderer() else None)
        elif isinstance(layer, QgsMapLayer):
            item["type"] = str(layer.type())
        rows.append(item)
    return rows


def _plugin_version():
    try:
        import cartogen_ai
        meta = os.path.join(os.path.dirname(cartogen_ai.__file__), "metadata.txt")
        with open(meta, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("version="):
                    return line.strip()
    except Exception as exc:
        return f"unknown ({exc})"
    return "unknown"


def _copy_plugin_evidence(out):
    """Copies plugin evidence folders newer than the previous snap and lists the tools they called."""
    from qgis.core import QgsProject
    roots = {os.path.join(os.path.dirname(QgsProject.instance().fileName() or ""), "cartogen_evidence")}
    for base, dirs, _files in os.walk(_STATE["out"]):
        if "evidence" in os.path.relpath(base, _STATE["out"]).split(os.sep)[:1]:
            dirs[:] = []
            continue
        roots.update(os.path.join(base, d) for d in dirs if d == "cartogen_evidence")
    tools = []
    for root in sorted(r for r in roots if os.path.isdir(r)):
        for name in sorted(os.listdir(root)):
            folder = os.path.join(root, name)
            if not os.path.isdir(folder) or os.path.getmtime(folder) < _STATE["last"]:
                continue
            shutil.copytree(folder, os.path.join(out, "plugin_evidence", name), dirs_exist_ok=True)
            steps = os.path.join(folder, "steps.jsonl")
            if os.path.exists(steps):
                with open(steps, encoding="utf-8") as fh:
                    for line in fh:
                        with contextlib.suppress(ValueError):
                            tools.append(f"{name}: {json.loads(line).get('tool')}")
    if tools:
        with open(os.path.join(out, "tools_called.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(tools) + "\n")


def snap(row, note=""):
    from qgis.core import Qgis, QgsProject
    from qgis.utils import iface
    if not _STATE["out"]:
        raise RuntimeError("call setup(<results folder>) first")
    out = os.path.join(_STATE["out"], "evidence", str(row))
    os.makedirs(out, exist_ok=True)
    try:
        lines = _STATE["lines"]
        with open(os.path.join(out, "log_all.txt"), "w", encoding="utf-8") as fh:
            fh.writelines(f"{t} [{tag}] L{lvl} {msg}\n" for t, tag, lvl, msg in lines)
        with open(os.path.join(out, "log_cartogenai.txt"), "w", encoding="utf-8") as fh:
            fh.writelines(f"{t} [{tag}] L{lvl} {msg}\n" for t, tag, lvl, msg in lines if "cartogen" in tag.lower() or tag in ("Agent", "Tools"))
        shutil.copyfile(os.path.join(out, "log_cartogenai.txt"), os.path.join(_STATE["out"], "logs", f"{row}.log"))
    except Exception:
        _err(f"{row}: log: {traceback.format_exc(limit=2)}")
    try:
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.processEvents()
        iface.mainWindow().grab().save(os.path.join(out, "window.png"))
        shutil.copyfile(os.path.join(out, "window.png"), os.path.join(_STATE["out"], "screens", f"{row}.png"))
        iface.mapCanvas().saveAsImage(os.path.join(out, "canvas.png"))
    except Exception:
        _err(f"{row}: screenshot: {traceback.format_exc(limit=2)}")
    try:
        layers = _layers()
        with open(os.path.join(out, "layers.json"), "w", encoding="utf-8") as fh:
            json.dump(layers, fh, indent=1, default=str)
        with open(os.path.join(out, "layers.txt"), "w", encoding="utf-8") as fh:
            for lyr in layers:
                fh.write(f"{lyr['name']} | {lyr.get('type')} | {lyr['crs']} | features={lyr.get('features')} | filter={lyr.get('filter')!r} | "
                         f"editing={lyr.get('editing')} | visible={lyr['visible']} | fields={lyr.get('fields')}\n")
    except Exception:
        _err(f"{row}: layers: {traceback.format_exc(limit=2)}")
    try:
        project = {"row": row, "time": datetime.datetime.now().isoformat(), "project_file": QgsProject.instance().fileName(),
                   "project_crs": QgsProject.instance().crs().authid(), "plugin": _plugin_version(), "qgis": Qgis.version(),
                   "python": platform.python_version(), "os": platform.platform(), "layer_count": len(QgsProject.instance().mapLayers()),
                   "evidence_folders_next_to_project": os.path.join(os.path.dirname(QgsProject.instance().fileName() or "."), "cartogen_evidence")}
        with open(os.path.join(out, "project.json"), "w", encoding="utf-8") as fh:
            json.dump(project, fh, indent=1)
    except Exception:
        _err(f"{row}: project: {traceback.format_exc(limit=2)}")
    try:
        _copy_plugin_evidence(out)
    except Exception:
        _err(f"{row}: plugin evidence: {traceback.format_exc(limit=2)}")
    _STATE["last"] = datetime.datetime.now().timestamp()
    if note:
        with open(os.path.join(out, "note.txt"), "w", encoding="utf-8") as fh:
            fh.write(note + "\n")
    print(f"collect_evidence: {row} saved to {out}")
    return out
