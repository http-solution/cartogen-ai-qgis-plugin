# -*- coding: utf-8 -*-
"""
PostGIS Database Integration and Workflow Persistence Tools for Cartogen AI.
Enforces read-only DB role execution guards for SQL queries and provides workflow saving/loading.
"""

import re
from .registry import register_tool

try:
    from qgis.core import QgsProject, QgsSettings, QgsVectorLayer, QgsDataSourceUri, QgsProviderRegistry
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _enforce_db_read_only(connection_uri_str: str, sql_query: str):
    """Second, database-level layer of read-only enforcement on top of the keyword blocklist
    below. The blocklist is a cheap first filter but not a real guarantee -- a sufficiently
    unusual SQL construct could theoretically slip past it. This uses QGIS's own connection
    API (not a new dependency) to open a real Postgres connection, best-effort SET the
    session itself to read-only, then actually execute the query on that same connection --
    if it's secretly destructive despite passing the blocklist, Postgres rejects it here,
    before any QgsVectorLayer/canvas step ever runs.

    Returns None on success (safe to proceed), or an error dict if the DB itself rejected it.
    Never raises -- if this defense-in-depth layer can't be set up at all (older QGIS/driver
    combo, no createConnection support), it degrades to a no-op and the caller proceeds with
    just the keyword-blocklist guarantee, same as before this was added."""
    try:
        md = QgsProviderRegistry.instance().providerMetadata("postgres")
        if md is None:
            return None
        conn = md.createConnection(connection_uri_str, {})
        if conn is None:
            return None
    except Exception:
        return None

    try:
        conn.executeSql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    except Exception as e:
        # Fail CLOSED, not open -- if we can't confirm the session is actually
        # read-only, refuse the query rather than silently running it with no
        # DB-level guarantee at all (the keyword blocklist alone is not a
        # substitute for this layer; that's the whole point of having it).
        return {"error": f"Could not enforce database-level read-only mode, refusing to execute: {e}"}

    try:
        conn.executeSql(sql_query)
    except Exception as e:
        return {"error": f"Database rejected query under read-only enforcement: {e}"}
    return None


