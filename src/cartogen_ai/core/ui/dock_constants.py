# -*- coding: utf-8 -*-
"""Data shared across dock_widget.py, chat_tab_widget.py, and help_tab_widget.py.
Pulled out (rather than one of those modules importing from another) so none of
the three tab modules has to import from dock_widget.py itself -- dock_widget.py
imports all three, so any of them importing back from it would be circular."""

PROVIDER_CHOICES = [
    ("OpenRouter", "openrouter"),
    ("Gemini", "gemini"),
    ("Ollama", "ollama"),
    ("OpenAI", "openai"),
    ("Claude", "claude"),
]

# Module-level (not a local in some widget's init_ui) so the Help tab can list the same
# example prompts as the Chat tab's quick suggestion chips without a second, driftable
# copy of the text.
QUICK_SUGGESTION_CHIPS = [
    ("💡 List layers", "List all layers in the project."),
    ("💡 Calculate area", "Calculate the area for the active layer."),
    ("💡 Style by attribute", "Suggest and apply a colorblind-safe style for the active layer based on its attributes."),
    ("💡 Style raster layer", "Apply a color ramp or contrast stretch to the active raster layer so it isn't flat/unstretched."),
    ("💡 Export to GeoJSON", "Export the active layer to GeoJSON."),
]
