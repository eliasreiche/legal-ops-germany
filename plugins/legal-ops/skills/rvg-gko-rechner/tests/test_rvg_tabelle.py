"""Tests für core/calc/rvg/tabelle.py — Stufenformel § 13 Abs. 1 RVG (P4).

Deckt ab: Stufengrenzen exakt und einen Cent darüber (für beide
Tabellenstände), Stichtag-basierte Standwahl (§ 60 Abs. 1 RVG), Fehler bei
Stichtag außerhalb der unterstützten Stände, über der Höchstwertgrenze.
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from rvg.tabelle import RVGTabellenFehler, einfachgebuehr, stand_fuer_stichtag  # noqa: E402
from wertgebuehr_formel import WertgebuehrFehler  # noqa: E402

STICHTAG_NEU = dt.date(2026, 1, 1)     # KostBRÄG 2025
STICHTAG_ALT = dt.date(2023, 1, 1)     # KostRÄG 2021


# --------------------------------------------------------------------------
# Standwahl
# --------------------------------------------------------------------------

def test_stand_kostbraeg_2025_ab_stichtag():
    assert stand_fuer_stichtag(dt.date(2025, 6, 1))["id"] == "kostbraeg_2025"
    assert stand_fuer_stichtag(dt.date(2026, 1, 1))["id"] == "kostbraeg_2025"


def test_stand_kostraeg_2021_im_fenster():
    assert stand_fuer_stichtag(dt.date(2021, 1, 1))["id"] == "kostraeg_2021"
    assert stand_fuer_stichtag(dt.date(2025, 5, 31))["id"] == "kostraeg_2021"


def test_stand_vor_2021_lehnt_ab():
    with pytest.raises(RVGTabellenFehler, match="kein RVG-Tabellenstand"):
        stand_fuer_stichtag(dt.date(2020, 12, 31))


# --------------------------------------------------------------------------
# Stufengrenzen exakt und 1 Cent darüber — KostBRÄG 2025 (aktuell)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert,erwartet", [
    ("500.00", "51.50"),        # Grundbetrag, exakt an der Grenze
    ("500.01", "93.00"),        # 1 Cent drüber -> ein angefangener Schritt
    ("2000.00", "176.00"),      # letzte Stufe im 500er-Schritt-Bereich
    ("2000.01", "235.50"),      # 1 Cent drüber -> Sprung in 1000er-Bereich
    ("10000.00", "652.00"),
    ("10000.01", "707.00"),
    ("25000.00", "927.00"),
    ("25000.01", "1013.00"),
    ("50000.00", "1357.00"),
    ("50000.01", "1456.50"),
    ("200000.00", "2352.00"),
    ("200000.01", "2492.00"),
    ("500000.00", "3752.00"),   # letzte tabellierte Stufe, exakt
    ("500000.01", "3927.00"),   # 1 Cent drüber -> über Höchstwert (+175,00)
])
def test_stufengrenzen_exakt_und_ein_cent_drueber_neu(wert, erwartet):
    r, stand = einfachgebuehr(wert, STICHTAG_NEU)
    assert stand["id"] == "kostbraeg_2025"
    assert str(r.einfachgebuehr) == erwartet, f"wert={wert}"


# --------------------------------------------------------------------------
# Stufengrenzen exakt und 1 Cent darüber — KostRÄG 2021 (Vorfassung)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert,erwartet", [
    ("500.00", "49.00"),
    ("500.01", "88.00"),
    ("2000.00", "166.00"),
    ("2000.01", "222.00"),
    ("10000.00", "614.00"),
    ("10000.01", "666.00"),
    ("500000.00", "3539.00"),
    ("500000.01", "3704.00"),   # 3539,00 + 165,00 (ein angefangener 50.000er-Schritt)
])
def test_stufengrenzen_exakt_und_ein_cent_drueber_alt(wert, erwartet):
    r, stand = einfachgebuehr(wert, STICHTAG_ALT)
    assert stand["id"] == "kostraeg_2021"
    assert str(r.einfachgebuehr) == erwartet, f"wert={wert}"


# --------------------------------------------------------------------------
# Über-Höchstwert-Formel (§ 13 Abs. 1 S. 3 RVG)
# --------------------------------------------------------------------------

def test_ueber_hoechstwert_mehrere_schritte():
    r, _ = einfachgebuehr("650000.00", STICHTAG_NEU)  # 3 angefangene 50.000er-Schritte
    assert r.einfachgebuehr == Decimal("3752.00") + 3 * Decimal("175.00")


# --------------------------------------------------------------------------
# Fehlerfälle
# --------------------------------------------------------------------------

def test_negativer_wert_lehnt_ab():
    with pytest.raises(WertgebuehrFehler):
        einfachgebuehr("-1", STICHTAG_NEU)


def test_nullwert_lehnt_ab():
    with pytest.raises(WertgebuehrFehler):
        einfachgebuehr("0", STICHTAG_NEU)


def test_float_eingabe_lehnt_ab():
    with pytest.raises(WertgebuehrFehler, match="float"):
        einfachgebuehr(0.1 + 0.2, STICHTAG_NEU)
