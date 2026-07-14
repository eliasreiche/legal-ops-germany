"""Unit-Tests für die wiederverwendbare Bibliothek core/calc/zeit/rechner.py.

Deckt ab: Dauer-Berechnung aus `minuten` bzw. `start`/`ende` (inkl. der
Fehlerfälle „beides angegeben" und „nur eine Seite von start/ende"),
Aufrunden angebrochener Minuten, Taktung (immer aufrunden, nie kaufmännisch)
sowie die Aggregation je Aktenzeichen und je (Aktenzeichen, Datum).

Eindeutiger Testdateiname (`test_taetigkeitstext_zeit_lib.py`), damit er im
selben pytest-Lauf nicht mit gleichnamigen Tests anderer Skills kollidiert.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_CALC_DIR = Path(__file__).resolve().parents[3] / "core" / "calc"
if str(_CALC_DIR) not in sys.path:
    sys.path.insert(0, str(_CALC_DIR))

from zeit.rechner import (  # noqa: E402
    ZeitEingabeFehler,
    ZeitEintrag,
    dauer_minuten,
    runde_auf_takt,
    summe_je_az,
    summe_je_az_und_datum,
)


# --------------------------------------------------------------------------
# dauer_minuten — direkte Minutenangabe
# --------------------------------------------------------------------------

def test_dauer_aus_minuten():
    assert dauer_minuten(start=None, ende=None, minuten=45) == 45


def test_dauer_minuten_muss_positiv_sein():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende=None, minuten=0)
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende=None, minuten=-5)


def test_dauer_minuten_muss_ganzzahl_sein():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende=None, minuten=45.5)  # type: ignore[arg-type]
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende=None, minuten=True)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# dauer_minuten — start/ende
# --------------------------------------------------------------------------

def test_dauer_aus_start_ende_exakte_minuten():
    assert dauer_minuten(start="2026-07-01T09:00:00",
                         ende="2026-07-01T09:45:00", minuten=None) == 45


def test_dauer_aus_start_ende_rundet_angebrochene_minute_auf():
    # 09:00:00 -> 09:47:01 = 47 Minuten und 1 Sekunde -> 48 (konservativ aufgerundet).
    assert dauer_minuten(start="2026-07-01T09:00:00",
                         ende="2026-07-01T09:47:01", minuten=None) == 48


def test_dauer_start_ende_ende_muss_nach_start_liegen():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start="2026-07-01T09:00:00",
                      ende="2026-07-01T09:00:00", minuten=None)
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start="2026-07-01T09:47:00",
                      ende="2026-07-01T09:00:00", minuten=None)


def test_dauer_start_ende_ungueltiges_format():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start="01.07.2026", ende="2026-07-01T09:45:00", minuten=None)


# --------------------------------------------------------------------------
# dauer_minuten — beide bzw. keine Quelle angegeben (Eingabefehler)
# --------------------------------------------------------------------------

def test_dauer_fehler_beides_angegeben():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start="2026-07-01T09:00:00", ende="2026-07-01T09:45:00", minuten=45)


def test_dauer_fehler_nur_start_ohne_ende():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start="2026-07-01T09:00:00", ende=None, minuten=None)


def test_dauer_fehler_nur_ende_ohne_start():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende="2026-07-01T09:45:00", minuten=None)


def test_dauer_fehler_keine_angabe():
    with pytest.raises(ZeitEingabeFehler):
        dauer_minuten(start=None, ende=None, minuten=None)


# --------------------------------------------------------------------------
# runde_auf_takt — immer aufrunden, nie kaufmännisch
# --------------------------------------------------------------------------

def test_takt_ohne_konfiguration_unveraendert():
    assert runde_auf_takt(47, None) == 47


def test_takt_exakter_wert_bleibt_gleich():
    assert runde_auf_takt(30, 6) == 30


@pytest.mark.parametrize("minuten,takt,erwartet", [
    (47, 6, 48),   # 47/6 = 7.83.. -> aufrunden auf 8*6=48 (nicht kaufmännisch auf 48 abrunden-nah)
    (1, 6, 6),     # jede angebrochene Minute zieht den vollen Takt nach sich
    (15, 6, 18),
    (22, 6, 24),
    (35, 15, 45),
    (30, 15, 30),
])
def test_takt_rundet_immer_auf(minuten, takt, erwartet):
    assert runde_auf_takt(minuten, takt) == erwartet


def test_takt_muss_positiv_sein():
    with pytest.raises(ZeitEingabeFehler):
        runde_auf_takt(30, 0)
    with pytest.raises(ZeitEingabeFehler):
        runde_auf_takt(30, -6)


def test_takt_muss_ganzzahl_sein():
    with pytest.raises(ZeitEingabeFehler):
        runde_auf_takt(30, 6.5)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def test_summe_je_az():
    eintraege = [
        ZeitEintrag(az="12/2026", datum="2026-07-01", minuten=48),
        ZeitEintrag(az="12/2026", datum="2026-07-01", minuten=30),
        ZeitEintrag(az="34/2026", datum="2026-07-02", minuten=18),
    ]
    assert summe_je_az(eintraege) == {"12/2026": 78, "34/2026": 18}


def test_summe_je_az_und_datum():
    eintraege = [
        ZeitEintrag(az="12/2026", datum="2026-07-01", minuten=48),
        ZeitEintrag(az="12/2026", datum="2026-07-01", minuten=30),
        ZeitEintrag(az="12/2026", datum="2026-07-02", minuten=10),
        ZeitEintrag(az="34/2026", datum="2026-07-02", minuten=18),
    ]
    summen = summe_je_az_und_datum(eintraege)
    assert summen == {
        ("12/2026", "2026-07-01"): 78,
        ("12/2026", "2026-07-02"): 10,
        ("34/2026", "2026-07-02"): 18,
    }


def test_summe_je_az_leere_liste():
    assert summe_je_az([]) == {}
    assert summe_je_az_und_datum([]) == {}


def test_zeit_eintrag_as_dict():
    e = ZeitEintrag(az="12/2026", datum="2026-07-01", minuten=48)
    assert e.as_dict() == {"az": "12/2026", "datum": "2026-07-01", "minuten": 48}
