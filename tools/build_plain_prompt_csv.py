"""Writes docs/HAND_TEST_rc46_algorithms_plain.csv: one row per algorithm of the rc44 hand-test sheet, with a plain-language prompt that never
names the algorithm (tools/plain_prompts_*.py), plus columns for what the chat actually did.

    python tools/build_plain_prompt_csv.py
"""
import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import plain_prompts_grass  # noqa: E402
import plain_prompts_raster  # noqa: E402
import plain_prompts_vector  # noqa: E402

PROMPTS = {**plain_prompts_vector.PROMPTS, **plain_prompts_raster.PROMPTS, **plain_prompts_grass.PROMPTS}
COLUMNS = ["family", "algorithm_id", "name", "plain_prompt", "expected",
           "chat_called (tool and algorithm id the chat showed)", "right_algorithm (Y / equivalent / N)",
           "result (Pass/Partial/Fail/Skip)", "notes"]
NEEDS_INPUTS = "or says clearly which input layers are missing; it must not invent a result"


def main():
    source = REPO / "docs/HAND_TEST_rc44_algorithms.csv"
    with open(source, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = REPO / "docs/HAND_TEST_rc46_algorithms_plain.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for row in rows:
            prompt = PROMPTS[row["algorithm_id"]]
            expected = row["expected"]
            if "Say what" in prompt or "say what" in prompt or "tell me" in prompt:
                expected = f"{expected.rstrip('.')}, {NEEDS_INPUTS}."
            writer.writerow([row["family"], row["algorithm_id"], row["name"], prompt, expected, "", "", "", ""])
    print(f"wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
