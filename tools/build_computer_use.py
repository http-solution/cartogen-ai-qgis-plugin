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

SIX_TOOLS = ("mcp_probe.py", "check_workflow_file.py", "summarize_usage_log.py", "verify_inputs.py")         # the rows say `python 6_tools/...`; PY.bat runs them with QGIS's own Python
TOOLS = ("record_result.py", "supervisor.ps1", "smoke_cards.py", "smoke_dock.py", "smoke_dock_start.py", "smoke_core.py", "run_smoke_headless.py", "analyze_smoke_run.py", "collect_evidence.py",
         "make_full_smoke_fixtures.py", "verify_inputs.py")

PROMPT = r"""You are the tester. Your job is to finish the whole Cartogen AI smoke test on this Windows 11 PC, by yourself, from the screen, the mouse and the keyboard. You may open
File Explorer, start and restart QGIS, and recover from failures. You never need to type in Command Prompt or PowerShell (the Claude app only lets you click there): everything is started by double-clicking the .bat files. Do not stop to ask unless the STOP list below applies. Work until every row has a result.

WHERE THINGS ARE
- The package folder is the one this file is in (the dock shows its full path under every card). It holds RUN_EVERYTHING.bat, START_QGIS.bat, ANALYZE.bat and the results folder.
- QGIS 4.2.3 normally runs with a dock called "Smoke test" on the right. It shows ONE row (a card) and always moves to the first row that has no result yet.

START
1. If QGIS with the "Smoke test" dock is not open: open File Explorer, go to the package folder and double-click RUN_EVERYTHING.bat. It runs the program-checked rows, opens QGIS, and
   reopens it after a crash. Leave its black window open. (START_QGIS.bat alone opens just QGIS.)
2. Wait for the dock. Then start the loop.

THE LOOP (repeat until every row has a result)
1. Click "Start this row". Do exactly the steps under DO, in QGIS. Chat prompts go in the Cartogen AI chat exactly as written, one at a time. Wait for each reply to finish before the next.
   If your own chat window covers the dock, move it away or minimise it first.
2. Write ONE line in the dock's note box: what you actually saw (a number, a layer name, an error text).
3. Click Pass, Partial, Fail or Skip. Pass only if every PASS ONLY IF condition is true on the screen. Not sure = Partial. A step you could not do = Fail, and say which step.
4. Wait 10 seconds and read the dock's status line: it must name the row and its status. The dock then shows the next row. Never press a result button twice.

WHEN SOMETHING GOES WRONG (fix it yourself)
- QGIS looks frozen ("Not Responding"): tools can block it for up to 6 minutes. Wait, screenshot every minute, click nothing. After 8 minutes with no change: click Fail with the note "no reply"; if QGIS still does not answer after 3 more minutes, open Task Manager (Ctrl+Shift+Esc), select QGIS, End task. RUN_EVERYTHING reopens it.
- QGIS closes or a crash window appears (qgiscrashhandler): click "Close" / "Don't send". The row that was open is recorded as FAIL "interrupted" automatically. If RUN_EVERYTHING's window is still open, QGIS comes back within seconds; otherwise double-click START_QGIS.bat. Then carry on with the next row.
- The dock is missing, or a button crashes QGIS: the result line is written BEFORE the evidence is taken, so the verdict is not lost. Reopen QGIS by double-clicking START_QGIS.bat (or let RUN_EVERYTHING reopen it); the dock returns at the first row with no result. If the same row crashes QGIS 3 times, click Skip on it (or Fail with the note "crashes QGIS") and go on.
- The QGIS window is hidden: click its button on the taskbar once.
- A row cannot be done as written (a file or program the card names is not there): Skip with the exact reason.

LIMITS (these are the only STOP cases)
- Never enter, read out, search for or change an API key or password. If a card needs the model and it is not connected, Skip with the note "no key".
- Only touch the package folder and QGIS. You may open files that are INSIDE the package folder (for example the pages exported by row A1) with the Windows image and PDF viewers, and close them again. Do not install software, change Windows settings, delete files, or open other programs or websites.
- The QGIS Python console is used for exactly one thing: the single line on card A1. Never type a command there that a card does not give you. Do not try to type in Command Prompt or PowerShell.
- Do not paste anything (the clipboard may hold old text): type each prompt yourself, and read the chat box before you press Enter.
- Never claim a result you did not see. A wrong Pass is worse than a Skip.

WHEN THE DOCK SAYS EVERY ROW HAS A RESULT
Double-click ANALYZE.bat (or wait for RUN_EVERYTHING to finish), open results\REPORT.md, and reply with its totals and the rows marked UNSUPPORTED or FAIL, each with your note. Then stop.

IF YOUR SESSION RUNS OUT OF ROOM: nothing is lost. A new session picks up at the first row with no result. Say in your last message which row you were on.
"""

