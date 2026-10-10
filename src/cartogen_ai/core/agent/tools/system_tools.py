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
    # Added 2026-09-05, a systematic sweep of this exact same gap shape (a
    # capability-bearing stdlib module this list hadn't happened to name
    # yet), each confirmed by actually running it through this file's real
    # _validate_script_safety + _SAFE_BUILTINS exec() path, not assumed:
    #   - `io.open` is the SAME function as the builtin `open` -- literally
    #     `import io; io.open is open` is True -- but reached via attribute
    #     access (`io.open(...)`) rather than the bare name `open`, so it
    #     wrote a real file to disk completely unblocked by _BLOCKED_CALLS'
    #     bare-name check on 'open'.
    #   - `tarfile.open(path, "w").addfile(...)`, `gzip.open(path, "wb")`,
    #     `bz2.open(...)`, `lzma.open(...)` all wrote real archive/compressed
    #     files to disk -- the exact same "arbitrary file write via an
    #     archive-writer object" shape as the already-blocked `zipfile`,
    #     just under different module names.
    #   - `winreg.CreateKey`/`SetValueEx` wrote a real Windows registry key
    #     -- persistent system-state modification with no filesystem
    #     footprint at all, a capability class this list hadn't covered.
    #   - `linecache.getline(path, n)` read a real line from a real file
    #     (`C:\Windows\win.ini` in the live test) with no `open` name
    #     involved -- confirms arbitrary file READ is exploitable through
    #     the same blind spot as the already-covered file WRITE gaps;
    #     `filecmp` grants the same class of file-content read/compare.
    #   - `socketserver`, `poplib`, `imaplib`, `nntplib`, `xmlrpc` are real
    #     network-protocol-client/server modules, the same category already
    #     blocked via `ftplib`/`smtplib`/`http`/`urllib`/`requests`, just
    #     not individually enumerated before.
    #   - `webbrowser`/`pydoc` can launch an external program (a browser, or
    #     a pager subprocess via `pydoc.pipepager`) -- the same "launch an
    #     arbitrary local program" risk already documented for
    #     `QDesktopServices` below, under stdlib names instead of a Qt one.
    #   - `zipimport` loads and executes code from a zip file -- the same
    #     dynamic-code-loading risk already blocked via `importlib`/`runpy`.
    #   - `venv`/`mmap` have no legitimate use in a PyQGIS spatial script
    #     (environment creation; raw memory-mapped file access) and sit in
    #     the same risk family as the rest of this list -- blocked for the
    #     same defense-in-depth reason as the Qt classes below, even without
    #     a standalone live repro for each individually.
    # As before: this closes what was actually found this sweep, not a claim
    # of completeness -- see point 19's review-doc entry for the standing
    # denylist-vs-allowlist architecture question this doesn't resolve.
    "io", "tarfile", "gzip", "bz2", "lzma", "winreg",
    "linecache", "filecmp",
    "socketserver", "poplib", "imaplib", "nntplib", "xmlrpc",
    "webbrowser", "pydoc", "zipimport", "venv", "mmap",
    # Added 2026-09-23, live-confirmed against this exact validator +
    # _SAFE_BUILTINS combination: this plugin's own package is never blocked
    # (a legitimate script has no reason to import it), so
    # `from cartogen_ai.infrastructure.auth import CredentialManager` reads
    # the live in-memory session credential store directly, and
    # `import cartogen_ai.core.agent.tools.system_tools as st` reaches this
    # very module's own _BLOCKED_MODULES/_SAFE_BUILTINS objects at runtime.
    # No PyQGIS spatial script needs anything from this plugin's own
    # internals -- QGIS objects (QgsProject, layers, etc.) are always passed
    # in via local_env in execute_pyqgis_script below, never via importing
    # this package.
    "cartogen_ai",
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
    # Added 2026-09-08, live-confirmed during a full independent code review (a real
    # reproduction against this exact denylist + _SAFE_BUILTINS combination, not a
    # theoretical concern, same as every prior sweep above): a script can reach the
    # REAL, unrestricted `builtins` module -- completely bypassing _SAFE_BUILTINS below
    # -- via exception-traceback frame-walking, with no import and no name this list
    # already caught:
    #     try:
    #         raise ValueError()
    #     except ValueError as e:
    #         f = e.__traceback__.tb_frame
    #         while f.f_back is not None:
    #             f = f.f_back
    #         real_builtins = f.f_globals["__builtins__"]  # the REAL module/dict
    # `f_back`/`f_globals`/`tb_frame` are ordinary attribute names on frame/traceback
    # objects that this list did not previously enumerate, and `__builtins__` here is a
    # string dict KEY (f.f_globals['__builtins__']), not an ast.Attribute node, so the
    # existing `__builtins__` entry above (which only catches `.` attribute access)
    # never sees it either. Blocking `f_globals`/`f_back` closes the technique at its
    # first step -- a script can no longer reach ANY frame's globals at all, regardless
    # of how the frame was obtained, so the remaining names below (gi_frame/cr_frame/
    # ag_frame/tb_frame/tb_next/__traceback__, the various ways to obtain a frame or
    # traceback object in the first place) are blocked too, as defense in depth, along
    # with f_locals/f_builtins/f_code (the same class of introspection surface on a
    # frame once one is reached). As with every prior sweep, this closes the specific
    # technique found this review -- not a claim that frame/interpreter introspection
    # is now exhaustively covered. See docs/CODE_REVIEW_2026-09-08.md Sec 4.1 and
    # BUG_TRACKER.md NEW-2026-09-08-1 for the full writeup and live PoC.
    "f_back", "f_globals", "f_locals", "f_builtins", "f_code",
    "gi_frame", "cr_frame", "ag_frame", "tb_frame", "tb_next", "__traceback__",
    # Added 2026-09-20, found and live-confirmed during Part B verification of the
    # standing "has a novel AST-sandbox bypass been attempted beyond the two already
    # checked" open item (docs/IMPLEMENTATION_TRACKER.md / the followup task list's
    # Part B1): `type.__dict__['__subclasses__']` retrieves the exact same
    # `__subclasses__` method the classic `().__class__.__bases__[0].__subclasses__()`
    # escape chain uses, but via a dict __getitem__ subscript on `.__dict__` instead of
    # a literal `.__subclasses__` attribute access -- the AST walk's `ast.Attribute`
    # check never sees it, because the dangerous name appears only as a string constant
    # inside an `ast.Subscript`, not as `node.attr`. `__dict__` itself was never in this
    # blocklist because ordinary instance/self attribute dicts are harmless; the risk is
    # specifically that ANY class or module's `__dict__` is a live mapping of every name
    # in its namespace (including the dangerous ones this list exists to block), fully
    # reachable via subscript with no attribute node involved at all. Live-verified: a
    # script doing exactly this passed `_validate_script_safety` (returned None) and,
    # run through the real restricted-`__builtins__` exec environment, successfully
    # enumerated all 178 currently-loaded subclasses of `object` -- the same reconnaissance
    # step the already-blocked classic chain performs, confirming this is a genuine bypass
    # of the SAME attack family, not a new capability. No legitimate PyQGIS script needs
    # raw `.__dict__` access (feature attributes go through `feature.attributes()`/
    # `feature['field']`, never an object's own namespace dict), so blocking it outright
    # costs no real functionality -- same call already made for `format`/`format_map`
    # above. See tests/test_new_tools.py for the regression test.
    "__dict__",
    # Added 2026-09-23: two allowed modules (qgis.utils, processing) expose os/sys
    # as ordinary attributes at module scope, which _BLOCKED_MODULES's
    # import-statement check doesn't cover. Blocking these attribute names closes
    # that path for any allowed module, not just the two found. No legitimate
    # PyQGIS script needs attribute access to os/sys/modules on anything.
    "os", "sys", "modules",
    # Added 2026-09-24, IMPLEMENTATION_TRACKER.md §1.11's two smaller deferred findings from
    # the same 2026-09-23 pass, now closed. Both are directly reachable via QgsProject/
    # QgsApplication, which are already in local_env for every legitimate PyQGIS script, so an
    # import-level or module-level check can't catch either -- an attribute-name block is the
    # narrowest fix that doesn't touch anything a real script needs:
    # - "write": QgsProject.instance().write(<any path>) live-confirmed (2026-09-24 re-check,
    #   same probe script) to write a real file to an arbitrary path with no path restriction
    #   and no confirmation gate -- every other file-producing tool in the registry goes
    #   through SECURITY.md §5's confirmation-gate mechanism; this let a script reach the same
    #   capability directly. No legitimate script needs to call QgsProject.write() itself --
    #   save_project (agent/tools/project_tools.py) is the gated, registered path for that.
    # - "authManager": QgsApplication.authManager().configIds() live-confirmed to return real
    #   config IDs from the machine's auth database with no gate at all -- doesn't return the
    #   secret values themselves (that needs loadAuthenticationConfig + the right ID), but
    #   config-ID enumeration is real reconnaissance a script shouldn't get for free. Blocking
    #   the attribute name closes the whole authManager() surface, not just configIds()
    #   specifically -- no legitimate PyQGIS script needs auth-manager access from inside this
    #   sandbox; credential handling goes through infrastructure/auth.py's own gated paths.
    # The third item this same tracker entry flagged (whether a script can enumerate/forge-call
    # TOOL_REGISTRY to bypass another tool's own confirmation gate) was live re-checked the same
    # pass and found to be a non-issue already: globals()/vars()/dir() aren't in _SAFE_BUILTINS
    # (NameError, confirmed live) and cartogen_ai.* imports are already blocked (see above),
    # so there is currently no live path to reach TOOL_REGISTRY from inside a script at all --
    # closed as a side effect of the 2026-09-23 cartogen_ai import block, not by a new fix here.
    "write", "authManager",
    # Added 2026-09-27, per docs/RESTRICTEDPYTHON_SANDBOX_LAYER_SCOPE_2026-09-27.md's Shape A
    # step 1: the frame/traceback/generator/coroutine names above (f_back/f_globals/.../tb_next)
    # were each found the hard way, one live-adversarial sweep at a time. RestrictedPython
    # (Zope Foundation, v8.5, verified live against this exact bypass class before this fold --
    # see that doc) maintains `RestrictedPython.transformer.INSPECT_ATTRIBUTES`, a superset
    # covering this same attack surface. These 10 names are the ones in that upstream list this
    # project hadn't independently found yet: f_generator/f_trace (frame), co_code (code
    # objects -- reachable via f_code above), gi_code/gi_yieldfrom (generators, alongside the
    # already-blocked gi_frame), cr_code/cr_await/cr_origin (coroutines, alongside cr_frame),
    # ag_code/ag_await (async generators, alongside ag_frame). Copied as literal names, not a
    # live `from RestrictedPython import ...` -- this sandbox's denylist must stay active
    # whether or not that optional package happens to be installed, matching every other name
    # in this set, which is stdlib-only by design. Not verified live as an actual bypass the way
    # every other entry in this set was (no live-confirmed PoC exists for these 10 specifically);
    # added on the strength of RestrictedPython's own tracking of this exact attack surface, per
    # the same "same shape of gap" reasoning this whole set already documents.
    "f_generator", "f_trace", "co_code", "gi_code", "gi_yieldfrom",
    "cr_await", "cr_code", "cr_origin", "ag_await", "ag_code",
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
        # `ddgs` first, `duckduckgo_search` as a fallback for an environment that
        # already has the old package working -- live-verified, 2026-09-18: PyPI's
        # `duckduckgo_search` (even at 8.1.1, the version requirements.txt pins as the
        # "thin compat shim" floor) silently returns ZERO results for a real query,
        # no error, nothing to catch -- while `ddgs` (the actual current package the
        # project renamed to) returns real results immediately for the identical
        # query. Not a hypothetical: confirmed with a live network call, not just
        # reading the deprecation notice. Same DDGS class/`.text()` call shape in
        # both packages, so no logic below needs to change, only which module
        # provides it.
        try:
            from ddgs import DDGS
        except ImportError:
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
            "error": "Required package 'ddgs' is missing. Ask the user to install it via "
            "the qpip plugin, or manually in the OSGeo4W Shell: python -m pip install ddgs"
        }
    except Exception as e:
        return {"error": f"Search failed: {e}"}


