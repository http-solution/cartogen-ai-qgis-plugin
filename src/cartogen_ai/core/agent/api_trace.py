# -*- coding: utf-8 -*-
"""Opt-in trace of every model call: the system instruction, the messages sent, the tool names offered, the reply and the usage.

Why: the 2026-10-10 investigation of "13 API calls for List the layers" could not be finished because the exported captures held only the
system instruction (no messages, tools or replies), and the Log Messages panel is metadata-only by policy (core/logger.py), so nothing on
disk showed what a loop actually sent and received. This writes one JSON line per call so a run can be replayed, counted and compared.

Privacy, deliberately unlike core/logger.py: these lines hold RAW prompts, replies, layer and field names, attribute values and tool results.
So it is OFF by default (Settings > "Record every model request and reply"), written only into a local folder next to the project (or the
profile export folder for an unsaved project), never uploaded, and API-key-shaped strings are still redacted. The system instruction is
stored once per distinct text (by SHA-256) and each call line carries its hash, so ~30,000 characters are not repeated on every line and
"which prompt shape was this call" is a one-glance question. Qt-free and QGIS-free; not hand-tested in the QGIS UI."""
import datetime
import hashlib
import json
import os

MAX_MESSAGE_CHARS = 30000
MAX_FILE_BYTES = 100 * 1024 * 1024
FOLDER_NAME = "cartogen_api_trace"


def _redact(text):
    try:
        from ..logger import _redact as redact
        return redact(text)
    except Exception:
        return text


def _clip(text, limit=MAX_MESSAGE_CHARS):
    text = _redact(str(text))
    return text if len(text) <= limit else text[:limit] + f"...[truncated {len(text) - limit} characters]"


def _content_text(content):
    """Message content as text. A list of parts keeps its text parts; an image part becomes a short size note, never the data URL."""
    if content is None or isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, dict) and part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url", "")
                parts.append(f"[image, {len(str(url))} characters of data omitted]")
            else:
                parts.append(f"[{type(part).__name__} part omitted]")
        return "\n".join(parts)
    return str(content)


def _tool_calls(calls):
    out = []
    for call in calls or []:
        fn = (call or {}).get("function", {}) if isinstance(call, dict) else {}
        out.append({"id": (call or {}).get("id") if isinstance(call, dict) else None, "name": fn.get("name"),
                    "arguments": _clip(fn.get("arguments", ""), 8000)})
    return out


def sanitize_message(message):
    """One chat message in the form that is stored. Pure."""
    if not isinstance(message, dict):
        return {"role": "?", "content": _clip(message)}
    out = {"role": message.get("role")}
    content = _content_text(message.get("content"))
    if content is not None:
        out["content"] = _clip(content)
    if message.get("tool_calls"):
        out["tool_calls"] = _tool_calls(message["tool_calls"])
    if message.get("tool_call_id"):
        out["tool_call_id"] = message["tool_call_id"]
    if message.get("name"):
        out["name"] = message["name"]
    return out


def tool_summary(tools):
    names, chars = [], 0
    for tool in tools or []:
        try:
            names.append((tool.get("function") or {}).get("name"))
            chars += len(json.dumps(tool, default=str))
        except Exception:
            continue
    return {"count": len(names), "names": names, "schema_chars": chars}


