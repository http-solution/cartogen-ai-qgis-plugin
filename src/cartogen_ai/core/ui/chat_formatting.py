# -*- coding: utf-8 -*-
"""
Pure-Python chat presentation logic for the dock widget: markdown-to-HTML
rendering, relative timestamps, and chat-bubble color derivation.

Deliberately has ZERO qgis/PyQt imports, unlike ui/dock_widget.py (which
imports qgis.PyQt.QtCore unconditionally at module level and so can't be
imported at all outside a real QGIS process). Everything actually testable
about the chat UI's presentation logic lives here so it can be unit tested
directly, instead of being unreachable inside dock_widget.py.
"""

import re
import datetime


def _is_table_row(line):
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _is_table_separator(line):
    if not (line.startswith("|") and line.endswith("|")):
        return False
    cells = [c.strip() for c in line.strip("|").split("|")]
    return bool(cells) and all(re.match(r'^:?-+:?$', c) for c in cells)


def _split_table_row(line):
    return [c.strip() for c in line.strip("|").split("|")]


def _render_table(rows, text_color, border_color, row_border_color):
    """rows[0] is the header row, rows[1:] are data rows -- caller already
    verified rows[0] is followed by a valid '|---|---|' separator and
    stripped that separator line out before calling this. Colors come from
    render_markdown's theme-derived locals (see its docstring) -- this
    function has no theme context of its own."""
    header = _split_table_row(rows[0])
    th = "".join(
        f'<th style="text-align:left;padding:4px 10px;border-bottom:2px solid {border_color};color:{text_color};">{c}</th>'
        for c in header
    )
    trs = []
    for row_line in rows[1:]:
        cells = _split_table_row(row_line)
        tds = "".join(
            f'<td style="padding:4px 10px;border-bottom:1px solid {row_border_color};color:{text_color};">{c}</td>'
            for c in cells
        )
        trs.append(f"<tr>{tds}</tr>")
    return f'<table style="border-collapse:collapse;margin:6px 0;">' f"<tr>{th}</tr>{''.join(trs)}</table>"