def resolve_gemini_search_config():
    """Reads the active provider/model and Gemini credential from QgsSettings/
    QgsAuthManager. Fast, local-only -- but still QGIS state, so agent_orchestrator.py's
    two-phase dispatch runs this on the main thread (same as any other
    QgsSettings/QgsProject access) and only sends the slow network call in
    grounded_search() to the background thread."""
    try:
        from qgis.core import QgsSettings
    except ImportError:
        return {"error": "QGIS not available"}

    from ....infrastructure.settings_keys import SETTINGS_PROVIDER, SETTINGS_GEMINI_MODEL, normalize_provider
    settings = QgsSettings()
    provider = normalize_provider(settings.value(SETTINGS_PROVIDER, "openrouter"))
    if provider != "gemini":
        return {"error": "gemini_grounded_search is only available when the active provider is Gemini. Use search_web instead."}

    from ....infrastructure.auth import CredentialManager
    api_key = CredentialManager.get_credential("gemini")
    if not api_key:
        return {"error": "No Gemini API key configured."}

    model = settings.value(SETTINGS_GEMINI_MODEL, "gemini-flash-latest")
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
    called directly (e.g. in tests) rather than through agent_orchestrator.py's two-phase
    dispatch."""
    config = resolve_gemini_search_config()
    if "error" in config:
        return config
    from ....infrastructure.providers.gemini import grounded_search
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

    from ....infrastructure.settings_keys import SETTINGS_PROVIDER, normalize_provider
    settings = QgsSettings()
    provider = normalize_provider(settings.value(SETTINGS_PROVIDER, "openrouter"))
    if provider != "openai":
        return {"error": "openai_grounded_search is only available when the active provider is OpenAI. Use search_web instead."}

    from ....infrastructure.auth import CredentialManager
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
    called directly (e.g. in tests) rather than through agent_orchestrator.py's two-phase
    dispatch."""
    config = resolve_openai_search_config()
    if "error" in config:
        return config
    from ....infrastructure.providers.openai import grounded_search
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
    from ...net import urlopen as _qgis_urlopen
    import json
    import urllib.parse

    cached = _GEOCODE_CACHE.get(location_name)
    if cached is not None:
        return {**cached, "cached": True}

    encoded = urllib.parse.quote(location_name)
    url = f"https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QGIS-AI-Assistant'})
        with _qgis_urlopen(req, timeout=15) as response:
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


