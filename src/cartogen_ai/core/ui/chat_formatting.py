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


# Extensions this project's own tools actually produce as output_path results (print
# layouts, dashboards, charts, exports, saved styles) -- scoped to these rather than any
# arbitrary file so a stray "C:\Users\x" mention in unrelated prose (not a tool output)
# doesn't get linkified. Windows drive-letter paths only (this plugin is a Windows desktop
# QGIS plugin per its own docs) -- a bare Unix-style "/a/b/c.pdf" is deliberately NOT
# matched, since that shape is common in ordinary prose/URLs and would produce far more
# false-positive "links" to a path that was never a real local file in the first place.
_OUTPUT_FILE_EXTENSIONS = (
    "pdf", "png", "jpg", "jpeg", "html", "htm", "csv", "xlsx",
    "geojson", "gpkg", "qml", "docx",
)
_OUTPUT_PATH_RE = re.compile(
    r'[A-Za-z]:[\\/](?:[^\s<>"\']+[\\/])*[^\s<>"\']+\.(?:' + "|".join(_OUTPUT_FILE_EXTENSIONS) + r')\b'
)


def _linkify_output_paths(text):
    """Turns a bare absolute Windows file path ending in a known tool-output extension
    (e.g. 'C:\\Users\\x\\situation_map.pdf', as the model's own narration of a tool result
    writes it -- see e.g. create_print_layout/generate_html_dashboard/generate_chart's
    output_path results) into a clickable 'file:///...' link, instead of the previous raw,
    unclickable path string. Relies on the SAME QDesktopServices link-opening path
    chat_tab_widget.py's QTextBrowser already uses for http(s) markdown links
    (setOpenExternalLinks(True) opens any external-scheme URL, including file://,
    independent of setOpenLinks(False) -- see init_ui's own comment) -- no new click
    handling needed in the widget layer for this to work. Runs on already HTML-escaped
    text, so the path itself needs no further escaping; only backslashes need converting
    to forward slashes for a valid file:// URI."""
    def _replace(m):
        path = m.group(0)
        filename = re.split(r'[\\/]', path)[-1]
        file_url = "file:///" + path.replace("\\", "/")
        return f'<a href="{file_url}">\U0001F4C4 {filename}</a>'

    return _OUTPUT_PATH_RE.sub(_replace, text)


# rc7 smoke test F15: replies showed literal "$\le$", "$\times$", "$\text{km}^2$". The chat view does not render
# LaTeX, so simple inline math is converted to Unicode. Anything it cannot fully convert is left exactly as written
# (a half-converted formula is worse than a raw one), and "$5 and $10" is not math: only $...$ spans that contain
# a backslash or a caret are touched.
_LATEX_SPAN = re.compile(r"\$([^$\n]{1,80}?)\$")
_LATEX_SYMBOLS = {
    r"\leq": "\u2264", r"\le": "\u2264", r"\geq": "\u2265", r"\ge": "\u2265", r"\neq": "\u2260",
    r"\times": "\u00d7", r"\cdot": "\u00b7", r"\approx": "\u2248", r"\pm": "\u00b1",
    r"\rightarrow": "\u2192", r"\to": "\u2192", r"\leftarrow": "\u2190", r"\Delta": "\u0394",
    r"\mu": "\u00b5", r"\circ": "\u00b0", r"\degree": "\u00b0", r"\%": "%", r"\,": " ", r"\ ": " ",
    r"\;": " ", r"\!": "",
}
_SUPERSCRIPTS = {"0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074", "5": "\u2075",
                 "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079", "-": "\u207b", "+": "\u207a"}


def _latex_inner(inner):
    """Unicode for a simple LaTeX fragment, or None if any command is left unconverted."""
    t = inner
    t = re.sub(r"\\(?:text|mathrm|textrm|mathbf|textbf)\{([^{}]*)\}", r"\1", t)
    # rc11 smoke test F15: "$15.35^\circ\,\text{N}$" stayed raw because the degree sign is written as a superscript
    # (^\circ / ^{\circ}); once \circ became a degree sign a stray caret was left and the whole span was rejected.
    t = re.sub(r"\^\s*\{?\s*(?:\\circ|\\degree)\s*\}?", "\u00b0", t)
    for cmd in sorted(_LATEX_SYMBOLS, key=len, reverse=True):
        t = t.replace(cmd, _LATEX_SYMBOLS[cmd])

    def _sup(m):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        return "".join(_SUPERSCRIPTS.get(ch, None) or "\x00" for ch in body)
    t = re.sub(r"\^(?:\{([0-9+\-]+)\}|([0-9]))", _sup, t)
    if "\x00" in t or "\\" in t or "^" in t:
        return None
    return t.replace("{", "").replace("}", "")


