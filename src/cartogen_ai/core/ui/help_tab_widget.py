# -*- coding: utf-8 -*-
"""Help tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). No live state -- lowest-risk of the
three tabs to split out, per that plan's step 4."""

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTextBrowser

from .dock_constants import PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS


def _build_help_html(version=None):
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
    version_line = f"<p style='color:gray;'>Version {version}</p>" if version else ""
    return f"""
    <h3>🗺️ Cartogen AI — Help</h3>
    {version_line}
    <p>Ask questions or give instructions in plain English in the <b>Chat</b> tab. The assistant
    can inspect your loaded layers, run real PyQGIS/Processing operations, and build maps for
    you — every action it takes is visible in the <b>Activity</b> tab.</p>

    <h4>Getting started</h4>
    <ol>
    <li>Open <b>Settings</b> (top-right gear icon) and pick a provider and enter its API key.</li>
    <li>Type a request in the chat box and press Enter (Shift+Enter for a new line).</li>
    <li>For anything that edits or deletes data, you'll be asked to confirm in the
    <b>Activity</b> tab before it actually runs.</li>
    </ol>

    <h4>Before your message is sent</h4>
    <p>Some requests match a task in the built-in Humanitarian Mapping Task Register (791 tasks
    across 35 sectors, aligned to DG ECHO-style workflows). When one does, the assistant may ask
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

    <h4>Safety</h4>
    <p>Destructive actions (removing a layer, changing attribute values) always require an
    explicit click on <b>Confirm and Apply Edit</b> in the Activity tab — the AI
    cannot apply them on its own.</p>

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
    <li>Full walkthrough, all 131 tools, and the security threat model:
    <code>docs/USER_GUIDE.md</code>, <code>docs/TOOLS_REFERENCE.md</code>, and
    <code>SECURITY.md</code> in the plugin's source repository.</li>
    </ul>
    """


class HelpTabWidget(QWidget):
    def __init__(self, parent=None, version=None):
        super().__init__(parent)
        help_layout = QVBoxLayout(self)
        help_layout.setContentsMargins(4, 4, 4, 4)
        help_browser = QTextBrowser()
        help_browser.setOpenExternalLinks(True)
        help_browser.setHtml(_build_help_html(version=version))
        help_layout.addWidget(help_browser)
