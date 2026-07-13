"""Tests für core/calc/gkg/tabelle.py — Stufenformel § 34 Abs. 1 GKG (P4).

Deckt ab: Stufengrenzen exakt und einen Cent darüber (für beide
Tabellenstände), Stichtag-basierte Standwahl (§ 71 Abs. 1 GKG,
Anhängigkeit — bewusst anderer Stichtagsbegriff als beim RVG), die
Streitwert-Höchstgrenze (§ 39 Abs. 2 GKG, 30 Mio. €).
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from gkg.tabelle import GKGTabellenFehler, einfachgebuehr, stand_fuer_stichtag  # noqa: E402
from wertgebuehr_formel import WertgebuehrFehler  # noqa: E402

STICHTAG_NEU = dt.date(2026, 1, 1)     # KostBRÄG 2025
STICHTAG_ALT = dt.date(2023, 1, 1)     # KostRÄG 2021


def test_stand_kostbraeg_2025_ab_stichtag():
    assert stand_fuer_stichtag(dt.date(2025, 6, 1))["id"] == "kostbraeg_2025"


def test_stand_kostraeg_2021_im_fenster():
    assert stand_fuer_stichtag(dt.date(2025, 5, 31))["id"] == "kostraeg_2021"


def test_stand_vor_2021_lehnt_ab():
    with pytest.raises(GKGTabellenFehler, match="kein GKG-Tabellenstand"):
        stand_fuer_stichtag(dt.date(2020, 12, 31))


@pytest.mark.parametrize("wert,erwartet", [
    ("500.00", "40.00"),
    ("500.01", "61.00"),
    ("2000.00", "103.00"),
    ("2000.01", "125.50"),
    ("10000.00", "283.00"),
    ("10000.01", "313.50"),
    ("500000.00", "4138.00"),
    ("500000.01", "4348.00"),   # 4138,00 + 210,00 (ein angefangener 50.000er-Schritt)
])
def test_stufengrenzen_exakt_und_ein_cent_drueber_neu(wert, erwartet):
    r, stand = einfachgebuehr(wert, STICHTAG_NEU)
    assert stand["id"] == "kostbraeg_2025"
    assert str(r.einfachgebuehr) == erwartet, f"wert={wert}"


@pytest.mark.parametrize("wert,erwartet", [
    ("500.00", "38.00"),
    ("500.01", "58.00"),
    ("2000.00", "98.00"),
    ("2000.01", "119.00"),
    ("500000.00", "3901.00"),
    ("500000.01", "4099.00"),   # 3901,00 + 198,00
])
def test_stufengrenzen_exakt_und_ein_cent_drueber_alt(wert, erwartet):
    r, stand = einfachgebuehr(wert, STICHTAG_ALT)
    assert stand["id"] == "kostraeg_2021"
    assert str(r.einfachgebuehr) == erwartet, f"wert={wert}"


def test_ueber_hoechstwert_mehrere_schritte():
    r, _ = einfachgebuehr("650000.00", STICHTAG_NEU)
    assert r.einfachgebuehr == Decimal("4138.00") + 3 * Decimal("210.00")


def test_streitwert_hoechstgrenze_exakt_ok():
    r, _ = einfachgebuehr("30000000.00", STICHTAG_NEU)
    assert r.einfachgebuehr is not None


def test_befund2_streitwert_ueber_hoechstgrenze_wird_gekappt():
    # Regressionstest Review-Befund 2: § 39 Abs. 2 GKG ist eine Kappungs-,
    # keine Zulässigkeitsgrenze — vor dem Fix wurde hier abgelehnt.
    an_der_grenze, _ = einfachgebuehr("30000000.00", STICHTAG_NEU)
    drueber, _ = einfachgebuehr("30000000.01", STICHTAG_NEU)
    weit_drueber, _ = einfachgebuehr("40000000", STICHTAG_NEU)
    assert drueber.einfachgebuehr == an_der_grenze.einfachgebuehr
    assert weit_drueber.einfachgebuehr == an_der_grenze.einfachgebuehr
    # Das Ergebnis trägt den gekappten Wert (keine stille Kappung).
    assert weit_drueber.gegenstandswert == Decimal("30000000.00")


def test_negativer_wert_lehnt_ab():
    with pytest.raises(WertgebuehrFehler):
        einfachgebuehr("-1", STICHTAG_NEU)
