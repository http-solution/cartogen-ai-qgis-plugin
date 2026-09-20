# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import cartogen_ai.core.agent.agent_orchestrator as agent_mod
from cartogen_ai.core.agent.agent_orchestrator import CartogenAi, NETWORK_ONLY_TOOLS, TWO_PHASE_TOOLS, TASK_MANAGEMENT_TOOLS
from cartogen_ai.core.agent.tools.db_and_workflow_tools import execute_read_only_sql, _enforce_db_read_only, load_workflow_preset
from cartogen_ai.core.agent.tools.vector_tools import (
    spatial_join, remove_layer, field_calculator,
    calculate_area, calculate_length,
    _prefetch_url_to_temp, join_by_attribute, _is_safe_url, load_tabular_data_as_layer,
    _detect_geometry_fields, _sniff_csv_header, _sniff_excel_header, _validate_wgs84_coordinates,
    _sample_xy_values, _qvariant_type_for_dtype,
)
from cartogen_ai.core.agent.tools.system_tools import execute_pyqgis_script, _validate_script_safety
from cartogen_ai.core.agent.tools.humanitarian_tools import (
    fetch_geoboundaries_network_phase, add_geoboundaries_layer_main_thread_phase, add_incident_point,
    add_point_layer, search_hdx_datasets, fetch_osm_features,
    fetch_hdx_admin_boundaries_network_phase, add_hdx_admin_boundaries_layer_main_thread_phase,
    fetch_building_footprints_network_phase, add_building_footprints_layer_main_thread_phase,
    _lonlat_to_tile_xy, _tile_xy_to_quadkey, _quadkeys_for_bbox,
    _match_building_footprints_location, _feature_centroid,
    _LOOKUP_CACHE as _HUMANITARIAN_LOOKUP_CACHE,
    _cleanup_cached_local_path,
)
from cartogen_ai.core.agent.tools.system_tools import (
    resolve_gemini_search_config, gemini_grounded_search, geocode_batch, _GEOCODE_CACHE,
    resolve_openai_search_config, openai_grounded_search, geocode_and_enrich,
)


def pytest_importorskip_pandas(test_case):
    """pandas/openpyxl are optional, qpip-managed dependencies -- skip
    Excel-dependent tests rather than fail on a machine that hasn't
    installed them, matching this suite's tolerance for optional deps."""
    try:
        import pandas as pd
        import openpyxl  # noqa: F401 -- required by pandas' to_excel/read_excel
        return pd
    except ImportError:
        test_case.skipTest("pandas/openpyxl not installed")


class _FakeField:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class _FakeFields(list):
    def indexOf(self, name):
        for i, f in enumerate(self):
            if f.name() == name:
                return i
        return -1


class _FakeLayer:
    """Minimal QgsVectorLayer stand-in for testing join_by_attribute's pure-Python
    fuzzy-matching/cardinality logic without needing a real QGIS layer."""
    def __init__(self, field_names, feature_count=0, unique_counts=None):
        self._fields = _FakeFields(_FakeField(n) for n in field_names)
        self._feature_count = feature_count
        self._unique_counts = unique_counts or {}

    def fields(self):
        return self._fields

    def featureCount(self):
        return self._feature_count

    def uniqueValues(self, idx):
        field_name = self._fields[idx].name()
        count = self._unique_counts.get(field_name, self._feature_count)
        return list(range(count))


