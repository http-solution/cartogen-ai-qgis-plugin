# -*- coding: utf-8 -*-
"""
Golden Scenario Runner: Executes all Golden Humanitarian Scenarios in sequence.
"""

import unittest
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
_src = os.path.join(_root, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
if _here not in sys.path:
    sys.path.insert(0, _here)

from qgis.core import QgsApplication
if not QgsApplication.instance():
    _qgs_app = QgsApplication([], False)
    _qgs_app.initQgis()

from test_golden_scenario_pin_001 import TestGoldenScenarioPin001
from test_golden_scenario_pin_002 import TestGoldenScenarioPin002
from test_golden_scenario_sev_001 import TestGoldenScenarioSev001
from test_golden_scenario_3w_001 import TestGoldenScenario3W001
from test_golden_scenario_access_001 import TestGoldenScenarioAccess001
from test_golden_scenario_jiaf_001 import TestGoldenScenarioJiaf001
from test_golden_scenario_output_001 import TestGoldenScenarioOutput001
from test_golden_scenario_cod_001 import TestGoldenScenarioCod001
from test_golden_scenario_prompt_001 import TestGoldenScenarioPrompt001
from test_golden_scenario_prompt_002 import TestGoldenScenarioPrompt002
from test_golden_scenario_protection_001 import TestGoldenScenarioProtection001
from test_golden_scenario_export_001 import TestGoldenScenarioExport001
from test_antimeridian_bbox import TestAntimeridianBbox


def suite():
    s = unittest.TestSuite()
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioPin001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioPin002))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioSev001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenario3W001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioAccess001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioJiaf001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioOutput001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioCod001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioPrompt001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioPrompt002))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioProtection001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestGoldenScenarioExport001))
    s.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TestAntimeridianBbox))
    return s


if __name__ == "__main__":
    from qgis.core import QgsApplication
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        runner = unittest.TextTestRunner(verbosity=2)
        res = runner.run(suite())
        sys.exit(0 if res.wasSuccessful() else 1)
    finally:
        qgs.exitQgis()
