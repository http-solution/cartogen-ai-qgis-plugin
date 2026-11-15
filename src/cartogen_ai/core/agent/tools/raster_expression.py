"""Validator for raster-calculator expressions (M7, roadmap 2026-10-14). Pure Python, no QGIS.

native:rastercalc evaluates QGIS's OWN raster-calculator grammar (QgsRasterCalculator), not Python: nothing here can run code. That is the
reason it is the safe route where gdal:rastercalculator is not (its FORMULA went through Python eval(), audit #137). This validator still
accepts only the grammar the calculator documents, so a typo or a steered model gets a plain message before QGIS is involved:

    numbers, "layer name@band" references, + - * / ^ , ( ), comparisons (< > = != <> <= >=), AND, OR,
    sqrt sin cos tan asin acos atan ln log10 abs min max

A layer reference is always written in double quotes as "name@N" with N counting from 1. Anything else (a bare word, a string, a semicolon, a
backtick, a function outside the list) is refused with the offending text. Whether `if()` and similar exist in the calculator's grammar is not
asserted here: the list above is what is known to work, and the live test (tests/test_raster_calculator_tool_live.py) runs each of them."""
import re

MAX_EXPRESSION_LENGTH = 2000
FUNCTIONS = frozenset({"sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "ln", "log10", "abs", "min", "max"})
KEYWORDS = frozenset({"and", "or"})

_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\.\d+")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_REF = re.compile(r"^(.+)@(\d+)$")
_OPERATORS = ("<=", ">=", "!=", "<>", "+", "-", "*", "/", "^", "(", ")", ",", "<", ">", "=")


def validate_raster_expression(expression, band_counts=None):
    """{"ok": True, "refs": [(layer_name, band), ...]} or {"ok": False, "error": message}.

    band_counts maps a layer name to its band count; when given, every reference must name one of those layers and a band within range."""
    text = str(expression or "").strip()
    if not text:
        return {"ok": False, "error": "The expression is empty."}
    if len(text) > MAX_EXPRESSION_LENGTH:
        return {"ok": False, "error": f"The expression is longer than {MAX_EXPRESSION_LENGTH} characters."}
    refs, depth, i, n = [], 0, 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            end = text.find('"', i + 1)
            if end == -1:
                return {"ok": False, "error": 'A quote is not closed. Write a layer as "layer name@band", for example "dem@1".'}
            match = _REF.match(text[i + 1:end])
            if not match:
                return {"ok": False, "error": f'"{text[i + 1:end]}" is not a layer reference. Write "layer name@band", for example "dem@1".'}
            name, band = match.group(1), int(match.group(2))
            if band < 1:
                return {"ok": False, "error": f'Band numbers start at 1, but "{name}@{band}" asks for band {band}.'}
            if band_counts is not None:
                if name not in band_counts:
                    return {"ok": False, "error": f"There is no raster layer named '{name}' in the project.",
                            "available": sorted(band_counts)}
                if band > band_counts[name]:
                    return {"ok": False, "error": f"Layer '{name}' has {band_counts[name]} band(s); band {band} does not exist."}
            refs.append((name, band))
            i = end + 1
            continue
        number = _NUMBER.match(text, i)
        if number:
            i = number.end()
            continue
        word = _WORD.match(text, i)
        if word:
            token = word.group(0).lower()
            after = text[word.end():].lstrip()
            if token in KEYWORDS:
                i = word.end()
                continue
            if token in FUNCTIONS and after.startswith("("):
                i = word.end()
                continue
            return {"ok": False, "error": f"'{word.group(0)}' is not allowed. Allowed functions: {', '.join(sorted(FUNCTIONS))}; "
                                          'write layers as "name@band".'}
        operator = next((op for op in _OPERATORS if text.startswith(op, i)), None)
        if operator is None:
            return {"ok": False, "error": f"The character '{c}' is not allowed in a raster expression."}
        if operator == "(":
            depth += 1
        elif operator == ")":
            depth -= 1
            if depth < 0:
                return {"ok": False, "error": "A closing bracket has no matching opening bracket."}
        i += len(operator)
    if depth:
        return {"ok": False, "error": "A bracket is not closed."}
    if not refs:
        return {"ok": False, "error": 'The expression names no raster. Write at least one layer as "layer name@band", for example "dem@1".'}
    return {"ok": True, "refs": refs}
