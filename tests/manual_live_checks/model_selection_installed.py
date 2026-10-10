# -*- coding: utf-8 -*-
"""Manual live check of automatic model selection against an INSTALLED plugin, in real QGIS.

Not part of the automated suite (needs QGIS and an installed plugin folder). Run with QGIS's Python:

    set QT_QPA_PLATFORM=offscreen
    "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" tests\\manual_live_checks\\model_selection_installed.py

Two parts:
  1. The user's REAL settings (their profile's QGIS4.ini, opened read-only): the real provider, the
     real model setting, and the real cached model list.
  2. A simulated OpenAI default install (expensive default model, auto), which is the case where
     automatic selection actually saves anything.
Only the outgoing HTTP call is replaced (nothing is sent anywhere) and the credential is a
placeholder, so the output contains no secrets. Paths are printed with the home folder replaced
by "~". It records WHICH MODEL each request goes out with, not what it costs: billed cost against
a real account is measured separately (docs/IMPLEMENTATION_TRACKER.md, API-cost plan item 2).

Environment overrides: CARTOGEN_PLUGINS_DIR, CARTOGEN_QGIS_INI.
"""
import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
PROFILE = os.path.join(APPDATA, "QGIS", "QGIS4", "profiles", "default")
PLUG = os.environ.get("CARTOGEN_PLUGINS_DIR", os.path.join(PROFILE, "python", "plugins"))
INI = os.environ.get("CARTOGEN_QGIS_INI", os.path.join(PROFILE, "QGIS", "QGIS4.ini"))
HOME = os.path.expanduser("~")

from qgis.core import Qgis, QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QSettings  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
from processing.core.Processing import Processing  # noqa: E402
Processing.initialize()
sys.path.insert(0, PLUG)
importlib.import_module("cartogen_ai_plugin")               # the installed plugin's own bootstrap
import cartogen_ai  # noqa: E402


def show(path):
    return path.replace(HOME, "~")


print("QGIS", Qgis.QGIS_VERSION.split("-")[0], "| plugin loaded from:", show(list(cartogen_ai.__path__)[0]))
with open(os.path.join(PLUG, "cartogen_ai_plugin", "metadata.txt"), encoding="utf-8") as f:
    print("plugin version:", next(ln.split("=", 1)[1].strip() for ln in f if ln.startswith("version=")))

import cartogen_ai.core.agent.agent_orchestrator as agent_mod  # noqa: E402
import cartogen_ai.infrastructure.auth as auth  # noqa: E402

results = []


def check(label, cond, detail=""):
    results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), "-", label, "|", detail)


def fake_post_factory(sent):
    def fake_post(url, headers, payload_json, timeout, **kw):
        sent.append(json.loads(payload_json)["model"])
        r = MagicMock()
        r.status_code = 200
        r.raise_for_status.return_value = None
        r.json.return_value = {"choices": [{"message": {"role": "assistant", "content": "ok"}}],
                               "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
        return r
    return fake_post


def run_requests(settings_cls, provider_module, queries):
    sent = []
    with patch.object(agent_mod, "QgsSettings", settings_cls), \
         patch.object(auth.CredentialManager, "get_credential", return_value="placeholder-not-a-key"), \
         patch.object(provider_module, "post_with_retry", side_effect=fake_post_factory(sent)):
        agent = agent_mod.CartogenAi()
        out = []
        for q, expect in queries:
            sent.clear()
            try:
                agent.run(q, map_context={})
                err = None
            except Exception as e:  # a crash here would be a new live error
                err = "%s: %s" % (type(e).__name__, e)
            out.append((q, expect, list(sent), err))
        return agent, out


SPECIAL = ("deep-research", "robotics", "lyria", "antigravity", "computer-use", "banana", "customtools")

# ---- part 1: the user's real settings -------------------------------------------------------
print("\n== Part 1: real profile settings (read-only) ==")
real = QSettings(INI, QSettings.Format.IniFormat)


class RealSettings:
    def value(self, key, default=None, type=None):
        v = real.value(key, default)
        return default if v is None else v

    def setValue(self, *a, **k):
        pass


provider = str(real.value("cartogen_ai/provider", "openrouter"))
print("provider =", provider, "| model setting =", real.value("cartogen_ai/%s_model" % provider))
if provider in ("gemini", "openai", "cartogen"):
    pmod = importlib.import_module("cartogen_ai.infrastructure.providers." + provider)
    listing = real.value("cartogen_ai/%s_model_list" % provider, "")
    print("cached model list:", len(json.loads(listing)) if listing else 0, "models")
    queries = [("list layers", None), ("zoom to Amman", None),
               ("Health facilities beyond one hour's travel 3999682,3756232", None),
               ("buffer the roads and then clip them, then calculate the area of each zone", None)]
    agent, out = run_requests(RealSettings, pmod, queries)
    default = agent._auto_default_model
    check("auto mode active with a default model", agent._auto_model_provider == provider and default, default)
    for q, _, sent, err in out:
        check("agent.run(%r) completes" % q[:38], err is None and len(sent) >= 1, err or sent[:1])
        check("   sends a model, never a special-purpose one", sent and not any(t in sent[0] for t in SPECIAL), sent[:1])
else:
    print("(provider %s does not use automatic selection; part 1 skipped)" % provider)

# ---- part 2: simulated OpenAI default install ------------------------------------------------
print("\n== Part 2: simulated OpenAI default install (expensive default, auto) ==")
OPENAI_LIST = ["gpt-5.6", "gpt-5.2-chat-latest", "gpt-5-mini", "gpt-5-nano", "gpt-5-pro", "o4-mini",
               "gpt-4.1", "gpt-5-codex", "gpt-realtime"]
FAKE = {"cartogen_ai/provider": "openai", "cartogen_ai/openai_model": "auto",
        "cartogen_ai/openai_model_list": json.dumps(OPENAI_LIST)}


class FakeSettings:
    def value(self, key, default=None, type=None):
        return FAKE.get(key, default)

    def setValue(self, *a, **k):
        pass


openai_mod = importlib.import_module("cartogen_ai.infrastructure.providers.openai")
queries = [("list layers", "gpt-5-mini"), ("zoom to Amman", "gpt-5-mini"),
           ("buffer the roads and then clip them, then calculate the area of each zone", "gpt-5.6"),
           ("list layers", "gpt-5-mini")]
agent, out = run_requests(FakeSettings, openai_mod, queries)
check("default model", agent._auto_default_model == "gpt-5.6", agent._auto_default_model)
for q, expect, sent, err in out:
    check("%r -> %s" % (q[:44], expect), err is None and sent[:1] == [expect], err or sent[:1])

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
