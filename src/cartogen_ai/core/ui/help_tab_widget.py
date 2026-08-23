# -*- coding: utf-8 -*-
"""Help tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). No live state -- lowest-risk of the
three tabs to split out, per that plan's step 4."""

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTextBrowser

from .dock_constants import PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS


def _build_help_html():
    """Static help content -- provider list and example prompts are built from the same
    source data as the rest of the UI (PROVIDER_CHOICES, QUICK_SUGGESTION_CHIPS) rather
    than a second, driftable copy of the text."""
    provider_items = "".join(f"<li>{label}</li>" for label, _ in PROVIDER_CHOICES)
    example_items = "".join(
        f"<li>{template}</li>" for _, template in QUICK_SUGGESTION_CHIPS
    )
    return f"""
    <h3>🗺️ Cartogen AI — Help</h3>
    <p>Ask questions or give instructions in plain English in the <b>Chat</b> tab. The assistant
    can inspect your loaded layers, run real PyQGIS/Processing operations, and build maps for
    you — every action it takes is visible in the <b>Tasks &amp; Notes</b> tab.</p>

    <h4>Getting started</h4>
    <ol>
    <li>Open <b>Settings</b> (top-right gear icon) and pick a provider and enter its API key.</li>
    <li>Type a request in the chat box and press Enter (Shift+Enter for a new line).</li>
    <li>For anything that edits or deletes data, you'll be asked to confirm in the
    <b>Tasks &amp; Notes</b> tab before it actually runs.</li>
    </ol>

    <h4>Supported AI providers</h4>
    <ul>{provider_items}</ul>
    <p>OpenRouter (openrouter.ai) offers a genuinely free tier covering many models.
    Ollama runs fully locally, no key needed.</p>

    <h4>Example things to ask</h4>
    <ul>{example_items}
    <li>"Create a buffer 500m around the hospital layer."</li>
    <li>"Map all the foreign embassies in Jordan."</li>
    <li>"Diagnose topology problems in the parcels layer."</li>
    </ul>

    <h4>Safety</h4>
    <p>Destructive actions (removing a layer, changing attribute values) always require an
    explicit click on <b>Confirm &amp; Apply Edit</b> in the Tasks &amp; Notes tab — the AI
    cannot apply them on its own.</p>
    """


class HelpTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        help_layout = QVBoxLayout(self)
        help_layout.setContentsMargins(4, 4, 4, 4)
        help_browser = QTextBrowser()
        help_browser.setOpenExternalLinks(True)
        help_browser.setHtml(_build_help_html())
        help_layout.addWidget(help_browser)
