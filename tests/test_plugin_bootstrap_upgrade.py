# -*- coding: utf-8 -*-
"""In-place upgrade must not keep the previous version's cartogen_ai.* modules cached.

Reported live on QGIS 4.2.2 after Install from ZIP of v1.16.0-rc5 over a running rc4:
"Failed to open panel: cannot import name 'SETTINGS_PROJECT_INSPECTOR_ENABLED' from
'cartogen_ai.infrastructure.settings_keys'". The files on disk were rc5; the rc4 module was still
in sys.modules because the root __init__.py only evicted when the cached package came from a
DIFFERENT path, and an upgrade reuses the same one. This drives the real root __init__.py through
the same sequence QGIS does (import, replace the files, drop the plugin-folder modules, re-import).
"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLUGIN = "cartogen-ai"


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class TestInPlaceUpgradeEvictsStaleModules(unittest.TestCase):
    def setUp(self):
        # The bootstrap evicts every cartogen_ai.* module, including the real ones the rest of
        # the suite imported from src/ -- snapshot and restore them so this test is isolated.
        self._saved_modules = dict(sys.modules)
        self._saved_path = list(sys.path)
        self._tmp = tempfile.mkdtemp(prefix="cg_upgrade_")
        self._pkg = os.path.join(self._tmp, _PLUGIN)
        shutil.copy(os.path.join(_REPO_ROOT, "__init__.py"), os.path.join(self._pkg + "_init.py"))

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self._saved_modules)
        sys.path[:] = self._saved_path
        importlib.invalidate_caches()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _install(self, settings_keys_src):
        shutil.rmtree(self._pkg, ignore_errors=True)
        os.makedirs(self._pkg)
        shutil.copy(self._pkg + "_init.py", os.path.join(self._pkg, "__init__.py"))
        src = os.path.join(self._pkg, "src", "cartogen_ai")
        _write(os.path.join(src, "core", "__init__.py"), "")
        _write(os.path.join(src, "infrastructure", "__init__.py"), "")
        _write(os.path.join(src, "infrastructure", "settings_keys.py"), settings_keys_src)

    def _load_plugin(self):
        for name in [n for n in sys.modules if n == _PLUGIN or n.startswith(_PLUGIN + ".")]:
            del sys.modules[name]  # what QGIS's unloadPlugin does -- only the plugin-folder name
        importlib.invalidate_caches()
        importlib.import_module(_PLUGIN)

    def test_upgrade_at_same_path_loads_the_new_modules(self):
        sys.path.insert(0, self._tmp)
        self._install("OLD_KEY = 'old'\n")
        self._load_plugin()
        import cartogen_ai.infrastructure.settings_keys as old  # the running version uses it
        self.assertFalse(hasattr(old, "NEW_KEY"))

        self._install("OLD_KEY = 'old'\nNEW_KEY = 'new'\n")
        self._load_plugin()
        from cartogen_ai.infrastructure.settings_keys import NEW_KEY  # raised ImportError before the fix
        self.assertEqual(NEW_KEY, "new")


if __name__ == "__main__":
    unittest.main()
