# -*- coding: utf-8 -*-
"""
System & External Integration Tools for Cartogen AI.
(Web Search, Geocoding, PyQGIS Dynamic Execution)
"""

import ast
import builtins as _builtins_module
from .registry import register_tool
from ._cache_utils import TTLCache

# execute_pyqgis_script runs model-generated code directly in the QGIS process.
# These modules/builtins give file-system, network, process, or interpreter-escape
# access and have no legitimate use in a PyQGIS spatial script -- block them
# outright rather than trying to sandbox them.
_BLOCKED_MODULES = {
    "os", "subprocess", "shutil", "sys", "socket", "ctypes",
    "importlib", "pty", "multiprocessing", "pip",
    "urllib", "requests", "http", "ftplib", "smtplib", "pickle", "codecs",
    "base64", "sqlite3", "tempfile", "platform", "threading", "asyncio",
    "pdb", "code", "marshal", "shelve",
    # Added after live adversarial testing confirmed each of these as a real
    # bypass of the restricted __builtins__ dict below, not just theoretical:
    # `import builtins; builtins.open(...)` gets a direct reference to the
    # REAL builtins module (unrestricted eval/exec/open), completely
    # sidestepping _SAFE_BUILTINS, since that dict only governs bare-name
    # lookups, not attribute access on an explicitly imported module object.
    "builtins",
    # `gc.get_objects()` walks the live object graph and can locate an
    # already-imported dangerous module/class (e.g. subprocess.Popen) even
    # though this script never imported it itself.
    "gc",
    # `inspect.currentframe()` and frame-walking can reach the globals of
    # other already-executing frames, which may hold unrestricted references.
    "inspect",
    "types", "copyreg", "runpy",
    # Added 2026-09-04, live-confirmed (a reproduction against this exact
    # blocklist + _SAFE_BUILTINS combination, not a theoretical concern) while
    # re-reviewing docs/DESTRUCTIVE_TOOLS_AUDIT_2026-08-21.md Section 4 against
    # an external critique of this sandbox's design. None of these four names
    # appear in os/subprocess/shutil/sys/socket -- the modules this blocklist
    # was built around -- and none of their file-writing methods are the
    # builtin `open` name _BLOCKED_CALLS already catches, so all four passed
    # _validate_script_safety completely unmodified and then actually wrote a
    # real file to disk when exec()'d through _SAFE_BUILTINS exactly as
    # execute_pyqgis_script does it. Confirms this project's own SECURITY.md
    # §1 disclaimer ("defense in depth against known techniques, not a
    # formally proven sandbox... a determined attacker with unlimited
    # creativity may find another gap") is not just a hedge -- it's what
    # this class of denylist actually looks like in practice:
    #   - `pathlib.Path(...).write_text()`/`.read_text()`/`.unlink()` --
    #     arbitrary file write, read, and delete via plain method calls, no
    #     `open()` name involved at all.
    #   - `dbm.open(path, 'c')` -- a different name from the blocked
    #     `open` builtin, but the same file-creation capability.
    #   - `logging.FileHandler(path)` -- creates and writes to an arbitrary
    #     path as an ordinary side effect of configuring a log handler.
    #   - `zipfile.ZipFile(path, 'w')` -- arbitrary file write via an
    #     archive-writer object instead of a bare file handle.
    # Blocking these four specific names closes what was actually found and
    # verified this session; it is not a claim that the module list is now
    # complete -- the same shape of gap (any stdlib module offering
    # file/process/network capability under a name this list didn't happen
    # to enumerate) can recur, which is the core of the tiered-execution-model
    # critique this re-review was checking. See docs/
    # QGIS_PRODUCTION_ARCHITECTURE_REVIEW_2026-09-04.md point 19 for the full
    # discussion of whether a denylist is the right long-term boundary at all.
    "pathlib", "dbm", "logging", "zipfile",
}
# Names that must never be *reachable* at all -- not just called. Blocking
# only direct calls (`eval(...)`) misses `x = eval; x(...)`, so every Name/
# Attribute load of these identifiers is rejected, whether or not it's the
# target of a Call node.
_BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "open", "getattr", "setattr", "delattr"}
# Attribute names that form the classic sandbox-escape chain
# (`().__class__.__bases__[0].__subclasses__()...`) or otherwise expose the
# interpreter's internals -- blocked regardless of what object they're
# accessed on, since a blocklist can't enumerate every possible receiver.
#
# format/format_map are here too, not just dunders: `"{0.__class__.__bases__}"
# .format(x)` is a confirmed-live bypass of the ast.Name/ast.Attribute checks
# above, because __class__ etc. appear as plain TEXT inside a string literal
# in that case, not as real Attribute nodes -- Python's str.format() mini-
# language does its own attribute traversal at runtime, invisible to this
# static AST walk. f-strings are unaffected (the expression inside {} is
# parsed as real AST nodes at compile time, already covered above); only the
# old-style .format()/.format_map() *methods* have this risk, and neither is
# needed for PyQGIS scripts (f-strings and % formatting cover the same ground).
_BLOCKED_DUNDER_ATTRS = {
    "__class__", "__bases__", "__subclasses__", "__mro__", "__globals__",
    "__builtins__", "__import__", "__loader__", "__spec__", "__reduce__",
    "__reduce_ex__", "__code__", "__closure__", "__getattribute__",
    "format", "format_map",
}
# Qt classes with file, process, network, or dynamic-library capability --
# confirmed live that QDirIterator (from `qgis.PyQt.QtCore`, a module that
# MUST stay importable for any normal PyQGIS work: QVariant, QColor, signals,
# etc. all live there too) walks the real filesystem and returns real paths
# from well outside the QGIS install, completely bypassing every os/sys/etc.
# check above -- because those only look at the MODULE being imported, not
# WHICH NAMES are pulled from an otherwise-legitimate module. QFile/QProcess/
# QNetworkAccessManager are the same category of risk (arbitrary file read,
# process launch, raw network I/O) via the exact same blind spot, whichever
# Qt submodule they're imported from. Checked as both a bare name (`from X
# import QFile` then `QFile(...)`) and an attribute (`qgis.PyQt.QtCore.QFile`
# or `some_module.QFile`) via _BLOCKED_CALLS and _BLOCKED_DUNDER_ATTRS below.
_BLOCKED_QT_NAMES = {
    "QFile", "QSaveFile", "QTemporaryFile", "QDir", "QDirIterator",
    "QFileInfo", "QFileSystemWatcher", "QProcess", "QProcessEnvironment",
    "QNetworkAccessManager", "QNetworkRequest", "QNetworkReply",
    "QTcpSocket", "QUdpSocket", "QLocalSocket", "QSslSocket",
    "QSettings", "QLibrary", "QPluginLoader",
    # QDesktopServices.openUrl() on a local file path launches it via the OS's
    # default shell association -- for an executable, that association IS to
    # run it, making this a real "launch an arbitrary local program" vector.
    "QDesktopServices",
}
_BLOCKED_CALLS |= _BLOCKED_QT_NAMES
_BLOCKED_DUNDER_ATTRS |= _BLOCKED_QT_NAMES
# Curated allowlist passed as the executed script's __builtins__ -- defense in
# depth on top of the AST checks above. Even if some future AST bypass is
# found, names like eval/open/getattr simply won't resolve inside the
# script's scope because they're absent from this dict entirely.
#
# __import__ IS included, deliberately -- Python's `import`/`from X import Y`
# statements need __builtins__.__import__ to exist at all, even for fully
# permitted modules (e.g. `from qgis.core import QgsFillSymbol`), so excluding
# it broke every import statement outright, not just disallowed ones. This
# doesn't reopen the dynamic-import bypass: `_validate_script_safety` blocks
# any disallowed module via the separate ast.Import/ImportFrom check below,
# AND independently rejects any literal `__import__` reference in the script
# source via the ast.Name check (so `__import__('os')` written as an
# expression is still caught at validation time, before this dict is ever
# consulted -- that check doesn't depend on __import__'s runtime presence).
_SAFE_BUILTIN_NAMES = (
    "bool", "int", "float", "complex", "str", "bytes", "list", "dict", "set",
    "frozenset", "tuple", "range", "slice", "type", "object", "__import__",
    # Needed for the `class X:` statement itself to work at all -- Python
    # compiles every class body to a call to this, same category as
    # __import__ above (required machinery, not an extra capability: it's
    # sugar around type(), which is already in this list).
    "__build_class__",
    "len", "iter", "next", "enumerate", "zip", "map", "filter", "sorted",
    "reversed", "sum", "min", "max", "abs", "round", "any", "all",
    "isinstance", "issubclass", "hasattr", "callable", "repr", "format",
    "hash", "id", "print", "super", "classmethod", "staticmethod", "property",
    "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "StopIteration", "RuntimeError",
    "ZeroDivisionError", "ArithmeticError", "NotImplementedError",
    "OSError", "IOError", "FileNotFoundError", "NameError", "LookupError",
    "True", "False", "None", "NotImplemented",
)
_SAFE_BUILTINS = {
    name: getattr(_builtins_module, name)
    for name in _SAFE_BUILTIN_NAMES
    if hasattr(_builtins_module, name)
}


