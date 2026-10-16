import unittest

from cartogen_ai.core.agent.tools.data_layer_options import (identifier_violation, layer_definition_path_violation, package_path_violation,
                                                             virtual_sql_violation)


class VirtualSqlTests(unittest.TestCase):
    def test_selects_over_project_layers_pass(self):
        for ok in ('SELECT * FROM towns', 'select a.name, count(*) from "my towns" a group by 1;',
                   "WITH x AS (SELECT * FROM t) SELECT * FROM x WHERE name = 'delete'",
                   "SELECT replace(name, 'a', 'b') FROM towns", "SELECT ST_Buffer(geometry, 10) FROM towns"):
            self.assertIsNone(virtual_sql_violation(ok), ok)

    def test_everything_else_is_refused(self):
        for bad in ("", "DROP TABLE t", "SELECT 1; SELECT 2", "SELECT * FROM t -- x", "ATTACH DATABASE 'x' AS y", "SELECT load_extension('x')",
                    "SELECT readfile('/x')", "SELECT * FROM \"ogr:/data/a.shp\"", "SELECT * FROM 'http://x'", "SELECT * FROM t WHERE a='b",
                    "PRAGMA table_info(t)", "INSERT INTO t VALUES (1)", "SELECT * FROM ../x", "x" * 4001, "WITH x AS (DELETE FROM t) SELECT 1"):
            self.assertIsNotNone(virtual_sql_violation(bad), bad)


class MiscTests(unittest.TestCase):
    def test_identifiers(self):
        self.assertIsNone(identifier_violation("table", "my_table1"))
        for bad in ("a b", "a;b", '"x"', "", "1a", None):
            self.assertIsNotNone(identifier_violation("table", bad), bad)

    def test_paths(self):
        self.assertIsNone(layer_definition_path_violation("/x/a.qlr", False))
        self.assertIsNotNone(layer_definition_path_violation("/x/a.qml", False))
        self.assertIsNotNone(layer_definition_path_violation("http://x/a.qlr", False))
        self.assertIsNotNone(layer_definition_path_violation("/nonexistent/a.qlr", True))
        self.assertIsNone(package_path_violation("/x/pack.GPKG"))
        self.assertIsNotNone(package_path_violation("/x/pack.shp"))


if __name__ == "__main__":
    unittest.main()
