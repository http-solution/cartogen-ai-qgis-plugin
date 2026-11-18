"""Records one row's result from the command line, for when the dock cannot be used (it is not on screen, or QGIS keeps closing on the button):

    RECORD.bat <row id> <PASS|PARTIAL|FAIL|SKIP> "one line: what was seen"

Writes the same results\\RESULTS_GUI.csv line the dock writes and takes a screenshot of the whole screen from outside QGIS (PowerShell) into results\\screens\\<row>.png. It cannot
read the layer table (that needs QGIS), so the line says so in evidence_error and the report treats a PASS recorded this way as UNSUPPORTED: the point is that a verdict is never
lost or kept in a hand-written note. Runs on any Python 3.10+; no QGIS import."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smoke_cards as sc  # noqa: E402


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    row_id, status, note = argv[1], argv[2].upper(), (argv[3] if len(argv) > 3 else "")
    package = HERE.parent
    results = package / "results"
    cards = json.loads((package / "cards.json").read_text(encoding="utf-8"))
    if row_id not in {c["id"] for c in cards}:
        print(f"no such row {row_id!r}; the rows are in cards.json")
        return 2
    if status not in sc.STATUSES:
        print(f"status must be one of {', '.join(sc.STATUSES)}")
        return 2
    results.mkdir(exist_ok=True)
    shot = results / "screens" / f"{row_id}.png"
    argv_capture = sc.screen_capture_command(shot)
    if argv_capture:
        try:
            subprocess.run(argv_capture, check=False, timeout=60, capture_output=True)  # noqa: S603
        except (OSError, subprocess.SubprocessError) as e:
            print(f"screen capture failed: {type(e).__name__}")
    now = round(time.time(), 1)
    sc.append_result(str(results), {"row": row_id, "status": status, "note": note, "started": now, "finished": now, "seconds": 0,
                                    "evidence_error": "recorded without the dock: no layer table"})
    marker = results / "CURRENT_ROW.txt"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == row_id:
        os.remove(marker)
    print(f"recorded {row_id}: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
