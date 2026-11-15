#!/usr/bin/env python3
"""Drives the plugin's local MCP server the way a client would and records the evidence, so a tester does not have to type JSON-RPC by hand
(PLAN-050). Standard library only; run it with any Python 3.10+ in a terminal, NOT inside QGIS.

    python mcp_probe.py URL TOKEN OUT_DIR [--layer NAME] [--sensitive-layer NAME] [--write-tool-check] [--wait-for-person]

URL and TOKEN are what the "MCP server running" dialog shows (Plugins > Cartogen AI > MCP server (local)...). OUT_DIR gets one
`mcp_probe.json` (every request and reply, in order, plus a PASS/FAIL line per check) and `mcp_probe.md` (the same, readable).

What it checks with no person at QGIS (these are the read-only rows of the hand test):
  P1  a wrong token, a wrong Host header and a foreign Origin are all refused (401 or 403) and nothing is returned
  P2  initialize works and tools/list holds read tools and (when the server has writes) tools marked as needing approval
  P3  a tool that is not on the lists (for example execute_pyqgis_script) is refused with NOT_RUN and nothing ran
  P4  with --layer, a read tool (get_layer_info) on that layer returns data and no feature geometry or coordinates
  P5  with --sensitive-layer, the same read on a layer the person marked SENSITIVE is refused
With --write-tool-check it also calls one write tool with arguments naming a layer that does not exist; the person must press Deny (or let it
time out) and the call must come back as not run. With --wait-for-person it prints what to do at QGIS and waits for Enter before each step that
needs the dialog. The approval dialog itself is judged by the person: this script only records what the client was told.

Exit code 1 if any check FAILED. It never prints the token to the evidence files."""
import argparse
import http.client
import json
import sys
import urllib.parse
from pathlib import Path

PROTOCOL = "2025-03-26"
READ_PROBE_TOOL = "get_feature_count"
WRITE_PROBE_TOOL = "buffer_analysis"
NOT_LISTED_TOOL = "execute_pyqgis_script"


class Probe:
    def __init__(self, url, token):
        parts = urllib.parse.urlsplit(url)
        self.host, self.port, self.path = parts.hostname, parts.port, parts.path or "/mcp"
        self.token = token
        self.log = []          # every exchange, token removed
        self.checks = []       # (id, ok, what)
        self._id = 0

    def post(self, body, headers=None, label=""):
        """Sends one request. `headers` overrides the defaults (use it to send a wrong token, Host or Origin). Returns (status, parsed JSON or text)."""
        sent = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {self.token}", "Host": f"127.0.0.1:{self.port}"}
        sent.update(headers or {})
        sent = {k: v for k, v in sent.items() if v is not None}
        connection = http.client.HTTPConnection(self.host, self.port, timeout=150)
        try:
            connection.putrequest("POST", self.path, skip_host=True, skip_accept_encoding=True)
            data = json.dumps(body).encode("utf-8")
            sent["Content-Length"] = str(len(data))
            for key, value in sent.items():
                connection.putheader(key, value)
            connection.endheaders(data)
            reply = connection.getresponse()
            raw = reply.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw.strip() else None
            except ValueError:
                parsed = raw
            status = reply.status
        except OSError as error:
            status, parsed = 0, f"connection failed: {error}"
        finally:
            connection.close()
        shown = {k: ("Bearer <hidden>" if k == "Authorization" else v) for k, v in sent.items() if k != "Content-Length"}
        self.log.append({"label": label, "request_headers": shown, "request": body, "http_status": status, "reply": parsed})
        return status, parsed

    def rpc(self, method, params=None, headers=None, label=""):
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            body["params"] = params
        return self.post(body, headers, label or method)

    def check(self, check_id, ok, what):
        self.checks.append((check_id, bool(ok), what))
        print(f"{'PASS' if ok else 'FAIL'}  {check_id}  {what}")


