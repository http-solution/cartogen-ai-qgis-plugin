"""Evidence collector for the Cartogen AI live smoke test. Runs in the QGIS Python console; makes NO model calls.

    exec(open(r"<PACKAGE>\\tools\\collect_evidence.py", encoding="utf-8").read())
    setup(r"<PACKAGE>\\results")        # once per session: sets the output folder, starts capturing the CartogenAI log
    snap("N1")                          # after each row: log text, screenshots, layer table, project state
    shot("D1-borders")                  # a screenshot of the QGIS window as results/screens/D1-borders.png (for a row that names one)
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
import re
import shutil
import traceback

_STATE = {"out": None, "lines": [], "connected": False, "last": 0.0}


def _err(text):
    out = _STATE["out"] or os.getcwd()
    with open(os.path.join(out, "snap_errors.txt"), "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now().isoformat()} {text}\n")
    print("collect_evidence:", text)


def _level_number(level):
    """The message level as a number, whatever object QGIS hands over. QGIS 4 (PyQt6) passes an Enum member, and int() of a plain Enum raises TypeError:
    DEF-9, the collector's slot died on that before it recorded anything, so every log file of round 3 was empty on QGIS 4.2.3. -1 when unreadable."""
    for candidate in (getattr(level, "value", level), level):
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return -1


def _on_message(message, tag, level):
    """Never raises: a slot that raises is dropped silently by Qt and the line is lost. A line identical to the one just recorded, within a fifth of a
    second, is the same message arriving through a second connection (setup connects every signal form), so it is dropped."""
    try:
        now = datetime.datetime.now()
        line = (str(tag), _level_number(level), str(message))
        previous = _STATE.get("previous")
        if previous and previous[0] == line and (now - previous[1]).total_seconds() < 0.2:
            return
        _STATE["previous"] = (line, now)
        _STATE["lines"].append((now.strftime("%H:%M:%S"), *line))
    except Exception:
        _STATE["lines"].append((datetime.datetime.now().strftime("%H:%M:%S"), "collector", -1, "a log line could not be recorded"))


def _plugin_lines(since):
    """The plugin's own log lines since `since` (epoch seconds) as 'HH:MM:SS [tag] LEVEL text' strings, read from the logger's in-memory buffer; [] when the
    plugin cannot be imported here. DEF-9: this is the path that works on QGIS 4, where the messageReceived signal delivered no text in a live run."""
    for name in ("cartogen_ai.core.logger", "core.logger"):
        try:
            module = __import__(name, fromlist=["recent_lines"])
            return [f"{datetime.datetime.fromtimestamp(t).strftime('%H:%M:%S')} [{tag}] {level} {message}"
                    for t, level, tag, message in module.recent_lines(since=since)]
        except Exception as e:
            _STATE.setdefault("plugin_log_errors", []).append(f"{name}: {type(e).__name__}: {str(e)[:80]}")
    return []


def _log_file_text(lines, connected_forms):
    """The text of a log file: the lines, or one sentence saying none were captured, so an empty result is never silent (DEF-9: 37 of 41 files were just empty)."""
    if lines:
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)
    return (f"(no log line was captured since setup(). {connected_forms} signal form(s) were connected and the plugin's own buffer was empty or could not be read. "
            "Copy the Log Messages tab CartogenAI by hand into results\\logs and say so in the notes.)\n")


def begin(bundle):
    """The one line a tester pastes: begin(r"<bundle folder>"). Evidence goes to <bundle>\\results, where the bundle already has one folder per row."""
    return setup(os.path.join(bundle, "results"))


def _row_folder(row):
    """results/evidence/<full row id>/ for a snap name such as 'W1a' or 'B1' (the bundle ships one folder per row, named by the row id). Falls back to the
    snap name when no folder matches. Pure."""
    head = re.match(r"^([A-Z]\d+)", str(row))              # W1a -> W1, V3 -> V3, and the full smoke package's B1, D2 ... : the first letter and number
    base = os.path.join(_STATE["out"], "evidence")
    if head and os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.startswith(head.group(1) + "-"):
                return os.path.join(base, name, str(row))
    return os.path.join(base, str(row))