def render_markdown(text, colors=None):
    """colors is the same theme-derived dict derive_bubble_colors() returns
    (text/subtle/border/agent_bg) -- threaded through so code blocks, inline
    code, blockquotes, tables, and <hr> follow the live QGIS theme instead of
    the fixed light-theme colors this used to hardcode (which made code blocks
    in particular unreadable in a dark QGIS theme: a light-grey background with
    no matching foreground color, against text meant to sit on a dark bubble).
    Defaults to the same static light-theme values derive_bubble_colors() falls
    back to when there's no live QApplication, so a bare render_markdown(text)
    call -- existing tests included -- keeps working unchanged."""
    if not colors:
        colors = {
            "user_bg": "#dce8f7", "agent_bg": "#eef0f2", "text": "#1c1c1c",
            "subtle": "#666666", "border": "#d0d0d0",
        }
    text_color = colors.get("text", "#1c1c1c")
    subtle_color = colors.get("subtle", "#666666")
    border_color = colors.get("border", "#d0d0d0")
    row_border_color = _blend_hex(border_color, colors.get("agent_bg", "#eef0f2"), 0.5)
    code_bg = _blend_hex(colors.get("agent_bg", "#eef0f2"), text_color, 0.15)

    # 1. Pull fenced code blocks out first (and drop the language tag, e.g. ```python)
    #    so everything below never touches code content.
    code_blocks = []

    def _stash_code(m):
        code_blocks.append(m.group(2))
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r'```(\w*)\n?(.*?)```', _stash_code, text, flags=re.DOTALL)

    # 2. Escape remaining HTML-sensitive characters.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 3. Block-level formatting. Index-based (not a plain for-line loop) so
    # multi-line constructs -- a table's header+separator+data rows, a run
    # of consecutive blockquote lines -- can consume more than one input
    # line per iteration instead of being handled one line at a time.
    lines = text.split("\n")
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if _is_table_row(stripped) and i + 1 < len(lines) and _is_table_separator(lines[i + 1].strip()):
            table_rows = [stripped]
            j = i + 2
            while j < len(lines) and _is_table_row(lines[j].strip()):
                table_rows.append(lines[j].strip())
                j += 1
            out_lines.append(_render_table(table_rows, text_color, border_color, row_border_color))
            i = j
            continue

        if re.match(r'^-{3,}$', stripped):
            out_lines.append(f'<hr style="border:none;border-top:1px solid {border_color};margin:6px 0;">')
            i += 1
            continue

        h = re.match(r'^(#{1,6})\s+(.*)$', stripped)
        if h:
            size = {1: "15px", 2: "14px", 3: "13.5px"}.get(len(h.group(1)), "13px")
            out_lines.append(f'<div style="font-weight:bold;font-size:{size};margin:8px 0 3px;">{h.group(2)}</div>')
            i += 1
            continue

        # Blockquote -- group consecutive '>' lines into one block (escaped
        # to "&gt;" already, since step 2 ran first).
        if stripped.startswith("&gt;"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith("&gt;"):
                quote_lines.append(re.sub(r'^&gt;\s?', '', lines[i].strip()))
                i += 1
            inner = "<br>".join(quote_lines)
            out_lines.append(
                f'<div style="border-left:3px solid {border_color};margin:6px 0;'
                f'padding:2px 10px;color:{subtle_color};">{inner}</div>'
            )
            continue

        n = re.match(r'^(\d+)\.\s+(.*)$', stripped)
        if n:
            out_lines.append(f'&nbsp;&nbsp;{n.group(1)}. {n.group(2)}')
            i += 1
            continue

        # Bullet -- indentation (2 spaces/level) maps to nesting depth, so a
        # sub-list under a bullet reads as visually nested instead of flat.
        b = re.match(r'^(\s*)[-*]\s+(.*)$', line)
        if b:
            indent_level = len(b.group(1)) // 2
            pad = "&nbsp;&nbsp;" * (2 + indent_level * 2)
            out_lines.append(f'{pad}&bull; {b.group(2)}')
            i += 1
            continue

        out_lines.append(line)
        i += 1
    text = "<br>".join(out_lines)

    # 4. Inline formatting.
    text = re.sub(
        r'`([^`]+?)`',
        f'<code style="background-color: {code_bg}; color: {text_color}; padding: 2px 4px; border-radius: 3px;">\\1</code>',
        text,
    )
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    text = re.sub(r'\[([^\]\[]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)

    # 5. Restore code blocks as styled, non-wrapping blocks.
    for idx, code in enumerate(code_blocks):
        code_html = code.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        block = (
            f'<pre style="background-color: {code_bg}; color: {text_color}; padding: 6px; border-radius: 4px; '
            f'white-space: pre-wrap;"><code>{code_html}</code></pre>'
        )
        text = text.replace(f"\x00CODEBLOCK{idx}\x00", block)

    return text


def now_iso():
    return datetime.datetime.now().isoformat()


def escape_plain_text(text):
    """HTML-escapes raw (non-markdown) text and converts newlines to <br> --
    used for the user's own chat input, which (unlike the agent's replies)
    was previously inserted into the bubble HTML completely unescaped, so a
    literal '<' or '>' in what someone typed could corrupt the display, and
    multi-line input (Shift+Enter) lost its line breaks entirely."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return escaped.replace("\n", "<br>")


def _relative_time(iso_str):
    """Formats an ISO timestamp (as stamped by agent/task_manager.py) as a short
    relative string ("2m ago") for task/memory/chat display. Returns "" for
    missing/unparseable input rather than raising -- this is display-only,
    never critical."""
    if not iso_str:
        return ""
    try:
        ts = datetime.datetime.fromisoformat(iso_str)
        now = datetime.datetime.now(ts.tzinfo) if ts.tzinfo else datetime.datetime.now()
        delta = now - ts
        seconds = delta.total_seconds()
        if seconds < 5:
            return "just now"
        if seconds < 60:
            return f"{int(seconds)}s ago"
        if seconds < 3600:
            return f"{int(seconds // 60)}m ago"
        if seconds < 86400:
            return f"{int(seconds // 3600)}h ago"
        return f"{int(seconds // 86400)}d ago"
    except (ValueError, TypeError):
        return ""


def _blend_hex(hex_a, hex_b, t):
    """Linear-interpolates between two '#RRGGBB' colors; t=0 -> hex_a, t=1 -> hex_b."""
    a, b = hex_a.lstrip("#"), hex_b.lstrip("#")
    ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
    br, bg, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


# branding/Cartogen_Brand_Guidelines.html's documented palette -- teal is the primary accent,
# amber the secondary/highlight one. Neither reached the running UI before the UI/chat redesign
# workstream (2026-09-12): every color in this module was previously derived purely from
# QGIS's own live palette, with no brand identity at all. BRAND_ACCENT_BLEND_T is deliberately
# modest (not a full color replacement) so the accent still visibly adapts across QGIS themes --
# it's blended INTO the theme's own highlight color, never substituted for it, so this can't
# produce a fixed color that clashes with an unexpected QGIS theme the way a hardcoded brand
# color used bare would.
BRAND_TEAL = "#1F7A6C"
BRAND_AMBER = "#C97F22"
BRAND_ACCENT_BLEND_T = 0.35


def _brand_accent(highlight_hex):
    """Blends QGIS's own live accent color toward the Cartogen brand teal -- the one place this
    module's colors pick up brand identity, reused by both derive_bubble_colors (user-message
    bubble tint) and build_dock_stylesheet (buttons, tab underline, focus border) so the accent
    reads as consistently brand-flavored across the whole dock, not just one corner of it."""
    return _blend_hex(highlight_hex, BRAND_TEAL, BRAND_ACCENT_BLEND_T)


def derive_bubble_colors(palette_dict):
    """Pure color logic: given a plain dict of theme hex colors (as read from
    the live QApplication palette by dock_widget._extract_theme_palette),
    derives chat bubble colors that work in both light and dark QGIS themes
    -- a tinted accent for the user's own messages, the theme's own
    'alternate row' color for the agent's (a role already designed to read
    as a subtly distinct background section), and the theme's own muted/
    disabled text color for timestamps rather than a hand-picked grey that
    might not suit a dark theme. No Qt/QGIS dependency -- takes/returns
    plain hex strings, so this (unlike the palette read itself) is directly
    unit-testable."""
    if not palette_dict:
        # Static fallback if there's genuinely no QApplication yet (matches
        # the old hardcoded light-theme colors this replaces).
        return {
            "user_bg": "#dce8f7", "agent_bg": "#eef0f2", "text": "#1c1c1c",
            "subtle": "#666666", "border": "#d0d0d0",
        }
    window = palette_dict.get("window", "#f0f0f0")
    highlight = _brand_accent(palette_dict.get("highlight", "#3daee9"))
    return {
        "user_bg": _blend_hex(window, highlight, 0.22),
        "agent_bg": palette_dict.get("alt_base", window),
        "text": palette_dict.get("text", "#000000"),
        "subtle": palette_dict.get("muted_text", "#808080"),
        "border": palette_dict.get("mid", "#c0c0c0"),
    }


# icon + label per step status, used by both the friendly-name renderer below
# and dock_widget.py's inline chat step line -- kept together so the two
# stay in sync instead of drifting into two separate icon/color choices.
_STEP_STATUS = {
    "running": {"icon": "&#9881;", "label": "Using", "color_key": "subtle"},
    "done": {"icon": "&#10003;", "label": "Used", "color_key": "subtle"},
    "failed": {"icon": "&#10007;", "label": "Failed:", "color_key": "text"},
}


def friendly_tool_name(name):
    """Turns a raw snake_case tool name (e.g. 'apply_graduated_style') into a
    readable phrase ('Apply graduated style') for the live step indicator in
    chat. Pure string transformation, no manual per-tool mapping to maintain
    across 100+ registered tools -- good enough for a live progress line,
    not meant to replace the tool's real description shown elsewhere."""
    if not name:
        return "tool"
    words = name.replace("_", " ").strip()
    return words[0].upper() + words[1:] if words else name