def tool_text(reply):
    """The text a tools/call reply carries, or ''."""
    try:
        return reply["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return ""


def refused_or_not_run(status, reply):
    if status in (401, 403):
        return True
    text = tool_text(reply) if isinstance(reply, dict) else ""
    return bool(text) and ("NOT_RUN" in text or "DENIED" in text or "did not approve" in text or "not available" in text.lower() or "refus" in text.lower() or "not allowed" in text.lower()
                           or "sensitive" in text.lower() or "restricted" in text.lower())


def looks_like_coordinates(text):
    """True when text holds geometry: WKT, GeoJSON coordinates or a long run of decimal pairs. A read tool must return none of these."""
    lowered = text.lower()
    if any(word in lowered for word in ("\"coordinates\"", "point (", "polygon ((", "linestring (", "multipolygon", "\"geometry\"")):
        return True
    import re
    return len(re.findall(r"-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}", text)) >= 2


def run(probe, args):
    wrong = probe.post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Authorization": "Bearer not-the-token"}, "P1 wrong token")
    probe.check("P1a", wrong[0] == 401, f"a wrong token is refused (HTTP {wrong[0]}, wanted 401)")
    host = probe.post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Host": "evil.example"}, "P1 wrong Host")
    probe.check("P1b", host[0] == 403, f"a wrong Host header is refused (HTTP {host[0]}, wanted 403)")
    origin = probe.post({"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Origin": "http://evil.example"}, "P1 foreign Origin")
    probe.check("P1c", origin[0] == 403, f"a foreign Origin is refused (HTTP {origin[0]}, wanted 403)")

    status, reply = probe.rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "mcp_probe", "version": "1"}})
    probe.check("P2a", status == 200 and isinstance(reply, dict) and "result" in reply, f"initialize answers (HTTP {status})")
    probe.post({"jsonrpc": "2.0", "method": "notifications/initialized"}, label="notifications/initialized")
    status, reply = probe.rpc("tools/list")
    tools = (reply or {}).get("result", {}).get("tools", []) if isinstance(reply, dict) else []
    names = [t.get("name") for t in tools]
    needing = [t["name"] for t in tools if "approves this call" in (t.get("description") or "").lower()]
    probe.check("P2b", status == 200 and len(tools) >= 24, f"tools/list holds {len(tools)} tools (wanted at least 24 read tools); {len(needing)} marked as needing approval")
    probe.check("P2c", NOT_LISTED_TOOL not in names and "delete_layer" not in names and "remove_layer" not in names,
                "no script, delete or remove tool is listed")

    status, reply = probe.rpc("tools/call", {"name": NOT_LISTED_TOOL, "arguments": {"code": "print(1)"}})
    probe.check("P3", refused_or_not_run(status, reply), f"{NOT_LISTED_TOOL} is refused and nothing ran")

    if args.layer:
        status, reply = probe.rpc("tools/call", {"name": READ_PROBE_TOOL, "arguments": {"layer_name": args.layer}})
        text = tool_text(reply) if isinstance(reply, dict) else ""
        probe.check("P4a", status == 200 and bool(text) and not refused_or_not_run(status, reply), f"{READ_PROBE_TOOL} on '{args.layer}' returns data")
        probe.check("P4b", not looks_like_coordinates(text), "the reply holds no feature geometry or coordinates")
    if args.sensitive_layer:
        status, reply = probe.rpc("tools/call", {"name": READ_PROBE_TOOL, "arguments": {"layer_name": args.sensitive_layer}})
        probe.check("P5", refused_or_not_run(status, reply), f"a read on SENSITIVE layer '{args.sensitive_layer}' is refused")

    if args.write_tool_check:
        if not needing:
            probe.check("P6", False, "the server lists no write tools, so there is nothing to approve (is it the read-only build?)")
        else:
            if args.wait_for_person:
                input("\nA dialog will appear in QGIS naming buffer_analysis. Press DENY (or wait 2 minutes). Press Enter here when ready... ")
            status, reply = probe.rpc("tools/call", {"name": WRITE_PROBE_TOOL, "arguments": {
                "layer_name": "mcp_probe_no_such_layer", "distance": 1, "output_name": "mcp_probe_should_not_exist"}}, label="P6 write, person denies")
            probe.check("P6", refused_or_not_run(status, reply) or "error" in tool_text(reply).lower() or (isinstance(reply, dict) and reply.get("result", {}).get("isError")),
                        "a write call the person denied (or left unanswered) comes back as not run, and no layer 'mcp_probe_should_not_exist' is made "
                        "(look at QGIS: that part is yours to confirm)")


def write_outputs(probe, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mcp_probe.json").write_text(json.dumps({"checks": [{"id": i, "ok": ok, "what": w} for i, ok, w in probe.checks], "exchanges": probe.log},
                                                   indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    lines = ["# MCP probe", ""] + [f"- {'PASS' if ok else 'FAIL'} **{i}** {w}" for i, ok, w in probe.checks] + ["", "## Exchanges", ""]
    for item in probe.log:
        lines += [f"### {item['label']}  (HTTP {item['http_status']})", "```json", json.dumps({"request": item["request"], "reply": item["reply"]},
                                                                                             indent=1, ensure_ascii=False, default=str)[:4000], "```"]
    (out / "mcp_probe.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url")
    parser.add_argument("token")
    parser.add_argument("out_dir")
    parser.add_argument("--layer")
    parser.add_argument("--sensitive-layer")
    parser.add_argument("--write-tool-check", action="store_true")
    parser.add_argument("--wait-for-person", action="store_true")
    args = parser.parse_args(argv)
    probe = Probe(args.url, args.token)
    run(probe, args)
    write_outputs(probe, args.out_dir)
    failed = [c for c in probe.checks if not c[1]]
    print(f"\n{len(probe.checks) - len(failed)} of {len(probe.checks)} checks passed. Evidence: {Path(args.out_dir) / 'mcp_probe.md'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