def add_sandbox_hint(result):
    """Adds a `hint` to a failed script result when the failure is the sandbox lacking Processing algorithms. Pure.

    rc15 hand test D09: a scripted buffer failed with "Algorithm native:buffer not found" (the isolated worker has no Processing
    providers) and the model kept trying variants of it; the error never said that a ready-made tool does the job."""
    if not isinstance(result, dict) or "error" not in result or result.get("hint"):
        return result
    text = str(result.get("error", ""))
    if "Algorithm" in text and "not found" in text:
        return {**result, "hint": (
            "Processing algorithms (native:*, gdal:*, qgis:*) are not available inside the script sandbox. Do not retry this in "
            "a script: call the matching Cartogen tool (for example buffer_analysis, clip_layer or run_allowlisted_processing_algorithm).")}
    return result


@register_tool(
    "execute_pyqgis_script",
    "LAST RESORT ONLY -- run this only when no other registered tool covers the task; check "
    "the rest of the tool list first, including run_allowlisted_processing_algorithm if the task "
    "is achievable via a single Processing algorithm -- that tool never executes Python code at "
    "all, so it's meaningfully safer than this one whenever it applies. Runs in a separate, "
    "isolated process (a snapshot of the project, not the live one) with its own denylist-based "
    "safety sandbox on top (blocked modules/builtins; see SECURITY.md) -- not a formally proven "
    "sandbox, so it is not a safe default path just because it's available. Fails with an error, "
    "without running, if any layer has uncommitted edits -- commit or discard them first. Execute "
    "arbitrary PyQGIS script; must define a run() function returning the result.",
    {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]},
)
def execute_pyqgis_script(script: str):
    import traceback

    safety_error = _validate_script_safety(script)
    if safety_error:
        return {"error": f"Script rejected for safety: {safety_error}"}

    import importlib.util
    qgis_available = (
        importlib.util.find_spec("qgis") is not None
        and importlib.util.find_spec("qgis.core") is not None
    )

    if qgis_available:
        # Process isolation (IMPLEMENTATION_TRACKER.md §1.11, go-ahead 2026-09-28):
        # inside a real running QGIS session there is a real live QgsProject to
        # isolate, so the script runs in a separate worker process instead of
        # exec()'ing in this plugin's own process -- see
        # agent/services/script_isolation.py's module docstring for the full
        # design and its documented limitations.
        from ..services.script_isolation import run_isolated_script, has_uncommitted_edits

        editable_layers = has_uncommitted_edits()
        if editable_layers:
            return {
                "error": (
                    "Refusing to run: layer(s) " + ", ".join(editable_layers) + " have "
                    "uncommitted edits. execute_pyqgis_script runs in an isolated process "
                    "against a saved snapshot of the project and cannot see in-progress "
                    "edits -- commit or discard them first, then retry."
                )
            }
        return add_sandbox_hint(run_isolated_script(script))

    # No live QGIS in this process (unit-test / validator-only context, e.g. this
    # repo's plain `test` CI job) -- the isolation boundary above needs a real
    # QgsApplication/QgsProject to isolate, which doesn't exist here anyway. Exec
    # in-process, same as before isolation existed: this still exercises
    # _validate_script_safety and the _SAFE_BUILTINS defense-in-depth layer,
    # which is what this repo's ~40 execute_pyqgis_script tests actually verify.
    local_env = {}
    local_env['__builtins__'] = _SAFE_BUILTINS
    # __name__ is a normal module global CPython's class-statement machinery
    # reads implicitly (for __qualname__/__module__), not a builtin -- without
    # it, `class X: ...` inside a script fails with a confusing NameError.
    local_env['__name__'] = 'execute_pyqgis_script'

    try:
        exec(script, local_env)  # nosec B102 (in-process fallback used only when qgis is not importable, i.e. unit tests; inside QGIS the script runs in the isolated worker above; builtins are restricted here too)
        if 'run' not in local_env:
            return {"error": "Script must define a 'run()' function."}

        result = local_env['run']()
        return {"success": True, "result": result}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}
