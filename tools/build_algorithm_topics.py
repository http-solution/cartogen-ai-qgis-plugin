"""Build src/cartogen_ai/core/agent/algorithm_topics.json: per approved Processing algorithm, the stems of its display-name words ("n")
and of the words in its plain-English purpose ("k").

    python tools/build_algorithm_topics.py --catalog path/to/processing_catalog.json

Purpose words come from the QGIS 4.2.3 Developer Reference's Processing catalog (first two sentences of each description, words only; no
sentences are stored) and, for the algorithms that catalog does not describe (GRASS and ten others), from tools/algorithm_topic_notes.py.
Re-run when ALLOWED_ALGORITHM_IDS changes; tests/test_algorithm_topics.py fails if an approved id has no entry.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools"))

from algorithm_topic_notes import NOTES  # noqa: E402

from cartogen_ai.core.agent.algorithm_topics import tokenize  # noqa: E402
from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS, FAMILY_NAMES  # noqa: E402

_ADDED = re.compile(r"^added in \d+(\.\d+)*\s*", re.IGNORECASE)


def first_sentences(text, count=2):
    text = _ADDED.sub("", (text or "").strip().replace("\n", " "))
    text = re.sub(r"This algorithm is derived from.*", "", text, flags=re.IGNORECASE)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(parts[:count])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    args = ap.parse_args()
    with open(args.catalog, encoding="utf-8") as fh:
        catalog = {x["id"]: x for x in json.load(fh)}
    out = {}
    for alg_id in sorted(ALLOWED_ALGORITHM_IDS):
        item = catalog.get(alg_id)
        name = FAMILY_NAMES.get(alg_id) or (item or {}).get("name", "") or alg_id.split(":", 1)[1]
        n = tokenize(name + " " + alg_id.split(":", 1)[1], synonyms=True)
        k = []
        if item:
            k += tokenize(item.get("name", "") + " " + first_sentences(item.get("description", "")), synonyms=True)
        if alg_id in NOTES:       # hand-written words add to (or, where the catalog has none, replace) the catalog's
            k += tokenize(NOTES[alg_id], synonyms=True)
        if not k:
            raise SystemExit(f"no description for {alg_id}: add it to tools/algorithm_topic_notes.py")
        out[alg_id] = {"n": sorted(set(n)), "k": sorted(set(k) - set(n))}
    dest = REPO / "src/cartogen_ai/core/agent/algorithm_topics.json"
    dest.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"wrote {dest} ({len(out)} algorithms, {dest.stat().st_size} bytes)")
    # the hand-written phrases themselves (never the reference's sentences) so find_processing_algorithm can show what an algorithm is for
    about = {alg_id: NOTES[alg_id] for alg_id in sorted(ALLOWED_ALGORITHM_IDS) if alg_id in NOTES}
    about_dest = REPO / "src/cartogen_ai/core/agent/algorithm_about.json"
    about_dest.write_text(json.dumps(about, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"wrote {about_dest} ({len(about)} phrases)")


if __name__ == "__main__":
    main()
