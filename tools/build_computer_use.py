"""Builds the computer-use smoke package for a Haiku-class agent driving a real desktop QGIS 4.2.3:

    python tools/build_computer_use.py --plugin-zip dist/cartogen_ai_v<version>.zip [--out-dir DIR]

Contents: every smoke row as ONE short card (cards.json / CARDS.md), the in-QGIS card dock that saves the evidence when the agent clicks a result button, the headless runner that checks the
numbers of the machine-checkable rows with no agent at all, the test inputs of the full smoke package (same files, same SHA-256 list), the plugin zip, one start script per job, a short
prompt for the agent, and the analysis script that refuses to trust a PASS without program-made evidence. Rows that need a second program or a fluent reader are on their cards as 'human row'."""
import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import build_full_smoke as full  # noqa: E402
import smoke_cards  # noqa: E402

TOOLS = ("smoke_cards.py", "smoke_dock.py", "smoke_dock_start.py", "smoke_core.py", "run_smoke_headless.py", "analyze_smoke_run.py", "collect_evidence.py",
         "make_full_smoke_fixtures.py", "verify_inputs.py")

PROMPT = """You are testing the Cartogen AI plugin in QGIS 4.2.3 on a Windows 11 PC. You work only by looking at the screen and using the mouse and keyboard. Follow ONLY this page.

WHAT YOU SEE
- QGIS is open, maximised. On the right is a dock called "Smoke test". It shows ONE row (a card): START FROM, DO, EXPECT, PASS ONLY IF. Use nothing else to find out what to do.
- The Cartogen AI chat is the other dock. Chat prompts go in it exactly as written on the card, one at a time. Wait for each reply to finish before sending the next.

THE LOOP (repeat for each row)
1. Click "Start this row".
2. Do exactly the steps under DO, in QGIS. Nothing more.
3. Write ONE line in the dock's note box: what you actually saw (a number, a layer name, an error text).
4. Click Pass, Partial, Fail or Skip. Pass only if every PASS ONLY IF condition is true on the screen. Not sure = Partial. A step you could not do = Fail or Skip, and say which step.
5. Wait about 5 seconds. The dock saves the evidence and moves to the next row. Read the status line at the bottom of the dock: it must say the row and its status. Then go on.

WINDOWS 11 RULES
- Never restart QGIS yourself, never close it, never start a second copy. If the QGIS window is not in front, click its button on the taskbar once.
- QGIS can look frozen ("Not Responding", a grey window) for up to 6 minutes while a tool runs. That is normal. Wait. Take a screenshot every minute. Do not click anything meanwhile. After 8 minutes with no change, click Fail with the note "no reply" and go on.
- If QGIS disappears or a crash window (qgiscrashhandler) appears: click "Close" or "Don't send" on the crash window, then STOP and say "QGIS crashed on row <id>". Do not start it again; the person running the test does that. The row is recorded automatically as interrupted.
- Do not type any command into the QGIS Python console, a terminal or PowerShell. Do not open File Explorer, a browser, Notepad or any other program. Do not paste anything: the clipboard may hold old text. Type prompts yourself, then read the chat box before you press Enter.
- Do not write, rename or save files by hand. The dock saves everything. If a button in the dock does not seem to work, wait 10 seconds and look at the status line before pressing it again; never press it twice.
- Never enter, read out or look for an API key or password. If a card needs one and the model is not connected, click Skip with the note "no key".

HOW MUCH
- Do at most 6 rows, then stop and reply with: the rows you finished, each with its status and your note. Do not start a 7th row.
- Never claim a result you did not see. A wrong Pass is worse than a Skip.
"""

