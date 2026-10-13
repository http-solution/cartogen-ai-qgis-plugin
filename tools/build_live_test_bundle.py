#!/usr/bin/env python3
"""Builds the live-test bundle zip for the current version. A tester needs no Python: README_FIRST.txt, the plugin zip, the fixtures, a prompts
page with Copy buttons (3_PROMPTS.html), and a results sheet (4_RESULTS.csv), all generated from docs/FULL_LIVE_TEST_rc37_ROWS.csv. The older
full pack and its helper ride along under extras/.

    python tools/build_live_test_bundle.py            # writes dist/cartogen_ai_live_test_<version>.zip

Standard library only. It runs plugin_upload.py first so the plugin zip inside the bundle is built from the current tree. The bundle holds only
synthetic data and public documents; it never includes credentials, API traces or run results."""
import csv
import hashlib
import html
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
GLOB_DOCS = ("SMOKE_RUN_SHEET_rc*.md",)

EXTRAS_DOCS = (
    "FULL_LIVE_TEST_rc34.md", "FULL_LIVE_TEST_rc34_ROWS.csv", "FULL_LIVE_TEST_rc34_INPUTS.sha256", "RC34_HAND_VERIFICATION_SHEET.md",
    "RC24_HAND_VERIFICATION_SHEET.md", "RELEASE_LIVE_TEST_SCENARIOS.md", "RELEASE_SMOKE_TEST.md", "LIVE_TEST_SCENARIOS.md",
    "RC22_LIVE_SMOKE_REPORT_2026-10-09.md", "RC22_RESULT_MATRIX_2026-10-09.csv", "FULL_LIVE_TEST_rc37_ROWS.csv",
)
START_HERE = {"RC37-I1", "RC37-I2", "RC37-I3", "RC37-A1", "RC37-N1", "RC37-E1", "RC37-F1", "RC37-F3"}
OPTIONAL = {"RC37-F6", "RC37-F7", "RC37-A2"}


def version():
    m = re.search(r"^version=(\S+)", (REPO / "metadata.txt").read_text(encoding="utf-8"), re.M)
    return m.group(1)


def read_rows():
    with open(DOCS / "FULL_LIVE_TEST_rc37_ROWS.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def prompts_page(rows, v):
    """One self-contained HTML page: every test in order, with a Copy button for the prompt. No network, no scripts beyond Copy."""
    out = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
           f"<title>Cartogen AI {html.escape(v)} - tests</title>",
           ("<style>body{font:16px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1b1b1b}"
           "h1{font-size:24px}h2{margin-top:36px;border-bottom:2px solid #ddd;padding-bottom:4px}"
           ".t{border:1px solid #ccc;border-radius:8px;padding:12px 14px;margin:14px 0}"
           ".id{font-weight:700}.tag{font-size:12px;border-radius:10px;padding:1px 8px;margin-left:6px;background:#e7f1ff}"
           ".opt{background:#f0f0f0}.box{background:#f6f6f6;border:1px solid #ddd;border-radius:6px;padding:8px 10px;margin:8px 0;white-space:pre-wrap}"
           "button{font:inherit;padding:4px 14px;border-radius:6px;border:1px solid #555;background:#fff;cursor:pointer}"
           ".l{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#555;margin-top:8px}"
           "@media (prefers-color-scheme:dark){body{background:#161616;color:#eee}.t{border-color:#444}.box{background:#222;border-color:#444}"
           "button{background:#222;color:#eee;border-color:#888}.tag{background:#243a55}.opt{background:#333}h2{border-color:#444}.l{color:#aaa}}"
           "</style>"),
           f"<h1>Cartogen AI {html.escape(v)}: tests</h1>",
           ("<p>Go from top to bottom. For each test: click <b>Copy</b>, paste into the Cartogen chat, send it unchanged, compare with "
           "<b>What you should see</b>, save a screenshot named with the test id, and write the result in <code>4_RESULTS.csv</code> "
           "(PASS, FAIL or SKIP, and one line of notes). Tests marked <span class=tag>START HERE</span> are the ones to do if you are short on time. "
           "Open a New Chat before each test unless it says same chat.</p>")]
    group = None
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            out.append(f"<h2>{html.escape(group.split(': ', 1)[-1])}</h2>")
        rid = r["id"]
        tags = ("<span class=tag>START HERE</span>" if rid in START_HERE else "") + ("<span class='tag opt'>optional</span>" if rid in OPTIONAL else "")
        text = r["prompt_or_action"].strip()
        out.append(f"<div class=t><div><span class=id>{html.escape(rid)}</span>{tags}</div>")
        if text.startswith("Send: "):
            msg = text[len("Send: "):]
            out.append(f"<div class=l>Send this in the chat</div><div class=box>{html.escape(msg)}</div>"
                       f"<button type=button data-msg=\"{html.escape(msg, quote=True)}\">Copy</button>")
        else:
            out.append(f"<div class=l>Do this</div><div class=box>{html.escape(text)}</div>")
        out.append(f"<div class=l>What you should see</div><div class=box>{html.escape(r['expected'])}</div></div>")
    out.append("<script>document.querySelectorAll('button[data-msg]').forEach(function(b){b.addEventListener('click',function(){"
               "var m=b.getAttribute('data-msg');var done=function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1500)};"
               "if(navigator.clipboard){navigator.clipboard.writeText(m).then(done,function(){fallback(m);done()})}else{fallback(m);done()}});});"
               "function fallback(m){var t=document.createElement('textarea');t.value=m;document.body.appendChild(t);t.select();"
               "try{document.execCommand('copy')}catch(e){}document.body.removeChild(t)}</script></html>")
    return "\n".join(out)


