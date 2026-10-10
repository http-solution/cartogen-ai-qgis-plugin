# -*- coding: utf-8 -*-
"""Which entries of sys.modules belong to THIS plugin's cartogen_ai tree (audit F31, #167).

__init__.py used to evict every `cartogen_ai` / `cartogen_ai.*` module on load. That is needed after an in-place upgrade
(see _bootstrap_namespace), but cartogen_ai is a namespace package that other distributions may extend (the Pro/Enterprise
design in docs/archive/MULTITIER_REPO_ARCHITECTURE_SPEC.md), and evicting their modules breaks them or running tasks. Only
modules whose file or package path lies under our own package directory are owned here.

Stdlib only, so it can be imported by __init__.py before anything else and tested without QGIS."""
import os


LEGACY_FOLDER_NAMES = ("cartogen-ai",)   # the folder rc24 and earlier were installed in (renamed in rc25 for plugins.qgis.org)


def legacy_copies(plugin_dir):
    """Paths of an old-named copy of this plugin sitting beside `plugin_dir` (same plugins directory), or [].

    rc25 renamed the install folder from "cartogen-ai" to "cartogen_ai_plugin", so a user upgrading by installing the new zip over
    rc24 or earlier gets BOTH folders, and QGIS loads both. Pure: stdlib only."""
    parent = os.path.dirname(os.path.abspath(plugin_dir))
    found = []
    for name in LEGACY_FOLDER_NAMES:
        candidate = os.path.join(parent, name)
        if os.path.normcase(candidate) != os.path.normcase(os.path.abspath(plugin_dir)) and os.path.isfile(os.path.join(candidate, "metadata.txt")):
            found.append(candidate)
    return found


def _under(path, directory):
    try:
        norm_path = os.path.normcase(os.path.abspath(path))
        norm_dir = os.path.normcase(os.path.abspath(directory))
        return norm_path == norm_dir or norm_path.startswith(norm_dir + os.sep)
    except (TypeError, ValueError):
        return False


def owned_module_names(modules, package_dir):
    """Names in `modules` (a sys.modules-like dict) that belong to the cartogen_ai tree under `package_dir`. Pure.

    A module is ours when its __file__ is under package_dir. The bare `cartogen_ai` namespace module has no __file__: it is
    ours only when every entry of its __path__ is under package_dir; if another portion contributes a path, it is shared and
    is left alone (a namespace package recomputes its path from sys.path, so keeping it is safe). A submodule of a package
    we keep is still judged by its own file."""
    owned = []
    for name, module in list(modules.items()):
        if name != "cartogen_ai" and not name.startswith("cartogen_ai."):
            continue
        filename = getattr(module, "__file__", None)
        if filename:
            if _under(filename, package_dir):
                owned.append(name)
            continue
        try:
            paths = list(getattr(module, "__path__", []) or [])
        except Exception:
            paths = []
        if paths and all(_under(p, package_dir) for p in paths):
            owned.append(name)
    return owned


def claimed_module_names(modules, package_dir):
    """Names in `modules` that this package directory claims by NAME, wherever the cached copy came from. Pure.

    Used only by the last-resort bootstrap path (rc20 audit A18), where a stale copy of OUR subpackages was cached from some other
    location and so is not "under" package_dir. The bare `cartogen_ai` entry plus every `cartogen_ai.<child>[...]` whose first
    component exists in package_dir (as a package directory or a .py file) is claimed; a child that another distribution
    contributes to the shared namespace (no such entry here) is left alone, unlike the old evict-everything fallback."""
    try:
        children = {os.path.splitext(entry)[0] for entry in os.listdir(package_dir) if not entry.startswith("__")}
    except OSError:
        children = set()
    claimed = []
    for name in list(modules):
        if name == "cartogen_ai":
            claimed.append(name)
        elif name.startswith("cartogen_ai.") and name.split(".")[1] in children:
            claimed.append(name)
    return claimed