def simplify_latex(text):
    """Converts simple inline LaTeX ($\\le$, $\\times$, $\\text{km}^2$, $10^3$) to Unicode. Pure."""
    if not text or "$" not in text:
        return text

    def _span(m):
        inner = m.group(1)
        if "\\" not in inner and "^" not in inner:
            return m.group(0)
        converted = _latex_inner(inner)
        return m.group(0) if converted is None else converted
    return _LATEX_SPAN.sub(_span, text)


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
    text = simplify_latex(text)

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
        # Supports standard markdown hyphens/asterisks (-/*) as well as unicode bullets (•).
        b = re.match(r'^(\s*)[-*\u2022]\s+(.*)$', line)
        if b:
            indent_level = len(b.group(1)) // 2
            pad = "&nbsp;&nbsp;" * (2 + indent_level * 2)
            content = b.group(2).strip()

            # Auto-linkify plain text next steps into cartogen action chips if not already linked:
            # e.g., "🔍 Zoom to Layer Extent" or "Export to CSV" or "Reproject to UTM Zone 36N"
            if not re.search(r'\[.+?\]\(.+?\)', content):
                zoom_match = re.search(r'(?:🔍\s*)?(?:Zoom\s+to|zoom\s+to)\s+(?:extent\s+of\s+)?([A-Za-z0-9_,\.\-]+)', content, re.IGNORECASE)
                csv_match = re.search(r'(?:📁\s*)?Export\s+(?:layer\s+|table\s+)?([A-Za-z0-9_,\.\-]+)?\s*(?:to\s+CSV|\.csv)', content, re.IGNORECASE)
                if zoom_match:
                    layer_target = zoom_match.group(1).strip()
                    content = f'<a href="cartogen://zoom/{layer_target}">{content}</a>'
                elif csv_match:
                    layer_target = (csv_match.group(1) or "").strip()
                    content = f'<a href="cartogen://export/{layer_target}">{content}</a>'
                elif any(action_kw in content.lower() for action_kw in ["reproject", "calculate", "generate", "analyze", "buffer", "heatmap", "kde", "filter"]):
                    import urllib.parse
                    encoded_prompt = urllib.parse.quote(content)
                    content = f'<a href="cartogen://prompt/{encoded_prompt}">{content}</a>'

            out_lines.append(f'{pad}&bull; {content}')
            i += 1
            continue

        out_lines.append(line)
        i += 1
    text = "<br>".join(out_lines)

    # 4. Inline formatting. Output-path linkification runs first, before inline code --
    # a tool result path is written as plain prose by the model, not backtick-wrapped, so
    # this ordering is the common case; see _linkify_output_paths' own docstring.
    text = _linkify_output_paths(text)
    text = re.sub(
        r'`([^`]+?)`',
        f'<code style="background-color: {code_bg}; color: {text_color}; padding: 2px 4px; border-radius: 3px;">\\1</code>',
        text,
    )
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    # cartogen:// alongside https?:// -- this app's own internal anchor scheme (see
    # chat_tab_widget.py's _on_step_anchor_clicked), used so markdown-authored content like
    # the welcome message's starter prompts and Next Steps action chips can link to in-app actions.
    def _style_link(m):
        label, url = m.group(1), m.group(2).strip()
        if (url.startswith("cartogen://action/") or
            url.startswith("cartogen://export/") or
            url.startswith("cartogen://prompt/") or
            url.startswith("cartogen://zoom/")):
            if url.startswith("cartogen://prompt/"):
                raw_prompt = url[len("cartogen://prompt/"):]
                import urllib.parse
                if " " in raw_prompt:
                    url = f"cartogen://prompt/{urllib.parse.quote(urllib.parse.unquote(raw_prompt))}"
            elif url.startswith("cartogen://export/"):
                import urllib.parse
                raw_name = url[len("cartogen://export/"):].strip()
                url = "cartogen://export/" + urllib.parse.quote(urllib.parse.unquote(raw_name), safe="")
            elif url.startswith("cartogen://zoom/"):
                raw_zoom = url[len("cartogen://zoom/"):].strip()
                import urllib.parse
                if " " in raw_zoom:
                    url = f"cartogen://zoom/{urllib.parse.quote(urllib.parse.unquote(raw_zoom))}"
            chip_style = (
                f"display: inline-block; padding: 2px 8px; margin: 2px 2px; "
                f"border: 1px solid {border_color}; border-radius: 6px; "
                f"background-color: {colors.get('agent_bg', '#eef0f2')}; "
                f"color: {text_color}; text-decoration: none; font-size: 11.5px; font-weight: 500;"
            )
            return f'<a href="{url}" style="{chip_style}">{label}</a>'
        return f'<a href="{url}">{label}</a>'

    # F15: a layer name such as "Health Facilities (OSM, Yemen)" inside cartogen://export/... contains parentheses;
    # the old pattern ended the URL at the first ")" and left the real closing ")" behind as stray text. One level
    # of balanced parentheses is now part of the URL.
    text = re.sub(r'\[([^\]\[]+)\]\(((?:https?|cartogen)://(?:[^\n()]|\([^\n()]*\))+)\)', _style_link, text)

    # Style any direct cartogen:// anchor tags generated during block parsing that lack style attributes:
    chip_css = (
        f"display: inline-block; padding: 2px 8px; margin: 2px 2px; "
        f"border: 1px solid {border_color}; border-radius: 6px; "
        f"background-color: {colors.get('agent_bg', '#eef0f2')}; "
        f"color: {text_color}; text-decoration: none; font-size: 11.5px; font-weight: 500;"
    )
    text = re.sub(r'<a href="(cartogen://[^"]+)">', rf'<a href="\1" style="{chip_css}">', text)

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


