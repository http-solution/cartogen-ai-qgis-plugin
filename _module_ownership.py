# -*- coding: utf-8 -*-
"""Which entries of sys.modules belong to THIS plugin's cartogen_ai tree (audit F31, #167).

__init__.py used to evict every `cartogen_ai` / `cartogen_ai.*` module on load. That is needed after an in-place upgrade
(see _bootstrap_namespace), but cartogen_ai is a namespace package that other distributions may extend (the Pro/Enterprise
design in docs/archive/MULTITIER_REPO_ARCHITECTURE_SPEC.md), and evicting their modules breaks them or running tasks. Only
modules whose file or package path lies under our own package directory are owned here.

Stdlib only, so it can be imported by __init__.py before anything else and tested without QGIS."""
import os


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
