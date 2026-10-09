# -*- coding: utf-8 -*-
"""Opt-in evidence folder for one request: what was asked, every tool call with its real arguments and result, how long it took, which
layers it created, the final reply, a canvas screenshot, and copies of the files it wrote (each with a SHA-256).

Why: a hand test or an acceptance run is only as good as what can be re-checked afterwards. Screenshots and logs kept by hand are lost or
disagree with what actually ran. This writes them next to the project, one folder per request, so a result can be compared with an
independent GIS calculation later and a failure can be reproduced.

Privacy, deliberately different from core/logger.py: the logs are metadata-only by policy, but this folder holds RAW arguments and results
(coordinates, attribute values, file paths). So it is OFF by default, switched on in Settings with that warning, written only into the
project's own folder (or the profile export folder for an unsaved project), and secret-looking values are still redacted. Nothing is
uploaded anywhere. Not hand-tested in the QGIS UI."""
import datetime
import hashlib
import json
import os
import shutil

MAX_RESULT_CHARS = 20000
MAX_COPY_BYTES = 50 * 1024 * 1024
MAX_TOTAL_COPY_BYTES = 200 * 1024 * 1024
PATH_KEYS = ("path", "output_path", "file_path", "local_path", "export_path", "output_file")


def _redact(text):
    try:
        from ..logger import _redact as redact
        return redact(text)
    except Exception:
        return text


def _dump(value, limit):
    text = json.dumps(value, default=str, ensure_ascii=False)
    if len(text) > limit:
        text = text[:limit] + '..."(truncated)"'
    return _redact(text)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def output_files(result):
    """Existing files a tool result points at (a few well-known keys, top level only). Pure apart from the filesystem check."""
    if not isinstance(result, dict):
        return []
    found = []
    for key in PATH_KEYS:
        value = result.get(key)
        if isinstance(value, str) and os.path.isfile(value) and value not in found:
            found.append(value)
    return found


class EvidenceRecorder:
    def __init__(self, folder, query, now=None):
        self.folder = folder
        self.query = query
        self.started = now or datetime.datetime.now().astimezone()
        self.calls = []
        self._copied = 0
        os.makedirs(self.folder, exist_ok=True)
        self._jsonl = os.path.join(self.folder, "steps.jsonl")

    def record_call(self, tool, arguments, result, elapsed_ms, new_layers=()):
        entry = {"n": len(self.calls) + 1, "tool": tool, "elapsed_ms": int(elapsed_ms),
                 "ok": not (isinstance(result, dict) and "error" in result),
                 "status": result.get("status") if isinstance(result, dict) else None,
                 "new_layers": list(new_layers), "outputs": output_files(result)}
        self.calls.append(entry)
        args_text = _dump(arguments, MAX_RESULT_CHARS)
        line = dict(entry, arguments=json.loads(args_text) if _is_json(args_text) else args_text, result=_dump(result, MAX_RESULT_CHARS))
        with open(self._jsonl, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, default=str, ensure_ascii=False) + "\n")

    def _copy_outputs(self):
        manifest = []
        out_dir = os.path.join(self.folder, "outputs")
        for call in self.calls:
            for src in call["outputs"]:
                size = os.path.getsize(src)
                entry = {"source": src, "bytes": size, "step": call["n"]}
                if size > MAX_COPY_BYTES or self._copied + size > MAX_TOTAL_COPY_BYTES:
                    entry["copied"] = False
                    entry["note"] = "not copied (size limit); the original is at the source path"
                    try:
                        entry["sha256"] = sha256_of(src)
                    except OSError:
                        pass
                else:
                    os.makedirs(out_dir, exist_ok=True)
                    dest = os.path.join(out_dir, f"{call['n']:02d}_{os.path.basename(src)}")
                    shutil.copy2(src, dest)
                    self._copied += size
                    entry.update(copied=True, copy=os.path.relpath(dest, self.folder), sha256=sha256_of(dest))
                manifest.append(entry)
        return manifest

    def finish(self, final_text, usage_line="", screenshot_fn=None):
        """Write summary.md, manifest.json and (if possible) screenshot.png. Returns the folder. Never raises."""
        manifest = {"started": self.started.isoformat(timespec="seconds"), "files": []}
        try:
            manifest["files"] = self._copy_outputs()
        except OSError as e:
            manifest["copy_error"] = str(e)
        shot = os.path.join(self.folder, "screenshot.png")
        try:
            if screenshot_fn is not None and screenshot_fn(shot) and os.path.isfile(shot):
                manifest["screenshot"] = {"file": "screenshot.png", "sha256": sha256_of(shot)}
        except Exception as e:
            manifest["screenshot_error"] = f"{type(e).__name__}"
        lines = [f"# Evidence for one request ({manifest['started']})", "", "## Request", "", _redact(self.query or ""), "",
                 "## Steps", "", "| # | Tool | OK | ms | Status | New layers | Output files |", "|---|---|---|---|---|---|---|"]
        for c in self.calls:
            lines.append(f"| {c['n']} | `{c['tool']}` | {'yes' if c['ok'] else 'NO'} | {c['elapsed_ms']} | {c['status'] or ''} | "
                         f"{', '.join(c['new_layers'])} | {', '.join(os.path.basename(o) for o in c['outputs'])} |")
        if not self.calls:
            lines.append("| - | (no tool calls) | | | | | |")
        lines += ["", "## Final reply", "", _redact(final_text or ""), ""]
        if usage_line:
            lines += ["## Usage", "", usage_line, ""]
        lines += ["## Files", "", "`steps.jsonl` has the full arguments and results of every call; `manifest.json` lists copied files with SHA-256.", ""]
        with open(os.path.join(self.folder, "summary.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        with open(os.path.join(self.folder, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        return self.folder


def _is_json(text):
    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def relative_folder(turn_label, now=None):
    """cartogen_evidence/<timestamp>_<label>, relative: resolve_output_path anchors it to the project folder. Pure."""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    return os.path.join("cartogen_evidence", f"{stamp}_{turn_label}")
