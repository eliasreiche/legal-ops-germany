"""Spec-Tests für core/calc/extf/formate.py — Decimal→Komma-String,
Datum→TTMM/JJJJMMTT/JJJJMMTTHHMMSSmmm, CP1252-Prüfung, DATEV-Quoting,
Konto-Format, Belegfeld-Zeichensatz (P3/P4).
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from extf.formate import (  # noqa: E402
    ExtfFormatFehler,
    datum_jjjjmmtt,
    datum_ttmm,
    datumzeit_kompakt,
    dezimal_komma,
    parse_datumzeit_strikt,
    pruefe_belegfeld,
    pruefe_cp1252,
    pruefe_konto,
    quote_text,
)


# --------------------------------------------------------------------------
# Decimal -> Komma-String
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert,stellen,erwartet", [
    (Decimal("952.5"), 2, "952,50"),
    (Decimal("0.1"), 2, "0,10"),
    (Decimal("1234567890.12"), 2, "1234567890,12"),
    (Decimal("1123.123456"), 6, "1123,123456"),
    (Decimal("10"), 2, "10,00"),
])
def test_dezimal_komma(wert, stellen, erwartet):
    assert dezimal_komma(wert, stellen) == erwartet


def test_dezimal_komma_rundet_kaufmaennisch():
    # 0.125 auf 2 Nachkommastellen -> 0,13 (ROUND_HALF_UP, nie float-round())
    assert dezimal_komma(Decimal("0.125"), 2) == "0,13"


# --------------------------------------------------------------------------
# Datum / Zeit
# --------------------------------------------------------------------------

def test_datum_ttmm():
    assert datum_ttmm(dt.date(2026, 3, 15)) == "1503"


def test_datum_ttmm_januar_erster_zweistellig():
    assert datum_ttmm(dt.date(2026, 1, 1)) == "0101"


def test_datum_jjjjmmtt():
    assert datum_jjjjmmtt(dt.date(2026, 3, 15)) == "20260315"


def test_datumzeit_kompakt_millisekunden():
    zeitpunkt = dt.datetime(2026, 7, 13, 10, 0, 0, 123000)
    assert datumzeit_kompakt(zeitpunkt) == "20260713100000123"


def test_datumzeit_kompakt_ohne_millisekunden():
    zeitpunkt = dt.datetime(2026, 7, 13, 10, 0, 0)
    assert datumzeit_kompakt(zeitpunkt) == "20260713100000000"


def test_parse_datumzeit_strikt():
    ergebnis = parse_datumzeit_strikt("2026-07-13T10:00:00", "feld")
    assert ergebnis == dt.datetime(2026, 7, 13, 10, 0, 0)


@pytest.mark.parametrize("wert", ["2026-07-13", "13.07.2026 10:00", 20260713100000, None, True, ""])
def test_parse_datumzeit_strikt_fehler(wert):
    with pytest.raises(ExtfFormatFehler):
        parse_datumzeit_strikt(wert, "feld")


# --------------------------------------------------------------------------
# CP1252
# --------------------------------------------------------------------------

def test_cp1252_umlaute_ok():
    assert pruefe_cp1252("Müller ./. Schmidt", "feld") == "Müller ./. Schmidt"


def test_cp1252_emoji_abgelehnt():
    with pytest.raises(ExtfFormatFehler, match="CP1252"):
        pruefe_cp1252("Honorar 🎉", "feld")


def test_cp1252_kyrillisch_abgelehnt():
    # Zeichen außerhalb der CP1252-Codepage (kein Latin-Alphabet-Zeichen).
    with pytest.raises(ExtfFormatFehler, match="CP1252"):
        pruefe_cp1252("Привет", "feld")


# --------------------------------------------------------------------------
# Quoting
# --------------------------------------------------------------------------

def test_quote_text_umschliesst_in_anfuehrungszeichen():
    assert quote_text("Buchungsstapel", "feld") == '"Buchungsstapel"'


def test_quote_text_verdoppelt_interne_anfuehrungszeichen():
    assert quote_text('Rechnung "A"', "feld") == '"Rechnung ""A"""'


def test_quote_text_none_wird_leer():
    assert quote_text(None, "feld") == ""


def test_quote_text_zu_lang_abgelehnt():
    with pytest.raises(ExtfFormatFehler, match="zu lang"):
        quote_text("x" * 31, "feld", laenge=30)


# --------------------------------------------------------------------------
# Konto-Format (nur Format, nie Kontenrahmen-Defaults)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert,laenge,erwartet", [
    ("1200", 4, "1200"),
    (1200, 4, "1200"),
    ("12000", 4, "12000"),  # Personenkonto: Sachkontenlänge + 1
])
def test_pruefe_konto_ok(wert, laenge, erwartet):
    assert pruefe_konto(wert, "feld", laenge) == erwartet


@pytest.mark.parametrize("wert,laenge", [
    ("ABCD", 4),
    ("120", 4),      # zu kurz
    ("120000", 4),   # zu lang (mehr als Sachkontenlaenge+1)
    ("12,00", 4),
    (None, 4),
    (True, 4),
])
def test_pruefe_konto_fehler(wert, laenge):
    with pytest.raises(ExtfFormatFehler):
        pruefe_konto(wert, "feld", laenge)


# --------------------------------------------------------------------------
# Belegfeld
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert", ["RE-2026-042", "AB$12&3%4*5+6/7", ""])
def test_pruefe_belegfeld_ok(wert):
    assert pruefe_belegfeld(wert, "feld", 36) == wert


@pytest.mark.parametrize("wert", ["Müller", "RE 2026", "RE#042"])
def test_pruefe_belegfeld_unzulaessige_zeichen(wert):
    with pytest.raises(ExtfFormatFehler):
        pruefe_belegfeld(wert, "feld", 36)


def test_pruefe_belegfeld_zu_lang():
    with pytest.raises(ExtfFormatFehler, match="zu lang"):
        pruefe_belegfeld("A" * 37, "feld", 36)


@pytest.mark.parametrize("wert", [42, 4.2, True, None, [1], {"a": 1}])
def test_pruefe_belegfeld_nicht_string_typ(wert):
    # Regressionstest D12-Review-Blocker: Typ-Check muss VOR len() greifen —
    # numerische Rechnungsnummern (JSON: "belegfeld1": 42) sind ein
    # Formatfehler mit klarer Meldung, nie ein TypeError.
    with pytest.raises(ExtfFormatFehler, match="muss ein Text"):
        pruefe_belegfeld(wert, "feld", 36)
