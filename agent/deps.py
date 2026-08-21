# -*- coding: utf-8 -*-
"""
Dependency Verification Utility for Cartogen AI.
Checks availability of optional third-party Python packages and reports what's
missing. Installation is handled by the qpip plugin (see metadata.txt
plugin_dependencies + requirements.txt) or manually by the user -- this
module deliberately does not run pip itself. Running pip from inside a
plugin can overwrite global libraries, silently downgrade a dependency
another plugin relies on, or fail on permissions the user doesn't have; the
QGIS community's own guidance is to let installation fail gracefully with
clear instructions instead. See get_dependency_warning_message().
"""

import sys

REQUIRED_PACKAGES = {
    "pypdf": "pypdf",
    "docx": "python-docx",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "duckduckgo_search": "duckduckgo-search",
    "pdfplumber": "pdfplumber",
    "matplotlib": "matplotlib",
    "folium": "folium",
}

# ultralytics (SAM-family imagery extraction, see
# docs/SAM_IMAGERY_EXTRACTION_SPEC.md) is deliberately NOT added to
# REQUIRED_PACKAGES above: it pulls in torch, a meaningfully heavier install
# (~200MB+ plus a model checkpoint on first use) than anything in that list,
# and most users never touch imagery extraction. Surfacing it in the
# always-shown startup banner (get_dependency_warning_message(), wired from
# ui/dock_widget.py) would nag everyone about a dependency only the tool
# that actually needs it should ask for. extract_features_from_imagery
# (agent/tools/imagery_extraction.py) checks for it inline, the same
# try/except ImportError pattern generate_chart already uses for
# matplotlib, so the request for it only appears at the moment it's
# actually needed.


def verify_dependencies() -> dict:
    """Verifies presence of optional and required third-party Python packages."""
    status = {}
    missing = []

    for mod_name, pip_name in REQUIRED_PACKAGES.items():
        try:
            __import__(mod_name)
            status[pip_name] = True
        except ImportError:
            status[pip_name] = False
            missing.append(pip_name)

    return {
        "all_installed": len(missing) == 0,
        "status": status,
        "missing_packages": missing,
        "install_command": f"{sys.executable} -m pip install {' '.join(missing)}" if missing else "",
    }


def get_dependency_warning_message() -> str:
    """Generates user-friendly message instructions for missing packages.
    Graceful-failure by design (see module docstring) -- this plugin never
    runs pip itself."""
    info = verify_dependencies()
    if info["all_installed"]:
        return ""

    missing_str = ", ".join(info["missing_packages"])
    return (
        f"⚠️ **Optional packages missing:** {missing_str}\n\n"
        "These enable document parsing (PDF, Word, Excel), web search, chart/dashboard generation, "
        "and PDF table extraction -- the rest of the plugin works fine without them.\n\n"
        "If you have the **qpip** plugin installed, it should have already offered to install "
        "these from this plugin's `requirements.txt`.\n\n"
        "Otherwise, run this command in the **OSGeo4W Shell**:\n\n"
        f"`{info['install_command']}`\n\n"
        "After running, reload the plugin (Plugins → Plugin Reloader)!"
    )
