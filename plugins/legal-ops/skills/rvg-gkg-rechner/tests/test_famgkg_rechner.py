"""Tests für core/calc/famgkg/rechner.py — KV-FamGKG-Positionen,
Ausschlussgruppen, Mehrvergleich KV 1500 mit § 30 Abs. 3 FamGKG, Teilwerte,
Scope-Ablehnungen (P4).

Orakel: die Gebührensätze stehen hier unabhängig vom Katalog als Literale
aus Anlage 1 FamGKG (web-verifiziert 2026-10-22, gesetze-im-internet.de/
famgkg/anlage_1.html); erwartete Beträge sind handgerechnet:
Verfahrenswert 10.000 € -> 1,0-Gebühr 283,00 € (Anlage 2 FamGKG, KostBRÄG
2025) bzw. 266,00 € (KostRÄG 2021); Betrag = Satz x 1,0-Gebühr, kaufmännisch
auf Cent gerundet, mindestens 15,00 € (§ 28 Abs. 2 FamGKG). Ein externes
Orakel lag nicht vor: borghei `legal_calc` kennt kein FamGKG (geprüft
2026-10-22).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from famgkg.rechner import FamGKGEingabeFehler, berechne, lade_katalog  # noqa: E402
from wertgebuehr_formel import WertgebuehrFehler  # noqa: E402

NEU = dt.date(2026, 1, 1)   # KostBRÄG 2025
ALT = dt.date(2023, 1, 1)   # KostRÄG 2021

# Nr. -> Satz laut Anlage 1 FamGKG (Literal, nicht aus dem Katalog gelesen).
SAETZE = {"1110": "2.0", "1111": "0.5", "1120": "3.0", "1121": "0.5",
          "1122": "1.0", "1220": "3.0", "1221": "1.0", "1222": "4.0",
          "1223": "1.0", "1224": "2.0", "1310": "0.5", "1314": "1.0",
          "1315": "0.5", "1320": "2.0", "1321": "0.5", "1322": "3.0",
          "1323": "0.5", "1324": "1.0", "1410": "0.3", "1420": "1.5",
          "1421": "0.5", "1500": "0.25"}


def test_katalog_deckt_genau_die_erwarteten_positionen():
    assert set(lade_katalog()["positionen"]) == set(SAETZE)


@pytest.mark.parametrize("nr", sorted(SAETZE))
def test_jede_katalogposition_einmal(nr):
    eintrag = {"nr": nr}
    if nr == "1500":
        eintrag["gegenstandswert"] = "10000"
    r = berechne("10000", NEU, [eintrag])
    pos = r.positionen[0]
    erwartet = (Decimal(SAETZE[nr]) * Decimal("283.00")).quantize(Decimal("0.01"))
    assert pos.satz == Decimal(SAETZE[nr])
    assert pos.betrag == erwartet, nr
    assert r.gesamt == erwartet
    assert pos.norm == f"KV {nr} FamGKG"


def test_handgerechnet_kv1410_aufrundung():
    # 0,3 x 283,00 = 84,90 €.
    assert berechne("10000", NEU, [{"nr": "1410"}]).gesamt == Decimal("84.90")


def test_alter_stand_kv1110():
    # KostRÄG 2021: 1,0-Gebühr 266,00 € x 2,0 = 532,00 €.
    r = berechne("10000", ALT, [{"nr": "1110"}])
    assert r.tabellenstand["id"] == "kostraeg_2021"
    assert r.gesamt == Decimal("532.00")


@pytest.mark.parametrize("paar", [
    ("1110", "1111"), ("1120", "1121"), ("1120", "1122"), ("1121", "1122"),
    ("1220", "1221"), ("1222", "1223"), ("1222", "1224"), ("1223", "1224"),
    ("1314", "1315"), ("1320", "1321"), ("1322", "1323"), ("1322", "1324"),
    ("1323", "1324"), ("1420", "1421"),
])
def test_ausschlussgruppen(paar):
    with pytest.raises(FamGKGEingabeFehler, match="schließen sich gegenseitig aus"):
        berechne("10000", NEU, [{"nr": n} for n in paar])


def test_verschiedene_instanzen_zusammen_erlaubt():
    r = berechne("10000", NEU, [{"nr": "1220"}, {"nr": "1222"}])
    assert r.gesamt == Decimal("849.00") + Decimal("1132.00")


# --------------------------------------------------------------------------
# Mehrvergleich KV 1500 + § 30 Abs. 3 FamGKG (Anm. zu KV 1500)
# --------------------------------------------------------------------------

def test_mehrvergleich_kappung_greift_nicht():
    """KV 1220 aus 10.000 € = 3,0 x 283,00 = 849,00 €; KV 1500 aus 5.000 € =
    0,25 x 170,50 = 42,625 -> 42,63 €; Summe 891,63 €. Höchstbetrag = 3,0 x
    1,0-Gebühr aus 15.000 € (283,00 + 2 x 30,50 = 344,00 €) = 1.032,00 € ->
    keine Kürzung."""
    r = berechne("10000", NEU, [{"nr": "1220"},
                                {"nr": "1500", "gegenstandswert": "5000"}])
    assert r.positionen[1].betrag == Decimal("42.63")
    assert r.kappung["gekappt"] is False
    assert r.kappung["hoechstbetrag"] == "1032.00"
    assert r.gesamt == Decimal("891.63")
    assert any(s.norm.startswith("§ 30 Abs. 3 FamGKG") for s in r.rechenkette)


def test_mehrvergleich_kappung_greift():
    """KV 1310 aus 10.000 € = 0,5 x 283,00 = 141,50 €; KV 1500 aus 5.000 € =
    42,63 €; Summe 184,13 €. Höchstbetrag = 0,5 x 344,00 = 172,00 € ->
    Kürzung 12,13 €, Gesamt 172,00 €."""
    r = berechne("10000", NEU, [{"nr": "1310"},
                                {"nr": "1500", "gegenstandswert": "5000"}])
    assert r.kappung["gekappt"] is True
    assert r.kappung["kuerzung"] == "12.13"
    assert r.gesamt == Decimal("172.00")


def test_mehrvergleich_ohne_gegenstandswert_abgelehnt():
    with pytest.raises(FamGKGEingabeFehler, match="verlangt 'gegenstandswert'"):
        berechne("10000", NEU, [{"nr": "1220"}, {"nr": "1500"}])


def test_mehrvergleich_mit_zwei_verfahrensgebuehren_abgelehnt():
    with pytest.raises(FamGKGEingabeFehler, match="mehreren Gebühren"):
        berechne("10000", NEU, [{"nr": "1220"}, {"nr": "1222"},
                                {"nr": "1500", "gegenstandswert": "5000"}])


def test_teilwerte_je_position():
    # KV 1220 aus 10.000 € (849,00 €) + KV 1420 aus eigenem Teilwert 5.000 €
    # (1,5 x 170,50 = 255,75 €) — jede Position trägt ihren Wert.
    r = berechne("10000", NEU, [{"nr": "1220"},
                                {"nr": "1420", "gegenstandswert": "5000"}])
    assert [p.gegenstandswert for p in r.positionen] == [Decimal("10000"), Decimal("5000")]
    assert r.positionen[1].betrag == Decimal("255.75")
    assert r.gesamt == Decimal("1104.75")


def test_teilwert_ueber_30_mio_abgelehnt():
    with pytest.raises(FamGKGEingabeFehler, match="§ 33 Abs. 2 FamGKG"):
        berechne("10000", NEU, [{"nr": "1220"},
                                {"nr": "1500", "gegenstandswert": "40000000"}])


# --------------------------------------------------------------------------
# Scope und Eingabefehler
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nr", ["1130", "1210", "1311", "1411", "1422", "9999"])
def test_nicht_unterstuetzte_nr(nr):
    with pytest.raises(FamGKGEingabeFehler, match="nicht unterstützt"):
        berechne("10000", NEU, [{"nr": nr}])


def test_unbekannter_key_in_position():
    with pytest.raises(FamGKGEingabeFehler, match="unbekanntes Feld"):
        berechne("10000", NEU, [{"nr": "1110", "satz": "1.0"}])


def test_float_verfahrenswert_abgelehnt():
    with pytest.raises(WertgebuehrFehler, match="float"):
        berechne(0.1 + 0.2, NEU, [{"nr": "1110"}])


def test_float_gegenstandswert_abgelehnt():
    with pytest.raises(WertgebuehrFehler, match="float"):
        berechne("10000", NEU, [{"nr": "1220"},
                                {"nr": "1500", "gegenstandswert": 5000.5}])


def test_doppelte_nr_abgelehnt():
    with pytest.raises(FamGKGEingabeFehler, match="mehrfach"):
        berechne("10000", NEU, [{"nr": "1110"}, {"nr": "1110"}])


def test_leere_positionen_abgelehnt():
    with pytest.raises(FamGKGEingabeFehler):
        berechne("10000", NEU, [])


@pytest.mark.parametrize("wert", ["0", "-1"])
def test_nicht_positiver_verfahrenswert(wert):
    with pytest.raises(FamGKGEingabeFehler, match="> 0"):
        berechne(wert, NEU, [{"nr": "1110"}])


def test_rechenkette_quelle_executor():
    r = berechne("10000", NEU, [{"nr": "1110"}])
    assert all(s.quelle == "executor" for s in r.rechenkette)
    assert r.rechenkette[0].norm == "§ 63 Abs. 1 FamGKG"
    assert r.rechenkette[1].norm == "§ 28 Abs. 1 FamGKG"