class TestNewTools(unittest.TestCase):
    def test_sql_read_only_guard(self):
        bad_res = execute_read_only_sql("DROP TABLE users;")
        self.assertIn("error", bad_res)
        self.assertIn("Destructive/non-read-only SQL keyword 'DROP' rejected", bad_res["error"])

    def test_enforce_db_read_only_degrades_gracefully_outside_qgis(self):
        # QgsProviderRegistry doesn't exist in this environment -- must not raise, must no-op (None)
        res = _enforce_db_read_only("dummy_uri", "SELECT 1")
        self.assertIsNone(res)

    def test_enforce_db_read_only_fails_closed_when_set_read_only_fails(self):
        # A2: if the DB-level READ ONLY session can't be confirmed, this must
        # refuse the query (fail closed) rather than silently proceeding
        # (fail open) with no real read-only guarantee at all.
        from unittest.mock import MagicMock
        fake_conn = MagicMock()
        fake_conn.executeSql.side_effect = Exception("driver does not support this statement")
        fake_md = MagicMock()
        fake_md.createConnection.return_value = fake_conn
        fake_registry = MagicMock()
        fake_registry.instance.return_value.providerMetadata.return_value = fake_md

        with patch("cartogen_ai.core.agent.tools.db_and_workflow_tools.QgsProviderRegistry", fake_registry, create=True):
            res = _enforce_db_read_only("dummy_uri", "SELECT 1")

        self.assertIsInstance(res, dict)
        self.assertIn("error", res)
        self.assertIn("refusing to execute", res["error"])
        # The query itself must never have been executed on this connection.
        fake_conn.executeSql.assert_called_once_with("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")

    def test_sql_rejects_multiple_statements(self):
        res = execute_read_only_sql("SELECT 1; DROP TABLE users;")
        self.assertIn("error", res)
        self.assertIn("Multiple SQL statements", res["error"])

    def test_sql_rejects_expanded_keywords(self):
        for query in (
            "SELECT * FROM t INTO new_table",
            "COPY (SELECT 1) TO PROGRAM 'curl x'",
            "SELECT pg_sleep(1); CALL some_proc()",
        ):
            res = execute_read_only_sql(query)
            self.assertIn("error", res, query)

    def test_sql_rejects_server_side_file_and_cross_server_functions(self):
        # Confirmed live: none of the DML/DDL keywords above catch these, and
        # the DB-level read-only-transaction enforcement doesn't either (these
        # aren't table mutations) -- lo_export/pg_read_file read arbitrary
        # server-side files from a plain SELECT, dblink runs SQL against a
        # completely different server.
        for query in (
            "SELECT lo_export(12345, '/tmp/leaked.txt')",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT pg_read_binary_file('/etc/passwd')",
            "SELECT pg_ls_dir('/tmp')",
            "SELECT * FROM dblink('host=attacker.com', 'SELECT 1') AS t(x int)",
            "SELECT dblink_exec('dbname=x', 'DROP TABLE y')",
        ):
            res = execute_read_only_sql(query)
            self.assertIn("error", res, query)

    def test_sql_allows_normal_select(self):
        res = execute_read_only_sql("SELECT * FROM parcels WHERE owner = 'x'")
        self.assertTrue(res.get("success"))

    def test_spatial_join_fallback(self):
        res = spatial_join("layer_a", "layer_b")
        self.assertIn("error", res)

    def test_join_by_attribute_fallback(self):
        res = join_by_attribute("layer_a", "layer_b")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    def test_join_by_attribute_suggests_fuzzy_field_matches(self, mock_find):
        target = _FakeLayer(["city_name", "population"])
        join_layer = _FakeLayer(["City_Name", "country"])
        mock_find.side_effect = lambda name: {"target_layer": target, "join_layer": join_layer}[name]

        res = join_by_attribute("target_layer", "join_layer")
        self.assertEqual(res.get("status"), "FIELD_SUGGESTION")
        self.assertTrue(any(s["target_field"] == "city_name" for s in res["suggestions"]))

    @patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.vector_tools._find_layer_by_name")
    @patch("cartogen_ai.core.agent.tools.vector_tools._run_and_add")
    def test_join_by_attribute_warns_on_non_unique_join_field(self, mock_run, mock_find):
        target = _FakeLayer(["id", "name"])
        join_layer = _FakeLayer(["ref_id"], feature_count=10, unique_counts={"ref_id": 3})
        mock_find.side_effect = lambda name: {"target_layer": target, "join_layer": join_layer}[name]
        mock_run.return_value = {"success": True, "layer_name": "target_layer_attrjoined"}

        res = join_by_attribute("target_layer", "join_layer", target_field="id", join_field="ref_id")
        self.assertIn("cardinality_warning", res)

    def test_detect_geometry_fields_lat_lon(self):
        self.assertEqual(
            _detect_geometry_fields(["id", "name", "Latitude", "Longitude"]),
            {"x_field": "Longitude", "y_field": "Latitude"},
        )

    def test_detect_geometry_fields_wkt(self):
        self.assertEqual(_detect_geometry_fields(["id", "geom"]), {"wkt_field": "geom"})

    def test_detect_geometry_fields_none_when_ambiguous(self):
        self.assertIsNone(_detect_geometry_fields(["id", "name", "value"]))

    def test_sniff_csv_header(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("id,latitude,longitude,name\n1,31.9,35.9,Amman\n")
            self.assertEqual(_sniff_csv_header(path), ["id", "latitude", "longitude", "name"])
        finally:
            os.remove(path)

    def test_load_tabular_data_as_layer_degrades_gracefully_outside_qgis(self):
        res = load_tabular_data_as_layer("/some/data.csv")
        self.assertIn("error", res)
        self.assertIn("QGIS not available", res["error"])

    def test_load_tabular_data_as_layer_rejects_missing_file(self):
        with patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True):
            res = load_tabular_data_as_layer("/definitely/not/a/real/file.csv")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    def test_load_tabular_data_as_layer_rejects_unsupported_extension(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".shp")
        os.close(fd)
        try:
            with patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True):
                res = load_tabular_data_as_layer(path)
            self.assertIn("error", res)
            self.assertIn("Unsupported file type", res["error"])
        finally:
            os.remove(path)

    def test_load_tabular_data_as_layer_suggests_fields_when_ambiguous(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("id,name,value\n1,a,10\n")
            with patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True):
                res = load_tabular_data_as_layer(path)
            self.assertEqual(res.get("status"), "FIELD_SUGGESTION")
            self.assertEqual(res["columns"], ["id", "name", "value"])
        finally:
            os.remove(path)

    def test_sniff_excel_header(self):
        # Regression test for the bug this was built to fix: geometry-column
        # auto-detection previously only ran for CSV, so an Excel file with
        # lat/lon columns was always loaded as a plain non-spatial table.
        import tempfile, os
        pd = pytest_importorskip_pandas(self)
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            pd.DataFrame({"id": [1], "latitude": [31.9], "longitude": [35.9], "name": ["Amman"]}).to_excel(path, index=False)
            self.assertEqual(_sniff_excel_header(path), ["id", "latitude", "longitude", "name"])
        finally:
            os.remove(path)

    def test_detect_geometry_fields_works_on_excel_header(self):
        # _detect_geometry_fields itself is QGIS-independent, but Excel column
        # names come back from pandas as native str already -- confirms the
        # str()-wrapped lower_map in _detect_geometry_fields still matches.
        self.assertEqual(
            _detect_geometry_fields(["id", "Latitude", "Longitude", "name"]),
            {"x_field": "Longitude", "y_field": "Latitude"},
        )

    def test_validate_wgs84_coordinates_accepts_real_lon_lat(self):
        self.assertIsNone(_validate_wgs84_coordinates([35.9, 44.19], [31.9, 15.36]))

    def test_validate_wgs84_coordinates_flags_projected_coordinates(self):
        warning = _validate_wgs84_coordinates([712345.6, 698234.1], [1698234.5, 1701234.0])
        self.assertIsNotNone(warning)
        self.assertIn("swapped", warning)

    def test_validate_wgs84_coordinates_empty_sample_skips_check(self):
        self.assertIsNone(_validate_wgs84_coordinates([], []))

    def test_sample_xy_values_from_csv(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("id,latitude,longitude\n1,31.9,35.9\n2,15.36,44.19\n")
            xs, ys = _sample_xy_values(path, ".csv", "longitude", "latitude", ",", None)
            self.assertEqual(xs, [35.9, 44.19])
            self.assertEqual(ys, [31.9, 15.36])
        finally:
            os.remove(path)

    def test_sample_xy_values_from_excel(self):
        import tempfile, os
        pd = pytest_importorskip_pandas(self)
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            pd.DataFrame({"latitude": [31.9, 15.36], "longitude": [35.9, 44.19]}).to_excel(path, index=False)
            xs, ys = _sample_xy_values(path, ".xlsx", "longitude", "latitude", ",", None)
            self.assertEqual(xs, [35.9, 44.19])
            self.assertEqual(ys, [31.9, 15.36])
        finally:
            os.remove(path)

    def test_load_tabular_data_as_layer_rejects_swapped_coordinates(self):
        # Integration-level regression test: this validation runs before any
        # QGIS layer object is touched, so it's reachable without mocking
        # QgsVectorLayer/QgsGeometry internals.
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("id,x,y\n1,712345.6,1698234.5\n2,698234.1,1701234.0\n")
            with patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True):
                res = load_tabular_data_as_layer(path, x_field="x", y_field="y")
            self.assertIn("error", res)
            self.assertIn("WGS84", res["error"])
        finally:
            os.remove(path)

    @patch("cartogen_ai.core.agent.tools.vector_tools.QVariant", create=True)
    def test_qvariant_type_for_dtype_maps_common_pandas_dtypes(self, mock_qvariant):
        pd = pytest_importorskip_pandas(self)
        mock_qvariant.LongLong, mock_qvariant.Double = "LongLong", "Double"
        mock_qvariant.DateTime, mock_qvariant.Bool, mock_qvariant.String = "DateTime", "Bool", "String"
        df = pd.DataFrame({
            "i": [1, 2], "f": [1.5, 2.5], "s": ["a", "b"], "b": [True, False],
        })
        self.assertEqual(_qvariant_type_for_dtype(df["i"].dtype), "LongLong")
        self.assertEqual(_qvariant_type_for_dtype(df["f"].dtype), "Double")
        self.assertEqual(_qvariant_type_for_dtype(df["s"].dtype), "String")
        self.assertEqual(_qvariant_type_for_dtype(df["b"].dtype), "Bool")

    def test_destructive_remove_layer_gate(self):
        res = remove_layer("layer_test", confirmed=False)
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")
        self.assertTrue(res.get("requires_confirmation"))

    def test_destructive_field_calculator_gate(self):
        res = field_calculator("layer_test", "pop_density", "pop / area", confirmed=False)
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")

    def test_destructive_calculate_area_gate(self):
        # docs/archive/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md: calculate_area calls the same
        # _add_calculated_field primitive as field_calculator, so it must be gated
        # the same way -- this was a real, fixed inconsistency, not a duplicate test.
        res = calculate_area("layer_test", confirmed=False)
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")
        self.assertTrue(res.get("requires_confirmation"))

    def test_destructive_calculate_length_gate(self):
        res = calculate_length("layer_test", confirmed=False)
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")
        self.assertTrue(res.get("requires_confirmation"))

    def test_dispatcher_schema_filtering_prevents_bypass(self):
        # Even if an LLM injects {"confirmed": True} into tool arguments, the dispatcher strips it
        agent = CartogenAi()
        res = agent._real_execute_tool("remove_layer", {"layer_name": "test_layer", "confirmed": True})
        self.assertEqual(res.get("status"), "PREVIEW_REQUIRED")

    def test_script_safety_blocks_dangerous_imports(self):
        self.assertIsNotNone(_validate_script_safety("import os\ndef run():\n    os.remove('x')"))
        self.assertIsNotNone(_validate_script_safety("import subprocess\ndef run():\n    pass"))
        self.assertIsNotNone(_validate_script_safety("from shutil import rmtree\ndef run():\n    pass"))

    def test_script_safety_blocks_dangerous_calls(self):
        self.assertIsNotNone(_validate_script_safety("def run():\n    eval('1+1')"))
        self.assertIsNotNone(_validate_script_safety("def run():\n    __import__('os')"))

    def test_script_safety_allows_normal_pyqgis(self):
        self.assertIsNone(_validate_script_safety(
            "def run():\n    from qgis.core import QgsProject\n    return len(QgsProject.instance().mapLayers())"
        ))

    def test_execute_pyqgis_script_rejects_blocked_import(self):
        res = execute_pyqgis_script("import os\ndef run():\n    return os.getcwd()")
        self.assertIn("error", res)
        self.assertIn("rejected for safety", res["error"])

    def test_script_safety_blocks_expanded_module_list(self):
        # A1: urllib/requests/pickle/etc. give network or serialization-based
        # exfiltration paths and had no legitimate use here, but weren't
        # blocked before this hardening pass.
        for snippet in (
            "import urllib.request\ndef run():\n    pass",
            "import requests\ndef run():\n    pass",
            "import pickle\ndef run():\n    pass",
            "import base64\ndef run():\n    pass",
            "import sqlite3\ndef run():\n    pass",
        ):
            self.assertIsNotNone(_validate_script_safety(snippet), snippet)

    def test_script_safety_blocks_open(self):
        self.assertIsNotNone(_validate_script_safety("def run():\n    return open('x').read()"))

    def test_script_safety_blocks_filesystem_modules_that_bypass_open(self):
        """Live-confirmed 2026-09-04 (re-review of docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md
        Section 4 against an external sandbox-design critique): pathlib/dbm/logging/zipfile
        each write real files to disk via a method call, not the builtin `open` name --
        so they passed this validator completely unblocked before this test/fix, and the
        resulting script executed successfully against the real _SAFE_BUILTINS-restricted
        exec() environment (reproduced against an extracted copy of this exact module before
        applying the fix). See the comment above _BLOCKED_MODULES for the full writeup."""
        snippets = [
            "import pathlib\ndef run():\n    pathlib.Path('x').write_text('y')",
            "import dbm\ndef run():\n    dbm.open('x', 'c')",
            "import logging\ndef run():\n    logging.FileHandler('x')",
            "import zipfile\ndef run():\n    zipfile.ZipFile('x', 'w')",
        ]
        for snippet in snippets:
            self.assertIsNotNone(_validate_script_safety(snippet), snippet)

    def test_script_safety_blocks_second_wave_of_filesystem_registry_and_network_modules(self):
        """Live-confirmed 2026-09-05 (a systematic sweep of the exact same gap shape
        the pathlib/dbm/logging/zipfile fix above closed, per point 19's "not a claim
        of completeness" note): each of these executed successfully -- a real file
        write, a real Windows registry key write, or a real file read -- against the
        actual _SAFE_BUILTINS-restricted exec() path before this fix, reproduced with
        a harness that calls this module's own _validate_script_safety + exec()
        exactly as execute_pyqgis_script does. `io.open` is literally the same
        function object as the builtin `open` (`io.open is open` is True) but reached
        via attribute access, invisible to the bare-name check on 'open'.
        socketserver/poplib/imaplib/nntplib/xmlrpc are the same network-protocol-
        client category already blocked via ftplib/smtplib; webbrowser/pydoc can
        launch an external program the same way the already-blocked QDesktopServices
        can; zipimport loads code from a zip file the same way importlib/runpy can.
        See the comment above _BLOCKED_MODULES for the full per-module writeup."""
        snippets = [
            "import io\ndef run():\n    io.open('x', 'w').write('y')",
            "import tarfile, io as _io\ndef run():\n    tarfile.open('x', 'w')",
            "import gzip\ndef run():\n    gzip.open('x', 'wb')",
            "import bz2\ndef run():\n    bz2.open('x', 'wb')",
            "import lzma\ndef run():\n    lzma.open('x', 'wb')",
            "import winreg\ndef run():\n    winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'x')",
            "import linecache\ndef run():\n    return linecache.getline('C:\\\\Windows\\\\win.ini', 1)",
            "import filecmp\ndef run():\n    return filecmp.cmp('a', 'b')",
            "import socketserver\ndef run():\n    pass",
            "import poplib\ndef run():\n    pass",
            "import imaplib\ndef run():\n    pass",
            "import nntplib\ndef run():\n    pass",
            "import xmlrpc.client\ndef run():\n    pass",
            "import webbrowser\ndef run():\n    pass",
            "import pydoc\ndef run():\n    pass",
            "import zipimport\ndef run():\n    pass",
            "import venv\ndef run():\n    pass",
            "import mmap\ndef run():\n    pass",
        ]
        for snippet in snippets:
            self.assertIsNotNone(_validate_script_safety(snippet), snippet)

    def test_script_safety_blocks_frame_traceback_introspection_escape(self):
        """Live-confirmed 2026-09-08 (full independent code review): a script can
        reach the REAL, unrestricted `builtins` module -- completely bypassing
        _SAFE_BUILTINS -- by walking an exception traceback's frame chain, with no
        blocked import and no name this validator previously checked. Reproduced
        against an extracted copy of this exact module before the fix: this exact
        script passed _validate_script_safety (returned None) and, run through the
        real _SAFE_BUILTINS-restricted exec() path exactly as execute_pyqgis_script
        does it, successfully wrote a real file to disk. `f_back`/`f_globals`/
        `tb_frame` are ordinary frame/traceback attribute names, and
        `f.f_globals['__builtins__']` is a string dict KEY, not an ast.Attribute
        node -- neither was covered by the existing `__builtins__` attribute check.
        See the 2026-09-08 comment above _BLOCKED_DUNDER_ATTRS for the full writeup,
        and docs/CODE_REVIEW_2026-09-08.md Sec 4.1 / BUG_TRACKER.md
        NEW-2026-09-08-1 for the original review finding."""
        full_escape_chain = (
            "def run():\n"
            "    try:\n"
            "        raise ValueError('trigger')\n"
            "    except ValueError as e:\n"
            "        f = e.__traceback__.tb_frame\n"
            "        while f.f_back is not None:\n"
            "            f = f.f_back\n"
            "        real_builtins = f.f_globals['__builtins__']\n"
            "        ns = real_builtins if isinstance(real_builtins, dict) else real_builtins.__dict__\n"
            "        return ns['open']\n"
        )
        self.assertIsNotNone(_validate_script_safety(full_escape_chain), full_escape_chain)

        # Each individual new attribute name, blocked on its own regardless of
        # receiver -- matches how every other entry in _BLOCKED_DUNDER_ATTRS is
        # tested elsewhere in this file.
        for attr in (
            "f_back", "f_globals", "f_locals", "f_builtins", "f_code",
            "gi_frame", "cr_frame", "ag_frame", "tb_frame", "tb_next",
            "__traceback__",
        ):
            snippet = f"def run():\n    x = 1\n    return x.{attr}"
            self.assertIsNotNone(_validate_script_safety(snippet), snippet)

    def test_execute_pyqgis_script_rejects_frame_traceback_escape_end_to_end(self):
        """Same PoC as above, run through execute_pyqgis_script itself (not just
        the validator function directly) -- confirms the fix actually protects the
        real tool entry point, not just the unit-tested internal helper."""
        script = (
            "def run():\n"
            "    try:\n"
            "        raise ValueError('trigger')\n"
            "    except ValueError as e:\n"
            "        f = e.__traceback__.tb_frame\n"
            "        while f.f_back is not None:\n"
            "            f = f.f_back\n"
            "        real_builtins = f.f_globals['__builtins__']\n"
            "        ns = real_builtins if isinstance(real_builtins, dict) else real_builtins.__dict__\n"
            "        real_open = ns['open']\n"
            "        real_open('/tmp/should_never_be_created_by_this_test.txt', 'w').write('pwned')\n"
            "        return 'escaped'\n"
        )
        res = execute_pyqgis_script(script)
        self.assertIn("error", res)
        self.assertIn("rejected for safety", res["error"])
        self.assertNotEqual(res.get("result"), "escaped")
        import os
        self.assertFalse(os.path.exists("/tmp/should_never_be_created_by_this_test.txt"))

    def test_script_safety_blocks_aliased_eval(self):
        # x = eval; x(...) doesn't call eval directly -- must still be caught
        # since the AST check now flags any Name/Attribute reference, not
        # just the direct target of a Call.
        self.assertIsNotNone(_validate_script_safety("def run():\n    x = eval\n    return x('1+1')"))

    def test_script_safety_blocks_getattr_setattr_delattr(self):
        self.assertIsNotNone(_validate_script_safety("def run():\n    return getattr(1, 'x')"))
        self.assertIsNotNone(_validate_script_safety("def run():\n    setattr(1, 'x', 2)"))
        self.assertIsNotNone(_validate_script_safety("def run():\n    delattr(1, 'x')"))

    def test_script_safety_blocks_dunder_escape_chain(self):
        # The classic ().__class__.__bases__[0].__subclasses__() sandbox
        # escape -- blocked regardless of what object it's accessed on.
        self.assertIsNotNone(_validate_script_safety(
            "def run():\n    return ().__class__.__bases__[0].__subclasses__()"
        ))

    def test_script_safety_blocks_dict_subscript_subclasses_bypass(self):
        # Found 2026-09-20 during Part B verification (a deliberate attempt at a novel
        # bypass beyond the two previously checked): type.__dict__['__subclasses__']
        # retrieves the same dangerous method the classic .__class__.__bases__[0].
        # __subclasses__() chain uses, but via a dict subscript on .__dict__ (an
        # ast.Subscript with a string constant) rather than a literal .__subclasses__
        # ast.Attribute node -- invisible to the attribute-name check above it. See
        # _BLOCKED_DUNDER_ATTRS's own comment on __dict__ for the full writeup.
        self.assertIsNotNone(_validate_script_safety(
            "def run():\n    return type.__dict__['__subclasses__'](object)"
        ))

    def test_execute_pyqgis_script_rejects_dict_subscript_subclasses_bypass_end_to_end(self):
        """Same PoC as above, run through execute_pyqgis_script itself -- confirms the
        fix protects the real tool entry point, not just the unit-tested validator."""
        res = execute_pyqgis_script(
            "def run():\n"
            "    subclasses_fn = type.__dict__['__subclasses__']\n"
            "    return [c.__name__ for c in subclasses_fn(object)]\n"
        )
        self.assertIn("error", res)
        self.assertIn("rejected for safety", res["error"])

    def test_script_safety_blocks_builtins_module_bypass(self):
        # Confirmed live: `import builtins; builtins.open(...)` bypassed the
        # restricted __builtins__ dict entirely (full arbitrary file read),
        # since importing the real builtins module gives a direct reference
        # to the unrestricted eval/exec/open, independent of __builtins__.
        self.assertIsNotNone(_validate_script_safety("import builtins\ndef run():\n    return builtins.eval('1+1')"))

    def test_script_safety_blocks_format_string_attribute_traversal(self):
        # Confirmed live: "{0.__class__.__bases__}".format(x) reaches dunder
        # attributes without any ast.Attribute node existing in the source --
        # they're just text inside a string literal, invisible to the AST walk
        # that catches the equivalent f-string or literal dot-access form.
        self.assertIsNotNone(_validate_script_safety('def run():\n    return "{0.__class__}".format(1)'))
        self.assertIsNotNone(_validate_script_safety('def run():\n    return "{x.__class__}".format_map({"x": 1})'))

    def test_script_safety_allows_fstrings_and_builtin_format_function(self):
        # The equivalent f-string form IS real AST attribute access, so it's
        # already covered by the dunder-attribute check above -- confirm that
        # still works, and that the unrelated builtin format() function
        # (format(value, spec), no attribute-traversal capability) is untouched.
        self.assertIsNone(_validate_script_safety('def run():\n    return f"{3.14:.2f}"'))
        self.assertIsNone(_validate_script_safety('def run():\n    return format(3.14, ".2f")'))

    def test_script_safety_blocks_object_graph_and_frame_walking_modules(self):
        # gc.get_objects() and inspect's frame-walking can locate an
        # already-imported dangerous module/class without this script ever
        # importing it directly -- confirmed live against the running process.
        for module in ("gc", "inspect", "types", "copyreg", "runpy"):
            self.assertIsNotNone(_validate_script_safety(f"import {module}\ndef run():\n    pass"), module)

    def test_script_safety_blocks_dangerous_qt_classes(self):
        # Confirmed LIVE in a real QGIS session: a model script imported
        # QDirIterator from qgis.PyQt.QtCore (a module that must stay
        # importable -- QVariant/QColor/signals all live there too) and
        # walked the real filesystem, returning real paths from well outside
        # the QGIS install. The module-level _BLOCKED_MODULES checks are
        # blind to this since qgis.PyQt.QtCore itself is legitimate; only the
        # specific class matters. QFile/QProcess/QNetworkAccessManager/
        # QSettings/QDesktopServices are the same blind spot for file read,
        # process launch, raw network I/O, registry access, and launching an
        # arbitrary local executable via shell association, respectively.
        for name in (
            "QFile", "QSaveFile", "QTemporaryFile", "QDir", "QDirIterator",
            "QFileInfo", "QProcess", "QNetworkAccessManager", "QSettings",
            "QLibrary", "QPluginLoader", "QDesktopServices",
        ):
            script = f"from qgis.PyQt.QtCore import {name}\ndef run():\n    pass"
            self.assertIsNotNone(_validate_script_safety(script), name)

    def test_script_safety_blocks_aliased_qt_class_import(self):
        # The class-usage-only version of this check (bare Name/Attribute
        # references) misses `from X import QFile as F` entirely, since the
        # script never writes the literal string "QFile" again after the
        # import line -- must be caught at the ImportFrom alias itself.
        self.assertIsNotNone(_validate_script_safety(
            'from qgis.PyQt.QtCore import QFile as F\ndef run():\n    return F("x")'
        ))

    def test_script_safety_allows_legitimate_qt_and_qgis_imports(self):
        self.assertIsNone(_validate_script_safety(
            'from qgis.PyQt.QtCore import QVariant\nfrom qgis.PyQt.QtGui import QColor\n'
            'def run():\n    return str(QColor("#FF0000"))'
        ))
        self.assertIsNone(_validate_script_safety(
            "from qgis.core import QgsVectorLayer, QgsProject\n"
            "def run():\n    return len(QgsProject.instance().mapLayers())"
        ))

    def test_execute_pyqgis_script_allows_class_definitions(self):
        # __build_class__ and __name__ are required machinery for the `class`
        # statement itself (sugar around the already-safe type()), not an
        # extra capability -- found broken while testing the restricted-
        # builtins defense-in-depth layer, fixed alongside the security pass.
        res = execute_pyqgis_script("def run():\n    class Point:\n        def __init__(self, x):\n            self.x = x\n    return Point(5).x")
        self.assertEqual(res, {"success": True, "result": 5})

    def test_execute_pyqgis_script_restricted_builtins_block_unlisted_names(self):
        # Defense in depth: names excluded from the safe-builtins allowlist
        # (vars/globals/input/etc.) aren't AST-blocked by name, but must still
        # be unreachable at exec() time since they're absent from __builtins__.
        res = execute_pyqgis_script("def run():\n    return vars()")
        self.assertIn("error", res)
        self.assertIn("not defined", res["error"])

    def test_execute_pyqgis_script_allows_normal_computation(self):
        res = execute_pyqgis_script("def run():\n    return sum(range(5))")
        self.assertEqual(res, {"success": True, "result": 10})

    def test_execute_pyqgis_script_allowed_imports_still_work(self):
        # Regression test: excluding __import__ from the restricted-builtins
        # dict broke EVERY import statement outright (even fully permitted
        # ones), not just disallowed ones, because Python's import statement
        # needs __builtins__.__import__ to exist at all -- caught live when a
        # model script doing `from qgis.core import QgsFillSymbol` failed with
        # "__import__ not found" instead of actually importing. Must fail (if
        # at all) because the module genuinely isn't importable here, never
        # with that specific error.
        res = execute_pyqgis_script("import json\ndef run():\n    return json.dumps({'a': 1})")
        self.assertEqual(res, {"success": True, "result": '{"a": 1}'})

        res = execute_pyqgis_script("from qgis.core import QgsFillSymbol\ndef run():\n    return 1")
        self.assertIn("error", res)
        self.assertNotIn("__import__", res["error"])

    def test_execute_pyqgis_script_literal_dunder_import_call_still_blocked(self):
        # The AST-level block on a literal __import__ reference must still
        # work even though __import__ is now present in the runtime builtins
        # (for the import statement's sake) -- this is what actually prevents
        # __import__('os')-style dynamic bypasses, independent of runtime
        # availability.
        res = execute_pyqgis_script("def run():\n    return __import__('os')")
        self.assertIn("error", res)
        self.assertIn("rejected for safety", res["error"])

    def test_network_only_tools_bypass_main_thread_dispatch(self):
        self.assertIn("search_web", NETWORK_ONLY_TOOLS)
        self.assertIn("fetch_osm_features", NETWORK_ONLY_TOOLS)
        self.assertNotIn("remove_layer", NETWORK_ONLY_TOOLS)

    def test_two_phase_tools_registered(self):
        self.assertIn("add_layer_from_path", TWO_PHASE_TOOLS)
        self.assertIn("fetch_geoboundaries", TWO_PHASE_TOOLS)
        self.assertIn("fetch_hdx_admin_boundaries", TWO_PHASE_TOOLS)
        self.assertIn("gemini_grounded_search", TWO_PHASE_TOOLS)
        self.assertIn("openai_grounded_search", TWO_PHASE_TOOLS)
        self.assertIn("ingest_osm_features", TWO_PHASE_TOOLS)
        self.assertNotIn("remove_layer", TWO_PHASE_TOOLS)
        # Never both -- a tool dispatched via NETWORK_ONLY_TOOLS never touches
        # QgsSettings/QgsProject, so the two sets must stay disjoint.
        self.assertEqual(NETWORK_ONLY_TOOLS & TWO_PHASE_TOOLS, frozenset())

    def test_task_management_tools_excluded_from_auto_advance(self):
        self.assertIn("create_plan", TASK_MANAGEMENT_TOOLS)
        self.assertIn("update_task", TASK_MANAGEMENT_TOOLS)
        self.assertNotIn("add_point_layer", TASK_MANAGEMENT_TOOLS)
        self.assertNotIn("add_incident_point", TASK_MANAGEMENT_TOOLS)

    def test_gemini_search_config_degrades_gracefully_outside_qgis(self):
        res = resolve_gemini_search_config()
        self.assertIn("error", res)

    def test_gemini_grounded_search_degrades_gracefully_outside_qgis(self):
        res = gemini_grounded_search("some query")
        self.assertIn("error", res)

    def test_openai_search_config_degrades_gracefully_outside_qgis(self):
        res = resolve_openai_search_config()
        self.assertIn("error", res)

    def test_openai_grounded_search_degrades_gracefully_outside_qgis(self):
        res = openai_grounded_search("some query")
        self.assertIn("error", res)

    def test_prefetch_passthrough_for_local_paths(self):
        # Non-URL paths are returned unchanged, with is_temp=False (nothing to clean up)
        path, is_temp = _prefetch_url_to_temp("/some/local/file.geojson")
        self.assertEqual(path, "/some/local/file.geojson")
        self.assertFalse(is_temp)

    def test_is_safe_url_rejects_loopback_private_and_metadata_endpoints(self):
        # A3: SSRF guard -- file_path is LLM-controlled, so a prompt-injected
        # instruction could otherwise point add_layer_from_path at an internal
        # service or the cloud-provider metadata endpoint.
        for url in (
            "http://127.0.0.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.1/x",
            "http://10.0.0.5/x",
        ):
            self.assertIsNotNone(_is_safe_url(url), url)

    def test_is_safe_url_accepts_public_host(self):
        self.assertIsNone(_is_safe_url("https://example.com/data.geojson"))

    def test_is_safe_url_rejects_non_http_scheme(self):
        self.assertIsNotNone(_is_safe_url("file:///etc/passwd"))

    def test_is_safe_url_fails_closed_on_ip_obfuscation_attempts(self):
        # Classic SSRF-filter-bypass techniques (decimal/hex/octal/short-form
        # IP notation for 127.0.0.1) -- confirmed live that ipaddress.ip_address
        # correctly rejects these as literal IPs, and the DNS-resolution
        # fallback then also fails (they're not valid hostnames either), so
        # this fails CLOSED rather than silently treating "can't classify" as
        # "safe to fetch".
        for url in ("http://2130706433/x", "http://0x7f000001/x", "http://017700000001/x", "http://127.1/x"):
            self.assertIsNotNone(_is_safe_url(url), url)

    def test_is_safe_url_not_fooled_by_userinfo_or_fragment_tricks(self):
        # http://trusted.com@127.0.0.1/ -- "trusted.com" is URL userinfo, not
        # the host; urlparse().hostname correctly extracts the real target.
        self.assertIsNotNone(_is_safe_url("http://trusted.com@127.0.0.1/x"))
        self.assertIsNotNone(_is_safe_url("http://127.0.0.1#trusted.com"))

    def test_prefetch_url_to_temp_refuses_unsafe_url(self):
        with self.assertRaises(ValueError):
            _prefetch_url_to_temp("http://127.0.0.1/internal")

    def test_prefetch_url_to_temp_revalidates_redirect_target(self):
        # Live proof (not mocked at the urllib level) that a URL passing
        # _is_safe_url at call time can't be redirected to an unvalidated
        # address afterward -- Python's default HTTPRedirectHandler follows
        # 3xx unconditionally, which let the actually-fetched URL differ from
        # the one that was checked. A real local server + a real redirect
        # response is used here specifically because a mock of urlopen()
        # can't demonstrate whether the redirect hop itself gets re-checked.
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import cartogen_ai.core.agent.tools.vector_tools as vt

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{srv.server_address[1]}/internal-secret")
                    self.end_headers()
                else:
                    body = b"internal data"
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        # Simulate "the starting URL looks public, only the redirect target is
        # internal" -- _is_safe_url's own IP-classification logic is already
        # covered above; this isolates whether the redirect hop gets re-checked.
        original_is_safe_url = vt._is_safe_url

        def fake_is_safe_url(url):
            if "internal-secret" in url:
                return "simulated non-public redirect target"
            return None

        vt._is_safe_url = fake_is_safe_url
        try:
            with self.assertRaises(Exception):
                vt._prefetch_url_to_temp(f"http://127.0.0.1:{srv.server_address[1]}/start")
        finally:
            vt._is_safe_url = original_is_safe_url
            srv.shutdown()
            # shutdown() only stops the serve_forever() loop -- it does not close the
            # listening socket itself (a real gotcha in socketserver.TCPServer/HTTPServer's
            # own API split). Without server_close() too, the socket stays open until
            # garbage collection, which is exactly the "unclosed socket" ResourceWarning
            # found in a 2026-09-20 release review of this suite's own output.
            srv.server_close()
            thread.join(timeout=5)

    def test_prefetch_url_to_temp_enforces_size_cap_and_cleans_up(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import cartogen_ai.core.agent.tools.vector_tools as vt

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                # Stream well past the cap; a correct implementation stops
                # reading (and errors out) long before this finishes.
                chunk = b"x" * 65536
                for _ in range(200):
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        return

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()

        original_cap = vt._MAX_DOWNLOAD_BYTES
        vt._MAX_DOWNLOAD_BYTES = 1024  # tiny cap so the test doesn't need a huge body
        original_is_safe_url = vt._is_safe_url
        vt._is_safe_url = lambda url: None
        try:
            with self.assertRaises(Exception):
                vt._prefetch_url_to_temp(f"http://127.0.0.1:{srv.server_address[1]}/big")
        finally:
            vt._MAX_DOWNLOAD_BYTES = original_cap
            vt._is_safe_url = original_is_safe_url
            srv.shutdown()
            # See the sibling test above for why server_close() is also required.
            srv.server_close()
            thread.join(timeout=5)

    def test_add_layer_from_path_rejects_unsafe_url_cleanly(self):
        from cartogen_ai.core.agent.tools.vector_tools import add_layer_from_path
        with patch("cartogen_ai.core.agent.tools.vector_tools.QGIS_AVAILABLE", True):
            res = add_layer_from_path("http://169.254.169.254/latest/meta-data/")
        self.assertIn("error", res)
        self.assertIn("Download failed", res["error"])

    def test_geoboundaries_main_thread_phase_passes_through_errors(self):
        # If the network phase failed, the main-thread phase must not try to touch it further
        res = add_geoboundaries_layer_main_thread_phase({"error": "geoBoundaries API request failed: boom"})
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_geoboundaries_network_phase_handles_request_failure_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_geoboundaries_network_phase("JOR", "ADM1")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_geoboundaries_rejects_unsafe_second_hop_url(self, mock_urlopen):
        """SEC-001 (2026-09-13 security audit): geoBoundaries' own API response names the
        actual download URL (gjDownloadURL) -- third-party-controlled content, not a
        hardcoded endpoint. A compromised/malicious response pointing that field at a
        loopback/private/metadata address must be refused, not silently fetched."""
        import json as _json
        mock_urlopen.return_value = MagicMock(
            __enter__=lambda s: MagicMock(read=lambda: _json.dumps(
                {"gjDownloadURL": "http://169.254.169.254/latest/meta-data/", "boundaryName": "Fake"}
            ).encode()),
            __exit__=lambda *a: False,
        )
        res = fetch_geoboundaries_network_phase("JOR", "ADM1")
        self.assertIn("error", res)
        self.assertIn("Refusing to fetch", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_rejects_unsafe_second_hop_url(self, mock_urlopen):
        """SEC-001: HDX's own catalog response names the zip resource URL -- published by
        whichever organization uploaded the dataset, third-party content. A fresh, unused
        iso3 -- this tool caches successful results at module scope keyed by (iso3,
        admin_level), and this test must not risk a stale cache hit from another test's
        real (mocked-success) call to the same key short-circuiting before ever reaching
        the malicious-URL code path this test exercises."""
        import json as _json
        mock_urlopen.return_value = MagicMock(
            __enter__=lambda s: MagicMock(read=lambda: _json.dumps({
                "result": {"resources": [
                    {"format": "geojson", "url": "http://127.0.0.1:9/internal.geojson.zip"},
                ]}
            }).encode()),
            __exit__=lambda *a: False,
        )
        res = fetch_hdx_admin_boundaries_network_phase("ZZR", "ADM1")
        self.assertIn("error", res)
        self.assertIn("Refusing to fetch", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_building_footprints_rejects_unsafe_tile_url(self, mock_urlopen):
        """SEC-001: each row's Url comes from Microsoft's own published tile index. Unlike
        the per-country caches elsewhere in this file, the index CSV here is cached under
        one single shared key regardless of country -- must be cleared explicitly, since
        there's no "fresh, unused" value to pick around a single shared key the way the
        other SEC-001 tests avoid collision via an unused iso3."""
        _HUMANITARIAN_LOOKUP_CACHE._store.pop(("building_footprints_links",), None)
        qk = "0"
        links_csv = (
            "Location,QuadKey,Url,Size,UploadDate\n"
            f"RepublicofYemen,{qk},http://169.254.169.254/tile.csv.gz,1KB,2026-01-01\n"
        )
        mock_urlopen.return_value = MagicMock(
            __enter__=lambda s: MagicMock(read=lambda: links_csv.encode("utf-8")),
            __exit__=lambda *a: False,
        )
        with patch(
            "cartogen_ai.core.agent.tools.humanitarian_tools._quadkeys_for_bbox",
            return_value={qk},
        ):
            res = fetch_building_footprints_network_phase("Yemen", [12.77, 45.00, 12.80, 45.04])
        self.assertIn("error", res)
        self.assertIn("Refusing to fetch", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_building_footprints_caches_tile_download_across_calls(self, mock_urlopen, mock_opener):
        """PERF-004, 2026-09-13 audit: the tile-index CSV was already cached, but the actual
        per-quadkey tile download wasn't -- a second call for the same bbox re-downloaded and
        re-decompressed the same multi-MB tile. Now cached by tile URL under the same
        _LOOKUP_CACHE instance. A fresh, unused tile URL avoids collision with any other
        test's cached entry (see the SEC-001 tests above for why that matters)."""
        import os
        import gzip
        import json as _json

        from cartogen_ai.core.agent.tools.humanitarian_tools import _quadkeys_for_bbox
        # Shared cache key across all tests regardless of country -- must be cleared
        # explicitly (same reason as test_building_footprints_rejects_unsafe_tile_url above).
        _HUMANITARIAN_LOOKUP_CACHE._store.pop(("building_footprints_links",), None)
        bbox = [12.77, 45.00, 12.80, 45.04]
        south, west, north, east = bbox
        qk = list(_quadkeys_for_bbox(south, west, north, east))[0]

        links_csv = (
            "Location,QuadKey,Url,Size,UploadDate\n"
            f"RepublicofYemen,{qk},https://example.com/perf004_cache_tile.csv.gz,1KB,2026-01-01\n"
        )
        inside_feat = {"type": "Feature", "properties": {"height": -1.0}, "geometry": {"type": "Polygon", "coordinates": [[[45.01, 12.78], [45.02, 12.78], [45.02, 12.79], [45.01, 12.79], [45.01, 12.78]]]}}
        gz_bytes = gzip.compress((_json.dumps(inside_feat) + "\n").encode("utf-8"))

        mock_index_response = MagicMock()
        mock_index_response.__enter__.return_value.read.return_value = links_csv.encode("utf-8")
        mock_tile_response = MagicMock()
        mock_tile_response.__enter__.return_value.read.return_value = gz_bytes
        mock_urlopen.return_value = mock_index_response
        mock_opener.return_value.open.return_value = mock_tile_response

        res1 = fetch_building_footprints_network_phase("Yemen", bbox, max_features=10)
        self.assertTrue(res1.get("success"), res1)
        self.assertEqual(mock_opener.return_value.open.call_count, 1)

        # Second call, same bbox/tile -- must be served from the cache, not a second fetch.
        res2 = fetch_building_footprints_network_phase("Yemen", bbox, max_features=10)
        self.assertTrue(res2.get("success"), res2)
        self.assertEqual(mock_opener.return_value.open.call_count, 1,
                         "second call must reuse the cached tile, not re-download it")

        for res in (res1, res2):
            if res.get("local_path") and os.path.exists(res["local_path"]):
                os.remove(res["local_path"])

    def test_hdx_admin_boundaries_main_thread_phase_passes_through_errors(self):
        res = add_hdx_admin_boundaries_layer_main_thread_phase({"error": "HDX request failed: boom"})
        self.assertIn("error", res)

    def test_hdx_admin_boundaries_network_phase_rejects_admin_level_without_digit(self):
        # Caught before any network call -- "ADM1"-style input must contain a
        # digit to derive both the in-zip filename (yem_admin1.geojson) and the
        # pcode field name (adm1_pcode) to look for.
        res = fetch_hdx_admin_boundaries_network_phase("YEM", "invalid")
        self.assertIn("error", res)
        self.assertIn("digit", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_network_phase_handles_request_failure_gracefully(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_hdx_admin_boundaries_network_phase("SDN", "ADM1")
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_network_phase_reports_404_as_no_coverage(self, mock_urlopen):
        import io
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError("url", 404, "Not Found", {}, io.BytesIO())
        res = fetch_hdx_admin_boundaries_network_phase("ATA", "ADM1")
        self.assertIn("error", res)
        self.assertIn("coverage isn't universal", res["error"])
        self.assertIn("fetch_geoboundaries", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_network_phase_non_dict_json_returns_clean_error(self, mock_urlopen):
        """Same live crash class fixed in hazard_monitoring_tools.py the same day
        (2026-09-13): package_show's own try/except only guarantees valid JSON, not a
        dict -- a CKAN error page or gateway response served with a JSON content-type
        used to reach data.get("result", {}) below and crash uncaught. A fresh, unused
        iso3 -- fetch_hdx_admin_boundaries_network_phase caches successful results at
        module scope keyed by (iso3, admin_level), and this test must not risk a stale
        cache hit from another test's real (mocked-success) call to the same key
        short-circuiting before ever reaching the code this test exercises."""
        import json as _json
        mock_response = MagicMock()
        mock_response.__enter__.return_value.read.return_value = _json.dumps("Service Unavailable").encode()
        mock_urlopen.return_value = mock_response

        res = fetch_hdx_admin_boundaries_network_phase("ZZQ", "ADM1")
        self.assertIn("error", res)
        self.assertIn("unexpected response shape", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_network_phase_errors_when_no_geojson_resource(self, mock_urlopen):
        import json as _json
        package_show_body = _json.dumps({
            "result": {"title": "Fake - Subnational Administrative Boundaries", "resources": [{"format": "SHP", "url": "https://example.com/fake.shp.zip"}]},
        }).encode()
        mock_response = MagicMock()
        mock_response.__enter__.return_value.read.return_value = package_show_body
        mock_urlopen.return_value = mock_response

        res = fetch_hdx_admin_boundaries_network_phase("FAK", "ADM1")
        self.assertIn("error", res)
        self.assertIn("no GeoJSON boundaries resource", res["error"])

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_hdx_admin_boundaries_network_phase_happy_path_extracts_pcode_field(self, mock_urlopen, mock_opener):
        # End-to-end through the real (non-mocked) JSON/zip/pcode-detection
        # logic -- only the two urlopen() network calls are mocked. Confirms
        # the whole pipeline (package_show -> zip download -> member
        # extraction -> pcode-field detection -> temp file write) actually
        # works together, not just that each piece is individually plausible.
        import os
        import io
        import zipfile
        import json as _json

        package_show_body = _json.dumps({
            "result": {
                "title": "Yemen - Subnational Administrative Boundaries",
                "resources": [
                    {"format": "GeoJSON", "url": "https://data.humdata.org/fake/yem_admin_boundaries.geojson.zip"},
                    {"format": "SHP", "url": "https://data.humdata.org/fake/yem_admin_boundaries.shp.zip"},
                ],
            }
        }).encode()

        geojson_content = _json.dumps({
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"adm1_pcode": "YE12", "adm1_name": "Test"}, "geometry": None}],
        }).encode()
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("yem_admin1.geojson", geojson_content)
            zf.writestr("yem_admin2.geojson", b"{}")  # decoy, must not be picked

        mock_show_response = MagicMock()
        mock_show_response.__enter__.return_value.read.return_value = package_show_body
        mock_zip_response = MagicMock()
        mock_zip_response.__enter__.return_value.read.return_value = zip_buf.getvalue()
        mock_urlopen.return_value = mock_show_response
        # SEC-001 (2026-09-13): the zip download now goes through
        # _build_safe_opener().open(...), not the bare urlopen() above.
        mock_opener.return_value.open.return_value = mock_zip_response

        res = fetch_hdx_admin_boundaries_network_phase("YEM", "ADM1")
        try:
            self.assertTrue(res.get("success"), res)
            self.assertEqual(res["iso3"], "YEM")
            self.assertEqual(res["admin_level"], "ADM1")
            self.assertEqual(res["pcode_field"], "adm1_pcode")
            self.assertTrue(os.path.exists(res["local_path"]))
            with open(res["local_path"], "rb") as f:
                self.assertEqual(f.read(), geojson_content)
        finally:
            if res.get("local_path") and os.path.exists(res["local_path"]):
                os.remove(res["local_path"])

    def test_two_phase_tools_registered_includes_building_footprints(self):
        self.assertIn("fetch_building_footprints", TWO_PHASE_TOOLS)

    def test_lonlat_to_tile_xy_matches_known_correct_values(self):
        # Cross-checked against the real `mercantile` library (the one
        # Microsoft's own example notebook for this exact dataset uses)
        # before hardcoding here -- includes Microsoft's own docs example
        # (Redmond, WA) plus equator/near-antimeridian/near-max-lat edges.
        self.assertEqual(_lonlat_to_tile_xy(-122.12934, 47.64054, 13), (1316, 2859))
        self.assertEqual(_lonlat_to_tile_xy(45.03, 12.78, 9), (320, 237))
        self.assertEqual(_lonlat_to_tile_xy(0.0, 0.0, 9), (256, 256))
        self.assertEqual(_lonlat_to_tile_xy(179.9, -85.0, 9), (511, 511))

    def test_tile_xy_to_quadkey_matches_known_correct_values(self):
        self.assertEqual(_tile_xy_to_quadkey(1316, 2859, 13), "0212300302122")
        self.assertEqual(_tile_xy_to_quadkey(320, 237, 9), "123202202")
        self.assertEqual(_tile_xy_to_quadkey(256, 256, 9), "300000000")

    def test_quadkeys_for_bbox_covers_a_small_area_with_few_tiles(self):
        qk = _quadkeys_for_bbox(12.7, 44.9, 12.9, 45.1)
        self.assertIsInstance(qk, set)
        self.assertGreaterEqual(len(qk), 1)
        self.assertLessEqual(len(qk), 4)
        for q in qk:
            self.assertEqual(len(q), 9)

    def test_match_building_footprints_location_exact_and_case_insensitive(self):
        known = ["Afghanistan", "RepublicofYemen", "UnitedStatesofAmerica", "Albania"]
        self.assertEqual(_match_building_footprints_location("Yemen", known), ("RepublicofYemen", []))
        self.assertEqual(_match_building_footprints_location("yemen", known), ("RepublicofYemen", []))

    def test_match_building_footprints_location_no_match(self):
        known = ["Afghanistan", "RepublicofYemen"]
        location, candidates = _match_building_footprints_location("Nowhereistan", known)
        self.assertIsNone(location)
        self.assertEqual(candidates, [])

    def test_match_building_footprints_location_ambiguous_returns_candidates(self):
        known = ["Afghanistan", "Albania", "UnitedStatesofAmerica", "RepublicofYemen"]
        location, candidates = _match_building_footprints_location("a", known)
        self.assertIsNone(location)
        self.assertEqual(candidates, ["Afghanistan", "Albania", "UnitedStatesofAmerica"])

    def test_feature_centroid_polygon(self):
        # Mean of all vertices, not a true area centroid (documented behavior
        # -- see _feature_centroid's docstring) -- the ring's duplicated
        # closing vertex (10, 20) is counted twice, so the mean is pulled
        # toward that corner rather than landing at the square's true center
        # (11, 21). Expected values hand-computed: sum_x=54/5=10.8, sum_y=104/5=20.8.
        geom = {"type": "Polygon", "coordinates": [[[10, 20], [12, 20], [12, 22], [10, 22], [10, 20]]]}
        lon, lat = _feature_centroid(geom)
        self.assertAlmostEqual(lon, 10.8)
        self.assertAlmostEqual(lat, 20.8)

    def test_feature_centroid_none_geometry(self):
        self.assertIsNone(_feature_centroid(None))
        self.assertIsNone(_feature_centroid({}))

    def test_building_footprints_main_thread_phase_passes_through_errors(self):
        res = add_building_footprints_layer_main_thread_phase({"error": "boom"})
        self.assertIn("error", res)

    def test_building_footprints_main_thread_phase_passes_through_location_suggestion(self):
        suggestion = {"status": "LOCATION_SUGGESTION", "candidates": ["Afghanistan", "Albania"]}
        res = add_building_footprints_layer_main_thread_phase(suggestion)
        self.assertEqual(res, suggestion)

    def test_building_footprints_network_phase_rejects_malformed_bbox(self):
        res = fetch_building_footprints_network_phase("Yemen", [1, 2, 3])
        self.assertIn("error", res)

    def test_building_footprints_network_phase_rejects_out_of_range_bbox(self):
        res = fetch_building_footprints_network_phase("Yemen", [200, 45, 12.9, 45.1])
        self.assertIn("error", res)

    def test_building_footprints_network_phase_rejects_inverted_bbox(self):
        res = fetch_building_footprints_network_phase("Yemen", [12.9, 45.1, 12.7, 44.9])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_building_footprints_network_phase_handles_request_failure_gracefully(self, mock_urlopen):
        # Shared cache key regardless of country -- must be cleared explicitly, or a
        # successful index fetch cached by an earlier test (e.g. the PERF-004 cache test
        # or the happy-path test) makes this urlopen mock never get reached at all.
        _HUMANITARIAN_LOOKUP_CACHE._store.pop(("building_footprints_links",), None)
        mock_urlopen.side_effect = OSError("network unreachable")
        res = fetch_building_footprints_network_phase("Yemen", [12.7, 44.9, 12.9, 45.1])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.tools.humanitarian_tools._build_safe_opener")
    @patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen")
    def test_building_footprints_network_phase_happy_path(self, mock_urlopen, mock_opener):
        # End-to-end through the real (non-mocked) CSV-index parsing, quadkey
        # filtering, gzip decompression, and bbox-crop logic -- only the two
        # urlopen() network calls (index CSV, tile download) are mocked.
        import os
        import gzip
        import json as _json

        # Shared cache key regardless of country -- must be cleared explicitly (PERF-004's
        # cache test above uses the identical bbox, which would otherwise leave this test
        # silently depending on that other test's cached index CSV/tile instead of its own).
        _HUMANITARIAN_LOOKUP_CACHE._store.pop(("building_footprints_links",), None)

        from cartogen_ai.core.agent.tools.humanitarian_tools import _quadkeys_for_bbox
        bbox = [12.77, 45.00, 12.80, 45.04]
        south, west, north, east = bbox
        quadkeys = list(_quadkeys_for_bbox(south, west, north, east))
        qk = quadkeys[0]

        links_csv = (
            "Location,QuadKey,Url,Size,UploadDate\n"
            f"RepublicofYemen,{qk},https://example.com/fake_tile.csv.gz,1KB,2026-01-01\n"
        )
        # One feature inside the bbox, one clearly outside -- confirms crop logic runs for real.
        inside_feat = {"type": "Feature", "properties": {"height": -1.0}, "geometry": {"type": "Polygon", "coordinates": [[[45.01, 12.78], [45.02, 12.78], [45.02, 12.79], [45.01, 12.79], [45.01, 12.78]]]}}
        outside_feat = {"type": "Feature", "properties": {"height": -1.0}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}
        geojsonl = (_json.dumps(inside_feat) + "\n" + _json.dumps(outside_feat) + "\n").encode("utf-8")
        gz_bytes = gzip.compress(geojsonl)

        mock_index_response = MagicMock()
        mock_index_response.__enter__.return_value.read.return_value = links_csv.encode("utf-8")
        mock_tile_response = MagicMock()
        mock_tile_response.__enter__.return_value.read.return_value = gz_bytes
        mock_urlopen.return_value = mock_index_response
        # SEC-001 (2026-09-13): the per-tile download now goes through
        # _build_safe_opener().open(...), not the bare urlopen() above.
        mock_opener.return_value.open.return_value = mock_tile_response

        res = fetch_building_footprints_network_phase("Yemen", bbox, max_features=10)
        try:
            self.assertTrue(res.get("success"), res)
            self.assertEqual(res["location"], "RepublicofYemen")
            self.assertEqual(res["feature_count"], 1)
            self.assertFalse(res["truncated"])
            # Moved here from the tool description -- see
            # docs/archive/API_COST_OPTIMIZATION_REVIEW.md section 2.3.
            self.assertIn("baseline_caveat", res)
            self.assertIn("not live extraction", res["baseline_caveat"])
            with open(res["local_path"], encoding="utf-8") as f:
                gj = _json.load(f)
            self.assertEqual(len(gj["features"]), 1)
        finally:
            if res.get("local_path") and os.path.exists(res["local_path"]):
                os.remove(res["local_path"])

    def test_add_incident_point_degrades_gracefully_outside_qgis(self):
        res = add_incident_point(31.95, 35.93, "2026-03-14", "Test incident")
        self.assertIn("error", res)

    def test_add_point_layer_degrades_gracefully_outside_qgis(self):
        res = add_point_layer("Embassies", [{"lat": 31.95, "lon": 35.93, "name": "Embassy of France"}])
        self.assertIn("error", res)

    def test_add_point_layer_rejects_empty_list(self):
        res = add_point_layer("Embassies", [])
        self.assertIn("error", res)

    @patch("cartogen_ai.core.agent.agent_orchestrator.time.sleep")
    def test_agent_run_saves_history_when_iteration_limit_hit(self, mock_sleep):
        # A client that never returns a final answer -- always another tool call --
        # simulates the exact failure mode from the embassy-layer bug report. time.sleep is
        # mocked since this drives the loop to MAX_ITERATIONS, which now includes real pacing
        # delays (2026-09-12, PACING_THRESHOLD_ITERATIONS) -- unmocked this test took ~21s.
        class LoopingClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": "1", "function": {"name": "get_layers", "arguments": "{}"}}],
                    },
                    "model": "fake",
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = LoopingClient()

        result = agent.run("create a layer for all the embassies")

        self.assertIn("tool-call limit", result)
        # Must not lose the attempt -- a retry needs to see it already ran into this,
        # instead of blindly repeating the identical one-call-per-item approach.
        self.assertEqual(len(agent.conversation_history), 2)
        self.assertEqual(agent.conversation_history[0]["role"], "user")
        self.assertEqual(agent.conversation_history[1]["role"], "assistant")

    def test_agent_run_accumulates_usage_from_provider_response(self):
        # docs/archive/ENGINEERING_PRODUCT_UX_REVIEW_2026-08-20.md SS3.2: session usage
        # tracking. A single-turn, no-tool-calls response should add exactly
        # that call's usage into session_usage and be reflected in
        # get_session_usage_text().
        class UsageReportingClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {"role": "assistant", "content": "Done."},
                    "model": "fake",
                    "usage": {"input_tokens": 100, "output_tokens": 25},
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = UsageReportingClient()

        agent.run("hello")

        self.assertEqual(agent.session_usage["input_tokens"], 100)
        self.assertEqual(agent.session_usage["output_tokens"], 25)
        self.assertEqual(agent.session_usage["calls_with_usage"], 1)
        self.assertEqual(agent.session_usage["calls_without_usage"], 0)
        self.assertEqual(agent.get_session_usage_text(), "~125 tokens this session (1 calls)")

    def test_agent_run_usage_accumulates_across_multiple_turns(self):
        class UsageReportingClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {"role": "assistant", "content": "Done."},
                    "model": "fake",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = UsageReportingClient()

        agent.run("first")
        agent.run("second")

        self.assertEqual(agent.session_usage["input_tokens"], 20)
        self.assertEqual(agent.session_usage["output_tokens"], 10)
        self.assertEqual(agent.session_usage["calls_with_usage"], 2)

    def test_agent_get_session_usage_text_none_before_any_usage_reported(self):
        # The honesty check this whole feature is built around: a fresh agent,
        # or one whose provider never reports usage, must show nothing at all
        # -- never a fabricated "0 tokens" that looks like a real, confirmed
        # measurement.
        agent = CartogenAi()
        self.assertIsNone(agent.get_session_usage_text())

        class NoUsageClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {"message": {"role": "assistant", "content": "Done."}, "model": "fake"}

        agent.conversation_history = []
        agent.client = NoUsageClient()
        agent.run("hello")

        self.assertIsNone(agent.get_session_usage_text())
        self.assertEqual(agent.session_usage["calls_without_usage"], 1)

    def test_agent_get_session_usage_text_caveats_partial_reporting(self):
        # Mixed session: some calls reported usage, some didn't (e.g. a
        # provider switch mid-session, or one model in a fallback chain
        # reporting and another not) -- the text must say so rather than
        # silently understating the real total.
        calls = {"n": 0}

        class MixedUsageClient:
            def complete(self, messages, tools=None, max_tokens=None):
                calls["n"] += 1
                msg = {"role": "assistant", "content": "Done."}
                if calls["n"] == 1:
                    return {"message": msg, "model": "fake", "usage": {"input_tokens": 50, "output_tokens": 10}}
                return {"message": msg, "model": "fake"}

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = MixedUsageClient()
        agent.run("first")
        agent.run("second")

        text = agent.get_session_usage_text()
        self.assertIn("60 tokens", text)
        self.assertIn("no usage reported", text)

    def test_agent_run_accumulates_cached_tokens_and_shows_them_in_session_text(self):
        # 2026-09-13, direct request ("implement gemini caching"): cached_tokens (from
        # providers/base.py's extract_openai_style_usage or providers/claude.py's
        # from_anthropic_response) must accumulate across calls and show up in the
        # session-usage text, so prompt caching's effect is actually visible.
        class CachingClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {"role": "assistant", "content": "Done."},
                    "model": "fake",
                    "usage": {"input_tokens": 8149, "output_tokens": 40, "cached_tokens": 7200},
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = CachingClient()

        agent.run("hello")

        self.assertEqual(agent.session_usage["cached_tokens"], 7200)
        text = agent.get_session_usage_text()
        self.assertIn("8,189 tokens", text)
        self.assertIn("7,200 served from cache", text)

    def test_agent_get_session_usage_text_omits_cache_clause_when_no_cache_hit(self):
        # No cached_tokens reported at all (a provider/model with no caching, or a genuine
        # cache miss) -- the summary text must look exactly like it did before this feature,
        # no "0 served from cache" clause fabricated onto it.
        class NoCacheClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {"role": "assistant", "content": "Done."},
                    "model": "fake",
                    "usage": {"input_tokens": 100, "output_tokens": 25},
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = NoCacheClient()
        agent.run("hello")

        text = agent.get_session_usage_text()
        self.assertEqual(text, "~125 tokens this session (1 calls)")
        self.assertNotIn("cache", text)

    def test_agent_run_stops_when_should_stop_returns_true(self):
        # There was previously no way to interrupt a running request at all.
        # should_stop (wired from the dock's Stop button -> QgsTask.isCanceled)
        # is checked once per loop iteration -- must stop before making
        # another API call rather than always running to completion/the limit.
        class LoopingClient:
            call_count = 0

            def complete(self, messages, tools=None, max_tokens=None):
                LoopingClient.call_count += 1
                return {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": "1", "function": {"name": "get_layers", "arguments": "{}"}}],
                    },
                    "model": "fake",
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = LoopingClient()

        result = agent.run("do something long", should_stop=lambda: True)

        self.assertIn("Stopped by user", result)
        # Stopped before the FIRST API call, since should_stop is checked at
        # the top of the loop, before iteration 0 runs.
        self.assertEqual(LoopingClient.call_count, 0)
        self.assertEqual(len(agent.conversation_history), 2)

    def test_agent_run_stops_partway_through(self):
        class CountingStopper:
            def __init__(self, stop_after):
                self.calls = 0
                self.stop_after = stop_after

            def __call__(self):
                self.calls += 1
                return self.calls > self.stop_after

        class LoopingClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{"id": "1", "function": {"name": "get_layers", "arguments": "{}"}}],
                    },
                    "model": "fake",
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = LoopingClient()
        stopper = CountingStopper(stop_after=2)

        result = agent.run("do something long", should_stop=stopper)

        self.assertIn("Stopped by user", result)

    def test_agent_run_stops_mid_batch_not_just_between_llm_rounds(self):
        """QGIS-003, 2026-09-13 audit: should_stop used to only be checked once per LLM
        round (at the top of the outer loop) -- a single response asking for SEVERAL tool
        calls at once (a real, common shape: buffer -> clip -> export style requests)
        could not be interrupted partway through; the next check only happened before the
        NEXT round's API call, after the whole batch had already run. Now checked before
        each individual tool call within a batch too."""
        class OneRoundTwoToolsClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {
                    "message": {
                        "role": "assistant", "content": None,
                        "tool_calls": [
                            {"id": "1", "function": {"name": "get_layers", "arguments": "{}"}},
                            {"id": "2", "function": {"name": "get_attributes", "arguments": '{"layer_name": "x"}'}},
                        ],
                    },
                    "model": "fake",
                }

        agent = CartogenAi()
        agent.conversation_history = []
        agent.client = OneRoundTwoToolsClient()

        executed = []

        def fake_execute_tool(self, name, arguments):
            executed.append(name)
            return {"success": True}

        # False on the outer loop's own pre-round check AND the per-tool-call check
        # before the batch's first tool (so get_layers actually dispatches), True from
        # the per-tool-call check before the batch's second tool onward -- lands the
        # stop strictly between the batch's two tool calls, not before the round even
        # starts (already covered by the sibling tests above).
        calls = {"n": 0}

        def stopper():
            calls["n"] += 1
            return calls["n"] > 2

        with patch.object(agent_mod.CartogenAi, "_execute_tool", fake_execute_tool):
            result = agent.run("do two things", should_stop=stopper)

        self.assertIn("Stopped by user", result)
        self.assertEqual(executed, ["get_layers"],
                         "must have stopped after the first tool call in the batch and "
                         "never dispatched the second")

    def test_agent_run_without_should_stop_behaves_as_before(self):
        # should_stop is optional -- omitting it (existing callers, existing
        # tests) must not change behavior.
        agent = CartogenAi()
        agent.conversation_history = []

        class SimpleClient:
            def complete(self, messages, tools=None, max_tokens=None):
                return {"message": {"role": "assistant", "content": "hi", "tool_calls": None}, "model": "fake"}

        agent.client = SimpleClient()
        result = agent.run("hello")
        self.assertEqual(result, "hi")

    def test_agent_can_reload_chat_history(self):
        agent = CartogenAi()
        agent.conversation_history = [{"role": "user", "content": "stale"}]
        agent.reload_chat_history()
        self.assertIsInstance(agent.conversation_history, list)

    def test_on_dispatcher_thread_false_outside_qgis(self):
        # QThread doesn't exist in this environment -- must degrade to False (use the
        # normal cross-thread signal path) rather than raise.
        agent = CartogenAi()
        self.assertFalse(agent._on_dispatcher_thread())

    def _agent_with_fake_settings(self, provider, saved_model_value):
        """Builds a CartogenAi with a mocked QgsSettings so a non-default
        provider (and a controlled 'nothing saved yet' vs 'explicitly saved'
        model setting) can be exercised outside a real QGIS process, where the
        QGIS_AVAILABLE=False QgsSettings stub always just echoes back whatever
        default it's given regardless of key."""
        fake_settings = MagicMock()

        def fake_value(key, default=""):
            if key == "cartogen_ai/provider":
                return provider
            if key.endswith("_model") and provider in key:
                return saved_model_value if saved_model_value is not None else default
            return default

        fake_settings.value.side_effect = fake_value
        with patch.object(agent_mod, "QgsSettings", return_value=fake_settings):
            return CartogenAi()

    def test_auto_model_routing_is_default_for_fresh_install(self):
        # Nothing saved for claude_model yet -- must default to auto-routing
        # instead of silently pinning to the fixed model forever (B4).
        agent = self._agent_with_fake_settings("claude", saved_model_value=None)
        self.assertEqual(agent._auto_model_provider, "claude")
        self.assertEqual(agent.client.model, "claude-opus-5")

    def test_explicit_model_choice_is_not_overridden_by_auto_default(self):
        agent = self._agent_with_fake_settings("claude", saved_model_value="claude-sonnet-5")
        self.assertIsNone(agent._auto_model_provider)
        self.assertEqual(agent.client.model, "claude-sonnet-5")

    def test_ollama_does_not_default_to_auto(self):
        # Ollama intentionally opts out (default_to_auto=False) -- local
        # models aren't a cost concern.
        agent = self._agent_with_fake_settings("ollama", saved_model_value=None)
        self.assertIsNone(agent._auto_model_provider)
        self.assertEqual(agent.client.model, "llama3.1")

    def test_reconcile_appends_correction_when_last_call_errored_unacknowledged(self):
        agent = CartogenAi()
        log = [("get_layers", False, None), ("add_point_layer", True, "boom")]
        result = agent._reconcile_final_text_with_tool_log("All done, layer created!", log)
        self.assertIn("actually returned an error", result)
        self.assertIn("boom", result)

    def test_reconcile_leaves_text_unchanged_when_last_call_succeeded(self):
        agent = CartogenAi()
        log = [("add_point_layer", True, "boom"), ("add_point_layer", False, None)]
        result = agent._reconcile_final_text_with_tool_log("All done!", log)
        self.assertEqual(result, "All done!")

    def test_reconcile_leaves_text_unchanged_when_model_already_acknowledges_failure(self):
        agent = CartogenAi()
        log = [("add_point_layer", True, "boom")]
        result = agent._reconcile_final_text_with_tool_log("I was unable to create the layer due to an error.", log)
        self.assertEqual(result, "I was unable to create the layer due to an error.")

    def test_reconcile_no_op_with_empty_tool_log(self):
        agent = CartogenAi()
        result = agent._reconcile_final_text_with_tool_log("Here's the answer.", [])
        self.assertEqual(result, "Here's the answer.")

    def test_reconcile_catches_earlier_unresolved_failure_not_just_the_last_call(self):
        # B1: originally only checked turn_tool_log[-1] -- missed the actual
        # common shape of this bug, where an EARLIER call fails, the model
        # recovers with an unrelated tool, and the final answer never
        # mentions the earlier failure at all.
        agent = CartogenAi()
        log = [("buffer_analysis", True, "Layer 'roads' not found"), ("get_layers", False, None)]
        result = agent._reconcile_final_text_with_tool_log("Done! I buffered the roads layer by 500m.", log)
        self.assertIn("buffer_analysis", result)
        self.assertIn("Layer 'roads' not found", result)

    def test_reconcile_does_not_flag_a_failure_retried_with_the_same_tool(self):
        # A later SUCCESS of the same tool name resolves an earlier failure of
        # that tool -- shouldn't produce a spurious warning about the first attempt.
        agent = CartogenAi()
        log = [("buffer_analysis", True, "transient error"), ("buffer_analysis", False, None)]
        result = agent._reconcile_final_text_with_tool_log("Done! I buffered the roads layer by 500m.", log)
        self.assertEqual(result, "Done! I buffered the roads layer by 500m.")

    def test_reconcile_lists_multiple_unresolved_failures(self):
        agent = CartogenAi()
        log = [("buffer_analysis", True, "boom1"), ("get_layers", True, "boom2")]
        result = agent._reconcile_final_text_with_tool_log("All done!", log)
        self.assertIn("boom1", result)
        self.assertIn("boom2", result)
        self.assertIn("2 tool calls", result)

    def test_sandbox_flailing_nudge_fires_after_threshold_consecutive_blocked_scripts(self):
        # Live-reported, 2026-09-19: the model burned its whole tool-call budget on
        # execute_pyqgis_script calls that were all rejected by the safety sandbox,
        # never calling a directed tool. 3 in a row must trigger the nudge.
        agent = CartogenAi()
        log = [
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'os' -- not allowed in execute_pyqgis_script."),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'QDir' -- not allowed in execute_pyqgis_script."),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'pathlib' -- not allowed in execute_pyqgis_script."),
        ]
        nudge = agent._sandbox_flailing_nudge(log)
        self.assertIsNotNone(nudge)
        self.assertIn("execute_pyqgis_script", nudge)

    def test_sandbox_flailing_nudge_does_not_fire_below_threshold(self):
        agent = CartogenAi()
        log = [
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'os' -- not allowed in execute_pyqgis_script."),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'QDir' -- not allowed in execute_pyqgis_script."),
        ]
        self.assertIsNone(agent._sandbox_flailing_nudge(log))

    def test_sandbox_flailing_nudge_ignores_non_safety_errors(self):
        # An execute_pyqgis_script call failing for a REAL reason (a bug in the model's
        # own script, a missing layer) is the model iterating on its own code, not
        # flailing against the sandbox wall -- must not trigger the nudge.
        agent = CartogenAi()
        log = [
            ("execute_pyqgis_script", True, "NameError: name 'foo' is not defined"),
            ("execute_pyqgis_script", True, "NameError: name 'bar' is not defined"),
            ("execute_pyqgis_script", True, "NameError: name 'baz' is not defined"),
        ]
        self.assertIsNone(agent._sandbox_flailing_nudge(log))

    def test_sandbox_flailing_nudge_ignores_a_mix_of_tools(self):
        # A get_layers call breaking up the streak means the model isn't purely
        # hammering the sandbox -- it's at least trying something else in between.
        agent = CartogenAi()
        log = [
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'os' -- not allowed in execute_pyqgis_script."),
            ("get_layers", False, None),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'QDir' -- not allowed in execute_pyqgis_script."),
        ]
        self.assertIsNone(agent._sandbox_flailing_nudge(log))

    def test_sandbox_flailing_nudge_only_looks_at_the_most_recent_window(self):
        # An earlier blocked streak that the model already moved on from (a
        # successful call happened after it) must not retroactively trigger.
        agent = CartogenAi()
        log = [
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'os' -- not allowed in execute_pyqgis_script."),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'QDir' -- not allowed in execute_pyqgis_script."),
            ("execute_pyqgis_script", True, "Script rejected for safety: Blocked import 'pathlib' -- not allowed in execute_pyqgis_script."),
            ("get_layers", False, None),
        ]
        self.assertIsNone(agent._sandbox_flailing_nudge(log))

    def test_geocode_batch_rejects_empty_list(self):
        self.assertIn("error", geocode_batch([]))

    def test_geocode_batch_rejects_too_many_locations(self):
        self.assertIn("error", geocode_batch(["x"] * 30))

    def test_geocode_batch_serves_cached_entries_without_network(self):
        # B3: a cache hit must short-circuit before any network call, and the
        # per-item delay must be skipped for cache hits (only real network
        # calls need to respect Nominatim's rate limit).
        _GEOCODE_CACHE.set("Amman, Jordan", {"location": "Amman, Jordan", "lat": 31.95, "lon": 35.93})
        with patch("time.sleep") as mock_sleep:
            res = geocode_batch(["Amman, Jordan"])
        self.assertTrue(res["success"])
        self.assertTrue(res["results"][0]["cached"])
        mock_sleep.assert_not_called()

    def _mock_urlopen_response(self, json_bytes):
        resp = MagicMock()
        resp.read.return_value = json_bytes
        resp.__enter__ = lambda self: resp
        resp.__exit__ = lambda self, *a: False
        return resp

    def test_geocode_and_enrich_sets_a_request_timeout(self):
        # A hardcoded, fixed-domain endpoint (Nominatim), unlike add_layer_from_path's
        # LLM-controlled URLs -- no timeout here isn't a security hole, but a hung
        # connection on a background thread would block indefinitely with nothing to
        # show for it. Every requests.get/post call in the provider modules already
        # sets one explicitly; this and the three tests below close the same gap for
        # the plain urllib.request.urlopen() calls in agent/tools/.
        # system_tools.py imports urllib locally inside the function (not at
        # module level), so there's no "cartogen_ai.core.agent.tools.system_tools.urllib"
        # attribute to patch through -- patch the real shared module instead.
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen_response(
                b'[{"display_name": "Amman, Jordan", "lat": "31.95", "lon": "35.93"}]'
            )
            geocode_and_enrich("Amman, Jordan Unique Test Query")
        self.assertEqual(mock_urlopen.call_args.kwargs.get("timeout"), 15)

    def test_search_hdx_datasets_sets_a_request_timeout(self):
        with patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen_response(b'{"result": {"results": []}}')
            search_hdx_datasets("floods")
        self.assertEqual(mock_urlopen.call_args.kwargs.get("timeout"), 15)

    def test_fetch_osm_features_sets_a_longer_timeout_than_its_own_query_budget(self):
        # The Overpass QL itself requests [timeout:25] server-side -- the client
        # timeout must be >= that, or a legitimate slow-but-still-running query gets
        # aborted client-side before the server's own deadline is even reached.
        with patch("cartogen_ai.core.agent.tools.humanitarian_tools.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._mock_urlopen_response(b'{"elements": []}')
            fetch_osm_features("amenity", "hospital", [1, 2, 3, 4])
        self.assertEqual(mock_urlopen.call_args.kwargs.get("timeout"), 30)


class TestCleanupCachedLocalPath(unittest.TestCase):
    """SEC-004, 2026-09-14 audit: fetch_geoboundaries_network_phase/
    fetch_hdx_admin_boundaries_network_phase/fetch_worldpop_population_network_phase cache
    their result dict (including a real local_path temp file, deliberately kept alive while
    cached so a repeat call within the TTL window reuses it) via _LOOKUP_CACHE -- but nothing
    ever deleted that file once the cache entry itself expired, a real (if low-severity)
    resource leak. _cleanup_cached_local_path is the on_evict callback that closes it; these
    tests exercise it directly, independent of the cache-expiry machinery itself (covered in
    test_cache_utils.py)."""

    def test_removes_the_file_when_value_has_a_local_path(self):
        import os
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".geojson")
        os.close(fd)
        try:
            self.assertTrue(os.path.exists(path))
            _cleanup_cached_local_path(("some", "key"), {"success": True, "local_path": path})
            self.assertFalse(os.path.exists(path))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_no_op_for_a_value_with_no_local_path(self):
        # Most cached values here (location lookups, tile-index CSV text, per-tile content)
        # have nothing to clean up -- must not raise or do anything surprising.
        _cleanup_cached_local_path(("some", "key"), {"success": True})  # must not raise

    def test_no_op_for_a_non_dict_value(self):
        _cleanup_cached_local_path(("building_footprints_links",), "raw csv text")  # must not raise

    def test_no_op_when_the_file_is_already_gone(self):
        # Defends against a double-cleanup path (e.g. some other code already removed it) --
        # must not raise on a stale path that no longer exists on disk.
        _cleanup_cached_local_path(("k",), {"local_path": "/definitely/not/a/real/path.geojson"})


