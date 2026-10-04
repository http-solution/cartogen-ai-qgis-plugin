# -*- coding: utf-8 -*-
"""Scoped module eviction on plugin load (audit F31, #167). Offline; the real unload (translator, isolation worker) needs QGIS."""
import importlib.util
import os
import types
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "_module_ownership", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_module_ownership.py"))
own = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(own)

OURS = os.path.join(os.sep, "plugins", "cartogen-ai", "src", "cartogen_ai")
OTHER = os.path.join(os.sep, "site-packages", "cartogen_ai")


def _module(file=None, path=None):
    m = types.ModuleType("x")
    if file:
        m.__file__ = file
    if path is not None:
        m.__path__ = path
    return m


class TestOwnedModuleNames(unittest.TestCase):
    def test_only_modules_under_our_package_dir_are_owned(self):
        modules = {
            "cartogen_ai.core": _module(os.path.join(OURS, "core", "__init__.py"), [os.path.join(OURS, "core")]),
            "cartogen_ai.core.agent.x": _module(os.path.join(OURS, "core", "agent", "x.py")),
            "cartogen_ai.pro.licence": _module(os.path.join(OTHER, "pro", "licence.py")),
            "json": _module(os.path.join(os.sep, "usr", "lib", "json", "__init__.py")),
        }
        self.assertEqual(sorted(own.owned_module_names(modules, OURS)), ["cartogen_ai.core", "cartogen_ai.core.agent.x"])

    def test_the_namespace_module_is_evicted_only_when_every_path_is_ours(self):
        mine = {"cartogen_ai": _module(path=[OURS])}
        shared = {"cartogen_ai": _module(path=[OURS, OTHER])}
        self.assertEqual(own.owned_module_names(mine, OURS), ["cartogen_ai"])
        self.assertEqual(own.owned_module_names(shared, OURS), [])

    def test_a_directory_with_the_same_prefix_is_not_ours(self):
        sibling = OURS + "_pro"
        modules = {"cartogen_ai.sibling": _module(os.path.join(sibling, "m.py"))}
        self.assertEqual(own.owned_module_names(modules, OURS), [])

    def test_modules_without_any_location_are_left_alone(self):
        self.assertEqual(own.owned_module_names({"cartogen_ai.odd": _module()}, OURS), [])


if __name__ == "__main__":
    unittest.main()