def _clock_time(iso_str):
    """Local clock time for a chat bubble: "23:41" for today, "Oct 01, 23:41" for another day. "" when missing or
    unparseable. rc11 smoke test F25: a relative label ("just now") is computed once when the bubble is drawn and never
    updated, so every bubble kept saying "just now" for the whole session; a clock time stays true."""
    if not iso_str:
        return ""
    try:
        ts = datetime.datetime.fromisoformat(iso_str)
        if ts.tzinfo:
            ts = ts.astimezone().replace(tzinfo=None)
        now = datetime.datetime.now()
        return ts.strftime("%H:%M") if ts.date() == now.date() else ts.strftime("%b %d, %H:%M")
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

# Broadsheet redesign (2026-09-16, mockup-driven): magenta reserved specifically for
# "the one thing that mutates your data" -- the destructive-action confirm button and
# the inline safety-gate card, never a general accent. #A3255A is not a new invented
# color: it's the exact numeral-label hex settings_dialog.py's and tasks_tab_widget.py's
# own _section_header already ship with, so this reuses an already-live color instead of
# introducing a second, competing "brand magenta." Blended at a stronger ratio than the
# teal accent (0.5 vs 0.35) -- a destructive action should read as more distinctly
# "different" than the routine interactive-accent nudge.
BRAND_MAGENTA = "#A3255A"
BRAND_DANGER_BLEND_T = 0.5

# Nearest serif stack Qt's desktop rendering can actually honor -- Source Serif (the
# mockup's stated typeface) is a web font with no bundled-with-Qt equivalent, and this is
# a native Qt app, not a browser. Georgia/Times New Roman is the same fallback stack
# settings_dialog.py's and tasks_tab_widget.py's own _section_header already use for their
# numeral labels -- shared here as one constant so any FUTURE heading reuses the same
# declared stack instead of a third hand-typed copy of the same string.
BROADSHEET_SERIF = "Georgia, 'Times New Roman', serif"


def _brand_accent(highlight_hex):
    """Blends QGIS's own live accent color toward the Cartogen brand teal -- the one place this
    module's colors pick up brand identity, reused by both derive_bubble_colors (user-message
    bubble tint) and build_dock_stylesheet (buttons, tab underline, focus border) so the accent
    reads as consistently brand-flavored across the whole dock, not just one corner of it."""
    return _blend_hex(highlight_hex, BRAND_TEAL, BRAND_ACCENT_BLEND_T)