README = """Cartogen AI {v} - computer-use smoke package ({n} rows)

WHO DOES WHAT
  A program (no model) checks the numbers and refusals of {m} rows:           RUN_HEADLESS.bat      -> results\\RESULTS.csv + evidence\\H*
  Haiku 5 with computer use does the {k} rows that need a screen:           START_QGIS.bat + HAIKU_PROMPT.md
  {h} rows are 'human rows' (a second program or a fluent reader is needed); the dock marks them Skip.
  A program then reads everything:                                        ANALYZE.bat           -> results\\REPORT.md

BEFORE THE RUN (once, by you, because it needs secrets and choices an agent should not make)
  1. QGIS 4.2.3 installed (the dock shows a red warning if the version differs).
  2. Open START_QGIS.bat once. In the Cartogen Connections window enter the key of the model the rows should use (for example Gemini or Claude) and press Test until it says OK. An agent is never given the key.
  3. Rows with 'needs: a real model' are only as good as that choice: write the model name in results\\ENVIRONMENT_NOTE.txt.
  4. Windows 11: Settings > System > Display: scale 100 percent, one monitor; Settings > System > Power: screen and sleep "Never" while the test runs.
  5. Claude desktop app with Haiku and computer use: allow it to use the screen; give it HAIKU_PROMPT.md as the first message. Do not let it open other programs.
  6. If QGIS crashes, press Close on the crash window and run START_QGIS.bat again. The open row is recorded as FAIL 'interrupted' automatically.

THE RUN
  1. RUN_HEADLESS.bat dry   (one row, under a minute)   then   RUN_HEADLESS.bat   (all {m} rows). Open results\\SUMMARY.md.
  2. START_QGIS.bat. Give Haiku HAIKU_PROMPT.md. Rows are done in order; the dock saves the evidence for each click. Work in batches of 8 rows if the agent tires.
  3. ANALYZE.bat. Open results\\REPORT.md. Send back the whole results folder.

HOW A RESULT IS TRUSTED
  An agent's PASS counts only when the program-made evidence exists (window screenshot, layer table, and for model rows the plugin's own tool-call record). Otherwise the report says UNSUPPORTED.

STATUS (said plainly)
  The headless rows ran on a real Windows QGIS 4.2.3 (all 15 PASS). The dock and the plugin auto-start ran in a first Haiku session on Windows 11: it worked for several rows, but QGIS crashed when
  a result button was pressed. This version records the result BEFORE taking evidence, takes the screenshot from outside QGIS (PowerShell) and no longer saves the canvas from inside QGIS;
  whether that removes the crash is NOT yet confirmed. Rows A1 and V1 are human rows. Try one row yourself with the Pass button before handing the set to Haiku.
"""

START = """@echo off
rem Opens QGIS 4.2.3 with the Cartogen plugin installed from 1_plugin and the smoke card dock.
setlocal
set PKG=%~dp0
set PKG=%PKG:~0,-1%
set QGIS=C:\\Program Files\\QGIS 4.2.3
if not exist "%QGIS%\\bin\\qgis-bin.exe" for /d %%D in ("C:\\Program Files\\QGIS*") do if exist "%%D\\bin\\qgis-bin.exe" set QGIS=%%D
if not exist "%QGIS%\\bin\\qgis-bin.exe" (echo Cannot find qgis-bin.exe. Edit the QGIS line of this file. & exit /b 2)
set CARTOGEN_SMOKE_DIR=%PKG%
set PLUGINS=%APPDATA%\\QGIS\\QGIS4\\profiles\\default\\python\\plugins
if not exist "%PLUGINS%\\cartogen_ai_plugin" (
  mkdir "%PLUGINS%" 2>nul
  powershell -NoProfile -Command "Expand-Archive -Force -Path (Get-ChildItem '%PKG%\\1_plugin\\cartogen_ai_v*.zip' | Select-Object -First 1).FullName -DestinationPath '%PLUGINS%'"
)
copy /y "%PKG%\\3_test_files\\smoke_start.qgz" "%PKG%\\results\\smoke_start_work.qgz" >nul 2>nul
start "" /max "%QGIS%\\bin\\qgis-bin.exe" --code "%PKG%\\tools\\smoke_dock_start.py" "%PKG%\\3_test_files\\smoke_start.qgz"
"""