def setup(out_dir):
    from qgis.core import QgsApplication
    os.makedirs(os.path.join(out_dir, "evidence"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "logs"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "screens"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "outputs"), exist_ok=True)
    _STATE["out"] = out_dir
    if not _STATE["connected"]:
        from qgis.core import Qgis
        signal = QgsApplication.messageLog().messageReceived
        # DEF-9: on QGIS 4.2.2 a live test saw nothing arrive through the form used here before (explicit enum, then a bare connect on failure). Which form
        # delivers on a given QGIS is not certain, so every form that can be connected is, and _on_message drops the duplicates that follow.
        forms = (lambda: signal[str, str, Qgis.MessageLevel], lambda: signal, lambda: signal[str, str, int], lambda: signal["QString", "QString", "Qgis::MessageLevel"])
        connected = 0
        for pick in forms:
            try:
                pick().connect(_on_message)
                connected += 1
            except Exception as e:                  # this form does not exist in this PyQt build; another may
                _STATE.setdefault("form_errors", []).append(f"{type(e).__name__}: {str(e)[:80]}")
        _STATE["connected"] = connected > 0
        _STATE["forms_connected"] = connected
        if not connected:
            _err("could not connect to QgsApplication.messageLog().messageReceived in any form: no log text will be recorded")
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
    """'version=...' from the metadata.txt above the cartogen_ai package, else 'unknown (why)'. cartogen_ai is a namespace package (no __init__.py), so its
    __file__ is None: the folder comes from __path__ and the search walks up to the plugin folder (hand run 2026-11-04: project.json said 'unknown')."""
    try:
        import cartogen_ai
        folder = os.path.abspath(next(iter(cartogen_ai.__path__)))
        for _ in range(4):
            meta = os.path.join(folder, "metadata.txt")
            if os.path.isfile(meta):
                with open(meta, encoding="utf-8") as fh:
                    for line in fh:
                        if line.startswith("version="):
                            return line.strip()
            folder = os.path.dirname(folder)
    except Exception as exc:
        return f"unknown ({exc})"
    return "unknown (metadata.txt not found above the package)"


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


def shot(name):
    """Saves a screenshot of the whole QGIS window as results/screens/<name>.png (adds .png when missing) and returns the path. For rows that name a
    screenshot file: an agent or a person on a remote desktop cannot always save one by hand (hand run 2026-11-04: eleven named screenshots were missing).
    Opens nothing and changes nothing in QGIS. Raises with a plain sentence when begin() was not run or the window cannot be read."""
    from qgis.PyQt.QtWidgets import QApplication
    from qgis.utils import iface
    if not _STATE["out"]:
        raise RuntimeError("call begin(<bundle folder>) first")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(name)) or "screenshot"
    path = os.path.join(_STATE["out"], "screens", safe if safe.lower().endswith(".png") else safe + ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    QApplication.processEvents()
    if not iface.mainWindow().grab().save(path):
        raise RuntimeError(f"the window could not be saved to {path}")
    print(f"collect_evidence: screenshot saved to {path}")
    return path


def snap(row, note=""):
    from qgis.core import Qgis, QgsProject
    from qgis.utils import iface
    if not _STATE["out"]:
        raise RuntimeError("call setup(<results folder>) first")
    out = _row_folder(row)
    os.makedirs(out, exist_ok=True)
    try:
        lines = _STATE["lines"]
        signal_lines = [f"{t} [{tag}] L{lvl} {msg}\n" for t, tag, lvl, msg in lines]
        plugin_lines = _plugin_lines(_STATE["last"])
        forms = _STATE.get("forms_connected", 0)
        with open(os.path.join(out, "log_all.txt"), "w", encoding="utf-8") as fh:
            fh.write(_log_file_text(signal_lines, forms))
        own_signal = [f"{t} [{tag}] L{lvl} {msg}\n" for t, tag, lvl, msg in lines if "cartogen" in tag.lower() or tag in ("Agent", "Tools")]
        with open(os.path.join(out, "log_cartogenai.txt"), "w", encoding="utf-8") as fh:
            fh.write(_log_file_text(plugin_lines or own_signal, forms))
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
        # PLAN-050: the plugin keeps its checks, data-source records, lineage, sensitivity and status on each layer as `cartogen/*` custom properties.
        # Dumping them lets a row be judged from a file (did the result gate record checks? is the source record there?) with no clicking. Not verified
        # in a real QGIS: written without one; a failure goes to snap_errors.txt like every other step.
        properties = {}
        for lyr in QgsProject.instance().mapLayers().values():
            found = {}
            for key in lyr.customProperties().keys():  # noqa: SIM118  (QgsObjectCustomProperties is not a dict; it has no __iter__)
                if str(key).startswith(("cartogen/", "cartogen_ai/")):          # checks/sources use cartogen/, lineage and sensitivity cartogen_ai/
                    found[str(key)] = lyr.customProperty(key)
            if found:
                properties[lyr.name()] = found
        with open(os.path.join(out, "layer_properties.json"), "w", encoding="utf-8") as fh:
            json.dump(properties, fh, indent=1, default=str)
    except Exception:
        _err(f"{row}: layer properties: {traceback.format_exc(limit=2)}")
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
    expected = ["window.png", "layers.txt", "layer_properties.json", "log_cartogenai.txt", "project.json"]
    missing = [name for name in expected if not os.path.isfile(os.path.join(out, name))]
    print(f"collect_evidence: {row} saved to {out}")
    print("collect_evidence: still yours to add by hand: see CHECKLIST.txt in the row's folder (output files go to results\\outputs\\<row>, screenshots to results\\screens)."
          + (f" NOT SAVED this time: {', '.join(missing)} (see snap_errors.txt)." if missing else ""))
    return out
