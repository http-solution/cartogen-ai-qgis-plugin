"""PLAN-038: the experimental CLI providers are reachable only through an explicit opt-in, and the wiring points where it should.
Pure Python: the Settings dialog and orchestrator import Qt/QGIS, so their wiring is checked from source here and exercised for real in
tests/test_cli_provider_settings_live.py (CI live job)."""
import ast
import contextlib
import unittest
from pathlib import Path
from unittest.mock import patch

from cartogen_ai.infrastructure import settings_keys as sk
from cartogen_ai.infrastructure.providers import cli_bridge

SRC = Path(__file__).resolve().parents[1] / "src" / "cartogen_ai"


def _text(*parts):
    return SRC.joinpath(*parts).read_text(encoding="utf-8")


class TestOptIn(unittest.TestCase):
    def test_cli_providers_are_not_in_the_enabled_set(self):
        self.assertFalse(set(sk.CLI_PROVIDERS) & set(sk.ENABLED_PROVIDERS))

    def test_without_the_switch_a_saved_cli_provider_falls_back(self):
        for p in sk.CLI_PROVIDERS:
            self.assertEqual(sk.normalize_provider(p), sk.DEFAULT_PROVIDER)  # no QGIS here, so the switch reads as off

    def test_with_the_switch_a_saved_cli_provider_is_kept(self):
        with patch.object(sk, "cli_providers_enabled", return_value=True):
            for p in sk.CLI_PROVIDERS:
                self.assertEqual(sk.normalize_provider(p), p)
            self.assertEqual(sk.normalize_provider("nonsense"), sk.DEFAULT_PROVIDER)
            self.assertEqual(sk.normalize_provider("openai"), sk.DEFAULT_PROVIDER)

    def test_the_switch_is_off_when_unreadable(self):
        self.assertFalse(sk.cli_providers_enabled())

    def test_path_setting_key_is_per_provider_and_namespaced(self):
        keys = {sk.cli_path_setting_key(p) for p in sk.CLI_PROVIDERS}
        self.assertEqual(len(keys), 3)
        self.assertTrue(all(k.startswith("cartogen_ai/") for k in keys))


class TestWiring(unittest.TestCase):
    @staticmethod
    def _module_constants():
        """Top-level `NAME = <literal>` assignments of the dialog module (it imports Qt, so it is parsed, not imported)."""
        tree = ast.parse(_text("core", "ui", "connections_catalog.py"))
        out = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                with contextlib.suppress(ValueError):
                    out[node.targets[0].id] = ast.literal_eval(node.value)
        return out

    def _cli_entries(self):
        """The _CLI_PROVIDERS dicts with their non-literal values (setting-key names, _CLI_NOTE) replaced by markers."""
        tree = ast.parse(_text("core", "ui", "connections_catalog.py"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_CLI_PROVIDERS":
                entries = []
                for d in node.value.elts:
                    entry = {}
                    for k, v in zip(d.keys, d.values, strict=True):
                        try:
                            entry[k.value] = ast.literal_eval(v)
                        except ValueError:
                            entry[k.value] = "<name>"
                    entries.append(entry)
                return entries
        self.fail("_CLI_PROVIDERS not found")
        return []

    def test_orchestrator_builds_each_cli_client(self):
        text = _text("core", "agent", "agent_orchestrator.py")
        self.assertIn("elif provider_name in CLI_PROVIDERS:", text)
        for cls in ("ClaudeCliClient", "CodexCliClient", "GeminiCliClient"):
            self.assertIn(cls, text)

    def test_the_dialog_always_lists_the_cli_entries_but_gates_choosing_them_on_the_acknowledgement(self):
        text = _text("core", "ui", "connections_dialog.py")
        self.assertIn("self._providers = PROVIDERS + _CLI_PROVIDERS", text)
        self.assertIn('use_btn.setEnabled(self.experimental_cli_checkbox.isChecked())', text)
        self.assertIn('self._use_buttons[pv].setEnabled(checked)', text)
        self.assertRegex(_text("core", "ui", "connections_catalog.py"),
                         r'PROVIDERS = \[e for e in _ALL_PROVIDERS if e\["value"\] in ENABLED_PROVIDERS\]')
        entries = self._cli_entries()
        self.assertEqual([e["value"] for e in entries], list(sk.CLI_PROVIDERS))
        self.assertTrue(all(e["key_storage"] == "setting" and e["group"] == "cli" for e in entries))

    def test_every_provider_belongs_to_a_known_group(self):
        consts = self._module_constants()
        groups = set(consts["_GROUP_TITLES"])
        self.assertEqual(groups, {"hosted", "local", "cli"})
        self.assertTrue(set(consts["_GROUP_OF"].values()) <= groups)
        self.assertEqual(consts["_GROUP_OF"]["ollama"], "local")

    def test_the_program_path_is_saved_as_a_plain_setting_not_a_credential(self):
        text = _text("core", "ui", "connections_dialog.py")
        self.assertRegex(text, r'if entry\.get\("key_storage"\) == "setting":\s+self\.settings\.setValue\(cli_path_setting_key\(pv\)')

    def test_every_cli_page_says_data_goes_to_the_vendor(self):
        note = self._module_constants()["_CLI_NOTE"]
        self.assertIn("sends the conversation, including any layer or attribute data a tool surfaces, to that vendor's service", note)
        self.assertIn("treat it as a cloud provider", note)
        self.assertIn("not yet verified", note)
        self.assertTrue(all(e["page_note"] is not None for e in self._cli_entries()))

    def test_quick_switcher_labels_cover_every_cli_provider(self):
        from cartogen_ai.core.ui.dock_constants import CLI_PROVIDER_LABELS
        self.assertEqual(set(CLI_PROVIDER_LABELS), set(sk.CLI_PROVIDERS))

    def test_quick_switcher_fixed_list_still_excludes_them(self):
        from cartogen_ai.core.ui.dock_constants import PROVIDER_CHOICES
        self.assertFalse({v for _, v in PROVIDER_CHOICES} & set(sk.CLI_PROVIDERS))

    def test_no_missing_key_nudge_for_cli_providers(self):
        self.assertIn("provider in CLI_PROVIDERS", _text("infrastructure", "auth.py"))

    def test_providers_package_exports_the_clients(self):
        from cartogen_ai.infrastructure import providers
        for name in ("ClaudeCliClient", "CodexCliClient", "GeminiCliClient"):
            self.assertIn(name, providers.__all__)


class TestStopButton(unittest.TestCase):
    def test_default_cancel_follows_the_agents_stop_signal(self):
        from cartogen_ai.core.agent import cancel_signal
        client = cli_bridge.ClaudeCliClient()
        self.assertFalse(client.cancel_event.is_set())
        token = cancel_signal.begin(lambda: True)
        try:
            self.assertTrue(client.cancel_event.is_set())
        finally:
            cancel_signal.end(token)
        self.assertFalse(client.cancel_event.is_set())

    def test_an_explicit_cancel_event_is_kept(self):
        import threading
        ev = threading.Event()
        self.assertIs(cli_bridge.CodexCliClient(cancel_event=ev).cancel_event, ev)


if __name__ == "__main__":
    unittest.main()