def _validate_script_safety(script: str):
    """Returns an error string if the script imports a blocked module, or
    references (loads OR calls -- aliasing doesn't help) a blocked builtin or
    interpreter-escape attribute, otherwise None. AST-based, so it can't be
    fooled by string obfuscation the way a regex check could. This is a
    blocklist, not a full sandbox on its own -- see _SAFE_BUILTINS in this
    module for the defense-in-depth layer applied at exec() time."""
    try:
        tree = ast.parse(script)
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BLOCKED_MODULES:
                    return f"Blocked import '{alias.name}' -- not allowed in execute_pyqgis_script."
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in _BLOCKED_MODULES:
                return f"Blocked import '{node.module}' -- not allowed in execute_pyqgis_script."
            # Check the imported NAMES too, not just the module -- an allowed
            # module (qgis.PyQt.QtCore etc, needed for QVariant/QColor/signals)
            # can still export a dangerous class like QFile/QProcess. Checked
            # here on the alias's real name (not asname), so `from
            # qgis.PyQt.QtCore import QFile as F` is still caught even though
            # the script never writes the literal string "QFile" again --
            # relying only on later Name/Attribute references misses aliasing.
            for alias in node.names:
                if alias.name in _BLOCKED_QT_NAMES:
                    return f"Blocked import '{alias.name}' -- not allowed in execute_pyqgis_script."
        elif isinstance(node, ast.Name):
            if node.id in _BLOCKED_CALLS:
                return f"Blocked reference to '{node.id}' -- not allowed in execute_pyqgis_script."
        elif isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_DUNDER_ATTRS:
                return f"Blocked attribute access '.{node.attr}' -- not allowed in execute_pyqgis_script."
    return None