class TestLoadWorkflowPreset(unittest.TestCase):
    """load_workflow_preset: no test coverage at all before QUAL-006 (2026-09-14 audit)."""

    def test_outside_qgis_reports_not_found_not_qgis_unavailable(self):
        # Unlike most tools, load_workflow_preset has no explicit `if not QGIS_AVAILABLE`
        # gate -- outside QGIS, `settings` is None and `raw` is "", so it falls through to
        # the same "not found" error a real missing preset would give, not a distinct
        # "QGIS not available" message. Documenting the actual behavior, not the more
        # common convention this file's other tools follow.
        res = load_workflow_preset("weekly_check")
        self.assertIn("error", res)
        self.assertIn("not found", res["error"])

    @patch("cartogen_ai.core.agent.tools.db_and_workflow_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.db_and_workflow_tools.QgsSettings", create=True)
    def test_missing_preset_reports_a_clear_error(self, mock_settings_cls):
        mock_settings_cls.return_value.value.return_value = ""
        res = load_workflow_preset("never_saved")
        self.assertIn("error", res)
        self.assertIn("never_saved", res["error"])

    @patch("cartogen_ai.core.agent.tools.db_and_workflow_tools.QGIS_AVAILABLE", True)
    @patch("cartogen_ai.core.agent.tools.db_and_workflow_tools.QgsSettings", create=True)
    def test_found_preset_returns_its_stored_json(self, mock_settings_cls):
        stored = '{"steps": [{"tool": "calculate_severity_index", "args": {}}]}'
        mock_settings_cls.return_value.value.return_value = stored

        res = load_workflow_preset("weekly_check")

        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["workflow_json"], stored)
        self.assertEqual(res["preset_name"], "weekly_check")
        # Confirms the settings key namespace actually reached QgsSettings.value(...).
        called_key = mock_settings_cls.return_value.value.call_args[0][0]
        self.assertEqual(called_key, "cartogen_ai/workflows/weekly_check")


