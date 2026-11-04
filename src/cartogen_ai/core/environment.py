"""What the plugin is running on: QGIS, Qt, Python, the operating system (PLAN-053 stage 1).

The plugin is meant to work on every PC that runs a current QGIS, so it must know what it is on instead of assuming, and say so in plain words
when the machine is outside what it was built and tested for. Before this module nothing read the QGIS version at run time (only QGIS's own
install gate, `qgisMinimumVersion` in metadata.txt, applied), and a failure on someone else's computer could not be read from a log.

Leaf module: standard library only, QGIS imported lazily and only to READ version strings. It never raises; an unreadable value is blank text, and
a blank value produces no finding (nothing is guessed). Nothing personal is read: no user name, host name, path or locale.

Status: the thresholds below are the project's rules (QGIS 4.2 and later only, owner decision 2026-11-03; Python 3.10, the oldest version CI runs).
That a QGIS 5 would be untested is a statement about the project, not a measurement. Not exercised on macOS or Linux desktops by a person."""
import contextlib
import platform
import re

MINIMUM_QGIS = (4, 2)
UNTESTED_FROM_QGIS = (5, 0)
MINIMUM_PYTHON = (3, 10)
TESTED_SYSTEMS = ("Windows", "macOS", "Linux")
_SYSTEM_NAMES = {"Darwin": "macOS"}
_NUMBER = re.compile(r"(\d+(?:\.\d+)*)")
_SERIOUSNESS = {"unsupported": 0, "untested": 1, "note": 2}


def parse_version(text):
    """The first dotted number in `text` as a tuple of ints, or () when there is none. '4.2.3-Prizren' -> (4, 2, 3). Pure."""
    found = _NUMBER.search(str(text or ""))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def qt_version_text(qtcore):
    """The Qt version this process is RUNNING: qVersion() of the given QtCore module, else its QT_VERSION_STR (the version PyQt was built against), else ''.
    Hand run 2026-11-04 (W13, Windows): the Help said Qt 6.11.0 while QGIS's About window said 6.11.1, because QT_VERSION_STR is a build-time constant.
    Never raises. Pure given the module."""
    with contextlib.suppress(Exception):
        running = str(qtcore.qVersion() or "")
        if running:
            return running
    with contextlib.suppress(Exception):
        return str(qtcore.QT_VERSION_STR or "")
    return ""


def _qgis_versions():
    """(QGIS version text, Qt version text, GDAL version text); '' for each one that cannot be read. Never raises."""
    qgis_text = qt_text = gdal_text = ""
    with contextlib.suppress(Exception):
        from qgis.core import Qgis
        qgis_text = str(Qgis.QGIS_VERSION)
    with contextlib.suppress(Exception):
        from qgis.PyQt import QtCore
        qt_text = qt_version_text(QtCore)
    with contextlib.suppress(Exception):
        from osgeo import gdal
        gdal_text = str(gdal.__version__)
    return qgis_text, qt_text, gdal_text


def _safe(call):
    try:
        return str(call() or "")
    except Exception:
        return ""


def detect():
    """{'os', 'os_release', 'arch', 'python', 'qgis', 'qt', 'gdal'}, all text, '' when unreadable. Reads this machine; never raises."""
    system = _safe(platform.system)
    qgis_text, qt_text, gdal_text = _qgis_versions()
    return {"os": _SYSTEM_NAMES.get(system, system), "os_release": _safe(platform.release), "arch": _safe(platform.machine),
            "python": _safe(platform.python_version), "qgis": qgis_text, "qt": qt_text, "gdal": gdal_text}


def describe(found):
    """One line a person can paste into a bug report, leaving out what is unknown. Pure."""
    parts = []
    if found.get("qgis"):
        parts.append(f"QGIS {found['qgis']}")
    if found.get("qt"):
        parts.append(f"Qt {found['qt']}")
    system = " ".join(p for p in (found.get("os"), found.get("os_release")) if p)
    if system:
        parts.append(system + (f" ({found['arch']})" if found.get("arch") else ""))
    if found.get("python"):
        parts.append(f"Python {found['python']}")
    return ", ".join(parts)


