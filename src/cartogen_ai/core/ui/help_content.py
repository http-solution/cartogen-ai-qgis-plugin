# -*- coding: utf-8 -*-
"""Help content for the Help dialog, kept Qt-free so tests can read it (help_tab_widget.py only wraps it in a widget).

The "What's new" and humanitarian-tool sections come from core/release_notes.py, which must be updated on every version bump
(tests/test_release_docs_in_sync.py enforces it). Tool, task and section counts are read from the live registries, not typed in.
"""
from .. import release_notes
from .dock_constants import PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS


def _registry_counts():
    """(tools, tasks, sections), each None when it cannot be read -- the text then drops the number rather than stating a wrong one."""
    tools = tasks = sections = None
    try:
        from ..agent.tools.registry import TOOL_REGISTRY
        from ..agent import tools as _load_all  # noqa: F401  (importing the package registers every tool)
        tools = len(TOOL_REGISTRY) or None
    except Exception:
        pass
    try:
        import json
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent", "task_register.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        tasks, sections = len(data), len({t.get("cat") for t in data})
    except Exception:
        pass
    return tools, tasks, sections


def build_help_html(version=None, tool_count=None, task_count=None, section_count=None):
    """Static help content -- provider list and example prompts are built from the same
    source data as the rest of the UI (PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS) rather
    than a second, driftable copy of the text.

    The "Before your message is sent" and "Something not working?" sections were added
    2026-08-31 -- until then this file had no mention of the prompt preview panel, the
    requirement/slot gate, the output-contract follow-up, or any troubleshooting content,
    despite docs/USER_GUIDE.md claiming this tab mirrors it. Still a static string, not
    literally generated from USER_GUIDE.md -- keep the two in sync by hand when either
    changes; the shared PROVIDER_CHOICES/QUICK_SUGGESTION_CHIPS above are the part that
    genuinely can't drift.

    version, when given, renders as a line under the title -- a second, redundant point of
    visibility alongside the disabled version QAction in the Plugins menu (plugin_main.py),
    per the 2026-09-12 real-session user report asking for version info to be discoverable.
    """
    provider_items = "".join(f"<li>{label}</li>" for label, _ in PROVIDER_CHOICES)
    example_items = "".join(
        f"<li>{template}</li>" for _, template in QUICK_SUGGESTION_CHIPS
    )
    counts = _registry_counts()
    tool_count = counts[0] if tool_count is None else tool_count
    task_count = counts[1] if task_count is None else task_count
    section_count = counts[2] if section_count is None else section_count
    tool_phrase = f"all {tool_count} tools" if tool_count else "every tool"
    task_phrase = f"{task_count} tasks across {section_count} sections," if task_count else "hundreds of tasks,"
    whats_new_items = "".join(f"<li><b>{title}</b> — {text}</li>" for title, text in release_notes.WHATS_NEW_ITEMS)
    workflow_items = "".join(
        "<li><b>{}</b>: {}</li>".format(title, ", ".join(
            f"<code>{t}</code>" + (" <i>(new)</i>" if release_notes.tool_is_new(t) else "") for t in tools))
        for title, tools in release_notes.HUMANITARIAN_WORKFLOWS)
    version_line = f"<p style='color:gray;'>Version {version}</p>" if version else ""
    # rc22 smoke V7: the sentence about (new) marks was shown although no tool carried one (no tool was added in the last two
    # releases), so the Help promised marks that were never there. It appears only when at least one mark is shown.
    any_new = any(release_notes.tool_is_new(t) for _title, tools in release_notes.HUMANITARIAN_WORKFLOWS for t in tools)
    new_note = ("<i>(new)</i> marks tools added in the last two releases; they have been tested in CI, not by hand.\n    "
                if any_new else "")
    return f"""
    <h3>🗺️ Cartogen AI — Help</h3>
    {version_line}
    <h4>What's new in {release_notes.WHATS_NEW_VERSION}</h4>
    <ul>{whats_new_items}</ul>
    <p>Ask questions or give instructions in plain English in the chat box. The assistant
    can inspect your loaded layers, run real PyQGIS/Processing operations, and build maps for
    you — every step of a multi-step request shows live in the <b>plan strip</b> pinned above
    the chat thread, no separate tab to switch to.</p>

    <h4>Getting started</h4>
    <ol>
    <li>Open <b>Settings</b> (top-right gear icon) and pick a provider and enter its API key.</li>
    <li>Type a request in the chat box and press Enter (Shift+Enter for a new line).</li>
    <li>For anything that edits or deletes data, you'll see a confirmation card right in the
    chat before it actually runs.</li>
    </ol>

    <h4>Before your message is sent</h4>
    <p>Some requests match a task in the built-in Humanitarian Mapping Task Register ({task_phrase}
    aligned to DG ECHO-style workflows). When one does, the assistant may ask
    you something in the chat before actually sending anything — just reply normally, like any
    other message:</p>
    <ul>
    <li><b>A question, only if something genuinely can't be guessed</b> — for example, which
    hazard or facility type. There's no safe default for these, so the assistant asks once
    rather than risk confidently wrong output. Type the missing detail and hit Send.</li>
    <li><b>A preview of the exact prompt about to be sent</b> — showing any values assumed on
    your behalf and what each attached file will be read as, with the reasoning behind it. Reply
    to confirm and send it as shown, tell the assistant what to change (that becomes what
    actually gets sent, with no enrichment), or reply "cancel" to abandon it. Turn this off in
    Settings ("Show the prompt and reasoning before sending") if you'd rather it never appear.</li>
    </ul>
    <p>If a task promises a specific deliverable (a dashboard, an export, a chart) and the
    answer comes back without it, you'll see one automatic follow-up asking for it — never
    more than one, and always disclosed in the chat rather than happening silently.</p>

    <h4>Supported AI providers</h4>
    <ul>{provider_items}</ul>
    <p>OpenRouter (openrouter.ai) offers a genuinely free tier covering many models.
    Ollama runs fully locally, no key needed.</p>

    <h4>Example things to ask</h4>
    <ul>{example_items}
    <li>"Create a buffer 500m around the hospital layer."</li>
    <li>"Map all the foreign embassies in Jordan."</li>
    <li>"Diagnose topology problems in the parcels layer."</li>
    <li>"Map population affected by flooding in Aleppo." <i>(humanitarian task register)</i></li>
    </ul>

    <h4>Humanitarian tools</h4>
    <p>Tools by workflow. Ask in plain language — you don't need the tool names. Where a number is a
    judgement call (a threshold, weights, a budget) the tool asks you for it and repeats it in the result.
    {new_note}Details: <code>docs/HUMANITARIAN_TOOLS_CATALOGUE.md</code>.</p>
    <ul>{workflow_items}</ul>

    <h4>Layer context</h4>
    <p>Every loaded layer's schema is visible to the model by default, so it can answer
    questions without you naming every layer. Click the <b>layers icon</b> next to the input
    box to choose exactly which layers it can see for a question — a layer already tagged
    RESTRICTED/SENSITIVE defaults unchecked. Only a schema and a sample of rows are ever sent,
    never a whole table.</p>

    <h4>Safety</h4>
    <p>Destructive actions (removing a layer, changing attribute values) always require an
    explicit confirmation — click <b>Apply edit</b> on the card that appears in the chat, click
    <b>Confirm and Apply Edit</b> in that task's inspector (click its row in the plan strip),
    or just reply "Confirm" — the AI cannot apply them on its own.</p>

    <h4>Something not working?</h4>
    <ul>
    <li><b>"No API key configured" / an authentication error</b> — open Settings and check the
    key for your selected provider, or switch to Ollama to run fully locally with no key.</li>
    <li><b>Rate limited or quota errors</b> — wait a moment and try again, or switch models or
    providers in Settings.</li>
    <li><b>A file attachment isn't being read</b> — PDF/Word/Excel parsing needs a few optional
    Python packages; everything else works without them (see the README's "Optional
    dependencies" section for how to install them).</li>
    <li><b>Coordinates from a CSV/Excel load look wrong</b> — check that longitude and latitude
    columns are in that order and use decimal degrees, not degrees-minutes-seconds.</li>
    <li>Full walkthrough, {tool_phrase}, and the security threat model:
    <code>docs/USER_GUIDE.md</code>, <code>docs/TOOLS_REFERENCE.md</code>, and
    <code>SECURITY.md</code> in the plugin's source repository.</li>
    </ul>
    """