class TestSearchWebPrefersDdgs(unittest.TestCase):
    """2026-09-18, live-verified: duckduckgo_search (even at 8.1.1, the version
    requirements.txt used to pin as the "thin compat shim" floor) silently returns
    ZERO results for a real query -- no error, nothing for search_web's own except
    ImportError to catch. ddgs (the actual current package the project renamed to)
    returned real results immediately for the identical query. search_web must
    import ddgs first, only falling back to duckduckgo_search if ddgs genuinely
    isn't installed."""

    def setUp(self):
        import sys
        self._sys_modules_backup = dict(sys.modules)

    def tearDown(self):
        import sys
        sys.modules.clear()
        sys.modules.update(self._sys_modules_backup)

    def _fake_ddgs_module(self, results):
        import sys
        import types

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def text(self, query, max_results=3):
                return results

        fake_mod = types.ModuleType("ddgs")
        fake_mod.DDGS = _FakeDDGS
        sys.modules["ddgs"] = fake_mod
        sys.modules.pop("duckduckgo_search", None)
        return fake_mod

    def test_uses_ddgs_when_available(self):
        from cartogen_ai.core.agent.tools.system_tools import search_web
        self._fake_ddgs_module([{"title": "QGIS", "href": "https://qgis.org", "body": "GIS software"}])

        res = search_web("qgis")

        self.assertIn("results", res)
        self.assertIn("QGIS", res["results"])

    def test_falls_back_to_duckduckgo_search_when_ddgs_missing(self):
        import sys
        import types

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def text(self, query, max_results=3):
                return [{"title": "Fallback result", "href": "https://x", "body": "y"}]

        # No "ddgs" entry in sys.modules AND no real ddgs installed in THIS test
        # process would make `from ddgs import DDGS` raise naturally -- but ddgs IS
        # a real installed dependency of this project's own test environment, so
        # block it explicitly the same way a genuinely-missing package would fail.
        sys.modules.pop("ddgs", None)
        sys.modules["ddgs"] = None  # import machinery treats a None entry as absent -> ImportError
        fake_mod = types.ModuleType("duckduckgo_search")
        fake_mod.DDGS = _FakeDDGS
        sys.modules["duckduckgo_search"] = fake_mod

        from cartogen_ai.core.agent.tools.system_tools import search_web
        res = search_web("qgis")

        self.assertIn("results", res)
        self.assertIn("Fallback result", res["results"])

    def test_no_results_from_ddgs_reports_a_message_not_a_silent_empty_success(self):
        from cartogen_ai.core.agent.tools.system_tools import search_web
        self._fake_ddgs_module([])

        res = search_web("a query with genuinely no results")

        self.assertIn("message", res)
        self.assertNotIn("results", res)


if __name__ == "__main__":
    unittest.main()