def results_sheet(rows):
    import io
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    w.writerow(["id", "test", "result (PASS / FAIL / SKIP)", "notes (what you saw; for a FAIL paste the last Log Messages lines, no keys)"])
    for r in rows:
        text = r["prompt_or_action"].strip()
        short = text if len(text) <= 100 else text[:100].rsplit(" ", 1)[0] + " ..."
        w.writerow([r["id"], short, "", ""])
    return "\ufeff" + buf.getvalue()


def main():
    v = version()
    subprocess.run([sys.executable, str(REPO / "plugin_upload.py")], cwd=REPO, check=True, stdout=subprocess.DEVNULL)  # noqa: S603  # fixed argv, our own script
    plugin_zip = REPO / "dist" / f"cartogen_ai_v{v}.zip"
    if not plugin_zip.is_file():
        raise SystemExit(f"plugin zip not found: {plugin_zip}")
    top = f"cartogen_ai_live_test_{v}"
    out = REPO / "dist" / f"{top}.zip"
    extras = [DOCS / n for n in EXTRAS_DOCS] + [p for g in GLOB_DOCS for p in sorted(DOCS.glob(g))]
    missing = [str(p.relative_to(REPO)) for p in extras if not p.is_file()]
    if missing:
        raise SystemExit("missing documents: " + ", ".join(missing))
    rows = [{k: x.replace("{VERSION}", v) for k, x in r.items()} for r in read_rows()]
    digest = hashlib.sha256(plugin_zip.read_bytes()).hexdigest()
    readme = (DOCS / "LIVE_TEST_rc37_README.txt").read_text(encoding="utf-8").replace("{VERSION}", v).replace("\r\n", "\n").replace("\n", "\r\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{top}/README_FIRST.txt", readme)
        z.write(plugin_zip, f"{top}/1_plugin/{plugin_zip.name}")
        z.writestr(f"{top}/1_plugin/checksum_sha256.txt", f"{digest}  {plugin_zip.name}\n")
        for p in sorted((DOCS / "release_smoke_assets" / "inputs").iterdir()):
            if p.is_file():
                z.write(p, f"{top}/2_test_files/{p.name}")
        z.writestr(f"{top}/3_PROMPTS.html", prompts_page(rows, v))
        z.writestr(f"{top}/4_RESULTS.csv", results_sheet(rows))
        z.writestr(f"{top}/screenshots/PUT_SCREENSHOTS_HERE.txt", "Save one screenshot per test here, named with the test id, e.g. RC37-N1.png\r\n")
        for p in extras:
            if p.name == "FULL_LIVE_TEST_rc37_ROWS.csv":
                z.writestr(f"{top}/extras/docs/{p.name}", p.read_bytes().decode("utf-8").replace("{VERSION}", v))
            else:
                z.write(p, f"{top}/extras/docs/{p.name}")
        z.write(REPO / "tools" / "live_test_pack.py", f"{top}/extras/tools/live_test_pack.py")
        for p in sorted((DOCS / "release_smoke_assets" / "inputs").iterdir()):
            if p.is_file():
                z.write(p, f"{top}/extras/docs/release_smoke_assets/inputs/{p.name}")
    print(f"{out}\nplugin sha256 {digest}")


if __name__ == "__main__":
    main()
