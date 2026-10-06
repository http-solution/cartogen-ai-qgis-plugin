# -*- coding: utf-8 -*-
"""GitHub #151 (audit F15): the DB-level read-only layer fails closed, and a SELECT becomes a proper query-layer table. Driven with
fake provider objects; nothing here contacts PostGIS."""
import unittest
from unittest.mock import MagicMock

from cartogen_ai.core.agent.tools import db_and_workflow_tools as d


def _registry(conn=None, md_none=False, raises=False):
    reg = MagicMock()
    if raises:
        reg.providerMetadata.side_effect = RuntimeError("no driver")
    elif md_none:
        reg.providerMetadata.return_value = None
    else:
        reg.providerMetadata.return_value.createConnection.return_value = conn
    return reg


def _conn(read_only_rows=(("on",),), fail_on=None):
    c = MagicMock()

    def execute(sql):
        if fail_on and fail_on in sql:
            raise RuntimeError("boom")
        if sql.startswith("SHOW"):
            return list(read_only_rows)
        return []
    c.executeSql.side_effect = execute
    return c


class TestEnforceReadOnly(unittest.TestCase):
    def test_confirmed_read_only_session_runs_the_query(self):
        c = _conn(read_only_rows=(("on",),))
        self.assertIsNone(d._enforce_db_read_only("u", "SELECT 1", _registry(c)))
        self.assertIn("SELECT 1", [a.args[0] for a in c.executeSql.call_args_list])

    def test_the_sessions_previous_mode_is_put_back_on_every_path(self):
        """A writable pooled connection must be writable again afterwards (PR #210 CI: it stayed read-only for everyone)."""
        def calls(c):
            return [a.args[0] for a in c.executeSql.call_args_list]

        def conn(previous):
            c = MagicMock()
            state = {"mode": previous}

            def execute(sql):
                if sql.startswith("SHOW default_transaction_read_only"):
                    return [(state["mode"],)]
                if sql.startswith("SHOW transaction_read_only"):
                    return [("on",)]
                if "READ ONLY" in sql:
                    state["mode"] = "on"
                if "READ WRITE" in sql:
                    state["mode"] = "off"
                return []
            c.executeSql.side_effect = execute
            return c, state

        c, state = conn("off")
        d._enforce_db_read_only("u", "SELECT 1", _registry(c))
        self.assertEqual(state["mode"], "off")
        self.assertEqual(calls(c)[-1], "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")
        c, state = conn("on")                                  # a connection that was read-only before stays read-only
        d._enforce_db_read_only("u", "SELECT 1", _registry(c))
        self.assertEqual(state["mode"], "on")
        c, state = conn("off")

        def failing(sql):
            if sql == "SELECT 1":
                raise RuntimeError("boom")
            if sql.startswith("SHOW transaction_read_only"):
                return [("on",)]
            return [("off",)] if sql.startswith("SHOW") else []
        c.executeSql.side_effect = failing
        self.assertIn("rejected", d._enforce_db_read_only("u", "SELECT 1", _registry(c))["error"])
        self.assertEqual(calls(c)[-1], "SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")

    def test_no_connection_fails_closed(self):
        for reg in (_registry(None), _registry(md_none=True), _registry(raises=True)):
            self.assertIn("error", d._enforce_db_read_only("u", "SELECT 1", reg))

    def test_unconfirmed_session_does_not_run_the_query(self):
        c = _conn(read_only_rows=(("off",),))              # the session reports "off" even after the SET: not confirmed
        res = d._enforce_db_read_only("u", "SELECT 1", _registry(c))
        self.assertIn("error", res)
        self.assertNotIn("SELECT 1", [a.args[0] for a in c.executeSql.call_args_list])

    def test_set_failure_fails_closed(self):
        self.assertIn("error", d._enforce_db_read_only("u", "SELECT 1", _registry(_conn(fail_on="SET SESSION"))))

    def test_rejected_query_is_reported(self):
        self.assertIn("rejected", d._enforce_db_read_only("u", "SELECT 1", _registry(_conn(fail_on="SELECT 1")))["error"])


class TestBuildQueryTable(unittest.TestCase):
    def test_wraps_with_generated_key_and_drops_trailing_semicolon(self):
        t = d.build_query_table("SELECT id, geom FROM places;")
        self.assertEqual(t, "(SELECT row_number() OVER () AS _cg_id, * FROM (SELECT id, geom FROM places) AS _cg_q)")


if __name__ == "__main__":
    unittest.main()
