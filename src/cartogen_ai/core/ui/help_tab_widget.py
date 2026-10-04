# -*- coding: utf-8 -*-
"""Help tab, extracted from dock_widget.py's CartogenAiDockWidget
(docs/archive/DOCK_WIDGET_SPLIT_PLAN_2026-08-21.md). No live state -- lowest-risk of the
three tabs to split out, per that plan's step 4. The text itself lives in help_content.py (Qt-free, testable)."""

from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QTextBrowser

from .help_content import build_help_html as _build_help_html


class HelpTabWidget(QWidget):
    def __init__(self, parent=None, version=None):
        super().__init__(parent)
        help_layout = QVBoxLayout(self)
        help_layout.setContentsMargins(4, 4, 4, 4)
        help_browser = QTextBrowser()
        help_browser.setOpenExternalLinks(True)
        help_browser.setHtml(_build_help_html(version=version))
        help_layout.addWidget(help_browser)
