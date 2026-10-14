"""Diagnostic: prints the WHOLE Processing registry of the QGIS in the CI image, one JSON line per algorithm, between two marker lines.

Why (owner request 2026-10-14: a full list of what QGIS can do versus what the plugin covers): the documentation lists 454 algorithms, the
real 4.2.2 registry has 772 (see test_processing_registry_diagnostic_live.py). This dump is the authoritative source for the coverage matrix
in docs/QGIS_COVERAGE_GAP_ANALYSIS_2026-10-14.md. It asserts nothing about content, so it cannot fail a build for a QGIS update; it only
needs the registry to be non-empty. Each line: id, display name, group, provider, flags (including the SecurityRisk flag QGIS puts on
algorithms that run code or touch the system), parameters as [name, type, is_destination, flags] and outputs as [name, type]."""
import json
import unittest

try:
    from qgis.core import QgsApplication
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False


@unittest.skipUnless(QGIS_LIVE_AVAILABLE, "requires real QGIS")
class TestRegistryDump(unittest.TestCase):
    def test_dump_registry(self):
        from tests.test_processing_registry_diagnostic_live import _boot
        _boot()
        registry = QgsApplication.processingRegistry()
        lines = ["", "=== REGISTRY-DUMP-BEGIN ==="]
        count = 0
        for alg in sorted(registry.algorithms(), key=lambda a: a.id()):
            try:
                params = [[p.name(), str(p.type()), bool(p.isDestination()), int(p.flags())] for p in alg.parameterDefinitions()]
                outputs = [[o.name(), str(o.type())] for o in alg.outputDefinitions()]
                lines.append("ALG " + json.dumps({
                    "id": alg.id(), "name": alg.displayName(), "group": alg.group(), "provider": alg.provider().id(),
                    "flags": str(alg.flags()), "params": params, "outputs": outputs}, ensure_ascii=False))
                count += 1
            except Exception as e:                       # one odd algorithm must not hide the others
                lines.append("ALGERR " + json.dumps({"id": alg.id(), "error": str(e)[:100]}))
        lines.append(f"=== REGISTRY-DUMP-END count={count} ===")
        print("\n".join(lines), flush=True)
        self.assertGreater(count, 100)


if __name__ == "__main__":
    unittest.main()
