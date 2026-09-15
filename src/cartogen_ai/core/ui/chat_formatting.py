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
    # cartogen:// alongside https?:// -- this app's own internal anchor scheme (see
    # chat_tab_widget.py's _on_step_anchor_clicked), used so markdown-authored content like
    # the welcome message's starter prompts can link to an in-app action (fill the input box)
    # instead of only ever linking out to the web.
    text = re.sub(r'\[([^\]\[]+)\]\(((?:https?|cartogen)://[^\s)]+)\)', r'<a href="\2">\1</a>', text)

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
            "subtle": "#666666", "border": "#d0d0d0", "accent": "#0b6ea3",
        }
    window = palette_dict.get("window", "#f0f0f0")
    highlight = _brand_accent(palette_dict.get("highlight", "#3daee9"))
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