def _brand_danger(base_hex):
    """Blends a base color toward the Broadsheet destructive-action magenta -- same
    "nudge the live theme color, never replace it outright" approach _brand_accent uses,
    so a destructive-action button/card still visibly adapts across light/dark QGIS themes
    instead of ever being a flat, theme-blind magenta."""
    return _blend_hex(base_hex, BRAND_MAGENTA, BRAND_DANGER_BLEND_T)


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
            "subtle": "#666666", "border": "#d0d0d0", "accent": "#0b6ea3",
            "danger": BRAND_MAGENTA, "danger_bg": "#f7e6ee",
        }
    window = palette_dict.get("window", "#f0f0f0")
    highlight = _brand_accent(palette_dict.get("highlight", "#3daee9"))
    danger = _brand_danger(palette_dict.get("highlight", "#3daee9"))
    return {
        "user_bg": _blend_hex(window, highlight, 0.22),
        "agent_bg": palette_dict.get("alt_base", window),
        "text": palette_dict.get("text", "#000000"),
        "subtle": palette_dict.get("muted_text", "#808080"),
        "border": palette_dict.get("mid", "#c0c0c0"),
        # Exposed for _add_message's left-accent bubble stripe (UI real-session-feedback
        # fixes, 2026-09-12) -- same brand-blended value already computed for user_bg's
        # blend above, just also returned directly so callers don't need a second palette
        # read/blend to get it.
        "accent": highlight,
        # Broadsheet redesign, 2026-09-16: magenta reserved for the one thing that mutates
        # data -- the destructive-action confirm button (build_dock_stylesheet's
        # successButton/dangerButton rules) and the inline safety-gate card (Phase 2,
        # render_safety_gate_html). "danger" is the solid ink (button fill, border,
        # emphasized text); "danger_bg" is a soft card-background tint blended from the
        # SAME window color user_bg/agent_bg already use, at a light ratio, so the gate
        # card reads as "tinted paper", not a jarring flat-magenta block.
        "danger": danger,
        "danger_bg": _blend_hex(window, danger, 0.12),
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
    tool-call step (see agent_orchestrator.py's run() tool_step_callback and
    dock_widget.py's _add_tool_step). Deliberately NOT a full chat bubble --
    smaller font, no avatar/label row, so a turn with many tool calls doesn't
    visually compete with the actual conversation.

    Superseded for "running"/"done" scrollback display by
    render_tool_steps_toggle_html/render_tool_steps_failure_details_html below (real user
    feedback 2026-09-12: a line per event was too much visual space/noise for a multi-tool-call
    turn) -- kept as-is since it's still a small, independently useful building block (and its
    own tests), not because anything still calls it for scrollback rendering."""
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


def render_welcome_html(intro, capabilities, starters, colors):
    """The chat panel's cold-start welcome body -- a numbered capability index (a big teal
    numeral beside a bold title and a muted description) and starter prompts rendered as
    bordered, clickable cards, not a plain bullet list. Design proposal, 2026-09-16 (Dateline
    Dock artifact): real user feedback on the first pass ("its not following the design
    notes") was that going through render_markdown's plain bullet/numbered-list output lost
    the mockup's actual visual treatment -- a numeral-led row and a bordered card per starter,
    not inline text. Hand-built HTML via Qt's table-based rich-text pattern instead (the same
    technique _add_message's own bubble wrapper already uses), bypassing render_markdown
    entirely for this one message. Border-radius is deliberately absent on the starter cards --
    see _add_message's own comment on why Qt's rich-text engine doesn't support it at all.

    `intro` is the italic hero line. `capabilities` is a list of (title, description) pairs;
    `starters` is a list of prompt strings, rendered as cartogen://starter/{index} links --
    see chat_tab_widget.py's _on_starter_prompt_clicked for what a click on one does."""
    text_color = colors.get("text", "#1c1c1c")
    subtle_color = colors.get("subtle", "#666666")
    border_color = colors.get("border", "#d0d0d0")
    teal = _brand_accent(colors.get("highlight", "#3daee9"))

    hero = (
        f'<div style="font-style:italic;font-size:13.5px;color:{text_color};margin-bottom:12px;">'
        f'{escape_plain_text(intro)}</div>'
    )

    rows = []
    for i, (title, desc) in enumerate(capabilities, start=1):
        rows.append(
            '<tr>'
            f'<td style="width:22px;vertical-align:top;padding:3px 6px 3px 0;'
            f'color:{teal};font-weight:bold;font-size:13px;">{i:02d}</td>'
            f'<td style="vertical-align:top;padding:3px 0;font-size:12.5px;">'
            f'<b>{escape_plain_text(title)}</b><br>'
            f'<span style="color:{subtle_color};font-size:11.5px;">{escape_plain_text(desc)}</span>'
            '</td></tr>'
        )
    plate_table = (
        '<table border="0" cellspacing="0" cellpadding="0" width="100%" '
        f'style="margin:2px 0 12px;">{"".join(rows)}</table>'
    )

    starter_cards = []
    for i, prompt in enumerate(starters):
        starter_cards.append(
            '<table border="0" cellspacing="0" cellpadding="0" width="100%" '
            'style="margin-bottom:6px;"><tr>'
            f'<td style="border:1px solid {border_color};padding:7px 10px;">'
            f'<a href="cartogen://starter/{i}" style="text-decoration:none;color:{text_color};'
            f'font-size:12px;">{escape_plain_text(prompt)}</a>'
            '</td></tr></table>'
        )

    starters_heading = (
        f'<div style="font-size:12px;font-weight:bold;color:{text_color};margin:2px 0 6px;">'
        'Try one of these</div>'
    )
    return hero + plate_table + starters_heading + "".join(starter_cards)


def render_preview_html(reasoning_lines, composed_prompt, colors):
    """The '01 Why this prompt' preview message (_ask_preview_in_chat) -- shown before a
    task-matched message is actually sent, so the user sees what's about to go out and why.
    Real live report, 2026-09-16: after render_welcome_html gave the welcome message real
    visual structure, the SAME feedback applied here -- this message was still going through
    render_markdown's plain bullet-list-plus-code-fence output, so it read as plain text next
    to the now much more visual welcome message. Rebuilt with the same table-based rich-text
    technique: a small teal heading, muted reasoning bullets, and the composed prompt in its
    own bordered card (monospace, matching the Keys summary's masked-value styling) instead of
    a code fence -- no border-radius, same Qt rich-text constraint as every other card in this
    UI. Bypasses render_markdown entirely, same as the welcome message -- see _add_message's
    _raw_html parameter."""
    text_color = colors.get("text", "#1c1c1c")
    subtle_color = colors.get("subtle", "#666666")
    border_color = colors.get("border", "#d0d0d0")
    teal = _brand_accent(colors.get("highlight", "#3daee9"))

    heading = (
        f'<div style="font-weight:bold;font-size:12.5px;color:{teal};margin-bottom:6px;">'
        'Why this prompt</div>'
    )
    reasoning_rows = "".join(
        f'<div style="font-size:12px;color:{subtle_color};margin:2px 0;">'
        f'&bull;&nbsp;{escape_plain_text(line)}</div>'
        for line in reasoning_lines
    )
    prompt_card = (
        '<table border="0" cellspacing="0" cellpadding="0" width="100%" '
        'style="margin:10px 0;"><tr>'
        f'<td style="border:1px solid {border_color};padding:8px 10px;'
        f'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;color:{text_color};">'
        f'{escape_plain_text(composed_prompt)}</td></tr></table>'
    )
    cta = (
        f'<div style="font-size:11.5px;font-style:italic;color:{subtle_color};">'
        'Reply to send this, or tell me what to change.</div>'
    )
    return heading + reasoning_rows + prompt_card + cta


def render_refinement_html(recommendations, colors):
    """Prompt-refinement recommendations ('Suggested rewordings'), shown in-chat instead of
    the old boxed QGroupBox panel -- design proposal, 2026-09-16 (Dateline Dock artifact),
    real live report: "the recommendation text as button style like the welcome message".
    Same bordered-card technique as render_welcome_html's starter prompts: each
    recommendation is a card with its label, the refined prompt itself as a clickable
    cartogen://refine/{index} link (chat_tab_widget.py's _on_refinement_card_clicked fills the
    input box with it, same click-to-edit pattern as a starter prompt -- never auto-sends,
    matching docs/archive/PROMPT_REFINEMENT_LAYER_SPEC.md §6's "never send a rewritten prompt
    the user hasn't seen"), and the rationale below in muted text. `recommendations` is the
    raw list prompt_refiner.refine() returns -- each a dict with id/label/refined_prompt/
    rationale keys."""
    text_color = colors.get("text", "#1c1c1c")
    subtle_color = colors.get("subtle", "#666666")
    border_color = colors.get("border", "#d0d0d0")
    teal = _brand_accent(colors.get("highlight", "#3daee9"))

    heading = (
        f'<div style="font-weight:bold;font-size:12.5px;color:{teal};margin-bottom:6px;">'
        'Suggested rewordings</div>'
    )
    hint = (
        f'<div style="font-size:11.5px;color:{subtle_color};margin-bottom:8px;">'
        'Click one to edit it in the input box, or just send your own wording as typed.</div>'
    )
    cards = []
    for i, rec in enumerate(recommendations):
        label = rec.get("label") or rec.get("id", "")
        prompt = rec.get("refined_prompt", "")
        rationale = rec.get("rationale", "")
        rationale_html = (
            f'<div style="font-size:11px;color:{subtle_color};margin-top:4px;">'
            f'{escape_plain_text(rationale)}</div>'
        ) if rationale else ""
        cards.append(
            '<table border="0" cellspacing="0" cellpadding="0" width="100%" '
            'style="margin-bottom:8px;"><tr>'
            f'<td style="border:1px solid {border_color};padding:8px 10px;">'
            f'<div style="font-size:11px;font-weight:bold;color:{text_color};margin-bottom:3px;">'
            f'{escape_plain_text(label)}</div>'
            f'<a href="cartogen://refine/{i}" style="text-decoration:none;color:{text_color};'
            f'font-size:12px;">{escape_plain_text(prompt)}</a>'
            f'{rationale_html}'
            '</td></tr></table>'
        )
    return heading + hint + "".join(cards)


def summarize_tool_result(result, limit=400):
    """One readable line for the result of a tool run confirmed from a card. Pure.

    rc11 smoke test (#124): after "Apply edit" the chat showed the raw Python dict, e.g.
    "{'success': True, 'layer_name': ..., 'fields': {...}}". An error or a message is shown as text; anything else lists
    the useful keys, never the whole structure."""
    if not isinstance(result, dict):
        text = str(result)
        return text if len(text) <= limit else text[:limit].rstrip() + " ..."
    if result.get("error"):
        return "failed: " + str(result["error"])[:limit]
    parts = []
    if result.get("message"):
        parts.append(str(result["message"]))
    elif result.get("success") is True:
        parts.append("completed")
    for key in ("layer_name", "layer_created", "output_path", "path", "feature_count", "features_updated"):
        if result.get(key) not in (None, ""):
            parts.append(f"{key.replace('_', ' ')}: {result[key]}")
    if result.get("egress_override_note"):
        parts.append(str(result["egress_override_note"]))
    text = "; ".join(parts) or "completed"
    return text if len(text) <= limit else text[:limit].rstrip() + " ..."


def render_safety_gate_html(task, colors):
    """Inline destructive-action confirmation card -- Broadsheet redesign Phase 2, mockup
    state 1f (the inline-card treatment, chosen over 1g's heavier bottom-anchored locking
    sheet). Same bordered-card/`<a>`-as-button technique render_refinement_html and
    render_welcome_html's starter prompts already use, styled with the `danger`/`danger_bg`
    tokens derive_bubble_colors added for exactly this -- magenta reserved for the one
    thing that mutates data, nothing else in this app uses these two colors.

    `task` is a task_manager.py task dict that has `pending_tool`/`pending_args` set (see
    agent_orchestrator.py's `_real_execute_tool` PREVIEW_REQUIRED handling) -- this function only reads
    it, never mutates it. The Confirm/Cancel links are `cartogen://confirm/{task_id}` and
    `cartogen://cancel/{task_id}`; chat_tab_widget.py's `_on_step_anchor_clicked` resolves
    the task by id and calls `_resolve_pending_confirmation` -- the exact same deterministic
    `agent._real_execute_tool(pending_tool, pending_args, user_confirmed=True)` path a
    plain-text "Confirm" reply already uses (this phase only adds a second, clickable entry
    point to that already-correct mechanism, not a new one).

    Best-effort on `pending_args`' shape: `layer_name`/`new_field` are shown as a labeled
    summary row WHEN present, since they're the two fields field_calculator (the common
    PREVIEW_REQUIRED source today) always includes -- but this renderer does not assume any
    tool-specific shape beyond that, so a future destructive tool with a different argument
    shape still renders sensibly (rationale + code snippet + the two action links)."""
    text_color = colors.get("text", "#1c1c1c")
    subtle_color = colors.get("subtle", "#666666")
    danger = colors.get("danger", "#A3255A")
    danger_bg = colors.get("danger_bg", "#f7e6ee")

    task_id = task.get("id", "")
    rationale = task.get("rationale", "")
    code_snippet = task.get("code_snippet", "")
    pending_args = task.get("pending_args") or {}
    layer_name = pending_args.get("layer_name")
    new_field = pending_args.get("new_field")

    heading = (
        f'<div style="font-weight:bold;font-size:11px;letter-spacing:0.04em;color:{danger};'
        'margin-bottom:6px;">&#128737;&nbsp;CONFIRMATION REQUIRED</div>'
    )
    summary_rows = []
    if layer_name:
        summary_rows.append(("Layer", layer_name))
    if new_field:
        summary_rows.append(("Adds field", new_field))
    summary_html = "".join(
        f'<div style="font-size:11.5px;color:{text_color};margin:2px 0;">'
        f'<span style="color:{subtle_color};">{escape_plain_text(label)}:</span>&nbsp;'
        f'<b>{escape_plain_text(str(value))}</b></div>'
        for label, value in summary_rows
    )
    rationale_html = (
        f'<div style="font-size:11.5px;color:{text_color};margin:6px 0;">'
        f'{escape_plain_text(rationale)}</div>'
    ) if rationale else ""
    code_html = (
        '<table border="0" cellspacing="0" cellpadding="0" width="100%" style="margin:6px 0;"><tr>'
        f'<td style="border:1px solid {danger};padding:8px 10px;'
        f'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:{text_color};">'
        f'{escape_plain_text(code_snippet)}</td></tr></table>'
    ) if code_snippet else ""
    # A real gap between the two links, not CSS margin -- Qt's rich-text engine doesn't
    # reliably honor margin on inline-block <a> tags (confirmed live: "Apply edit" and
    # "Cancel" rendered touching with zero gap despite margin-right:8px). An explicit
    # non-breaking-space run is the same &nbsp;-for-spacing workaround this file already
    # relies on elsewhere (render_markdown's list indentation, render_tool_step_html's
    # icon gap) for exactly this class of Qt rich-text CSS limitation.
    # rc11 smoke test (#124): the cloud-data override card said "Apply edit", which reads as a data edit. It is a decision
    # to let protected data leave the machine, so say that.
    confirm_label = "Send to cloud once" if task.get("egress_override") else "Apply edit"
    actions = (
        f'<a href="cartogen://confirm/{task_id}" style="text-decoration:none;'
        f'display:inline-block;padding:5px 14px;'
        f'background-color:{danger};color:#ffffff;font-weight:600;font-size:12px;">'
        f'&#10003;&nbsp;{confirm_label}</a>'
        '&nbsp;&nbsp;&nbsp;'
        f'<a href="cartogen://cancel/{task_id}" style="text-decoration:none;'
        f'display:inline-block;padding:5px 14px;border:1px solid {subtle_color};'
        f'color:{text_color};font-size:12px;">Cancel</a>'
    )
    card = (
        '<table border="0" cellspacing="0" cellpadding="0" width="100%" '
        f'style="margin:10px 0;background-color:{danger_bg};"><tr>'
        f'<td style="border:1px solid {danger};padding:10px 12px;">'
        f'{heading}{summary_html}{rationale_html}{code_html}{actions}'
        '</td></tr></table>'
    )
    return card


# Braille-dot spinner frames for the one task currently IN_PROGRESS in an in-chat plan
# card (render_task_progress_html) -- cycled by chat_tab_widget._tick_plan_spinner on a
# QTimer. Chosen over a rotating clock/hourglass emoji: renders as a single quiet glyph
# at any font size instead of a cartoonish icon, matching this app's "elegant but
# professional" bar for in-chat motion (2026-09-17, replacing the sticky plan-strip
# widget above the chat -- see plan_strip_widget.py's own docstring for what this
# superseded and why: a separately-docked progress bar read as a debug-panel leftover,
# and the user asked for task progress to live inside the conversation itself instead).
PLAN_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

_PLAN_TASK_STATUS_STYLE = {
    # (glyph, color_key) -- color_key is resolved against `colors` at render time so every
    # row stays theme-aware instead of a hardcoded hex per status.
    "DONE": ("&#10003;", "subtle"),
    "FAILED": ("&#10007;", "danger"),
    "TODO": ("&#8211;", "subtle"),
}


def render_task_progress_html(plan_data, colors, spinner_frame=0):
    """In-chat plan/progress card -- supersedes plan_strip_widget.py's always-docked strip
    above the chat (2026-09-17 redesign: the user found a separate pinned panel with
    animation on it felt like a debug overlay, and asked for task progress to render
    inside the conversation instead, with the current task animated and the list settling
    into place as steps complete). Lives in the message log like any other block, updated
    in place while the plan it names is still the active one (see chat_tab_widget.py's
    _on_live_plan_updated/_tick_plan_spinner, which reuse the same tracked-cursor-span
    technique render_tool_steps_toggle_html's click-to-expand already relies on) --
    once a NEW plan starts, the old card is left as a frozen record in scrollback rather
    than overwritten, so plan history is just "scroll up" instead of a separate dropdown
    (plan_strip_widget.py needed its own plan_history_combo for exactly this; here the
    chat log already provides it for free).

    A DONE task renders as a single condensed line (checkmark + description) so finished
    steps visually "settle" into a quiet trail; the one IN_PROGRESS task is the only line
    that's bold/accented and carries the animated spinner glyph; TODO tasks stay dim.
    `pending_tool` tasks (waiting on the user via the separate safety-gate card, see
    render_safety_gate_html) get a small "needs you" chip here too, so the plan card
    doesn't silently look "stuck" while the real confirmation card is what's asking.

    Clicking any row opens the Task Inspector dialog exactly like the old strip's list
    did (cartogen://task/{id}, resolved by chat_tab_widget._on_step_anchor_clicked); a
    small "Clear plan" link at the bottom is cartogen://clearplan."""
    subtle_color = colors.get("subtle", "#666666")
    accent = colors.get("accent", "#0b6ea3")
    danger = colors.get("danger", "#A3255A")
    border = colors.get("border", "#d0d0d0")

    title = plan_data.get("title", "")
    tasks = plan_data.get("tasks", [])
    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "DONE")

    heading = (
        f'<div style="font-size:11px;font-weight:bold;letter-spacing:0.04em;color:{subtle_color};'
        f'text-transform:uppercase;margin-bottom:4px;">&#128203;&nbsp;{escape_plain_text(title) or "Plan"}'
        f'&nbsp;&middot;&nbsp;{done}/{total} done</div>'
    )

    rows = []
    for task in tasks:
        status = task.get("status", "TODO")
        desc = escape_plain_text(task.get("description", ""))
        task_id = task.get("id", "")
        href = f"cartogen://task/{task_id}"
        chip = ""
        if task.get("pending_tool"):
            chip = (
                f'<span style="background-color:{danger};color:#ffffff;border-radius:2px;'
                'padding:0 5px;font-size:9.5px;margin-left:6px;">needs you</span>'
            )
        if status == "IN_PROGRESS":
            glyph = PLAN_SPINNER_FRAMES[spinner_frame % len(PLAN_SPINNER_FRAMES)]
            rows.append(
                f'<div style="font-size:12px;color:{accent};font-weight:600;margin:3px 0;">'
                f'<a href="{href}" style="text-decoration:none;color:{accent};">'
                f'{glyph}&nbsp;{desc}</a>{chip}</div>'
            )
        elif status == "DONE":
            glyph, color_key = _PLAN_TASK_STATUS_STYLE["DONE"]
            rows.append(
                f'<div style="font-size:11px;color:{colors.get(color_key, subtle_color)};margin:1px 0;">'
                f'<a href="{href}" style="text-decoration:none;color:inherit;">{glyph}&nbsp;{desc}</a></div>'
            )
        elif status == "FAILED":
            glyph, color_key = _PLAN_TASK_STATUS_STYLE["FAILED"]
            rows.append(
                f'<div style="font-size:11.5px;color:{colors.get(color_key, danger)};margin:2px 0;">'
                f'<a href="{href}" style="text-decoration:none;color:inherit;">{glyph}&nbsp;{desc}</a>{chip}</div>'
            )
        else:
            glyph, color_key = _PLAN_TASK_STATUS_STYLE["TODO"]
            rows.append(
                f'<div style="font-size:11.5px;color:{colors.get(color_key, subtle_color)};margin:2px 0;">'
                f'<a href="{href}" style="text-decoration:none;color:inherit;">{glyph}&nbsp;{desc}</a>{chip}</div>'
            )

    footer = (
        f'<div style="margin-top:4px;text-align:right;">'
        f'<a href="cartogen://clearplan" style="font-size:10px;color:{subtle_color};">Clear plan</a></div>'
    )

    card = (
        '<table border="0" cellspacing="0" cellpadding="0" width="100%" style="margin:8px 0;"><tr>'
        f'<td style="border-left:2px solid {border};padding:4px 0 4px 10px;">'
        f'{heading}{"".join(rows)}{footer}'
        '</td></tr></table>'
    )
    return card