@register_tool("execute_read_only_sql", "Execute a read-only SQL query against a named PostGIS connection or active project layers.", {"type": "object", "properties": {"connection_name": {"type": "string"}, "sql_query": {"type": "string"}}, "required": ["sql_query"]})
def execute_read_only_sql(sql_query: str, connection_name: str = ""):
    """Executes SQL query enforcing strict read-only statement checks and PostGIS connection lookups."""
    query_upper = sql_query.strip().upper()

    # Stacked-query guard: reject anything but a single statement (one trailing
    # semicolon is fine) -- a keyword blocklist alone can't stop "SELECT 1;
    # DROP TABLE users;" style injection since the destructive half is a
    # separate statement, not a keyword-modified one.
    statements = [s.strip() for s in sql_query.split(";") if s.strip()]
    if len(statements) > 1:
        return {"error": "Multiple SQL statements in one query are not permitted."}

    # Enforce read-only safety guard at statement parser level
    forbidden = [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE",
        "GRANT", "REVOKE", "INTO", "COPY", "PROGRAM", "EXECUTE", "CALL", "DO",
        "MERGE", "VACUUM", "ANALYZE",
        # Confirmed live: none of the above catch these, and the DB-level
        # "read-only transaction" enforcement in _enforce_db_read_only doesn't
        # block them either since they're not table mutations -- lo_export/
        # pg_read_file can read arbitrary server-side files from a plain
        # SELECT, dblink can run SQL against a completely different server.
        "LO_EXPORT", "LO_IMPORT", "PG_READ_FILE", "PG_READ_BINARY_FILE", "PG_LS_DIR",
    ]
    for keyword in forbidden:
        if re.search(r'\b' + keyword + r'\b', query_upper):
            return {
                "error": f"Destructive/non-read-only SQL keyword '{keyword}' rejected. Only SELECT/read-only spatial SQL queries are permitted."
            }
    # dblink's function family (dblink_exec, dblink_connect, ...) doesn't fit
    # the \b...\b word-boundary check above -- underscore is a word character,
    # so "DBLINK" alone wouldn't match "DBLINK_EXEC". Plain substring match
    # instead; "dblink" is not a word that appears in legitimate spatial SQL.
    if "DBLINK" in query_upper:
        return {"error": "Destructive/non-read-only SQL keyword 'DBLINK' rejected. Only SELECT/read-only spatial SQL queries are permitted."}

    if not QGIS_AVAILABLE:
        return {"success": True, "validated_sql": sql_query, "note": "SQL safety checks passed (QGIS offline)."}

    try:
        # 1. PostGIS Connection Lookup by connection_name
        if connection_name:
            settings = QgsSettings()
            host = settings.value(f"QGIS/connections-postgres/{connection_name}/host", "")
            database = settings.value(f"QGIS/connections-postgres/{connection_name}/database", "")
            port = settings.value(f"QGIS/connections-postgres/{connection_name}/port", "5432")
            username = settings.value(f"QGIS/connections-postgres/{connection_name}/username", "")
            password = settings.value(f"QGIS/connections-postgres/{connection_name}/password", "")

            if host and database:
                uri = QgsDataSourceUri()
                uri.setConnection(host, str(port), database, username, password)
                uri.setSql(f"({sql_query})")

                db_error = _enforce_db_read_only(uri.uri(False), sql_query)
                if db_error is not None:
                    return db_error

                layer = QgsVectorLayer(uri.uri(False), f"pg_{connection_name}_result", "postgres")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    return {
                        "success": True,
                        "layer_name": f"pg_{connection_name}_result",
                        "connection": connection_name,
                        "provider": "postgres",
                        "feature_count": layer.featureCount()
                    }

        # 2. Local Virtual Layer Fallback against project layers
        v_uri = f"query=({sql_query})"
        layer = QgsVectorLayer(v_uri, "sql_query_result", "virtual")
        if layer.isValid():
            QgsProject.instance().addMapLayer(layer)
            return {"success": True, "layer_name": "sql_query_result", "provider": "virtual", "feature_count": layer.featureCount()}

        return {"error": f"Failed to execute SQL query on {'PostGIS connection ' + connection_name if connection_name else 'virtual provider'}."}
    except Exception as e:
        return {"error": f"SQL execution failed: {e}"}


@register_tool("save_workflow_preset", "Save an agent plan as a re-usable JSON workflow preset. To build a "
    "recurring monitoring workflow (see run_monitoring_workflow/schedule_recurring_workflow), save "
    'workflow_json in the shape \'{"steps": [{"tool": "calculate_severity_index", "args": {...}}, ...]}\' '
    "-- an ordered list of read-only analysis tool calls to re-run and diff over time.",
    {"type": "object", "properties": {"preset_name": {"type": "string"}, "workflow_json": {"type": "string"}}, "required": ["preset_name", "workflow_json"]})
def save_workflow_preset(preset_name: str, workflow_json: str):
    """Saves workflow preset JSON into project settings or desktop storage."""
    try:
        settings = QgsSettings() if QGIS_AVAILABLE else None
        key = f"cartogen_ai/workflows/{preset_name}"
        if settings:
            settings.setValue(key, workflow_json)
        return {"success": True, "preset_name": preset_name, "stored_key": key}
    except Exception as e:
        return {"error": f"save_workflow_preset failed: {e}"}


@register_tool("load_workflow_preset", "Load a saved workflow preset JSON by name.", {"type": "object", "properties": {"preset_name": {"type": "string"}}, "required": ["preset_name"]})
def load_workflow_preset(preset_name: str):
    """Loads saved workflow preset JSON."""
    try:
        settings = QgsSettings() if QGIS_AVAILABLE else None
        key = f"cartogen_ai/workflows/{preset_name}"
        raw = settings.value(key, "") if settings else ""
        if raw:
            return {"success": True, "preset_name": preset_name, "workflow_json": raw}
        return {"error": f"Workflow preset '{preset_name}' not found."}
    except Exception as e:
        return {"error": f"load_workflow_preset failed: {e}"}