HEADLESS = """@echo off
set PKG=%~dp0
set QGIS=C:\\Program Files\\QGIS 4.2.3
if not exist "%QGIS%\\bin\\python-qgis.bat" for /d %%D in ("C:\\Program Files\\QGIS*") do if exist "%%D\\bin\\python-qgis.bat" set QGIS=%%D
if not exist "%QGIS%\\bin\\python-qgis.bat" (echo Cannot find python-qgis.bat. Edit the QGIS line of this file. & exit /b 2)
set ROWS=
if /i "%1"=="dry" set ROWS=--rows H1-rates-crude
call "%QGIS%\\bin\\python-qgis.bat" "%PKG%tools\\run_smoke_headless.py" --out "%PKG%results" --plugin-src "%PKG%plugin" --rows-file "%PKG%docs\\AGENT_RUN_ROWS.json" %ROWS%
echo Exit code %errorlevel%. Now open results\\SUMMARY.md.
"""

ANALYZE = """@echo off
set PKG=%~dp0
python "%PKG%tools\\analyze_smoke_run.py" "%PKG%results" "%PKG%cards.json"
"""


def machine_map():
    doc = json.loads((REPO / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))
    out = {}
    for r in doc["rows"]:
        out.setdefault(r["covers_row"], []).append(r["id"])
    return out, doc["rows"]


def build(plugin_zip, out_dir):
    plugin_zip = Path(plugin_zip).resolve()
    v = full.v2.version()
    if f"_v{v}.zip" not in plugin_zip.name:
        raise SystemExit(f"{plugin_zip.name} is not the {v} build")
    rows = full.all_rows(full.load())
    mm, machine_rows = machine_map()
    cards = smoke_cards.make_cards(rows, mm)
    unknown = sorted(set(mm) - {r["id"] for r in rows})
    if unknown:
        raise SystemExit(f"agent-run rows cover hand rows that do not exist: {unknown}")
    top = f"cartogen_ai_computer_use_{v}"
    out = Path(out_dir) / f"{top}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        full.main(["x", "--plugin-zip", str(plugin_zip), "--out-dir", tmp])             # the same inputs, plugin zip and SHA-256 list as the full smoke package
        base = zipfile.ZipFile(next(Path(tmp).glob("cartogen_ai_full_smoke_*.zip")))
        runnable = [c for c in cards if c["can_run"]]
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for name in base.namelist():
                parts = name.split("/", 1)
                if len(parts) == 2 and parts[1].startswith(("3_test_files/", "1_plugin/")):
                    z.writestr(f"{top}/{parts[1]}", base.read(name))
            readme = README.format(v=v, n=len(cards), m=len(machine_rows), k=len(runnable), h=len(cards) - len(runnable))
            z.writestr(f"{top}/README.txt", readme.replace("\n", "\r\n"))
            z.writestr(f"{top}/HAIKU_PROMPT.md", PROMPT + "\n")
            z.writestr(f"{top}/cards.json", json.dumps(cards, indent=1, ensure_ascii=False))
            z.writestr(f"{top}/CARDS.md", "\n\n---\n\n".join(smoke_cards.card_text(c) for c in cards) + "\n")
            for name, text in (("START_QGIS.bat", START), ("RUN_HEADLESS.bat", HEADLESS), ("ANALYZE.bat", ANALYZE)):
                z.writestr(f"{top}/{name}", text.replace("\n", "\r\n"))
            for t in TOOLS:
                z.write(HERE / t, f"{top}/tools/{t}")
            z.write(REPO / "docs" / "AGENT_RUN_ROWS.json", f"{top}/docs/AGENT_RUN_ROWS.json")
            for p in sorted((REPO / "src" / "cartogen_ai").rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                    z.write(p, f"{top}/plugin/cartogen_ai/{p.relative_to(REPO / 'src' / 'cartogen_ai').as_posix()}")
            z.writestr(f"{top}/results/README.txt", "Everything the run writes goes here. Send this whole folder back.\r\n")
        base.close()
    return out, len(cards), len(runnable)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin-zip", required=True)
    ap.add_argument("--out-dir", default=str(REPO / "dist"))
    a = ap.parse_args()
    path, n, k = build(a.plugin_zip, a.out_dir)
    print(f"wrote {path}: {n} cards, {k} for the agent")
