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


def temp_location_note(path, temp_dir=None):
    """A sentence for the tool result when `path` is inside the system temporary folder, else ''. Pure (PLAN-012 item 3).

    The DEM, contour and temporal-frame tools write to a fresh temporary folder when no path is given, and nothing removes it. It is left in
    place on purpose (a loaded layer or a saved project may point into it), so the user is told where the files are instead of finding out later."""
    import tempfile
    root = os.path.normcase(os.path.realpath(temp_dir or tempfile.gettempdir()))
    target = os.path.normcase(os.path.realpath(str(path)))
    if not path or not (target == root or target.startswith(root + os.sep)):
        return ""
    return (f"Saved in the system temporary folder ({os.path.dirname(os.path.realpath(str(path)))}), which the operating system or a cleanup "
            "tool may empty. Export the layer or copy the files if you want to keep them.")


def safe_file_stem(name, fallback="layer"):
    """`name` reduced to one safe file-name stem: no path separators or dots-only names, no leading dots. Pure (PLAN-012 item 2)."""
    stem = "".join(c if c.isalnum() or c in "_- " else "_" for c in str(name or "")).strip().strip("._ ")
    return stem or fallback


def unique_path(directory, stem, extension, exists=None):
    """`directory/stem.ext`, or `stem_2.ext`, `stem_3.ext`... so an earlier file is never overwritten. `exists` is injectable for tests."""
    check = exists or os.path.exists
    candidate = os.path.join(directory, f"{stem}{extension}")
    counter = 2
    while check(candidate):
        candidate = os.path.join(directory, f"{stem}_{counter}{extension}")
        counter += 1
    return candidate
