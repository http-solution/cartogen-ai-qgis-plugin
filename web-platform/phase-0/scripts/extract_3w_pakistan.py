from __future__ import annotations

import csv
import io
import pathlib
import zipfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1] / "data" / "pakistan"
SOURCE = ROOT / "global-3w-2023-06-08.xlsx"
OUTPUT = ROOT / "global-3w-pakistan-2023-06-08.csv"
A = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": A, "r": R}


def cell_value(cell, shared):
    value = cell.find("a:v", NS)
    text = "" if value is None else value.text or ""
    if cell.attrib.get("t") == "s" and text:
        return shared[int(text)]
    return text


def main():
    archive = zipfile.ZipFile(SOURCE)
    shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    shared = [
        "".join(t.text or "" for t in item.iter(f"{{{A}}}t"))
        for item in shared_root.findall(f"{{{A}}}si")
    ]
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    relation_map = {item.attrib["Id"]: item.attrib["Target"] for item in relationships}
    sheet = workbook.find("a:sheets/a:sheet", NS)
    target = relation_map[sheet.attrib[f"{{{R}}}id"]]
    worksheet = "xl/" + target.lstrip("/")
    if worksheet not in archive.namelist():
        worksheet = "xl/worksheets/" + target.split("/")[-1]
    root = ET.fromstring(archive.read(worksheet))
    rows = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        rows.append([cell_value(cell, shared) for cell in row.findall("a:c", NS)])
    headers = rows[0]
    selected = [row for row in rows[2:] if row and row[0].strip().upper() == "PAK"]
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(selected)
    print(f"wrote {OUTPUT} rows={len(selected)} columns={len(headers)}")


if __name__ == "__main__":
    main()
