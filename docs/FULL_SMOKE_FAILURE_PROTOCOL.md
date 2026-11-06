# Failure protocol - what to capture the moment a row fails or looks wrong

Read this once before row 1. It adds to EVIDENCE_HOWTO.txt (which says how the routine evidence is collected); it does not replace it.
"Pass" or "Fail" with no file behind it does not count: 5_check_evidence.py marks such a row **unverified**.

## 1. What every row needs

| Outcome | Capture | Where it goes |
|---|---|---|
| **Pass** | `snap('<row id>')` in the QGIS Python console, plus ONE full-screen screenshot (whole monitor, not only the QGIS window) showing the final state and the Windows clock | `results\evidence\<row>\` and `results\screens\<row>-pass.png` |
| **Partial** | Everything in the Fail table, and say in the notes which part worked | as Fail |
| **Fail** or anything odd (a dialog, a freeze, a wrong number, a missing layer, a traceback) | Everything in the Fail table below, **before** you close the dialog, retry, or undo | as below |

## 2. Fail table - do these in this order, right away

| # | Capture | How (Windows, QGIS 4.2) | Save as |
|---|---|---|---|
| 1 | **Full-screen screenshot with the clock visible**: the error text, the layer panel, the chat, and the taskbar clock in one picture | Win+PrtScn (saves to Pictures\Screenshots) or Snipping Tool, full screen. If the taskbar is hidden, open the Start menu first so the clock shows | `results\screens\<row>-FAIL-<hhmm>.png` |
| 2 | **The plugin's record of the failing request** | In the QGIS Python console type `snap('<row id>')` straight away (the console, never the chat) | `results\evidence\<row>\` (written for you) |
| 3 | **The log around the failure time** | `snap` saves the CartogenAI log. Also open View > Panels > Log Messages, set the tab to Python and to CartogenAI, select all, copy into a text file | `results\logs\<row>-logmessages.txt` |
| 4 | **Python traceback** if one is shown anywhere (error bar, console, a dialog) | Copy the whole text, not a photo. Include the first and last line | `results\logs\<row>-traceback.txt` |
| 5 | **Network evidence** | The plugin does not log raw prompts, replies or tool arguments (by design, privacy). What exists: the HTTP status and provider named in the CartogenAI log lines, and `plugin_evidence` from `snap`. If your QGIS has View > Panels > Network Logger, switch it on BEFORE the row, and screenshot its rows for the failing request. If it is not there, write "no Network Logger panel" in the notes. Do not paste keys or personal data | `results\screens\<row>-network.png` |
| 6 | **The input that triggered it** | Copy the exact input file(s) from `3_test_files` and the project you were in (File > Save As first, into `results\outputs\<row>\`) | `results\outputs\<row>\` |
| 7 | **Partial or corrupted output** | Copy any file the row produced, even if it is empty or will not open. Note its size | `results\outputs\<row>\` |
| 8 | **Steps to reproduce** | In the notes column of `4_RESULTS.csv`: numbered clicks and the exact text you typed in the chat, the model and connection used, and whether the project was saved | `4_RESULTS.csv` |
| 9 | **Environment line** | The grey "This computer:" line in Cartogen AI > Help (QGIS, Qt, OS, Python), copied as text | in the same notes |

Rules:
- Take the screenshot (1) first, then `snap` (2). Do not retry the request before both are saved: a retry overwrites what the plugin recorded.
- Never edit a saved file. If you could not capture something, write `not saved: <why>`. A missing item with a reason is useful; a missing item with no word is not.
- No API keys, tokens, passwords, personal addresses or real beneficiary data in anything you save. If a screenshot shows one, blur it and say so.
- A model that answered but gave a different wording is a **Partial** for the wording, not a plugin failure, when the plugin's saved record is right (see EVIDENCE_HOWTO.txt).

## 3. Diagnostic block - paste into the notes cell for every Fail

```
ROW:            <id>
BUILD:          <commit from 1_plugin\BUILD.txt> / zip SHA-256 matched: yes/no
ENVIRONMENT:    <the "This computer:" line>
MODEL/CONN:     <provider, model name, hosted or local>
STARTED FROM:   <the row's "Starts from", and whether you did that>
STEPS:          1) ... 2) ... 3) ...
EXPECTED:       <the row's Expect line, in one sentence>
ACTUAL:         <what happened, with the exact error text>
TIME (local):   <hh:mm:ss, same as the screenshot clock>
FILES SAVED:    <screens\..., evidence\..., logs\..., outputs\...>
NOT SAVED:      <item - why>
REPEATABLE:     once / every time (tried N times, only AFTER everything above was saved)
```

## 4. Hand-off

1. Send the whole `results` folder, `4_RESULTS.csv` and the `cartogen_evidence` folder (see EVIDENCE_HOWTO.txt).
2. Run `python 5_check_evidence.py` in this folder. It prints a verdict per row and names what is missing; fix what it names before sending.
3. For each Fail, open a GitHub issue in `http-solution/cartogen-ai-qgis-plugin` titled `Live smoke <row id>: <short symptom>`. Paste the diagnostic block, attach the screenshot and the log files, and label it `bug`. Do not close or edit an existing issue from a smoke run.
4. Do not mark a row Pass only because a later attempt worked. Record the first failure, then the retry as a second line.