class ApiTrace:
    def __init__(self, folder):
        self.folder = folder
        self._stopped = False

    def _write_system_text(self, text):
        digest = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        directory = os.path.join(self.folder, "system_instructions")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, digest[:12] + ".txt")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_redact(text))
        return digest[:12]

    def record(self, turn_id, call_index, provider, model, messages, tools, response=None, usage=None, latency_ms=None,
               outcome="ok", error=None, now=None):
        """Appends one call. Never raises. Returns True when a line was written."""
        if self._stopped:
            return False
        try:
            os.makedirs(self.folder, exist_ok=True)
            stamp = now or datetime.datetime.now()
            path = os.path.join(self.folder, f"api_calls_{stamp.strftime('%Y%m%d')}.jsonl")
            if os.path.exists(path) and os.path.getsize(path) > MAX_FILE_BYTES:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"note": "size limit reached; later calls in this file are not recorded"}) + "\n")
                self._stopped = True
                return False
            system_text = ""
            rest = []
            for message in messages or []:
                if isinstance(message, dict) and message.get("role") == "system" and not system_text:
                    system_text = str(_content_text(message.get("content")) or "")
                else:
                    rest.append(sanitize_message(message))
            record = {
                "ts": stamp.isoformat(timespec="milliseconds"), "turn_id": turn_id, "call_index": call_index,
                "provider": provider, "model": model, "outcome": outcome, "latency_ms": latency_ms,
                "system_instruction": {"sha256_12": self._write_system_text(system_text) if system_text else None,
                                       "chars": len(system_text)},
                "messages": rest, "tools": tool_summary(tools),
                "response": sanitize_message(response) if response is not None else None,
                "usage": usage, "error": _clip(error, 2000) if error else None,
            }
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            return True
        except Exception:
            return False


def read_records(path):
    """Records from one .jsonl file or every api_calls_*.jsonl in a folder, in file order. Bad lines are skipped. Pure apart from reading."""
    paths = [path]
    if os.path.isdir(path):
        paths = sorted(os.path.join(path, f) for f in os.listdir(path) if f.startswith("api_calls_") and f.endswith(".jsonl"))
    records = []
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if "turn_id" in data:
                    records.append(data)
    return records


def summarize(records, loop_threshold=6):
    """Per-turn summary rows plus plain-language flags. Pure.

    A row: turn_id, calls, latency_ms, input/cached/output tokens, the distinct system-instruction hashes (more than one in a single turn
    means the prompt was rebuilt mid-turn), tools offered (max), the tool names called in order, and the outcomes. Flags: a turn with
    `loop_threshold` or more calls, the same tool called with the same arguments more than twice, and a non-ok outcome."""
    turns = {}
    for r in records:
        turns.setdefault(r.get("turn_id"), []).append(r)
    rows, flags = [], []
    for turn_id, calls in turns.items():
        calls.sort(key=lambda r: (r.get("call_index") or 0))
        usage = [c.get("usage") or {} for c in calls]
        called, seen = [], {}
        for c in calls:
            for tc in (c.get("response") or {}).get("tool_calls") or []:
                called.append(tc.get("name"))
                key = (tc.get("name"), tc.get("arguments"))
                seen[key] = seen.get(key, 0) + 1
        row = {
            "turn_id": turn_id, "calls": len(calls),
            "latency_ms": sum(c.get("latency_ms") or 0 for c in calls),
            "input_tokens": sum(u.get("input_tokens") or 0 for u in usage),
            "cached_tokens": sum(u.get("cached_tokens") or 0 for u in usage),
            "output_tokens": sum(u.get("output_tokens") or 0 for u in usage),
            "system_hashes": sorted({(c.get("system_instruction") or {}).get("sha256_12") for c in calls} - {None}),
            "system_chars": max(((c.get("system_instruction") or {}).get("chars") or 0 for c in calls), default=0),
            "tools_offered": max(((c.get("tools") or {}).get("count") or 0 for c in calls), default=0),
            "tools_called": called, "outcomes": sorted({c.get("outcome") for c in calls}),
        }
        rows.append(row)
        if len(calls) >= loop_threshold:
            flags.append(f"turn {turn_id}: {len(calls)} model calls ({', '.join(called[:8]) or 'no tools'})")
        repeats = [f"{k[0]} x{n}" for k, n in seen.items() if n > 2]
        if repeats:
            flags.append(f"turn {turn_id}: identical tool call repeated: {', '.join(repeats)}")
        if len(row["system_hashes"]) > 1:
            flags.append(f"turn {turn_id}: the system instruction changed inside one turn ({len(row['system_hashes'])} versions)")
        bad = [o for o in row["outcomes"] if o not in (None, "ok")]
        if bad:
            flags.append(f"turn {turn_id}: non-ok outcome(s): {', '.join(bad)}")
    return rows, flags


def relative_folder():
    return FOLDER_NAME
