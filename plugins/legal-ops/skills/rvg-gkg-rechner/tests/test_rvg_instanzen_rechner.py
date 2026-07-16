"""Tests für den Zivilprozess-Instanzenzug im RVG-Rechner (Berufung/Revision).

Deckt ab: Berufung solo, Revision solo (regulär und mit BGH-Vertretungszwang),
1.+2. Instanz als zwei Angelegenheiten in einer Anfrage, Mischung
verschiedener Instanzen in EINER Angelegenheit (Fehler, § 17 Nr. 1 RVG),
Einigungsgebühr Nr. 1004 (nur in Berufung/Revision), Erhöhungsgebühr Nr. 1008
auf die Berufungs-Verfahrensgebühr (inkl. Kappung 2,0) und die Anrechnung
mit 3200 statt 3100 (Fehler).

Orakel-Werte werden aus der gesetzlichen Stufenformel (tabelle.py) hergeleitet,
nie frei gesetzt: 1,0-Gebühr (KostBRÄG 2025) für Streitwert 10.000 € = 652,00 €
(Prüfpunkt in gebuehrentabelle.json), für 5.000 € = 354,50 €. Jeder
Erwartungswert unten = web-verifizierter Satz × 1,0-Gebühr. Zusätzlich ein
externer Orakel-Abgleich gegen rvg-rechner.de (Live-Abgleich 2026-07-17):
Streitwert 5.000 €, erste Instanz (3100+3104), brutto 1.078,44 €.
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from rvg.rechner import RVGEingabeFehler, berechne  # noqa: E402

STICHTAG = dt.date(2026, 1, 1)   # KostBRÄG 2025, 1,0-Gebühr(10.000) = 652,00 €


def _b(tatbestaende, **kwargs):
    """Kurzform: eine einzelne Angelegenheit."""
    return berechne(kwargs.pop("streitwert", "10000"), STICHTAG,
                    [{"bezeichnung": "Test", "tatbestaende": tatbestaende}],
                    **kwargs)


def _erste(r):
    assert len(r.angelegenheiten) == 1
    return r.angelegenheiten[0]


# --------------------------------------------------------------------------
# Berufung solo
# --------------------------------------------------------------------------

def test_berufung_solo():
    # Nr. 3200 (1,6) und Nr. 3202 (1,2) bei 1,0-Gebühr 652,00 €:
    #   3200: 1,6 × 652,00 = 1.043,20 €
    #   3202: 1,2 × 652,00 =   782,40 €
    r = _b([{"nr": "3200"}, {"nr": "3202"}])
    assert r.einfachgebuehr == Decimal("652.00")
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["3200"].betrag == Decimal("1043.20")
    assert pos["3202"].betrag == Decimal("782.40")
    assert pos["3200"].satz == Decimal("1.6")


def test_berufung_ermaessigt_3201():
    # Nr. 3201 (1,1, vorzeitige Beendigung): 1,1 × 652,00 = 717,20 €.
    r = _b([{"nr": "3201"}])
    assert _erste(r).positionen[0].betrag == Decimal("717.20")


# --------------------------------------------------------------------------
# Revision solo — regulär (3206) und mit BGH-Vertretungszwang (3208)
# --------------------------------------------------------------------------

def test_revision_regulaer_3206():
    # Nr. 3206 (1,6): 1,6 × 652,00 = 1.043,20 €.
    r = _b([{"nr": "3206"}])
    assert _erste(r).positionen[0].betrag == Decimal("1043.20")


def test_revision_bgh_3208_3210():
    # BGH-Zivilrevision: Nr. 3208 (2,3) statt 3206, Terminsgebühr Nr. 3210 (1,5):
    #   3208: 2,3 × 652,00 = 1.499,60 €
    #   3210: 1,5 × 652,00 =   978,00 €
    r = _b([{"nr": "3208"}, {"nr": "3210"}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["3208"].betrag == Decimal("1499.60")
    assert pos["3210"].betrag == Decimal("978.00")


def test_revision_ermaessigt_bgh_3209():
    # Nr. 3209 (1,8): 1,8 × 652,00 = 1.173,60 €.
    r = _b([{"nr": "3209"}])
    assert _erste(r).positionen[0].betrag == Decimal("1173.60")


# --------------------------------------------------------------------------
# 1. + 2. Instanz als zwei Angelegenheiten in EINER Anfrage
# --------------------------------------------------------------------------

def test_erste_und_zweite_instanz_zwei_angelegenheiten():
    r = berechne("10000", STICHTAG, [
        {"bezeichnung": "Erste Instanz",
         "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]},
        {"bezeichnung": "Berufung",
         "tatbestaende": [{"nr": "3200"}, {"nr": "3202"}]},
    ])
    assert len(r.angelegenheiten) == 2
    a1, a2 = r.angelegenheiten
    # Erste Instanz: 3100 (1,3×652=847,60) + 3104 (1,2×652=782,40) = 1.630,00 €
    assert a1.zwischensumme_gebuehren == Decimal("1630.00")
    # Berufung: 3200 (1.043,20) + 3202 (782,40) = 1.825,60 €
    assert a2.zwischensumme_gebuehren == Decimal("1825.60")
    # Je Angelegenheit eigene 7002-Pauschale (je 20 €) und eigene USt-Basis.
    assert a1.auslagenpauschale == Decimal("20.00")
    assert a2.auslagenpauschale == Decimal("20.00")
    assert r.gesamt_verguetung == a1.gesamt + a2.gesamt


# --------------------------------------------------------------------------
# Mischung verschiedener Instanzen in EINER Angelegenheit -> Fehler
# --------------------------------------------------------------------------

def test_instanzmischung_in_einer_angelegenheit_abgelehnt():
    # Erste Instanz (3100) + Berufung (3200) in derselben Angelegenheit:
    # § 17 Nr. 1 RVG — jeder Rechtszug ist eine eigene Angelegenheit.
    with pytest.raises(RVGEingabeFehler, match=r"§ 17 Nr\. 1 RVG"):
        _b([{"nr": "3100"}, {"nr": "3200"}])


def test_instanzmischung_berufung_revision_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="eigene Angelegenheit"):
        _b([{"nr": "3200"}, {"nr": "3206"}])


def test_gleiche_instanz_verfahrens_und_terminsgebuehr_erlaubt():
    # Verfahrens- und Terminsgebühr derselben Instanz sind zulässig.
    r = _b([{"nr": "3200"}, {"nr": "3202"}])
    assert len(_erste(r).positionen) == 2


# --------------------------------------------------------------------------
# Einigungsgebühr Nr. 1004 — nur in Berufung/Revision
# --------------------------------------------------------------------------

def test_1004_in_erster_instanz_abgelehnt():
    # Nr. 1004 verlangt einen Berufungs-/Revisions-Tatbestand in derselben
    # Angelegenheit — in erster Instanz (3100) unzulässig, Hinweis auf 1000/1003.
    with pytest.raises(RVGEingabeFehler, match=r"Nr\. 1000"):
        _b([{"nr": "3100"}, {"nr": "1004"}])


def test_1004_ohne_gerichtstatbestand_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="Berufungs- oder Revisions"):
        _b([{"nr": "1004"}])


def test_1004_in_berufung_zulaessig():
    # Nr. 1004 (1,3): 1,3 × 652,00 = 847,60 €.
    r = _b([{"nr": "3200"}, {"nr": "1004"}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["1004"].betrag == Decimal("847.60")


# --------------------------------------------------------------------------
# Erhöhungsgebühr Nr. 1008 auf die Berufungs-Verfahrensgebühr (3200)
# --------------------------------------------------------------------------

def test_1008_auf_3200():
    # 1 weiterer Auftraggeber: Satz 0,3 × 652,00 = 195,60 €.
    r = _b([{"nr": "3200"},
            {"nr": "1008", "erhoeht_position": "3200", "weitere_auftraggeber": 1}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["1008"].satz == Decimal("0.3")
    assert pos["1008"].betrag == Decimal("195.60")


def test_1008_auf_3200_kappung_auf_2_0():
    # 10 weitere Auftraggeber: roh 3,0 -> gekappt auf 2,0 (Anm. Abs. 3 zu
    # Nr. 1008): 2,0 × 652,00 = 1.304,00 €.
    r = _b([{"nr": "3200"},
            {"nr": "1008", "erhoeht_position": "3200", "weitere_auftraggeber": 10}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["1008"].satz == Decimal("2.0")
    assert pos["1008"].betrag == Decimal("1304.00")
    assert any("gekappt" in w for w in r.warnungen)


# --------------------------------------------------------------------------
# Anrechnung: nur auf die Verfahrensgebühr des ersten Rechtszugs (3100)
# --------------------------------------------------------------------------

def test_anrechnung_auf_3200_statt_3100_abgelehnt():
    # Geschäftsgebühr + Berufungs-Verfahrensgebühr, Anrechnung angefordert:
    # Vorbem. 3 Abs. 4 VV RVG rechnet nur auf die Verfahrensgebühr des ersten
    # Rechtszugs (Nr. 3100) an, nicht auf Nr. 3200.
    with pytest.raises(RVGEingabeFehler, match="ersten Rechtszugs"):
        berechne("10000", STICHTAG, [
            {"bezeichnung": "Außergerichtliche Vertretung",
             "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
            {"bezeichnung": "Berufung",
             "tatbestaende": [{"nr": "3200"}]},
        ], anrechnung_2300_auf_3100=True)


# --------------------------------------------------------------------------
# Externer Orakel-Abgleich (rvg-rechner.de, Live-Abgleich 2026-07-17)
# --------------------------------------------------------------------------

def test_externes_orakel_erste_instanz_brutto():
    # Streitwert 5.000 €, erste Instanz: Verfahrensgebühr (3100) +
    # Terminsgebühr (3104). 1,0-Gebühr 354,50 €:
    #   3100: 1,3 × 354,50 = 460,85 €
    #   3104: 1,2 × 354,50 = 425,40 €
    #   Zwischensumme (netto Gebühren)      886,25 €
    #   + Auslagenpauschale Nr. 7002         20,00 €
    #   = Netto                             906,25 €
    #   + 19 % USt (172,19 €)   -> brutto 1.078,44 €
    r = berechne("5000", STICHTAG,
                 [{"bezeichnung": "Erste Instanz",
                   "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]}])
    a = _erste(r)
    assert a.zwischensumme_gebuehren == Decimal("886.25")
    assert a.auslagenpauschale == Decimal("20.00")
    assert a.netto == Decimal("906.25")
    assert a.gesamt == Decimal("1078.44")