@register_tool("search_web", "Search internet for real-time information or facts.", {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]})
def search_web(query: str, max_results: int = 3):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return {"message": f"No results found for '{query}'"}
            formatted = []
            for r in results:
                formatted.append(f"Title: {r.get('title')}\nURL: {r.get('href')}\nSnippet: {r.get('body')}")
            return {"results": "\n\n".join(formatted)}
    except ImportError:
        return {
            "error": "Required package 'duckduckgo-search' is missing. Ask the user to install it via "
            "the qpip plugin, or manually in the OSGeo4W Shell: python -m pip install duckduckgo-search"
        }
    except Exception as e:
        return {"error": f"Search failed: {e}"}


def resolve_gemini_search_config():
    """Reads the active provider/model and Gemini credential from QgsSettings/
    QgsAuthManager. Fast, local-only -- but still QGIS state, so agent.py's
    two-phase dispatch runs this on the main thread (same as any other
    QgsSettings/QgsProject access) and only sends the slow network call in
    grounded_search() to the background thread."""
    try:
        from qgis.core import QgsSettings
    except ImportError:
        return {"error": "QGIS not available"}

    settings = QgsSettings()
    provider = settings.value("cartogen_ai/provider", "openrouter")
    if provider != "gemini":
        return {"error": "gemini_grounded_search is only available when the active provider is Gemini. Use search_web instead."}

    from ..auth import CredentialManager
    api_key = CredentialManager.get_credential("gemini")
    if not api_key:
        return {"error": "No Gemini API key configured."}

    model = settings.value("cartogen_ai/gemini_model", "gemini-flash-latest")
    if not model or model == "auto":
        model = "gemini-flash-latest"

    return {"success": True, "api_key": api_key, "model": model}


