#!/usr/bin/env python3
"""extf/formate — gemeinsame Format-/Validierungsbausteine für den EXTF-Export (P3).

Reine Formatierungsfunktionen ohne Executor-Ablauflogik (die liegt in
executor.py) — Decimal→Komma-String, Datum→TTMM/JJJJMMTT/JJJJMMTTHHMMSSmmm,
CP1252-Encodierbarkeitsprüfung, DATEV-Quoting (Textfelder in doppelten
Anführungszeichen, Zahlen/Daten unquotiert) und Konto-Formatprüfung.

Nur Standardbibliothek. Ausschließlich `decimal.Decimal` für Geldbeträge,
niemals `float` (CONVENTIONS.md P3) — `D()`/`parse_datum_strikt()` werden aus
der geteilten `wertgebuehr_formel.py` übernommen (keine Zweitimplementierung
derselben Float-Ablehnung).
"""
from __future__ import annotations

import datetime as _dt
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

_EXTF_DIR = Path(__file__).resolve().parent
_CALC_DIR = _EXTF_DIR.parent
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from wertgebuehr_formel import D, WertgebuehrFehler, parse_datum_strikt  # noqa: E402

__all__ = [
    "ExtfFormatFehler", "D", "parse_datum_strikt", "parse_datumzeit_strikt",
    "dezimal_komma", "datum_jjjjmmtt", "datum_ttmm", "datumzeit_kompakt",
    "pruefe_cp1252", "quote_text", "bare_zahl", "leer", "pruefe_konto",
    "pruefe_belegfeld",
]


class ExtfFormatFehler(ValueError):
    """Eingabe- oder Formatfehler des EXTF-Exports → Exit 2, nie ein Traceback."""


# --------------------------------------------------------------------------
# Datum / Zeit
# --------------------------------------------------------------------------

_DATUMZEIT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d{1,6})?$")


def parse_datumzeit_strikt(wert: Any, feld: str) -> _dt.datetime:
    """Strikt JJJJ-MM-TTTHH:MM:SS[.ffffff] als String (ISO 8601, 'T' oder
    Leerzeichen als Trenner). Wird für 'erzeugt_am' gebraucht — der Wert
    kommt aus der Eingabe, nie aus der Wall-Clock (Idempotenz-Baustein, wie
    core/calc/fristen/kalender_executor.py bei DTSTAMP)."""
    if isinstance(wert, bool) or not isinstance(wert, str) or not _DATUMZEIT_RE.match(wert):
        raise ExtfFormatFehler(
            f"'{feld}' muss ein ISO-Datum+Zeit als String sein "
            f"(JJJJ-MM-TTTHH:MM:SS, optional mit Sekundenbruchteil), "
            f"nicht {wert!r}")
    try:
        return _dt.datetime.fromisoformat(wert)
    except ValueError as exc:
        raise ExtfFormatFehler(f"'{feld}' ist kein gültiges ISO-Datum+Zeit: {wert!r} ({exc})")


def datum_jjjjmmtt(datum: _dt.date) -> str:
    return datum.strftime("%Y%m%d")


def datum_ttmm(datum: _dt.date) -> str:
    return datum.strftime("%d%m")


def datumzeit_kompakt(zeitpunkt: _dt.datetime) -> str:
    """JJJJMMTTHHMMSSmmm (17-stellig, Millisekunden dreistellig)."""
    ms = zeitpunkt.microsecond // 1000
    return zeitpunkt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"


# --------------------------------------------------------------------------
# Decimal → Komma-String
# --------------------------------------------------------------------------

def dezimal_komma(wert: Decimal, nachkommastellen: int) -> str:
    """Formatiert einen Decimal-Betrag mit fester Nachkommastellenzahl und
    Komma statt Punkt (DATEV-Konvention) — nie über float/round()."""
    quant = Decimal(1).scaleb(-nachkommastellen)
    gerundet = wert.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{gerundet:.{nachkommastellen}f}".replace(".", ",")


# --------------------------------------------------------------------------
# CP1252 / Quoting
# --------------------------------------------------------------------------