README = """Cartogen AI {v} - computer-use smoke package ({n} rows)

WHO DOES WHAT
  A program (no model) checks the numbers and refusals of {m} rows:           RUN_HEADLESS.bat      -> results\\RESULTS.csv + evidence\\H*
  Haiku 5 (Claude desktop app, computer use) does the {k} rows that need a screen, and starts, restarts and recovers QGIS itself:   RUN_EVERYTHING.bat + HAIKU_PROMPT.md
  {h} rows are 'human rows' (a second program or a fluent reader is needed); the dock marks them Skip.
  A program then reads everything:                                        ANALYZE.bat           -> results\\REPORT.md

BEFORE THE RUN (once, by you, because it needs secrets and choices an agent should not make)
  1. QGIS 4.2.3 installed (the dock shows a red warning if the version differs).
  2. Open START_QGIS.bat once. In the Cartogen Connections window enter the key of the model the rows should use (for example Gemini or Claude) and press Test until it says OK. An agent is never given the key.
  3. Rows with 'needs: a real model' are only as good as that choice: write the model name in results\\ENVIRONMENT_NOTE.txt.
  4. Windows 11: Settings > System > Display: scale 100 percent, one monitor; Settings > System > Power: screen and sleep "Never" while the test runs.
  5. Claude desktop app with Haiku and computer use: allow it to use the screen, File Explorer and Command Prompt. It must not need your API key: you connected the model in step 2.
  6. After a crash the supervisor (RUN_EVERYTHING) reopens QGIS by itself, up to 8 times; the open row is recorded as FAIL 'interrupted' automatically.

THE RUN
  1. RUN_HEADLESS.bat dry   (one row, under a minute)   then   RUN_HEADLESS.bat   (all {m} rows). Open results\\SUMMARY.md.
  2. Open the Claude desktop app, choose Haiku, switch computer use on, and send HAIKU_PROMPT.md as the first message. Haiku opens RUN_EVERYTHING.bat itself (or you double-click it first).
     RUN_EVERYTHING runs the program-checked rows, opens QGIS with the dock, and reopens QGIS after a crash. Rows are done in order; the dock saves the evidence for each click.
  3. Haiku runs ANALYZE.bat at the end. Open results\\REPORT.md. Send back the whole results folder.
  If a Haiku session ends early, start a new one with the same message: it carries on at the first row with no result.

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

PYBAT = """@echo off
rem Runs QGIS's own Python with the given arguments:  PY.bat 6_tools\\mcp_probe.py ...
set QGIS=C:\\Program Files\\QGIS 4.2.3
if not exist "%QGIS%\\bin\\python-qgis.bat" for /d %%D in ("C:\\Program Files\\QGIS*") do if exist "%%D\\bin\\python-qgis.bat" set QGIS=%%D
if not exist "%QGIS%\\bin\\python-qgis.bat" (echo Cannot find python-qgis.bat. Edit the QGIS line of this file. & exit /b 2)
call "%QGIS%\\bin\\python-qgis.bat" %*
"""

RECORD = """@echo off
rem RECORD.bat <row id> <PASS|PARTIAL|FAIL|SKIP> "one line"   : records a result when the dock cannot be used
call "%~dp0PY.bat" "%~dp0tools\\record_result.py" %*
"""

EVERYTHING = """@echo off
rem Runs the whole test: the program-checked rows, then QGIS with the card dock, reopened after a crash, then the report. Keep this window open.
setlocal
set PKG=%~dp0
set PKG=%PKG:~0,-1%
set PLUGINS=%APPDATA%\\QGIS\\QGIS4\\profiles\\default\\python\\plugins
if not exist "%PLUGINS%\\cartogen_ai_plugin" (
  mkdir "%PLUGINS%" 2>nul
  powershell -NoProfile -Command "Expand-Archive -Force -Path (Get-ChildItem '%PKG%\\1_plugin\\cartogen_ai_v*.zip' | Select-Object -First 1).FullName -DestinationPath '%PLUGINS%'"
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PKG%\\tools\\supervisor.ps1" -Pkg "%PKG%"
echo.
echo Finished. Open results\\REPORT.md.
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
            for name, text in (("START_QGIS.bat", START), ("RUN_HEADLESS.bat", HEADLESS), ("ANALYZE.bat", ANALYZE), ("PY.bat", PYBAT), ("RECORD.bat", RECORD), ("RUN_EVERYTHING.bat", EVERYTHING)):
                z.writestr(f"{top}/{name}", text.replace("\n", "\r\n"))
            for t in TOOLS:
                z.write(HERE / t, f"{top}/tools/{t}")
            for t in SIX_TOOLS:
                z.write(HERE / t, f"{top}/6_tools/{t}")
            z.write(HERE / "layout_check_script.py", f"{top}/2_layout_check/layout_check_script.py")
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
