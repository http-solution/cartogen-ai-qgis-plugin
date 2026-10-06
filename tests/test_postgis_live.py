# -*- coding: utf-8 -*-
"""#151: execute_read_only_sql against a real PostGIS server. Skipped unless CARTOGEN_TEST_PG_HOST is set (the CI live job starts a
postgis service container and sets it). Written without a local QGIS or database: CI's first run is its first execution, and what it
shows about the read-only enforcement is the point of the test, not an assumption."""
import os
import unittest

try:
    from qgis.core import QgsDataSourceUri, QgsProject, QgsProviderRegistry, QgsSettings
    QGIS_LIVE_AVAILABLE = True
except ImportError:
    QGIS_LIVE_AVAILABLE = False

PG = {k: os.environ.get("CARTOGEN_TEST_PG_" + k.upper(), "") for k in ("host", "port", "database", "user", "password")}
HAVE_DB = bool(PG["host"])
SCHEMA = "cartogen_ci"
CONNECTION = "cartogen_ci_conn"


def _boot_qgis():
    from tests.test_chat_widget_live import _boot_qgis as _shared_boot
    return _shared_boot()


def _admin_connection():
    uri = QgsDataSourceUri()
    uri.setConnection(PG["host"], PG["port"] or "5432", PG["database"] or "postgres", PG["user"], PG["password"])
    return QgsProviderRegistry.instance().providerMetadata("postgres").createConnection(uri.connectionInfo(False), {})


def _set_connection(host=None, port=None):
    s = QgsSettings()
    base = f"QGIS/connections-postgres/{CONNECTION}"
    s.setValue(f"{base}/host", host or PG["host"])
    s.setValue(f"{base}/port", port or PG["port"] or "5432")
    s.setValue(f"{base}/database", PG["database"] or "postgres")
    s.setValue(f"{base}/username", PG["user"])
    s.setValue(f"{base}/password", PG["password"])


@unittest.skipUnless(QGIS_LIVE_AVAILABLE and HAVE_DB, "needs real QGIS and a PostGIS server (CARTOGEN_TEST_PG_HOST)")
class TestExecuteReadOnlySqlOnPostgis(unittest.TestCase):
    def setUp(self):
        _boot_qgis()
        QgsProject.instance().clear()
        self.addCleanup(QgsProject.instance().clear)
        conn = _admin_connection()
        for stmt in (
            f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE",
            f"CREATE SCHEMA {SCHEMA}",
            f"CREATE TABLE {SCHEMA}.places (id integer PRIMARY KEY, name text, geom geometry(Point, 4326))",
            f"INSERT INTO {SCHEMA}.places VALUES (1,'a',ST_SetSRID(ST_MakePoint(44.0,15.0),4326)),"
            f"(2,'b',ST_SetSRID(ST_MakePoint(44.1,15.1),4326)),(3,'c',ST_SetSRID(ST_MakePoint(44.2,15.2),4326))",
            f"CREATE TABLE {SCHEMA}.facts (id integer PRIMARY KEY, label text)",
            f"INSERT INTO {SCHEMA}.facts VALUES (1,'x'),(2,'y')",
            f"CREATE SEQUENCE {SCHEMA}.seq1",
        ):
            conn.executeSql(stmt)
        self.conn = conn
        _set_connection()
        self.addCleanup(lambda: QgsSettings().remove(f"QGIS/connections-postgres/{CONNECTION}"))

    def _run(self, sql, geometry_column="", name=CONNECTION):
        from cartogen_ai.core.agent.tools.db_and_workflow_tools import execute_read_only_sql
        return execute_read_only_sql(sql, name, geometry_column)

    def _scalar(self, sql):
        rows = self.conn.executeSql(sql)
        return rows[0][0]

    def test_a_geometry_select_becomes_a_valid_point_layer(self):
        out = self._run(f"SELECT id, name, geom FROM {SCHEMA}.places", "geom")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["feature_count"], 3)
        layer = QgsProject.instance().mapLayersByName(out["layer_name"])[0]
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.wkbType() % 1000 if layer.wkbType() > 1000 else layer.wkbType(), 1, "expected a Point layer")

    def test_a_non_spatial_select_becomes_an_attribute_table(self):
        out = self._run(f"SELECT id, label FROM {SCHEMA}.facts")
        self.assertTrue(out.get("success"), out)
        self.assertEqual(out["feature_count"], 2)

    def test_the_tool_leaves_the_users_connection_writable(self):
        """The first CI run showed the read-only setting staying on a pooled connection that everything else shares."""
        self._run(f"SELECT id FROM {SCHEMA}.facts")
        _admin_connection().executeSql(f"INSERT INTO {SCHEMA}.facts VALUES (99, 'after')")
        self.assertEqual(self._scalar(f"SELECT count(*) FROM {SCHEMA}.facts WHERE id = 99"), 1)

    def test_an_unknown_connection_is_an_error_not_a_silent_fallback(self):
        out = self._run("SELECT 1", name="no_such_connection")
        self.assertIn("error", out)
        self.assertIn("not found", out["error"])

    def test_an_unreachable_server_is_an_error(self):
        _set_connection(host="127.0.0.1", port="1")
        out = self._run("SELECT 1")
        self.assertIn("error", out, out)

    def test_bad_sql_is_an_error(self):
        out = self._run(f"SELECT * FROM {SCHEMA}.no_such_table")
        self.assertIn("error", out, out)

    def test_a_blocked_keyword_never_reaches_the_server(self):
        out = self._run(f"DELETE FROM {SCHEMA}.places")
        self.assertIn("error", out)
        self.assertEqual(self._scalar(f"SELECT count(*) FROM {SCHEMA}.places"), 3)

    def test_a_mutation_hidden_in_a_function_call_is_stopped_by_the_database(self):
        """nextval() passes the keyword filter; only a genuinely read-only session stops it. If this fails, the database-level
        guarantee the tool claims does not hold through QGIS's connection API and the enforcement must change."""
        out = self._run(f"SELECT nextval('{SCHEMA}.seq1')")
        called = self._scalar(f"SELECT is_called FROM {SCHEMA}.seq1")
        self.assertIn("error", out, f"nextval was accepted: {out}")
        self.assertIn(str(called).lower(), ("false", "f", "0"), "the sequence was advanced by a 'read-only' query")


if __name__ == "__main__":
    unittest.main()
