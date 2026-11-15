"""Screen for QGIS expressions that the MODEL wrote (owner decision 2026-10-14, roadmap section 2b).

Why: a QGIS expression can call env('NAME'), which reads an environment variable of the QGIS process (API keys, tokens, home and
network paths), and file functions (file_exists, file_path, file_name, ...) that reveal what is on the user's disk. A model that has
just read untrusted text (a web page, a layer attribute) can be steered into putting those values into a label, an attribute or an
export. Nothing a mapping request needs uses them, so model-written expressions may not call them. eval() and eval_template() are
denied too because they evaluate a string as an expression, which would build env(...) at run time and walk around this screen; exif()
is denied because it reads a file from a path.

What it is not: a sandbox for expressions. Everything else in the grammar stays available, and an expression the USER typed or asked
for by name is outside this screen (the tools that take model input call `screen_expression`; a user-confirmed expression can be
passed with allow_denied=True after a confirmation, which is a UI step not built yet, so today the screen always applies).

Pure Python, no QGIS: the text is tokenised so a denied name inside a string literal, a quoted field name or a comment is not a call,
and a call split by a comment (env /*x*/ ('A')) is still seen."""
import re

DENIED_FUNCTIONS = frozenset({
    "env",
    "file_exists", "file_name", "file_path", "file_size", "file_suffix", "base_file_name", "is_file", "is_directory",
    "exif",
    "eval", "eval_template",
})

_CALL = re.compile(r"(?<![A-Za-z0-9_@$.])([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def _code_only(text):
    """The expression with string literals, quoted identifiers and comments replaced by a space, so only code remains."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in ("'", '"'):
            quote = c
            i += 1
            while i < n:
                if text[i] == quote:
                    if i + 1 < n and text[i + 1] == quote:     # doubled quote = escaped quote
                        i += 2
                        continue
                    break
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                i += 1
            i += 1
            out.append(" ")
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
        elif text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def denied_calls(expression):
    """Sorted denied function names that the expression calls."""
    code = _code_only(str(expression or ""))
    return sorted({m.group(1).lower() for m in _CALL.finditer(code)} & DENIED_FUNCTIONS)


def screen_expression(expression):
    """None when the expression may run, else the message to give back to the model."""
    found = denied_calls(expression)
    if not found:
        return None
    return (f"The expression calls {', '.join(found)}(), which a model-written expression may not use: it can read environment "
            "variables or probe files on this computer. Rewrite it without it, or ask the user to type the expression.")
