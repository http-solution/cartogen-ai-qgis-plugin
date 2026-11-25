"""Prepares a computer-use run BEFORE QGIS opens, with plain Python (no QGIS, no Qt): writes CARDS_FILLED.md (every card with the real package folder in its paths, which is what the agent
reads) and makes sure results/RESULTS_GUI.csv exists with its header and a SKIP line for every row that is not for the agent. START_QGIS.bat and the supervisor run it first.

Why: the first version of the watcher-based package wrote both from inside QGIS, so if QGIS or the watcher failed to start the agent had no cards to read and no CSV to append to.
Safe to run again (it never rewrites a result line). Usage:  python prepare_run.py <package folder>"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import smoke_cards as cards_mod  # noqa: E402


def prepare(package_dir):
    package_dir = os.path.abspath(package_dir)
    results = os.path.join(package_dir, "results")
    os.makedirs(results, exist_ok=True)
    with open(os.path.join(package_dir, "cards.json"), encoding="utf-8") as fh:
        cards = json.load(fh)
    text = "\n\n---\n\n".join(cards_mod.card_text(c) for c in cards) + "\n"
    filled = os.path.join(package_dir, "CARDS_FILLED.md")
    with open(filled, "w", encoding="utf-8") as fh:
        fh.write(text.replace("<PACKAGE>", package_dir))
    recorded = cards_mod.record_human_rows(results, cards)
    csv_path = os.path.join(results, "RESULTS_GUI.csv")
    if not os.path.isfile(csv_path):                                    # a package with no human rows still gets its header, so the agent only ever appends
        with open(csv_path, "w", encoding="utf-8", newline="") as fh:
            csv.DictWriter(fh, cards_mod.RESULT_FIELDS).writeheader()
    cards_mod.start_log(results, f"prepare_run: CARDS_FILLED.md written ({len(cards)} cards), {len(recorded)} human rows recorded as SKIP")
    return filled, recorded


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python prepare_run.py <package folder>")
        sys.exit(2)
    path, rows = prepare(sys.argv[1])
    print(f"wrote {path}; recorded {len(rows)} human rows as SKIP")
