"""PLAN-021 WP-C (#224): the namespace eviction on plugin load touches only this plugin's modules, checked against the REAL sys.modules of this
test run, not only the synthetic ones tests/test_module_ownership.py uses. Offline; the real load, unload and reload of the plugin is the CI
smoke step 'plugin_main load->unload->reload' and the owner's update-in-place row."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location("_module_ownership", os.path.join(ROOT, "_module_ownership.py"))
own = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(own)

PKG_DIR = os.path.join(ROOT, "src", "cartogen_ai")


class TestEvictionOnRealModules(unittest.TestCase):
    def setUp(self):
        import cartogen_ai.core.logger  # noqa: F401  (make sure the plugin's own modules are really loaded)
        self.foreign = types.ModuleType("cartogen_ai.zz_other_distribution")
        self.foreign.__file__ = os.path.join(os.sep, "site-packages", "cartogen_ai", "zz_other_distribution.py")
        sys.modules[self.foreign.__name__] = self.foreign
        self.addCleanup(lambda: sys.modules.pop(self.foreign.__name__, None))

    def test_a_module_from_another_distribution_is_never_selected(self):
        self.assertNotIn("cartogen_ai.zz_other_distribution", own.owned_module_names(sys.modules, PKG_DIR))

    def test_every_loaded_module_of_this_plugin_is_selected_and_only_those(self):
        ours = own.owned_module_names(sys.modules, PKG_DIR)
        self.assertIn("cartogen_ai.core.logger", ours)
        for name in ours:
            module = sys.modules[name]
            filename = getattr(module, "__file__", None)
            if filename:
                self.assertTrue(os.path.abspath(filename).startswith(os.path.abspath(PKG_DIR)), name)
        loaded_here = [n for n, m in sys.modules.items()
                       if n.startswith("cartogen_ai.") and getattr(m, "__file__", None) and os.path.abspath(m.__file__).startswith(os.path.abspath(PKG_DIR))]
        self.assertEqual(sorted(set(loaded_here) - set(ours)), [], "a loaded module of this plugin would survive an in-place update")

    def test_the_root_init_uses_the_scoped_selection_and_nothing_wider(self):
        source = Path(ROOT, "__init__.py").read_text(encoding="utf-8")
        self.assertIn("for name in owned_module_names(sys.modules, _PKG_DIR):", source)
        self.assertEqual(source.count("del sys.modules["), 2, "a new unscoped deletion was added to the bootstrap")


if __name__ == "__main__":
    unittest.main()
