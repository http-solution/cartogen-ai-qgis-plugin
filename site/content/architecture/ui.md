---
description: The dock panel, dialogs and pure helpers that make up Cartogen AI's interface.
---
All UI code lives in `core/ui/` and runs on the GUI thread. The dock is one continuous scroll, not tabs: a sticky **plan strip** for the active multi-step task sits above the chat thread, so you never switch views mid-conversation.

## Components

| Module | Role |
|---|---|
| `dock_widget.py` (`CartogenAiDockWidget`) | The dock: provider dropdown, **Memory** and **Settings** buttons, chat, plan strip, input row. Starts agent turns through `task_runner`. |
| `chat_tab_widget.py`, `chat_view_presenter.py`, `chat_input_controller.py` | The chat view, scroll-back trimming, input handling and the confirmation cards. |
| `settings_dialog.py` | Provider, keys, model, privacy toggles, limits, evidence and trace switches, gate modes. |
| `memory_dialog.py` | Stored memory: notes, learned preferences, export, clear. Also deletes the saved chat. |
| `layer_sensitivity_dialog.py`, `layer_context_picker_dialog.py` | Tag layers with a sensitivity level; pick which layers form the context for a question. |
| `account_dialog.py` | The hosted-account client (create account, sign in); needs a deployed service, which does not exist yet. |
| `onboarding_dialog.py`, `help_tab_widget.py`, `help_content.py` | First-run welcome and the Help window (provider list, tips, examples, version, "What's new"). Help text comes from the same data as the user guide and from `core/release_notes.py`. |
| `task_inspector_dialog.py` | Inspect a task's contract and plan. |
| `canvas_highlight.py` | Highlight features on the canvas (and remove the overlays). |
| `attachments.py` | Classify attached files and route them to the right tool. |
| `local_answers.py` | Requests answered from the open project with **no model call** (for example a bare "list the layers"). |
| `dialog_messages.py` | A `QgsMessageBar` inside dialogs for notices; questions that need an answer still use a pop-up. |
| `theme.py`, `icons.py`, `dock_constants.py`, `reply_vocab.py` | Theme integration with QGIS's palette, SVG icons, constants and the vocabulary for recognising "yes / cancel / proceed". |

## Qt-free by design

`chat_formatting.py` (Markdown to the chat's HTML, tool-step cards, safety-gate card, welcome page) and the string-generating half of `icons.py` import neither Qt nor QGIS. That makes them unit-testable in the plain test job. New pure logic should follow that pattern.

## Replies are untrusted text

Replies are rendered by the plugin, and a reply (or a layer attribute it quoted) could try to forge an internal link such as an Apply-edit link. Since rc29 only four chip links can be created (action, export, prompt, zoom), a quote, angle bracket or space in a link address is encoded, and a file link opens only an existing file of a type the tools write.

## Hand-check what tests cannot see

Anything with Qt widget wiring, layout or paint behaviour needs a real QGIS session. CI runs live tests inside QGIS 4.2.2 for widget construction and behaviour, and the project's practice is to build the real widget headless and look at a rendered screenshot, but the on-screen look in a user's desktop is covered only by the manual [live tests](@development/live-testing).
