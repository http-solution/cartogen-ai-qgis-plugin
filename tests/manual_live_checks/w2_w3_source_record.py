"""Smoke rows W2 (a fetched layer gets result checks and a source record) and W3 (the provenance record and the spatial report print the data source) driven in a real QGIS
(offscreen; written 2026-11-27). Needs internet. Run it inside the QGIS 4.2.2 image CI uses, with the repository mounted, for example:
docker run --rm --network host -e QT_QPA_PLATFORM=offscreen -v "$PWD":/repo:ro qgis/qgis@<digest from .github/workflows/tests.yml> python3 /repo/tests/manual_live_checks/w2_w3_source_record.py
Result on 2026-11-27: the rc5 code answered success with NO layer (the owner's W2/W3 symptom, the truncated streamed download of BUG-2026-11-26-5); the current code adds the layer with its
cartogen/sources record (licence_checked false) and cartogen/checks, the provenance record names the source, and the report has a 'Data source:' line. Not a unit test (it uses the network)."""
# ruff: noqa: E402
import json
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)
from qgis.core import QgsApplication, QgsProject
app = QgsApplication([b"w2w3"], False)
QgsApplication.setPrefixPath("/usr", True)
app.initQgis()
sys.path.insert(0, os.path.join(QgsApplication.pkgDataPath(), "python", "plugins"))
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
QgsProject.instance().clear()
agent = agent_mod.CartogenAi()
print("== W2: fetch the admin level 1 boundaries for Yemen from geoBoundaries")
r = agent._execute_tool("fetch_geoboundaries", json.dumps({"iso3": "YEM", "admin_level": "ADM1"}))
print("  result:", {k: str(v)[:100] for k, v in r.items() if k in ("success", "error", "layer_name", "status", "checks_summary")})
layers = list(QgsProject.instance().mapLayers().values())
print("  layers:", [(layer.name(), layer.isValid(), layer.featureCount()) for layer in layers])
lyr = layers[0] if layers else None
if lyr:
    src = lyr.customProperty("cartogen/sources")
    chk = lyr.customProperty("cartogen/checks")
    print("  cartogen/sources present:", bool(src), "| cartogen/checks present:", bool(chk))
    try:
        s = json.loads(src) if isinstance(src, str) else src
        e = s[0] if isinstance(s, list) else s
        print("  source record:", json.dumps({k: e.get(k) for k in ("name", "url", "licence", "licence_checked", "retrieved_at", "fetched", "coverage") if k in e}, indent=None)[:420])
        print("  W2 PASS?", all(k in e for k in ("name", "url", "licence")) and e.get("licence_checked") is False and bool(chk))
    except Exception as ex:
        print("  could not read the source record:", ex, str(src)[:200])
    print("  checks:", str(chk)[:260])
    print("== W3: provenance record of that layer")
    p = agent._execute_tool("get_provenance_record", json.dumps({"layer_name": lyr.name()}))
    txt = json.dumps(p, default=str)
    urls = [e.get("url", "") for e in (p.get("sources") or p.get("data_sources") or []) if isinstance(e, dict)] if isinstance(p, dict) else []
    hosts = [urlparse(u).hostname for u in urls]          # compared as a host name, never as a substring of the whole record
    print("  record mentions geoBoundaries:", "geoBoundaries" in txt, "| source hosts:", hosts, "| licence:", "CC BY" in txt, "| says not checked:", ("not checked" in txt.lower()) or ('"licence_checked": false' in txt))
    print("  record (start):", txt[:420])
    print("== W3: spatial report titled Source check")
    rep = agent._execute_tool("generate_spatial_report", json.dumps({"title": "Source check", "insights": "The Yemen boundaries come from geoBoundaries.", "source_layers": [lyr.name()]}))
    rt = rep if isinstance(rep, str) else json.dumps(rep, default=str)
    i = rt.find("Data source")
    print("  report has 'Data source:':", "Data source:" in rt, "| mentions geoBoundaries:", "geoBoundaries" in rt, "| says licence verified:", "licence was verified" in rt.lower() or "licence verified" in rt.lower())
    print("  report excerpt:", rt[max(0, i - 40):i + 380].replace("\\n", " | ") if i >= 0 else rt[:400])
app.exitQgis()
