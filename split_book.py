"""Split a country workbook that exceeds the 30 MB delivery limit into parts
under it, by region: part 1 = Cover + GLOBAL / DM / regional sheets + DM
countries, part 2 = Cover + EM sheet + EM countries (each part re-saved
with only its sheets, so styles and layout are untouched).

    python3 split_book.py country_archetype_book.xlsx
-> country_archetype_book_DM.xlsx, country_archetype_book_EM.xlsx
"""
from __future__ import annotations

import os
import sys

import openpyxl

from region_map import classify

REGIONAL = {"Cover", "GLOBAL", "DM", "EM", "North America", "W Europe", "Nordics", "DM Asia-Pac", "MidEast DM",
            "EM Asia", "EM EMEA", "LatAm"}


def _bucket(sheet_name: str) -> str:
    if sheet_name in REGIONAL:
        return "EM" if sheet_name in ("EM", "EM Asia", "EM EMEA", "LatAm") else "DM"
    code = sheet_name.split(" ")[0].split("_")[0]
    b, _ = classify(code)
    return "EM" if str(b).upper().startswith("EM") else "DM"


def split(path: str) -> list:
    base, ext = os.path.splitext(path)
    out = []
    for part in ("DM", "EM"):
        wb = openpyxl.load_workbook(path)
        for name in list(wb.sheetnames):
            if name == "Cover":
                continue
            if _bucket(name) != part:
                del wb[name]
        dest = f"{base}_{part}{ext}"
        wb.save(dest)
        out.append(dest)
        print(f"{dest}: {len(wb.sheetnames)} sheets, {os.path.getsize(dest) / 1e6:.1f} MB", flush=True)
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        split(p)
