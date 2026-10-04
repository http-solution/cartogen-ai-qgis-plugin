# -*- coding: utf-8 -*-
"""Diagnostic (GitHub #162, audit F26): which Processing algorithm ids the plugin references are missing from the real registry.

Step 1 of the work package: it changes no behaviour and does not fail on a missing id -- it PRINTS a report (visible in the CI log)
so the fixes in step 2 are based on what QGIS 4.2.2 actually has, not on guesses. Written without a local QGIS: CI's first run is
its first execution."""
import unittest

try:
    from qgis.core import QgsApplication
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


def _boot():
    from tests.test_chat_widget_live import _boot_qgis
    _boot_qgis()
    notes = []
    try:
        from processing.core.Processing import Processing
        Processing.initialize()
    except Exception as e:
        notes.append(f"Processing.initialize() failed: {e}")
    try:
        from qgis.analysis import QgsNativeAlgorithms
        registry = QgsApplication.processingRegistry()
        if registry.providerById("native") is None:
            registry.addProvider(QgsNativeAlgorithms())
    except Exception as e:
        notes.append(f"native provider could not be added: {e}")
    return notes


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestProcessingRegistryDiagnostic(unittest.TestCase):
    def test_report_referenced_ids_missing_from_the_registry(self):
        from qgis.core import Qgis
        from tests._algorithm_ids import referenced_algorithm_ids, suggestions
        notes = _boot()
        registry = QgsApplication.processingRegistry()
        all_ids = sorted(a.id() for a in registry.algorithms())
        providers = sorted(p.id() for p in registry.providers())
        referenced = referenced_algorithm_ids()
        missing = {i: files for i, files in referenced.items() if registry.algorithmById(i) is None}
        lines = ["", "=== PROCESSING REGISTRY DIAGNOSTIC (#162) ===",
                 f"QGIS {Qgis.version()} | providers: {providers} | algorithms in registry: {len(all_ids)}",
                 f"ids referenced by the plugin source: {len(referenced)} | missing: {len(missing)}"]
        lines += [f"note: {n}" for n in notes]
        for algorithm_id, files in missing.items():
            lines.append(f"MISSING {algorithm_id}  (used in: {', '.join(files)})")
            lines.append(f"    possible replacements in this registry: {suggestions(algorithm_id, all_ids) or 'none found'}")
        if not missing:
            lines.append("all referenced ids resolve")
        lines.append("=== END DIAGNOSTIC ===")
        print("\n".join(lines), flush=True)
        # The report above covers every id mentioned anywhere in the source (a gated SAGA reference may still be listed). The
        # ALLOWLIST is different: the generic tool offers those ids to the model, so each must exist in this registry.
        self.assertGreater(len(all_ids), 100, "the Processing registry is nearly empty, so the report above is meaningless")
        from cartogen_ai.core.agent.tools._processing_allowlist import ALLOWED_ALGORITHM_IDS
        offered_but_missing = sorted(i for i in ALLOWED_ALGORITHM_IDS if registry.algorithmById(i) is None)
        self.assertEqual(offered_but_missing, [], f"allowlisted ids the registry does not have: {offered_but_missing}")


if __name__ == "__main__":
    unittest.main()
