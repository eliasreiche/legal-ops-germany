#!/usr/bin/env python3
"""extf/parser — strikter Leser für DATEV-EXTF-Buchungsstapel (Format 700,
Kategorie 21), das Gegenstück zum Writer in executor.py (P3).

Liest genau das Format, das der eigene Writer erzeugt: CP1252-kodiert,
Semikolon-getrennt, Textfelder in doppelten Anführungszeichen (`""`-Escape),
zweizeiliger Kopf (Zeile 1 = 31-Feld-Metadaten-Header, Zeile 2 = 20
Spaltenköpfe), ab Zeile 3 ein Buchungssatz je Zeile (20 Spalten, Komma-
Dezimal). Der Writer ist das Orakel — Round-Trip (Writer-Ausgabe → Parser →
identische Werte) ist testgesichert.

Strenge Validierung (D21-Stil): jeder Formatfehler wird mit **Zeilenangabe**
als `ExtfParseFehler` geworfen — keine stille Reparatur, kein Raten, keine
Teil-Ergebnisse. Der Parser rechnet nichts (keine Salden, keine Fristen) — er
liefert nur die deterministisch geparsten Roh-Werte (Decimal für Geld, `date`
für Daten). Die Auswertung (offene Posten) macht `core/calc/opos/`.

Nur Standardbibliothek. Ausschließlich `decimal.Decimal` für Geldbeträge,
niemals `float` (CONVENTIONS.md P3) — `D()` wird aus der geteilten
`wertgebuehr_formel.py` übernommen.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

_EXTF_DIR = Path(__file__).resolve().parent
_CALC_DIR = _EXTF_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from wertgebuehr_formel import D, WertgebuehrFehler  # noqa: E402

__all__ = ["ExtfParseFehler", "ExtfBuchung", "ExtfStapel",
           "parse_extf", "parse_extf_datei"]

# Fixe Kopf-Kennung (identisch zu executor._header_zeile / header_format_700.json).
_KENNZEICHEN = "EXTF"
_VERSIONSNUMMER = "700"
_KATEGORIE = "21"
_FORMATNAME = "Buchungsstapel"
_HEADER_FELDER = 31
_SPALTEN = 20

# Erwartete Spaltenköpfe (Zeile 2) — 1:1 aus buchungssatz_spalten_700.json.
_ERWARTETE_KOEPFE = [
    "Umsatz (ohne Soll/Haben-Kz)", "Soll/Haben-Kennzeichen", "WKZ Umsatz",
    "Kurs", "Basis-Umsatz", "WKZ Basis-Umsatz", "Konto",
    "Gegenkonto (ohne BU-Schlüssel)", "BU-Schlüssel", "Belegdatum",
    "Belegfeld 1", "Belegfeld 2", "Skonto", "Buchungstext", "Postensperre",
    "Diverse Adressnummer", "Geschäftspartnerbank", "Sachverhalt",
    "Zinssperre", "Beleglink",
]


class ExtfParseFehler(ValueError):
    """Format-/Eingabefehler beim Lesen einer EXTF-Datei (mit Zeilenangabe)."""


@dataclass
class ExtfBuchung:
    """Ein geparster Buchungssatz (Roh-Werte, nichts berechnet)."""
    zeile: int                       # physische Zeilennummer (1-basiert)
    umsatz: Decimal                  # immer > 0 (Vorzeichen steckt in soll_haben)
    soll_haben: str                  # "S" | "H"
    konto: str
    gegenkonto: str
    belegdatum_ttmm: str             # wie in der Datei (TTMM, 4-stellig)
    belegdatum: _dt.date | None      # rekonstruiert, wenn WJ eindeutig; sonst None
    wkz_umsatz: str | None = None
    kurs: Decimal | None = None
    basisumsatz: Decimal | None = None
    wkz_basisumsatz: str | None = None
    bu_schluessel: str | None = None
    belegfeld1: str | None = None
    belegfeld2: str | None = None
    skonto: Decimal | None = None
    buchungstext: str | None = None


@dataclass
class ExtfStapel:
    """Ergebnis des Parsers: normalisierter Header + Buchungsliste."""
    header: dict[str, Any]
    buchungen: list[ExtfBuchung]


# --------------------------------------------------------------------------
# Feld-Helfer
# --------------------------------------------------------------------------

def _geld(wert: str, feld: str, zeile: int) -> Decimal:
    """DATEV-Komma-Dezimal (z. B. '1500,00') → Decimal. Kein float, keine
    stille Reparatur — ungültig ist ein Fehler mit Zeilenangabe."""
    roh = wert.strip()
    if "." in roh:
        raise ExtfParseFehler(
            f"Zeile {zeile}: '{feld}' enthält einen Punkt ({roh!r}) — DATEV-EXTF "
            f"nutzt Komma als Dezimaltrennzeichen ohne Tausenderpunkt")
    try:
        return D(roh.replace(",", "."))
    except WertgebuehrFehler as exc:
        raise ExtfParseFehler(f"Zeile {zeile}: '{feld}' ist kein gültiger Betrag: {wert!r} ({exc})")


def _int(wert: str, feld: str, zeile: int) -> int:
    roh = wert.strip()
    if not roh.isdigit():
        raise ExtfParseFehler(f"Zeile {zeile}: '{feld}' muss numerisch sein, nicht {wert!r}")
    return int(roh)


def _datum_jjjjmmtt(wert: str, feld: str, zeile: int) -> _dt.date:
    roh = wert.strip()
    if len(roh) != 8 or not roh.isdigit():
        raise ExtfParseFehler(
            f"Zeile {zeile}: '{feld}' muss ein Datum im Format JJJJMMTT (8 Ziffern) "
            f"sein, nicht {wert!r}")
    try:
        return _dt.date(int(roh[:4]), int(roh[4:6]), int(roh[6:8]))
    except ValueError as exc:
        raise ExtfParseFehler(f"Zeile {zeile}: '{feld}' ist kein gültiges Datum ({roh}): {exc}")


def _datumzeit_kompakt(wert: str, feld: str, zeile: int) -> _dt.datetime:
    """JJJJMMTTHHMMSSmmm (17-stellig) → datetime (Millisekunden → Mikrosekunden)."""
    roh = wert.strip()
    if len(roh) != 17 or not roh.isdigit():
        raise ExtfParseFehler(
            f"Zeile {zeile}: '{feld}' muss 17-stellig JJJJMMTTHHMMSSmmm sein, nicht {wert!r}")
    try:
        return _dt.datetime(
            int(roh[0:4]), int(roh[4:6]), int(roh[6:8]),
            int(roh[8:10]), int(roh[10:12]), int(roh[12:14]),
            int(roh[14:17]) * 1000)
    except ValueError as exc:
        raise ExtfParseFehler(f"Zeile {zeile}: '{feld}' ist kein gültiger Zeitstempel ({roh}): {exc}")


# --------------------------------------------------------------------------
# Header (Zeile 1)
# --------------------------------------------------------------------------

def _parse_header(felder: list[str]) -> dict[str, Any]:
    if len(felder) != _HEADER_FELDER:
        raise ExtfParseFehler(
            f"Zeile 1: EXTF-Header muss {_HEADER_FELDER} Felder haben, "
            f"gefunden {len(felder)} — keine gültige Buchungsstapel-Kopfzeile")
    if felder[0] != _KENNZEICHEN or felder[1] != _VERSIONSNUMMER \
            or felder[2] != _KATEGORIE or felder[3] != _FORMATNAME:
        raise ExtfParseFehler(
            f"Zeile 1: kein EXTF-Buchungsstapel (Format {_VERSIONSNUMMER} / "
            f"Kategorie {_KATEGORIE}) — erwartet "
            f"'EXTF;{_VERSIONSNUMMER};{_KATEGORIE};Buchungsstapel', "
            f"gefunden {felder[0:4]!r}")

    von = _datum_jjjjmmtt(felder[14], "Buchungszeitraum von", 1)
    bis = _datum_jjjjmmtt(felder[15], "Buchungszeitraum bis", 1)
    if von > bis:
        raise ExtfParseFehler(
            f"Zeile 1: 'Buchungszeitraum von' ({von.isoformat()}) liegt nach "
            f"'Buchungszeitraum bis' ({bis.isoformat()})")

    return {
        "formatversion": _int(felder[4], "Formatversion", 1),
        "erzeugt_am": _datumzeit_kompakt(felder[5], "Erzeugt am", 1),
        "herkunft": felder[7] or None,
        "exportiert_von": felder[8] or None,
        "beraternummer": _int(felder[10], "Beraternummer", 1),
        "mandantennummer": _int(felder[11], "Mandantennummer", 1),
        "wirtschaftsjahresbeginn": _datum_jjjjmmtt(felder[12], "Wirtschaftsjahresbeginn", 1),
        "sachkontenlaenge": _int(felder[13], "Sachkontenlaenge", 1),
        "buchungszeitraum_von": von,
        "buchungszeitraum_bis": bis,
        "bezeichnung": felder[16] or None,
        "diktatkuerzel": felder[17] or None,
        "buchungstyp": _int(felder[18], "Buchungstyp", 1) if felder[18].strip() else None,
        "waehrung": felder[21] or None,
    }


# --------------------------------------------------------------------------
# Buchungszeile (ab Zeile 3)
# --------------------------------------------------------------------------

def _belegdatum(ttmm: str, header: dict[str, Any], zeile: int) -> tuple[str, _dt.date | None]:
    """TTMM (4-stellig) + eindeutiges Wirtschaftsjahr → volles Datum. Ist der
    Buchungszeitraum über eine Jahresgrenze gespannt (von.year != bis.year),
    lässt sich das Jahr nicht eindeutig ableiten — dann wird nur das TTMM
    zurückgegeben (belegdatum = None), nie ein geratenes Jahr (P3)."""
    roh = ttmm.strip()
    if len(roh) != 4 or not roh.isdigit():
        raise ExtfParseFehler(
            f"Zeile {zeile}: 'Belegdatum' muss 4-stellig TTMM sein, nicht {ttmm!r}")
    tag, monat = int(roh[:2]), int(roh[2:])
    von = header["buchungszeitraum_von"]
    bis = header["buchungszeitraum_bis"]
    if von.year != bis.year:
        if not (1 <= monat <= 12 and 1 <= tag <= 31):
            raise ExtfParseFehler(f"Zeile {zeile}: 'Belegdatum' {roh!r} ist kein gültiges TTMM")
        return roh, None
    try:
        return roh, _dt.date(von.year, monat, tag)
    except ValueError as exc:
        raise ExtfParseFehler(
            f"Zeile {zeile}: 'Belegdatum' {roh!r} ergibt kein gültiges Datum "
            f"im Wirtschaftsjahr {von.year}: {exc}")


def _parse_buchung(felder: list[str], header: dict[str, Any], zeile: int) -> ExtfBuchung:
    if len(felder) != _SPALTEN:
        raise ExtfParseFehler(
            f"Zeile {zeile}: Buchungssatz muss {_SPALTEN} Spalten haben, "
            f"gefunden {len(felder)}")

    umsatz = _geld(felder[0], "Umsatz", zeile)
    if umsatz <= 0:
        raise ExtfParseFehler(
            f"Zeile {zeile}: 'Umsatz' muss > 0 sein (Vorzeichen über Soll/Haben), "
            f"ist {umsatz}")

    soll_haben = felder[1].strip()
    if soll_haben not in ("S", "H"):
        raise ExtfParseFehler(
            f"Zeile {zeile}: 'Soll/Haben-Kennzeichen' muss 'S' oder 'H' sein, nicht {felder[1]!r}")

    konto = felder[6].strip()
    gegenkonto = felder[7].strip()
    for name, wert in (("Konto", konto), ("Gegenkonto", gegenkonto)):
        if not wert.isdigit():
            raise ExtfParseFehler(f"Zeile {zeile}: '{name}' muss numerisch sein, nicht {wert!r}")

    ttmm, belegdatum = _belegdatum(felder[9], header, zeile)

    # Spalten 15–20 (Index 14–19) führt der Writer immer leer — ein befüllter
    # Platzhalter ist ein Formatfehler (v1 kennt diese Spalten nicht).
    for idx in range(14, 20):
        if felder[idx].strip():
            raise ExtfParseFehler(
                f"Zeile {zeile}: Spalte {idx + 1} ('{_ERWARTETE_KOEPFE[idx]}') ist "
                f"befüllt ({felder[idx]!r}), wird von diesem Parser (v1) aber nicht "
                f"unterstützt — nur die ersten 14 Buchungssatz-Spalten")

    return ExtfBuchung(
        zeile=zeile,
        umsatz=umsatz,
        soll_haben=soll_haben,
        konto=konto,
        gegenkonto=gegenkonto,
        belegdatum_ttmm=ttmm,
        belegdatum=belegdatum,
        wkz_umsatz=felder[2].strip() or None,
        kurs=_geld(felder[3], "Kurs", zeile) if felder[3].strip() else None,
        basisumsatz=_geld(felder[4], "Basis-Umsatz", zeile) if felder[4].strip() else None,
        wkz_basisumsatz=felder[5].strip() or None,
        bu_schluessel=felder[8].strip() or None,
        belegfeld1=felder[10].strip() or None,
        belegfeld2=felder[11].strip() or None,
        skonto=_geld(felder[12], "Skonto", zeile) if felder[12].strip() else None,
        buchungstext=felder[13] or None,
    )


# --------------------------------------------------------------------------
# Gesamtdatei
# --------------------------------------------------------------------------

def parse_extf(quelle: str | bytes) -> ExtfStapel:
    """Parst eine EXTF-Datei (als CP1252-Bytes oder bereits dekodierter String)
    in Header + Buchungsliste. Wirft ExtfParseFehler (mit Zeilenangabe) bei
    jedem Formatverstoß — kein Traceback, keine Teil-Ergebnisse."""
    if isinstance(quelle, bytes):
        try:
            text = quelle.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ExtfParseFehler(
                f"Datei ist nicht CP1252-kodiert (DATEV-EXTF verlangt CP1252): {exc}")
    elif isinstance(quelle, str):
        text = quelle
    else:
        raise ExtfParseFehler(f"parse_extf erwartet str oder bytes, nicht {type(quelle).__name__}")

    # DATEV-Quoting mit dem csv-Modul lesen (Semikolon-Trenner, ""-Escape).
    # newline="" überlässt csv die \r\n-Behandlung.
    reader = csv.reader(io.StringIO(text), delimiter=";", quotechar='"', doublequote=True)
    zeilen = [z for z in reader if z != []]
    if len(zeilen) < 2:
        raise ExtfParseFehler(
            "EXTF-Datei unvollständig: erwartet mindestens die Kopfzeile (Zeile 1) "
            "und die Spaltenkopf-Zeile (Zeile 2)")

    header = _parse_header(zeilen[0])

    koepfe = [k.strip() for k in zeilen[1]]
    if koepfe != _ERWARTETE_KOEPFE:
        raise ExtfParseFehler(
            "Zeile 2: unerwartete Spaltenköpfe — die Datei entspricht nicht dem "
            "erwarteten 20-Spalten-Buchungsstapel dieses Formats")

    buchungen = [_parse_buchung(z, header, i) for i, z in enumerate(zeilen[2:], start=3)]
    return ExtfStapel(header=header, buchungen=buchungen)


def parse_extf_datei(pfad: str | Path) -> ExtfStapel:
    p = Path(pfad)
    if not p.is_file():
        raise ExtfParseFehler(f"EXTF-Datei nicht gefunden: {p}")
    return parse_extf(p.read_bytes())
