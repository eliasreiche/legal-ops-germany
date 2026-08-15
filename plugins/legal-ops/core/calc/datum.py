#!/usr/bin/env python3
"""datum — Kanonisierung von Datumsangaben (P3-Bibliothek).

Ein Datum kommt in Kanzlei-Dokumenten in zwei Schreibweisen vor: ISO
(`2026-03-01`) und deutsch (`01.03.2026`, auch zweistellig `01.03.26`).
Für jeden Wortlaut-Abgleich (Provenienz, Beleg-Suche) müssen beide auf
dieselbe Kanonform `JJJJ-MM-TT` gebracht werden — sonst gilt ein wörtlich
im Dokument stehendes Datum als „nicht belegt", nur weil die Schreibweise
abweicht.

Diese Bibliothek ist die **eine** Stelle dafür (vorher je einmal in
`aktenkopf-extraktor/executor.py`, `posteingang-ocr-verteilung/executor.py`
und `taetigkeitstext-rvg/executor.py` dupliziert).

Nur Standardbibliothek. Reine Funktionen, kein Datei-/Netzwerkzugriff.

Zweistellige Jahre: `<= 69` → 20xx, sonst 19xx (Fenster wie POSIX/`strptime`).
Ein Wert, der kein gültiges Kalenderdatum ist (31.02.), ergibt `None` — nie
ein geratenes Nachbardatum.
"""
from __future__ import annotations

import datetime as _dt
import re

# Roh-Muster (ohne Wortgrenzen) — auch für `re.fullmatch` auf einem
# Einzelwert verwendbar.
ISO_RAW = r"(\d{4})-(\d{1,2})-(\d{1,2})"
DE_RAW = r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})"

_DATUM_ISO = re.compile(r"\b" + ISO_RAW + r"\b")
_DATUM_DE = re.compile(r"(?<!\d)" + DE_RAW + r"(?!\d)")


def norm_jahr(jahr: str) -> str:
    """Zweistelliges Jahr auf vier Stellen (`26` → `2026`, `85` → `1985`)."""
    if len(jahr) == 2:
        jj = int(jahr)
        return ("20" if jj <= 69 else "19") + jahr
    return jahr.zfill(4)


def kanon_datum(jahr: str, monat: str, tag: str) -> str | None:
    """Kanonisiert ein Datum auf `JJJJ-MM-TT`; None, wenn kein gültiges Kalenderdatum."""
    j = norm_jahr(jahr)
    try:
        _dt.date(int(j), int(monat), int(tag))
    except ValueError:
        return None
    return f"{int(j):04d}-{int(monat):02d}-{int(tag):02d}"


def kanon_wert(wert: str) -> str | None:
    """Kanonform eines einzelnen Datumswerts (`01.03.2026` ↔ `2026-03-01`).

    None, wenn der Wert insgesamt keine der beiden Schreibweisen ist (ein
    Datum *innerhalb* eines Satzes findet `kanons_in_zeile`).
    """
    wert = wert.strip()
    mi = re.fullmatch(ISO_RAW, wert)
    if mi:
        return kanon_datum(mi.group(1), mi.group(2), mi.group(3))
    md = re.fullmatch(DE_RAW, wert)
    if md:
        return kanon_datum(md.group(3), md.group(2), md.group(1))
    return None


def kanons_in_zeile(zeile: str) -> set[str]:
    """Alle gültigen Datumsnennungen einer Zeile in Kanonform."""
    res: set[str] = set()
    for m in _DATUM_ISO.finditer(zeile):
        k = kanon_datum(m.group(1), m.group(2), m.group(3))
        if k:
            res.add(k)
    for m in _DATUM_DE.finditer(zeile):
        k = kanon_datum(m.group(3), m.group(2), m.group(1))
        if k:
            res.add(k)
    return res
