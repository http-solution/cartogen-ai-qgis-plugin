#!/usr/bin/env python3
"""Checks that every input file of the full smoke package is present and unchanged, and says which rows use each one. Standard library only.

    python 6_tools/verify_inputs.py [3_test_files]

Reads SHA256SUMS.txt in the test-files folder (written when the package was built), compares every file, and prints OK / MISSING / CHANGED per file.
If 3_ROWS.json sits beside that folder it also lists, per row, any file the row names that is not there. Exit code 1 when anything is wrong.
Run it once before the first row: a damaged download or a file the unzip tool skipped shows up here, not in the middle of a row."""
import hashlib
import json
import sys
from pathlib import Path


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(folder):
    """([(name, status, detail)], [problem sentence]) for a test-files folder. Status is OK, MISSING or CHANGED. Pure apart from reading files."""
    folder = Path(folder)
    sums = folder / "SHA256SUMS.txt"
    if not sums.is_file():
        return [], [f"{sums} not found: is this the 3_test_files folder of the package?"]
    entries, problems = [], []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        path = folder / name
        if not path.is_file():
            entries.append((name, "MISSING", ""))
            problems.append(f"{name} is missing")
        elif sha256(path) != digest:
            entries.append((name, "CHANGED", "its contents differ from the package as built"))
            problems.append(f"{name} was changed or damaged")
        else:
            entries.append((name, "OK", ""))
    rows_file = folder.parent / "3_ROWS.json"
    if rows_file.is_file():
        present = {name for name, status, _ in entries if status == "OK"}
        for row in json.loads(rows_file.read_text(encoding="utf-8")).get("rows", []):
            problems += [f"row {row['id']} needs {name}, which is not usable" for name in row.get("files", []) if name not in present]
    return entries, problems


def main(argv):
    entries, problems = check(argv[1] if len(argv) > 1 else "3_test_files")
    for name, status, detail in entries:
        print(f"{status:8} {name} {detail}".rstrip())
    print(f"\n{sum(1 for _n, s, _d in entries if s == 'OK')} of {len(entries)} files OK" + ("" if not problems else f"; {len(problems)} problem(s):"))
    for problem in problems:
        print("  -", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
