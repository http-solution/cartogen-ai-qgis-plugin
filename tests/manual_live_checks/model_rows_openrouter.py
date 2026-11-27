"""Runs rows of docs/FULL_SMOKE_ROWS.json that need a model, end to end in a real QGIS, with the plugin's default OpenRouter provider (written 2026-11-27; the first run is the dry run).

Why: the rows that check which tool the model picks (A5, A6, C1, C3, C4, C6, D4, E2, S5) could only be run by hand on a PC. This runs the real agent loop, the real tools and the real plugin
code in the QGIS image CI uses, and prints for each step the tools the model called, a start of its reply, and the layers afterwards. It asserts nothing: a person reads the output against the
row's Expect text. A step that says 'Apply' is answered by pressing Apply on the pending confirmation (execute_confirmed), like the card's button.

Needs internet and an OpenRouter key that the sandbox PROXY injects (Network secrets for the host openrouter.ai in the cloud environment's settings). The plugin is given only a placeholder key; the
proxy replaces the Authorization header. Never put a real key in this script or in the environment.
Run inside the QGIS 4.2.2 image CI uses, with the repository mounted:
docker run --rm --network host -e MODEL=openai/gpt-4o-mini -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/model_rows_openrouter.py C1 C6
(after trusting the sandbox CA inside the container, as the other manual_live_checks scripts note). MODEL defaults to a cheap model; MAX_STEPS caps the steps per row (default 6).
FIXTURES must name the folder that holds smoke_data.gpkg and smoke_network.gpkg (the test package's 3_test_files: build it with tools/build_computer_use.py and unzip it); without it only the small headless
fixtures exist and rows that load those GeoPackages cannot start. Dry run 2026-11-27 (no key yet): the plugin reached OpenRouter and got 401 "no API key". Not a unit test."""
# ruff: noqa: E402
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsProject, QgsSettings, QgsVectorLayer

app = QgsApplication([b"model-rows"], False)
QgsApplication.setPrefixPath("/usr", True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
from processing.core.Processing import Processing

Processing.initialize()
import make_full_smoke_fixtures as fx

import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.infrastructure.auth import CredentialManager
from cartogen_ai.infrastructure.settings_keys import SETTINGS_OPENROUTER_MODEL, SETTINGS_PROVIDER

MODEL = os.environ.get("MODEL", "openai/gpt-4o-mini")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "6"))
FX = "/tmp/model_rows_fixtures"
if not os.environ.get("FIXTURES"):
    fx.write_all(FX)
settings = QgsSettings()
settings.setValue(SETTINGS_PROVIDER, "openrouter")
settings.setValue(SETTINGS_OPENROUTER_MODEL, MODEL)
CredentialManager.save_credential("openrouter", "placeholder-the-proxy-injects-the-real-key")

with open(os.path.join(ROOT, "docs", "FULL_SMOKE_ROWS.json"), encoding="utf-8") as _f:
    rows = {r["id"]: r for r in json.load(_f)["rows"]}
calls = []
_orig = agent_mod.log_event


def _spy(event, *a, **k):
    if event == "tool_call" and k.get("status") in ("done", "failed"):
        calls.append(f"{k.get('tool')}:{k.get('status')}")
    return _orig(event, *a, **k)


agent_mod.log_event = _spy


def find_dir():
    """The folder holding the fixture files: FIXTURES if set, else the small headless set the writer makes."""
    if os.environ.get("FIXTURES"):
        return os.environ["FIXTURES"]
    for base, _dirs, files in os.walk(FX):
        if "smoke_data.gpkg" in files:
            return base
    return FX


def load_start_layers(row, folder):
    for fname, names in (row.get("layers") or {}).items():
        for n in names:
            lyr = QgsVectorLayer(f"{os.path.join(folder, fname)}|layername={n}", n, "ogr")
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
            else:
                print(f"  (could not load start layer {n} from {fname})")


def steps_of(do):
    """['(1) text', ...] split from 'Send in order: (1) ... (2) ...'."""
    parts = re.split(r"\((\d+)\)\s*", do)
    return [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)] if len(parts) > 2 else [do]


def pending_task(agent):
    tasks = [t for t in agent.task_manager.tasks if t.get("status") == "PREVIEW_READY" and t.get("pending_tool")]
    return max(tasks, key=lambda t: t.get("updated_at", "")) if tasks else None


folder = find_dir()
for row_id in sys.argv[1:] or ["C1"]:
    match = [k for k in rows if k == row_id or k.startswith(row_id + "-")]
    if not match:
        print(f"no such row: {row_id}")
        continue
    row = rows[match[0]]
    print(f"\n######## {match[0]}: {row.get('title', '')}")
    print("EXPECT:", str(row.get("expect", ""))[:600])
    QgsProject.instance().clear()
    load_start_layers(row, folder)
    agent = agent_mod.CartogenAi()
    for n, step in enumerate(steps_of(str(row.get("do", "")))[:MAX_STEPS], 1):
        text = step.replace("<F>", folder)
        del calls[:]
        started = time.time()
        if re.match(r"^(answer\s+)?apply\b", text, re.I):
            task = pending_task(agent)
            out = agent.execute_confirmed(task["pending_tool"], task.get("pending_args", {})) if task else "(nothing pending to Apply)"
            kind = "APPLY"
        else:
            out = agent.run(text)
            kind = "SEND"
        print(f"\n  step {n} [{kind}] {text[:160]}")
        print(f"    tools: {calls}")
        print(f"    reply: {str(out)[:420]}")
        print(f"    layers: {[lyr.name() for lyr in QgsProject.instance().mapLayers().values()]}  ({time.time() - started:.0f}s)")
app.exitQgis()