def render_tool_steps_toggle_html(steps, block_id, colors, expanded):
    """One compact summary line for an entire turn's tool calls, replacing the old
    one-line-per-event approach (real user feedback 2026-09-12: "too much visual space", "too
    much raw detail", "general visual noise"). `steps` is a list of {"name","status","error"}
    dicts for TERMINAL statuses only ("running" never reaches here -- see
    chat_tab_widget._add_tool_step, which redirects live "running" text to the status label
    instead). `block_id` is baked into the toggle anchor's href so multiple summary blocks in
    the same scrollback toggle independently (chat_tab_widget._on_step_anchor_clicked looks it
    up). Collapsed (expanded=False) shows one line with friendly names comma-joined; expanded
    shows one line per step with a status icon, still no raw error text (that's always-visible
    separately -- see render_tool_steps_failure_details_html, never gated behind this toggle)."""
    color = colors.get("subtle", "#808080")
    n = len(steps)
    plural = "" if n == 1 else "s"
    href = f"cartogen://steps/{block_id}"
    if not expanded:
        names = ", ".join(friendly_tool_name(s["name"]) for s in steps)
        return (
            f'<div style="font-size:11px;color:{color};margin:2px 0;">'
            f'&#128295;&nbsp;{n} tool call{plural} &middot; {names}'
            f'&nbsp;<a href="{href}">Details&nbsp;&#9662;</a></div>'
        )
    lines = [
        f'<div style="font-size:11px;color:{color};margin:2px 0;">'
        f'&#128295;&nbsp;{n} tool call{plural}'
        f'&nbsp;<a href="{href}">Hide details&nbsp;&#9652;</a></div>'
    ]
    for s in steps:
        icon = _STEP_STATUS.get(s["status"], _STEP_STATUS["done"])["icon"]
        friendly = friendly_tool_name(s["name"])
        lines.append(
            f'<div style="font-size:11px;color:{color};margin:1px 0 1px 16px;">'
            f'{icon}&nbsp;{friendly}</div>'
        )
    return "".join(lines)


