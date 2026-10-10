# -*- coding: utf-8 -*-
"""
PostGIS Database Integration and Workflow Persistence Tools for Cartogen AI.
Enforces read-only DB role execution guards for SQL queries and provides workflow saving/loading.
"""

import re
from .registry import register_tool
from ....infrastructure.settings_keys import workflow_preset_key


try:
    from qgis.core import QgsProject, QgsSettings, QgsVectorLayer, QgsDataSourceUri, QgsProviderRegistry
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False


def _is_on(value):
    return str(value).strip().lower() in ("on", "true", "t", "1")


def _enforce_db_read_only(connection_uri_str: str, sql_query: str, provider_registry=None):
    """Database-level layer of read-only enforcement on top of the keyword blocklist in execute_read_only_sql (which is a cheap
    first filter, not a guarantee). Opens a connection through QGIS's own API, puts that session in read-only mode, CHECKS that the
    server now reports `transaction_read_only = on`, and only then runs the query on the same connection.

    GitHub #151 (audit F15): this used to return None (= proceed) whenever the connection could not be created, so the layer that
    claims to be a guarantee silently turned itself off. It now fails CLOSED at every step. What it still cannot do: the result
    layer is created afterwards through a separate provider connection, so the real guarantee is a read-only database role;
    this check proves the validation run was read-only, nothing more. Never raises. Returns None when safe to proceed, else an
    error dict. Not exercised against a real PostGIS server."""
    try:
        registry = provider_registry or QgsProviderRegistry.instance()
        md = registry.providerMetadata("postgres")
        conn = md.createConnection(connection_uri_str, {}) if md is not None else None
    except Exception as e:
        return {"error": f"Could not open the database connection to enforce read-only mode, refusing to execute: {e}"}
    if conn is None:
        return {"error": "Could not open the database connection to enforce read-only mode, refusing to execute."}

    # CI finding (PR #210, first run against a real PostGIS server): SET SESSION CHARACTERISTICS changes the session of a POOLED connection that
    # QGIS shares with everything else using the same connection info, and it was never reset, so after one call the user's own
    # connection refused every write ("cannot execute DROP SCHEMA in a read-only transaction"). The previous setting is read first and put
    # back in a finally, on every exit path.
    previous_read_only = False
    try:
        before = conn.executeSql("SHOW default_transaction_read_only")
        previous_read_only = bool(before and before[0] and _is_on(before[0][0] if isinstance(before[0], (list, tuple)) else before[0]))
    except Exception as e:
        return {"error": f"Could not read the database session's current mode, refusing to execute: {e}"}

    def _restore():
        try:
            conn.executeSql("SET SESSION CHARACTERISTICS AS TRANSACTION READ " + ("ONLY" if previous_read_only else "WRITE"))
        except Exception:
            pass          # nothing more can be done; the query below has already been refused or has finished

    try:
        try:
            conn.executeSql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            rows = conn.executeSql("SHOW transaction_read_only")
            if not (rows and rows[0] and _is_on(rows[0][0] if isinstance(rows[0], (list, tuple)) else rows[0])):
                return {"error": "The database did not confirm a read-only session, refusing to execute."}
        except Exception as e:
            # Fail CLOSED: if we can't confirm the session is read-only, refuse rather than run with no DB-level guarantee.
            return {"error": f"Could not enforce database-level read-only mode, refusing to execute: {e}"}

        try:
            conn.executeSql(sql_query)
        except Exception as e:
            return {"error": f"Database rejected query under read-only enforcement: {e}"}
        return None
    finally:
        _restore()


def build_query_table(sql_query: str, key_column: str = "_cg_id") -> str:
    """The `table` part of a PostGIS data source that turns a SELECT into a layer: a parenthesised subquery with a generated
    unique key (a query layer needs one). Pure. #151: the old code used `uri.setSql("(...)")`, which is a feature FILTER on a
    table that was never named, not a query-layer definition."""
    inner = sql_query.strip().rstrip(";").strip()
    return f"(SELECT row_number() OVER () AS {key_column}, * FROM ({inner}) AS _cg_q)"


@register_tool("execute_read_only_sql", "Execute a read-only SQL query against a named PostGIS connection or active project layers.", {"type": "object", "properties": {"connection_name": {"type": "string"}, "sql_query": {"type": "string"}, "geometry_column": {"type": "string", "description": "Name of the geometry column in the query result; omit for a non-spatial result table."}}, "required": ["sql_query"]})
def execute_read_only_sql(sql_query: str, connection_name: str = "", geometry_column: str = ""):
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
            base = f"QGIS/connections-postgres/{connection_name}"
            host = settings.value(f"{base}/host", "")
            database = settings.value(f"{base}/database", "")
            port = settings.value(f"{base}/port", "5432")
            username = settings.value(f"{base}/username", "")
            password = settings.value(f"{base}/password", "")
            authcfg = settings.value(f"{base}/authcfg", "")

            # #151: a named connection that cannot be resolved is an ERROR. It used to fall through to the project-layer
            # virtual provider and run the SQL there, i.e. answer a different question from the one asked.
            if not (host and database):
                return {"error": f"PostGIS connection '{connection_name}' was not found in QGIS (host/database missing)."}

            uri = QgsDataSourceUri()
            if authcfg:
                uri.setConnection(host, str(port), database, "", "", authConfigId=str(authcfg))
            else:
                uri.setConnection(host, str(port), database, username, password)

            db_error = _enforce_db_read_only(uri.connectionInfo(True), sql_query)
            if db_error is not None:
                return db_error

            uri.setDataSource("", build_query_table(sql_query), geometry_column or "", "", "_cg_id")
            layer_name = f"pg_{connection_name}_result"
            layer = QgsVectorLayer(uri.uri(False), layer_name, "postgres")
            if not layer.isValid():
                return {"error": f"The query ran on PostGIS connection '{connection_name}' but QGIS could not load its result as a layer"
                                 + (f" (is '{geometry_column}' a geometry column?)." if geometry_column else ".")}
            # #151: the result is a view of a query, never an editable table. Without this QGIS would let a later tool or the user
            # start editing it and push changes back to the database through a normal (writable) connection.
            layer.setReadOnly(True)
            QgsProject.instance().addMapLayer(layer)
            return {
                "success": True,
                "layer_name": layer_name,
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
        key = workflow_preset_key(preset_name)
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
        key = workflow_preset_key(preset_name)
        raw = settings.value(key, "") if settings else ""
        if raw:
            return {"success": True, "preset_name": preset_name, "workflow_json": raw}
        return {"error": f"Workflow preset '{preset_name}' not found."}
    except Exception as e:
        return {"error": f"load_workflow_preset failed: {e}"}