def pruefe_cp1252(text: str, feld: str) -> str:
    """Prüft, ob `text` verlustfrei in CP1252 (Windows-1252) kodierbar ist —
    DATEV-EXTF verlangt dieses Encoding, u. a. für deutsche Umlaute/ß. Ein
    Zeichen außerhalb von CP1252 (z. B. Emoji, Sonderanführungszeichen wie
    „…", manche Gedankenstriche/Aufzählungszeichen) ist ein Formatfehler
    (Exit 2), keine stille Ersetzung/Transliteration."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError as exc:
        unzeichen = text[exc.start:exc.end]
        raise ExtfFormatFehler(
            f"'{feld}' enthält ein Zeichen, das nicht in CP1252 "
            f"(Windows-1252) kodierbar ist: {unzeichen!r} "
            f"(Position {exc.start}) — DATEV-EXTF verlangt CP1252")
    return text


def quote_text(wert: str | None, feld: str, *, laenge: int | None = None) -> str:
    """DATEV-Quoting für Textfelder: immer in doppelte Anführungszeichen,
    enthaltene '\"' werden verdoppelt. `None`/leer → leerer, unquotierter
    Token (reservierte/optionale Felder müssen laut Referenzstruktur
    vollständig leer bleiben, nicht `\"\"`)."""
    if wert is None or wert == "":
        return ""
    if not isinstance(wert, str):
        raise ExtfFormatFehler(f"'{feld}' muss ein Text (String) sein, nicht {wert!r}")
    if laenge is not None and len(wert) > laenge:
        raise ExtfFormatFehler(
            f"'{feld}' ist zu lang: {len(wert)} Zeichen, erlaubt sind "
            f"höchstens {laenge}: {wert!r}")
    pruefe_cp1252(wert, feld)
    escaped = wert.replace('"', '""')
    return f'"{escaped}"'


def bare_zahl(wert: Any) -> str:
    """Zahlen-/Datumsfelder werden unquotiert ausgegeben. `None` → leer."""
    return "" if wert is None else str(wert)


def leer() -> str:
    """Reservierte/nicht implementierte Spalte — immer ein leerer Token."""
    return ""


# --------------------------------------------------------------------------
# Konto-Format (P3: nur Format, nie Kontenrahmen-Defaults raten)
# --------------------------------------------------------------------------

def pruefe_konto(wert: Any, feld: str, sachkontenlaenge: int) -> str:
    """Validiert NUR das Format (numerisch, Länge konsistent zur
    Header-Sachkontenlänge) — nie eine Annahme über SKR03/SKR04 oder einen
    konkreten Kontenrahmen (Maintainer-Entscheidung D20). Zulässige Länge:
    genau `sachkontenlaenge` (Sachkonto) oder `sachkontenlaenge + 1`
    (Personenkonto, per DATEV-Konvention maximal eine Stelle länger)."""
    if isinstance(wert, bool) or not isinstance(wert, (str, int)):
        raise ExtfFormatFehler(f"'{feld}' muss numerisch sein (String oder Ganzzahl), nicht {wert!r}")
    s = str(wert).strip()
    if not s.isdigit():
        raise ExtfFormatFehler(f"'{feld}' muss rein numerisch sein, nicht {wert!r}")
    if len(s) not in (sachkontenlaenge, sachkontenlaenge + 1):
        raise ExtfFormatFehler(
            f"'{feld}' hat {len(s)} Stellen ({s!r}) — erwartet werden "
            f"{sachkontenlaenge} Stellen (Sachkonto) oder "
            f"{sachkontenlaenge + 1} Stellen (Personenkonto) gemäß "
            f"Header-Sachkontenlänge {sachkontenlaenge}")
    return s


# --------------------------------------------------------------------------
# Belegfeld 1/2 (Rechnungs-/Belegnummer, OPOS-Schlüssel)
# --------------------------------------------------------------------------

BELEGFELD_REGEX = re.compile(r"^[A-Za-z0-9$&%*+\-/]*$")


def pruefe_belegfeld(wert: Any, feld: str, laenge: int) -> str:
    """Belegfeld 1/2 erlauben laut DATEV-Konvention nur alphanumerische
    Zeichen plus `$ & % * + - /` (OPOS-Abgleichsschlüssel) — kein CP1252-
    Check nötig, da der Zeichensatz eine ASCII-Teilmenge ist.

    Typ-Check VOR len(): Rechnungsnummern kommen im JSON oft als bare Zahl
    (`"belegfeld1": 42`) — das ist ein Formatfehler (Exit 2, klare Meldung
    mit Korrekturhinweis), nie ein TypeError-Traceback (D12-Review-Blocker)."""
    if not isinstance(wert, str):
        raise ExtfFormatFehler(
            f"'{feld}' muss ein Text (String) sein, nicht {wert!r} — "
            f"Beleg-/Rechnungsnummern als JSON-String angeben "
            f"(z. B. \"42\" statt 42)")
    if len(wert) > laenge:
        raise ExtfFormatFehler(
            f"'{feld}' ist zu lang: {len(wert)} Zeichen, erlaubt sind "
            f"höchstens {laenge}: {wert!r}")
    if not BELEGFELD_REGEX.match(wert):
        raise ExtfFormatFehler(
            f"'{feld}' enthält unzulässige Zeichen: {wert!r} — erlaubt sind "
            f"nur Buchstaben, Ziffern und $ & % * + - /")
    return wert