@register_tool(
    "gemini_grounded_search",
    "Search the live web using Gemini's native Google Search grounding for real-time, source-cited facts. "
    "Only works when the active provider is Gemini with a configured API key -- prefer this over search_web "
    "when the active provider is Gemini.",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def gemini_grounded_search(query: str):
    """Standalone entry point: does both phases inline, so it still works when
    called directly (e.g. in tests) rather than through agent.py's two-phase
    dispatch."""
    config = resolve_gemini_search_config()
    if "error" in config:
        return config
    from ..providers.gemini import grounded_search
    return grounded_search(config["api_key"], query, model=config["model"])


def resolve_openai_search_config():
    """Same role as resolve_gemini_search_config, for OpenAI's dedicated
    web-search Chat Completions model -- unlike Gemini, that model is fixed
    (gpt-5-search-api), not the user's configured chat model, so there's no
    model setting to read here."""
    try:
        from qgis.core import QgsSettings
    except ImportError:
        return {"error": "QGIS not available"}

    settings = QgsSettings()
    provider = settings.value("cartogen_ai/provider", "openrouter")
    if provider != "openai":
        return {"error": "openai_grounded_search is only available when the active provider is OpenAI. Use search_web instead."}

    from ..auth import CredentialManager
    api_key = CredentialManager.get_credential("openai")
    if not api_key:
        return {"error": "No OpenAI API key configured."}

    return {"success": True, "api_key": api_key}


@register_tool(
    "openai_grounded_search",
    "Search the live web using OpenAI's dedicated web-search model for real-time, source-cited facts. "
    "Only works when the active provider is OpenAI with a configured API key -- prefer this over "
    "search_web when the active provider is OpenAI.",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def openai_grounded_search(query: str):
    """Standalone entry point: does both phases inline, so it still works when
    called directly (e.g. in tests) rather than through agent.py's two-phase
    dispatch."""
    config = resolve_openai_search_config()
    if "error" in config:
        return config
    from ..providers.openai import grounded_search
    return grounded_search(config["api_key"], query)


_GEOCODE_CACHE = TTLCache(ttl_seconds=1800)
_GEOCODE_BATCH_DELAY_SECONDS = 1.0  # Nominatim's usage policy caps requests at ~1/sec
_GEOCODE_BATCH_MAX = 25


def _geocode_one(location_name: str):
    """Single-location Nominatim lookup, shared by geocode_and_enrich and
    geocode_batch. Cached -- repeated lookups of the same place name within a
    session (e.g. the model re-checking a coordinate it already resolved)
    cost zero extra network calls."""
    import urllib.request
    import json
    import urllib.parse

    cached = _GEOCODE_CACHE.get(location_name)
    if cached is not None:
        return {**cached, "cached": True}

    encoded = urllib.parse.quote(location_name)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            if data:
                result = {
                    "location": data[0]['display_name'],
                    "lat": float(data[0]['lat']),
                    "lon": float(data[0]['lon'])
                }
                _GEOCODE_CACHE.set(location_name, result)
                return result
            else:
                return {"error": "Location not found."}
    except Exception as e:
        return {"error": str(e)}


@register_tool("geocode_and_enrich", "Geocode a SINGLE address/place name into lat/lon via Nominatim API. For multiple locations in one request, use geocode_batch instead -- one call per place will run out of tool-call steps before finishing a long list.", {"type": "object", "properties": {"location_name": {"type": "string"}}, "required": ["location_name"]})
def geocode_and_enrich(location_name: str):
    return _geocode_one(location_name)


@register_tool(
    "geocode_batch",
    "Geocode MULTIPLE address/place names into lat/lon in a single call. Use this instead of "
    "calling geocode_and_enrich in a loop whenever more than one location needs coordinates.",
    {"type": "object", "properties": {"location_names": {"type": "array", "items": {"type": "string"}}}, "required": ["location_names"]},
)
def geocode_batch(location_names: list):
    import time

    if not location_names:
        return {"error": "location_names must be a non-empty list."}
    if len(location_names) > _GEOCODE_BATCH_MAX:
        return {"error": f"Too many locations in one batch (max {_GEOCODE_BATCH_MAX}); split into smaller batches."}

    results = []
    for i, name in enumerate(location_names):
        res = _geocode_one(name)
        results.append({"location_name": name, **res})
        # Only sleep between real network calls, not cache hits, and never after the last item.
        if i < len(location_names) - 1 and not res.get("cached"):
            time.sleep(_GEOCODE_BATCH_DELAY_SECONDS)

    return {"success": True, "results": results}


@register_tool("execute_pyqgis_script", "Execute arbitrary PyQGIS script. Must define run() function returning result.", {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]})
def execute_pyqgis_script(script: str):
    import traceback

    safety_error = _validate_script_safety(script)
    if safety_error:
        return {"error": f"Script rejected for safety: {safety_error}"}

    try:
        from qgis.core import (
            QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature,
            QgsGeometry, QgsPointXY, QgsField, QgsApplication
        )
        from qgis.PyQt.QtCore import QVariant
        
        local_env = {
            'QgsProject': QgsProject,
            'QgsVectorLayer': QgsVectorLayer,
            'QgsRasterLayer': QgsRasterLayer,
            'QgsFeature': QgsFeature,
            'QgsGeometry': QgsGeometry,
            'QgsPointXY': QgsPointXY,
            'QgsField': QgsField,
            'QgsApplication': QgsApplication,
            'QVariant': QVariant,
        }
    except ImportError:
        local_env = {}

    # Defense in depth on top of _validate_script_safety's AST checks: even if
    # some future AST bypass slips through, eval/open/__import__/getattr etc.
    # simply aren't resolvable names inside this restricted builtins scope.
    local_env['__builtins__'] = _SAFE_BUILTINS
    # __name__ is a normal module global CPython's class-statement machinery
    # reads implicitly (for __qualname__/__module__), not a builtin -- without
    # it, `class X: ...` inside a script fails with a confusing NameError.
    local_env['__name__'] = 'execute_pyqgis_script'

    try:
        exec(script, local_env)
        if 'run' not in local_env:
            return {"error": "Script must define a 'run()' function."}
            
        result = local_env['run']()
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