def render_tool_steps_failure_details_html(steps, colors):
    """Full error text for any FAILED step in `steps`, always rendered regardless of the toggle
    above's collapsed/expanded state -- failures are load-bearing information the user needs to
    see, not detail they have to opt into (matching this codebase's existing no-silent-failures
    posture elsewhere: the false-success narrative backstop, SECURITY.md's disclosure
    conventions). Returns "" (append nothing) when nothing failed."""
    failed = [s for s in steps if s.get("status") == "failed"]
    if not failed:
        return ""
    color = colors.get("text", "#000000")
    icon = _STEP_STATUS["failed"]["icon"]
    parts = []
    for s in failed:
        friendly = friendly_tool_name(s["name"])
        text = f"Failed: {friendly}"
        if s.get("error"):
            text += f" &mdash; {escape_plain_text(str(s['error']))}"
        parts.append(
            f'<div style="font-size:11px;color:{color};margin:1px 0 1px 8px;">'
            f'{icon}&nbsp;{text}</div>'
        )
    return "".join(parts)


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
    # Broadsheet redesign, 2026-09-16: magenta reserved for the one thing that mutates data.
    # #successButton is the Activity tab's "Confirm and Apply Edit" button -- the actual
    # destructive-edit confirm action, not a generic "success" -- so it now takes the same
    # danger token dangerButton uses, just filled instead of outlined (the stronger of the
    # two treatments, since it's the one button that actually executes a data mutation).
    danger = _brand_danger(palette_dict.get("highlight", "#3daee9"))
    danger_hover = _blend_hex(danger, "#000000", 0.12)
    danger_pressed = _blend_hex(danger, "#000000", 0.22)
    danger_bg = _blend_hex(window, danger, 0.12)

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
    color: {danger};
    border: 1px solid {danger};
    font-weight: 500;
}}
QPushButton#dangerButton:hover {{
    background-color: {danger_bg};
}}
QPushButton#dangerButton:disabled {{
    background-color: transparent;
    color: {subtle};
    border-color: {border};
}}
QPushButton#successButton {{
    background-color: {danger};
    color: {highlighted_text};
    font-weight: 600;
}}
QPushButton#successButton:hover {{
    background-color: {danger_hover};
}}
QPushButton#successButton:pressed {{
    background-color: {danger_pressed};
}}
QPushButton#successButton:disabled {{
    background-color: {border};
    color: {subtle};
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
QPushButton#providerPill {{
    background-color: transparent;
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 6px 10px;
    font-size: 11px;
    font-weight: 600;
    text-align: left;
}}
QPushButton#providerPill:hover {{
    background-color: {alt_base};
}}
QPushButton#providerPill:checked {{
    background-color: {base};
    color: {highlight};
    border: 1px solid {highlight};
}}
QPushButton#linkButton {{
    background-color: transparent;
    color: {highlight};
    border: none;
    padding: 0;
    font-size: 11px;
    font-weight: 600;
    text-decoration: underline;
}}
QPushButton#linkButton:hover {{
    color: {highlight_hover};
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
