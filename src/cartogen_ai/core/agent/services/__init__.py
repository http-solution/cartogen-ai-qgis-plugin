# -*- coding: utf-8 -*-
"""
Agent-internal services that are not registered tools -- process-isolation
management for `execute_pyqgis_script` lives here (script_isolation.py). Not
imported by anything on the plain-`test` CI path unconditionally, since
importing `qgis.core` at module scope would break there like every other
QGIS-touching module -- each module in this package guards its own
`qgis.core` import exactly like `agent/tools/*.py` does.
"""
