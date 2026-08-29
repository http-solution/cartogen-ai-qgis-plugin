# -*- coding: utf-8 -*-
"""
Automated packaging and release script for Cartogen AI.
Zips plugin assets for deployment and upload to QGIS Plugin Repository.
"""

import fnmatch
import os
import re
import shutil
import sys
import zipfile

PLUGIN_NAME = "cartogen_ai"

# The single top-level folder inside the release zip -- and therefore the name
# of the directory QGIS installs the plugin into.
#
# This used to be derived from the build directory's own name, via
#   os.path.relpath(abs_path, os.path.dirname(script_dir))
# which made the installed plugin folder depend on whatever the checkout
# happened to be called. Confirmed live: v1.4.3 was built from a scratch
# directory and shipped with a top-level folder "_tmp_v143_build", so QGIS
# installed it as a SECOND, separately-named plugin sitting alongside the
# existing "cartogen-ai" install instead of replacing it. Two copies of the
# same plugin then load in one session, each inserting its own src/ onto
# sys.path, and whichever loads first wins the cartogen_ai namespace for both.
#
# MUST NOT be "cartogen_ai". The plugins directory is on sys.path, so a folder
# with that exact name is a REGULAR package (it has __init__.py) that contains
# no core/ -- it would beat the PEP-420 namespace package under src/ at any
# sys.path position and produce "No module named 'cartogen_ai.core'". The
# hyphen is deliberate: it cannot be imported as a top-level Python name, so it
# cannot shadow anything. See __init__.py's _bootstrap_namespace().
PACKAGE_DIR = "cartogen-ai"

if PACKAGE_DIR == "cartogen_ai":
    raise SystemExit(
        "PACKAGE_DIR must not be 'cartogen_ai': an importable folder of that "
        "name in the plugins directory shadows the cartogen_ai namespace "
        "package under src/ and breaks every cartogen_ai.core import."
    )