def render_tool_step_html(name, status, error, colors):
    """Pure Python -- builds the small, muted inline-chat line shown for one
    tool-call step (see agent.py's run() tool_step_callback and
    dock_widget.py's _add_tool_step). Deliberately NOT a full chat bubble --
    smaller font, no avatar/label row, so a turn with many tool calls doesn't
    visually compete with the actual conversation."""
    meta = _STEP_STATUS.get(status, _STEP_STATUS["running"])
    color = colors.get(meta["color_key"], colors.get("subtle", "#808080"))
    # friendly_tool_name only ever transforms a real registered tool name
    # (never arbitrary/model-authored text), but error messages can embed
    # data the model supplied (e.g. a layer name it named) -- escape those.
    friendly = friendly_tool_name(name)
    text = f"{meta['label']} {friendly}"
    if status == "failed" and error:
        text += f" &mdash; {escape_plain_text(str(error))}"
    return (
        f'<div style="font-size:11px;color:{color};margin:1px 0 1px 8px;">'
        f'{meta["icon"]}&nbsp;{text}</div>'
    )


def format_send_error(err) -> str:
    """Turns the raw exception text task_runner.py surfaces from a failed
    provider/network call into an actionable chat message, without ever
    hiding the original detail -- classification is a hint layered on top,
    never a replacement (this plugin's whole design point is showing the
    real error, not a black-box one). Matches on the parts that are reliably
    present across 5 different provider SDKs/HTTP layers (a status code, or a
    recognizable requests/urllib3 exception shape) rather than trying to
    fully parse provider-specific JSON error bodies. Found missing in the UX
    audit dated 2026-08-31: every send error used to reach the user as raw
    f"**Error:** {err}", e.g. a bare "401 Client Error: Unauthorized for
    url: ...", with no indication of what to do about it."""
    text = str(err or "").strip() or "(no error detail was provided)"
    lower = text.lower()

    def has(*needles):
        for n in needles:
            if isinstance(n, int):
                if re.search(r"(?<!\d)%d(?!\d)" % n, text):
                    return True
            elif n in lower:
                return True
        return False

    if has(401, "unauthorized", "invalid api key", "incorrect api key", "invalid_api_key"):
        hint = ("**That looks like an authentication problem.** Check the API key for your "
                "selected provider in Settings (\u2699) -- it may be missing, expired, or "
                "pasted incorrectly.")
    elif has(403, "forbidden", "permission denied"):
        hint = ("**That looks like a permissions problem.** Your API key may not have access "
                "to the selected model, or the account behind it may need billing set up with "
                "this provider.")
    elif has(429, "rate limit", "rate_limit", "quota", "too many requests"):
        hint = ("**Rate limited.** You've hit your provider's request or quota limit -- wait a "
                "moment and try again, or switch models/providers in Settings.")
    elif has("timed out", "timeout"):
        hint = ("**The request timed out.** Check your network connection -- or, for Ollama, "
                "that the local server is running -- and try again.")
    elif has("connection", "name resolution", "network is unreachable", "connection refused",
             "failed to establish a new connection"):
        hint = ("**Couldn't reach the provider.** Check your network connection -- or, for "
                "Ollama, that a local server is running at the configured endpoint.")
    elif has(404, "model not found", "does not exist", "no longer available"):
        hint = ("**The selected model wasn't found.** It may have been retired or renamed -- "
                "pick a different model in Settings.")
    else:
        hint = None

    if hint:
        return f"{hint}\n\nDetails: {text}"
    return f"**Error:** {text}"


