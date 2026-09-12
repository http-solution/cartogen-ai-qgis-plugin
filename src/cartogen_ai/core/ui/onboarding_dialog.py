# -*- coding: utf-8 -*-
"""
Onboarding profile dialog -- a short, narrative first-use questionnaire (role/use-case, QGIS
experience level, communication style). Requested directly 2026-09-12: "introduce your self and
ask the user to select his profile type", saved to local .md files (agent/onboarding_profile.py
owns the storage; this file is presentation only).

Deliberately a static dialog, not a real LLM-driven conversational flow: onboarding has to work
before any API key is configured (it runs at first launch), so an actual "the agent asks you"
exchange would silently fail for the exact users who most need it. This gets the "introduce
itself, ask the user" feeling via narrative prose + simple pickers instead, with zero API
dependency.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QPushButton,
)

from ..agent import onboarding_profile as op
from .chat_formatting import build_dock_stylesheet
from .theme import extract_theme_palette

_INTRO_TEXT = (
    "Hi, I'm Cartogen AI -- a spatial assistant built into QGIS. I can inspect your layers, run "
    "real PyQGIS/Processing operations, and build maps from plain-language requests.\n\n"
    "It helps me tailor my answers if I know a little about how you work. This takes about 15 "
    "seconds, and you can change it anytime from Settings -> Edit My Profile -- or skip it "
    "entirely."
)


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Welcome to Cartogen AI"))
        self.resize(440, 360)

        layout = QVBoxLayout(self)

        intro = QLabel(_INTRO_TEXT)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        self.role_combo = QComboBox()
        for value, label in op.ROLE_CHOICES.items():
            self.role_combo.addItem(label, value)
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)
        form.addRow(self.tr("Role / use case:"), self.role_combo)

        self.role_other_edit = QLineEdit()
        self.role_other_edit.setPlaceholderText(self.tr("e.g. Freelance surveyor"))
        self.role_other_edit.setEnabled(False)
        form.addRow(self.tr("If Other, describe:"), self.role_other_edit)

        self.experience_combo = QComboBox()
        for value, label in op.EXPERIENCE_CHOICES.items():
            self.experience_combo.addItem(label, value)
        form.addRow(self.tr("QGIS experience:"), self.experience_combo)

        self.style_combo = QComboBox()
        for value, label in op.STYLE_CHOICES.items():
            self.style_combo.addItem(label, value)
        form.addRow(self.tr("Communication style:"), self.style_combo)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QHBoxLayout()
        self.skip_btn = QPushButton(self.tr("Skip for now"))
        self.skip_btn.setObjectName("secondaryButton")
        self.skip_btn.clicked.connect(self._on_skip)
        self.save_btn = QPushButton(self.tr("Save and continue"))
        self.save_btn.clicked.connect(self._on_save)
        buttons.addWidget(self.skip_btn)
        buttons.addStretch()
        buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)

        self.setStyleSheet(build_dock_stylesheet(extract_theme_palette()))
        self._load_existing()

    def _on_role_changed(self, _index):
        self.role_other_edit.setEnabled(self.role_combo.currentData() == "other")

    def _load_existing(self):
        """Pre-fills from the saved .md file when reopened via Settings -> Edit My Profile.
        On first-ever launch there's nothing to load yet (load_onboarding_profile() returns
        None), so the combos simply keep their natural first-item selection -- no special-casing
        needed."""
        profile = op.load_onboarding_profile()
        if profile is None:
            return
        role_idx = self.role_combo.findData(profile["role"])
        if role_idx >= 0:
            self.role_combo.setCurrentIndex(role_idx)
        self.role_other_edit.setText(profile["role_other"])
        self.role_other_edit.setEnabled(profile["role"] == "other")
        experience_idx = self.experience_combo.findData(profile["experience"])
        if experience_idx >= 0:
            self.experience_combo.setCurrentIndex(experience_idx)
        style_idx = self.style_combo.findData(profile["style"])
        if style_idx >= 0:
            self.style_combo.setCurrentIndex(style_idx)

    def _on_save(self):
        op.save_onboarding_profile(
            role=self.role_combo.currentData(),
            role_other=self.role_other_edit.text(),
            experience=self.experience_combo.currentData(),
            style=self.style_combo.currentData(),
        )
        self.accept()

    def _on_skip(self):
        # Still marks onboarding completed -- the user has SEEN the offer and chosen not to
        # fill it in; it should not ask again next launch (op.save_onboarding_profile() would
        # also mark it, but skip must do so WITHOUT writing a profile file at all).
        op.mark_onboarding_completed()
        self.reject()
