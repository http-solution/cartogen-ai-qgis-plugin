#!/usr/bin/env python3
"""Builds the live-test bundle zip for the current version: the plugin zip, its checksum, the live-test documents, the synthetic fixtures
and the helper, laid out so tools/live_test_pack.py works from the unzipped folder exactly as it does from the repository.

    python tools/build_live_test_bundle.py            # writes dist/cartogen_ai_live_test_<version>.zip

Standard library only. It runs plugin_upload.py first so the plugin zip inside the bundle is built from the current tree. The bundle holds only
synthetic data and public documents; it never includes credentials, API traces or run results."""
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
FIXED_DOCS = (
    "LIVE_TEST_rc37_START_HERE.md", "FULL_LIVE_TEST_rc34.md", "FULL_LIVE_TEST_rc34_ROWS.csv", "FULL_LIVE_TEST_rc37_ROWS.csv",
    "FULL_LIVE_TEST_rc34_INPUTS.sha256", "RC34_HAND_VERIFICATION_SHEET.md", "RC24_HAND_VERIFICATION_SHEET.md",
    "RELEASE_LIVE_TEST_SCENARIOS.md", "RELEASE_SMOKE_TEST.md", "LIVE_TEST_SCENARIOS.md",
    "RC22_LIVE_SMOKE_REPORT_2026-10-09.md", "RC22_RESULT_MATRIX_2026-10-09.csv",
)
GLOB_DOCS = ("SMOKE_RUN_SHEET_rc*.md",)


def version():
    m = re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M)
    return m.group(1)


def main():
    v = version()
    # Fixed argv, our own script, no shell and no user input.
    subprocess.run([sys.executable, str(REPO / "plugin_upload.py")], cwd=REPO, check=True, stdout=subprocess.DEVNULL)  # noqa: S603
    plugin_zip = REPO / "dist" / f"cartogen_ai_v{v}.zip"
    if not plugin_zip.is_file():
        raise SystemExit(f"plugin zip not found: {plugin_zip}")
    top = f"cartogen_ai_live_test_{v}"
    out = REPO / "dist" / f"{top}.zip"
    docs = [DOCS / n for n in FIXED_DOCS] + [p for g in GLOB_DOCS for p in sorted(DOCS.glob(g))]
    missing = [str(p.relative_to(REPO)) for p in docs if not p.is_file()]
    if missing:
        raise SystemExit("missing documents: " + ", ".join(missing))
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(DOCS / "LIVE_TEST_rc37_START_HERE.md", f"{top}/START_HERE.md")
        z.write(plugin_zip, f"{top}/plugin/{plugin_zip.name}")
        z.writestr(f"{top}/plugin/SHA256.txt", f"{digest}  {plugin_zip.name}\n")
        for p in docs:
            z.write(p, f"{top}/docs/{p.name}")
        for p in sorted((DOCS / "release_smoke_assets" / "inputs").iterdir()):
            if p.is_file():
                z.write(p, f"{top}/docs/release_smoke_assets/inputs/{p.name}")
        z.write(REPO / "tools" / "live_test_pack.py", f"{top}/tools/live_test_pack.py")
    print(f"{out}\nplugin sha256 {digest}")


if __name__ == "__main__":
    main()