def findings(found):
    """[{'level': 'unsupported' | 'untested' | 'note', 'code': str, 'text': str}] for what is outside the supported range. [] when all is well.
    A blank value gives no finding: the check never refuses on something it could not read. Pure."""
    out = []
    qgis_text = found.get("qgis") or ""
    if qgis_text:
        version = parse_version(qgis_text)
        if not version:
            out.append({"level": "note", "code": "qgis_version_unreadable",
                        "text": f"The QGIS version could not be read from '{qgis_text}', so it was not checked against the supported range."})
        elif version[:2] < MINIMUM_QGIS:
            out.append({"level": "unsupported", "code": "qgis_too_old",
                        "text": f"This computer runs QGIS {qgis_text}. Cartogen AI needs QGIS {MINIMUM_QGIS[0]}.{MINIMUM_QGIS[1]} or later, so parts of it may not work. "
                                "Update QGIS, or keep using the Cartogen AI version that matches your QGIS."})
        elif version[:2] >= UNTESTED_FROM_QGIS:
            out.append({"level": "untested", "code": "qgis_newer_than_tested",
                        "text": f"This computer runs QGIS {qgis_text}, a newer major version than Cartogen AI has been tested on. It may work; "
                                "if something does not, say which QGIS you have when you report it."})
    python_version = parse_version(found.get("python"))
    if python_version and python_version[:2] < MINIMUM_PYTHON:
        out.append({"level": "unsupported", "code": "python_too_old",
                    "text": f"QGIS is using Python {found['python']}. Cartogen AI needs Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} or later."})
    system = found.get("os") or ""
    if system and system not in TESTED_SYSTEMS:
        out.append({"level": "untested", "code": "os_untested",
                    "text": f"Cartogen AI has been built for Windows, macOS and Linux; {system} has not been tried."})
    return sorted(out, key=lambda f: _SERIOUSNESS[f["level"]])


def startup_message(found_findings):
    """The text to show the user at start-up: the unsupported and untested findings only, most serious first; None when there is nothing to say. Pure."""
    shown = [f["text"] for f in found_findings if f["level"] in ("unsupported", "untested")]
    return " ".join(shown) if shown else None


_LEVEL_WORDS = {"unsupported": "Not supported", "untested": "Not tried", "note": "Note"}
_QGIS_WORDS = ("qgis", "qgs", "pyqt", "qt")


def report_text(found, plugin_version=""):
    """The text of the Settings section 'This computer' and of a bug report: the plugin version, the machine on one line, GDAL, and either 'inside the
    range' or each finding with its seriousness in words. No path, user name or host name. Pure."""
    lines = [f"Cartogen AI {plugin_version}".strip(), describe(found) or "The machine could not be described."]
    if found.get("gdal"):
        lines.append(f"GDAL {found['gdal']}")
    problems = findings(found)
    if not problems:
        lines.append("Checked against what Cartogen AI was built for (QGIS 4.2 or later, Python 3.10 or later, Windows, macOS or Linux): inside the range.")
    else:
        lines.append("Checked against what Cartogen AI was built for:")
        lines.extend(f"- {_LEVEL_WORDS[f['level']]}: {f['text']}" for f in problems)
    return "\n".join(lines)


def api_mismatch_note(error, found):
    """The machine line to add to an unexpected tool failure when it looks like a QGIS or Qt version problem (a missing attribute, import or name, or a wrong
    argument type, in a message that names QGIS or Qt), else ''. Other failures get nothing, so ordinary bugs are not blamed on the machine. Pure."""
    if not isinstance(error, (AttributeError, ImportError, NameError, TypeError)):
        return ""
    message = str(error).lower()
    return describe(found) if any(word in message for word in _QGIS_WORDS) else ""

