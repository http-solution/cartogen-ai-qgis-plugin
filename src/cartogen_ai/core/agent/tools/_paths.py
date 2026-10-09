# -*- coding: utf-8 -*-
"""Where a tool-supplied output path really points.

rc22 live smoke test (2026-10-09, N3/N8/N9/H4): the model passed relative paths such as "outputs/smoke_layout.pdf" and the tools used
them verbatim. A relative path resolves against the QGIS PROCESS's working directory (on Windows typically the QGIS "bin" folder),
not the project, so (a) the file landed somewhere the user never looked, (b) the overwrite check looked for an existing file in that
wrong place and never found the user's real one (N3: no confirmation, sentinel untouched), and (c) the reply named the relative
path and the file was "absent". resolve_output_path anchors a relative path to the saved project's folder (or the profile export
folder for an unsaved project) and every tool reports the absolute result.

Qt-free: QGIS is imported lazily so the pure rule is unit-testable offline."""
import os


def _project_home():
    try:
        from qgis.core import QgsProject
        return QgsProject.instance().homePath() or ""
    except Exception:
        return ""


def _profile_export_dir():
    try:
        from qgis.core import QgsApplication
        return os.path.join(QgsApplication.qgisSettingsDirPath(), "cartogen_ai", "exports")
    except Exception:
        return os.path.join(os.path.expanduser("~"), "cartogen_ai", "exports")


def resolve_output_path(path, project_home=None, fallback_dir=None):
    """Absolute, normalised version of `path`; falsy input is returned unchanged.

    `~` is expanded. An absolute path is kept. A relative path is joined to the saved project's folder, or to `fallback_dir`
    (the profile export folder) when the project is unsaved. `project_home`/`fallback_dir` are injectable for tests."""
    if not path:
        return path
    text = os.path.expanduser(str(path).strip())
    if os.path.isabs(text):
        return os.path.normpath(text)
    home = _project_home() if project_home is None else project_home
    base = home or (fallback_dir if fallback_dir is not None else _profile_export_dir())
    return os.path.normpath(os.path.join(base, text))
