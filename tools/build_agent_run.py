"""Builds the agent-run smoke package: one zip with the plugin source, the headless runner, the rows and a README that tells a person or an agent the ONE command to run.

    python tools/build_agent_run.py [--out-dir dist]

Why a separate package: the hand packages ask a person (or a chat agent standing in for one) to click, type into the QGIS console and save screenshots. A small agent failed that on 2026-11-13/14. This package has no
clicking; the runner (tools/run_smoke_headless.py) calls the plugin's tools itself and writes every evidence file. Rows that need a person's eyes stay in the hand packages."""
import argparse
import re
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = ("run_smoke_headless.py", "smoke_core.py", "make_full_smoke_fixtures.py")

README = """Cartogen AI {v} - agent-run smoke package

WHAT THIS IS
  One command runs {n} checks against the real plugin tools in a real QGIS, with no model, no network and no clicking. The program writes every evidence file itself.
  Nobody (person or agent) has to remember to save anything, type into a console, or take a screenshot.

RUN IT (Windows; QGIS 4.2 installed in the usual place)
  1. Unzip this package anywhere. Open a normal Command Prompt in the unzipped folder.
  2. Dry run, 1 row:   RUN.bat dry
  3. Full run:         RUN.bat
  If RUN.bat cannot find QGIS, edit the QGIS line at the top of RUN.bat (the folder that holds bin\\python-qgis.bat).

WHAT YOU GET (in results\\)
  RESULTS.csv   one line per row: PASS, FAIL, ERROR or NO-CHECKS
  SUMMARY.md    the counts
  evidence\\<row>\\row.json   every step: the arguments sent to the tool, its full result, timing, the layer table, sha256 of any file written
  evidence\\<row>\\checks.txt each check with OK/FAIL and the value it saw
  evidence\\<row>\\verdict.json
  inputs\\      the test files the run generated and used
  The program's last line says "EVIDENCE PROBLEM: ..." if any row folder is incomplete, and exits non-zero.

RULES FOR AN AGENT RUNNING THIS (read before doing anything)
  - Run RUN.bat exactly as written and wait for it to finish. Do NOT open QGIS, do NOT type into any chat, do NOT paste anything, do NOT take screenshots.
  - Do NOT write, edit or "complete" any file in results\\. If a row is FAIL or ERROR, report it as it is and send the folder back; never change a status.
  - If RUN.bat prints an error before any row, stop and report the whole message. Do not try another way.
  - When it ends, reply with the contents of results\\SUMMARY.md and the path of results\\ and nothing else. Then stop.

WHAT THIS DOES NOT COVER
  Anything that needs a model reply, the internet, or a person looking at a map (colours, the bulletin page, the Settings windows, MCP). Those rows stay in the hand packages. A PASS here means the numbers
  and refusals are right, not that a picture looks right. Status: this package has been exercised in the QGIS CI job; the first run on a real Windows QGIS is the dry run above.
"""

RUN_BAT = """@echo off
rem Edit this line if QGIS is installed somewhere else (the folder that contains bin\\python-qgis.bat).
set QGIS=C:\\Program Files\\QGIS 4.2.3
if not exist "%QGIS%\\bin\\python-qgis.bat" (
  for /d %%D in ("C:\\Program Files\\QGIS*") do if exist "%%D\\bin\\python-qgis.bat" set QGIS=%%D
)
if not exist "%QGIS%\\bin\\python-qgis.bat" (
  echo Cannot find python-qgis.bat. Edit the QGIS line at the top of RUN.bat.
  exit /b 2
)
set ROWS=
if /i "%1"=="dry" set ROWS=--rows H1-rates-crude
call "%QGIS%\\bin\\python-qgis.bat" "%~dp0tools\\\\run_smoke_headless.py" --out "%~dp0results" %ROWS%
echo.
echo Exit code %errorlevel%. Now open results\\SUMMARY.md.
"""


def version():
    return re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M).group(1)


def build(out_dir):
    import json
    v = version()
    n = len(json.loads((REPO / "docs" / "AGENT_RUN_ROWS.json").read_text(encoding="utf-8"))["rows"])
    target = Path(out_dir) / f"cartogen_ai_agent_run_{v}.zip"
    top = f"cartogen_ai_agent_run_{v}"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README.txt", README.format(v=v, n=n).replace("\n", "\r\n"))
        z.writestr(f"{top}/RUN.bat", RUN_BAT.replace("\n", "\r\n"))
        for t in TOOLS:
            z.write(REPO / "tools" / t, f"{top}/tools/{t}")
        z.write(REPO / "docs" / "AGENT_RUN_ROWS.json", f"{top}/docs/AGENT_RUN_ROWS.json")
        for p in sorted((REPO / "src" / "cartogen_ai").rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                z.write(p, f"{top}/plugin/cartogen_ai/{p.relative_to(REPO / 'src' / 'cartogen_ai').as_posix()}")
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(REPO / "dist"))
    print(build(ap.parse_args().out_dir))
