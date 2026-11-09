"""Keeps the pictures a live render test makes, so a CI failure leaves something to look at (master list DEF-1, #379). The live job sets CARTOGEN_LIVE_ARTIFACTS to a folder and
uploads it; everywhere else the variable is unset and nothing is written. Standard library only; the image is anything with save(path, format) returning a truthy value on success
(a QImage)."""
import os
import re
from pathlib import Path

ENV = "CARTOGEN_LIVE_ARTIFACTS"


def artifact_dir():
    value = os.environ.get(ENV)
    return Path(value) if value else None


def save_png(name, image):
    """The path the picture was saved to, or None when no folder is set or the save failed. The name is reduced to letters, digits, dots, dashes and underscores so it cannot leave the folder."""
    folder = artifact_dir()
    if folder is None:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("._") or "image"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe}.png"
    return str(path) if image.save(str(path), "PNG") else None


def save_text(name, text):
    """The path a small text note was saved to in the artifact folder, or None when no folder is set. A live test uses it for facts the CI log would hide (prints of passing tests
    are not shown). The name is reduced like save_png's."""
    folder = artifact_dir()
    if folder is None:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name)).strip("._") or "note"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe}.txt"
    path.write_text(str(text), encoding="utf-8")
    return str(path)
