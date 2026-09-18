# -*- coding: utf-8 -*-
"""
Centralized Logging Infrastructure for Cartogen AI.

Routes diagnostic, warning, and error messages to QgsMessageLog when running inside QGIS,
falling back gracefully to standard Python logging / sys.stderr in headless or test environments.
"""

import sys

try:
    from qgis.core import QgsMessageLog, Qgis
    QGIS_LOG_AVAILABLE = True
except ImportError:
    QGIS_LOG_AVAILABLE = False
    class Qgis:
        Info = 0
        Warning = 1
        Critical = 2
        Success = 3

TAG = "CartogenAI"


def log_info(message: str, tag: str = TAG) -> None:
    """Logs an informational message to QgsMessageLog."""
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(str(message), tag, Qgis.Info)
            return
        except Exception:
            pass
    print(f"[{tag}] {message}", file=sys.stdout)


def log_warning(message: str, tag: str = TAG) -> None:
    """Logs a warning message to QgsMessageLog."""
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(str(message), tag, Qgis.Warning)
            return
        except Exception:
            pass
    print(f"[{tag}] WARNING: {message}", file=sys.stderr)


def log_error(message: str, tag: str = TAG) -> None:
    """Logs an error message to QgsMessageLog."""
    if QGIS_LOG_AVAILABLE:
        try:
            QgsMessageLog.logMessage(str(message), tag, Qgis.Critical)
            return
        except Exception:
            pass
    print(f"[{tag}] ERROR: {message}", file=sys.stderr)