EXCLUDE_DIRS = {
    ".git", ".github", "__pycache__", ".pytest_cache", "tests", ".idea", ".vscode", ".claude",
    "dist", "brain", "scratch",
    # Brand assets (guidelines HTML, SVG lockups) have no function inside an
    # installed plugin.
    "branding",
    # service/ is the standalone hosted-gateway/monetization prototype (see
    # docs/PRODUCT_TIERS.md's Professional tier) -- not part of the QGIS
    # plugin. Also matters for correctness, not just scope: it contains
    # node_modules/, whose .bin/ entries are Windows reparse points that
    # zipfile.write() can fail to os.stat() (WinError 1920), aborting the
    # whole build -- confirmed live, this exclusion is what fixed it.
    "service",
    # Scratch holding area for content moved out of the old root-level
    # agent/ui/cartogen_ai.py locations during the namespace-package
    # restructure (see docs/BUG_TRACKER.md BUG-2026-08-21-6). Not part of
    # the published package.
    "_legacy_stubs",
    # Standalone web-dashboard prototype (Phase 0/1) for the planned
    # Professional-tier Cloud Connect Gateway -- not part of the QGIS plugin,
    # same category as service/ above. Confirmed live on 2026-08-26: without
    # this exclusion the release zip pulled in web-platform/phase-1's
    # node_modules/ wholesale (2400+ files), ballooning a ~600KB plugin
    # package to over 10MB with code that can't even run inside QGIS.
    "web-platform",
    # Marker directory for files awaiting manual deletion once this sandbox's
    # FUSE-mount unlink restriction allows it (see docs/BUG_TRACKER.md's
    # rm/mv finding) -- by definition nothing here belongs in a release.
    "_to_delete",
}
# Directory names excluded ONLY at the plugin root, not wherever they occur --
# unlike EXCLUDE_DIRS above, these bare names ("agent", "ui") also legitimately
# exist deeper in the tree now (src/cartogen_ai/core/agent/, .../ui/, the real
# code after the namespace-package restructure -- see
# docs/MULTITIER_REPO_ARCHITECTURE_SPEC.md). A plain EXCLUDE_DIRS entry would
# match by bare name at every depth and silently drop the real code from the
# release zip. These two are leftover "MOVED" stub directories at the plugin
# root only (can't be deleted -- see their own file contents for why).
# tools/ at the repo ROOT holds build-time dev scripts (tools/derive_task_io.py
# regenerates the task register's derived fields); it has no caller inside an
# installed plugin. It MUST be root-only, not an EXCLUDE_DIRS entry: there is a
# real src/cartogen_ai/core/agent/tools/ package holding every registered tool,
# and a bare-name exclusion drops all 19 of those modules from the release zip,
# shipping a plugin whose agent has nothing to call. Verified: adding "tools" to
# EXCLUDE_DIRS took the zip from 63 source files to 44.
EXCLUDE_ROOT_ONLY_DIRS = {"agent", "ui", "tools"}
EXCLUDE_EXTS = {".pyc", ".zip", ".tmp"}
# Internal dev docs/scripts/config that have no purpose inside an installed QGIS
# plugin and shouldn't ship in the release package.
EXCLUDE_FILES = {
    "IMPLEMENTATION_TASK_LIST.md", "LICENSE_AUDIT.md", "CARTOGEN_AI_PRD.md",
    "CARTOGEN_AI_FEATURE_LIST.md", "pytest.ini", "plugin_upload.py",
    "API open router.txt", "CLAUDE.md",
    # Leftover stub from consolidating this repo out of the old dual-tree
    # setup -- see the file's own docstring. Not git-tracked; safe to delete
    # by hand, kept excluded here defensively in case it's still present.
    "build_cartogen_ai.py",
    # Leftover stub from the namespace-package restructure -- this filename
    # collided with the cartogen_ai.core namespace package (see
    # docs/BUG_TRACKER.md BUG-2026-08-21-6). Real content now at
    # plugin_main.py, which is NOT excluded and ships normally.
    "cartogen_ai.py",
}
# Name PATTERNS (fnmatch, not exact match) for stray files that land at the repo
# root and must never ship, even when the dev environment couldn't clean them up
# before packaging -- confirmed live on 2026-08-21: a sandbox whose file-deletion
# was blocked left 6 scratch_test_*.csv/.docx/.pdf files (written by
# tests/test_reporting_tools.py's cleanup-on-teardown, which normally os.remove()s
# them) and a leftover .git_commit_msg.txt (a git -F scratch file) sitting in the
# repo root, and the v1.2.34 zip built that day silently included all 7 of them
# because EXCLUDE_FILES only does exact matches and neither of these was ever
# expected to exist at build time. The packaging step must defend against this
# itself -- it can't assume the working tree is always clean when it runs.
# _delete_probe.py is a 5-byte scratch file containing the literal word
# "test" -- left over from probing this sandbox's FUSE unlink restriction.
# Nothing imports it and it is not valid Python, so it fails any
# import-everything sweep (including pyqgis4-checker on upload). Caught by
# importing all 59 modules against real QGIS bindings: 58 OK, this one
# NameError: name 'test' is not defined. Excluded from the package;
# delete the file itself when the mount allows it.
# *.bak-YYYYmmdd-HHMMSS files are backups this workflow writes before an
# in-place edit. They are the previous version of a shipped module, so
# packaging them would put two copies of the same file in the plugin --
# and the stale one would still be importable.
EXCLUDE_FILE_PATTERNS = ("scratch_test_*", ".git_commit_msg*", "_delete_probe.py",
                         "*.bak", "*.bak-*", "*.orig", "*.rej")


def get_plugin_version(script_dir):
    metadata_path = os.path.join(script_dir, "metadata.txt")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                match = re.match(r"^version\s*=\s*(.+)$", line.strip())
                if match:
                    return match.group(1).strip()
    return "0.1.0"


def package_plugin():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    version = get_plugin_version(script_dir)

    dist_dir = os.path.join(script_dir, "dist")
    os.makedirs(dist_dir, exist_ok=True)

    versioned_filename = os.path.join(dist_dir, f"{PLUGIN_NAME}_v{version}.zip")
    root_filename = os.path.join(script_dir, f"{PLUGIN_NAME}.zip")

    print(f"[Release] Packaging '{PLUGIN_NAME}' v{version} into {versioned_filename}...")

    with zipfile.ZipFile(versioned_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(script_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            if root == script_dir:
                dirs[:] = [d for d in dirs if d not in EXCLUDE_ROOT_ONLY_DIRS]

            for file in files:
                if (
                    file in EXCLUDE_FILES
                    or any(file.endswith(ext) for ext in EXCLUDE_EXTS)
                    or any(fnmatch.fnmatch(file, pat) for pat in EXCLUDE_FILE_PATTERNS)
                ):
                    continue

                abs_path = os.path.join(root, file)
                rel_path = os.path.join(
                    PACKAGE_DIR, os.path.relpath(abs_path, script_dir)
                )
                zipf.write(abs_path, rel_path)
                print(f"  + Added: {rel_path}")

    shutil.copyfile(versioned_filename, root_filename)

    print(f"\n[Release] Success!")
    print(f"  Versioned archive: {versioned_filename}")
    print(f"  Latest bundle:     {root_filename}")
    return versioned_filename


if __name__ == "__main__":
    package_plugin()