def build_dock_stylesheet(palette_dict):
    """Pure Python, no QGIS needed -- builds a QSS stylesheet for the whole
    dock widget (buttons, tabs, inputs, progress bar, group boxes, list
    widget) from the same live-palette dict _extract_theme_palette() reads,
    so the "modern" look still adapts to light/dark QGIS themes instead of
    hardcoding colors that would look wrong in one of them. Only styles
    widget TYPES generically; a few specific widgets (the confirm button, the
    stop button, quick-suggestion chips) keep their own targeted inline
    styles on top of this for meaning-carrying color (success green, danger
    red) that a generic rule shouldn't own.

    Object names referenced here (secondaryButton, dangerButton) must be set
    on the relevant widgets in dock_widget.py via setObjectName() for the
    corresponding rule to apply -- QSS object-name selectors are inert
    otherwise, not an error, so a missing setObjectName() just silently
    falls through to the generic QPushButton rule instead of breaking."""
    if not palette_dict:
        palette_dict = {}
    window = palette_dict.get("window", "#f0f0f0")
    base = palette_dict.get("base", "#ffffff")
    alt_base = palette_dict.get("alt_base", window)
    text = palette_dict.get("text", "#000000")
    subtle = palette_dict.get("muted_text", "#808080")
    border = palette_dict.get("mid", "#c0c0c0")
    highlight = _brand_accent(palette_dict.get("highlight", "#3daee9"))
    highlighted_text = palette_dict.get("highlighted_text", "#ffffff")
    highlight_hover = _blend_hex(highlight, "#000000", 0.12)
    highlight_pressed = _blend_hex(highlight, "#000000", 0.22)

    return f"""
QPushButton {{
    background-color: {highlight};
    color: {highlighted_text};
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {highlight_hover};
}}
QPushButton:pressed {{
    background-color: {highlight_pressed};
}}
QPushButton:disabled {{
    background-color: {border};
    color: {subtle};
}}
QPushButton#secondaryButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid {border};
    font-weight: 500;
}}
QPushButton#secondaryButton:hover {{
    background-color: {alt_base};
}}
QPushButton#dangerButton {{
    background-color: transparent;
    color: #c0392b;
    border: 1px solid #c0392b;
    font-weight: 500;
}}
QPushButton#dangerButton:hover {{
    background-color: rgba(192, 57, 43, 0.12);
}}
QPushButton#successButton {{
    background-color: #2e7d32;
    color: white;
    font-weight: 600;
}}
QPushButton#successButton:hover {{
    background-color: #276428;
}}
QPushButton#chipButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid {border};
    border-radius: 11px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 500;
}}
QPushButton#chipButton:hover {{
    background-color: {alt_base};
    border-color: {highlight};
}}
QPushButton#iconButton {{
    padding: 2px;
    border-radius: 15px;
    font-size: 14px;
}}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    top: -1px;
    background-color: {window};
}}
QTabBar::tab {{
    background: transparent;
    color: {subtle};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    background: {alt_base};
    color: {text};
    font-weight: 600;
    border-bottom: 2px solid {highlight};
}}
QTabBar::tab:hover:!selected {{
    background: {alt_base};
}}
QLineEdit, QTextEdit, QComboBox {{
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
    background-color: {base};
    color: {text};
    selection-background-color: {highlight};
    selection-color: {highlighted_text};
}}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border: 1px solid {highlight};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QProgressBar {{
    border: 1px solid {border};
    border-radius: 6px;
    text-align: center;
    background-color: {alt_base};
    color: {text};
}}
QProgressBar::chunk {{
    background-color: {highlight};
    border-radius: 5px;
}}
QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: {text};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}
QListWidget {{
    border: 1px solid {border};
    border-radius: 6px;
    background-color: {base};
    outline: none;
}}
QListWidget::item {{
    border-radius: 4px;
    padding: 2px;
}}
QListWidget::item:selected {{
    background-color: {highlight};
}}
QScrollArea {{
    border: none;
}}
""".strip()
