"""Tests für core/calc/gkg/rechner.py — Positionen, Ermäßigungs-Ausschluss,
versionierter Mindestbetrag (KV 1100), Rundung, Scope-Ablehnungen (P4).
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "core" / "calc"))

from gkg.rechner import GKGEingabeFehler, berechne  # noqa: E402

STICHTAG_NEU = dt.date(2026, 1, 1)   # KostBRÄG 2025
STICHTAG_ALT = dt.date(2023, 1, 1)   # KostRÄG 2021


def test_kv1210_grundfall():
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1210"}])
    assert r.einfachgebuehr == Decimal("283.00")
    assert r.positionen[0].betrag == Decimal("849.00")  # 283,00 * 3,0
    assert r.gesamt == Decimal("849.00")


def test_kv1211_ermaessigung():
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1211"}])
    assert r.positionen[0].betrag == Decimal("283.00")  # 283,00 * 1,0


def test_kv1210_und_1211_gleichzeitig_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match="schließen sich gegenseitig aus"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1210"}, {"nr": "1211"}])


def test_kv1220_und_1222_gleichzeitig_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match="schließen sich gegenseitig aus"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1220"}, {"nr": "1222"}])


def test_kv1210_und_kv1220_zusammen_erlaubt():
    # Zwei verschiedene Instanzen (1. Instanz + Berufung) dürfen zusammen
    # abgefragt werden, sind kein Ausschlusspaar.
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1210"}, {"nr": "1220"}])
    assert len(r.positionen) == 2


# --------------------------------------------------------------------------
# KV 1100 — versionierter, positionsspezifischer Mindestbetrag
# --------------------------------------------------------------------------

def test_kv1100_mindestbetrag_neu():
    r = berechne("100", STICHTAG_NEU, [{"nr": "1100"}])
    pos = r.positionen[0]
    assert pos.mindestbetrag_gegriffen is True
    assert pos.betrag == Decimal("38.00")


def test_kv1100_mindestbetrag_alt():
    r = berechne("100", STICHTAG_ALT, [{"nr": "1100"}])
    pos = r.positionen[0]
    assert pos.mindestbetrag_gegriffen is True
    assert pos.betrag == Decimal("36.00")


def test_kv1100_kein_mindestbetrag_bei_hohem_streitwert():
    # 0,5 * Einfachgebühr übersteigt bei hohem Streitwert den Mindestbetrag.
    r = berechne("100000", STICHTAG_NEU, [{"nr": "1100"}])
    assert r.positionen[0].mindestbetrag_gegriffen is False


# --------------------------------------------------------------------------
# Streitwert-Höchstgrenze, Scope, Eingabefehler
# --------------------------------------------------------------------------

def test_befund2_streitwert_ueber_30_mio_wird_gekappt():
    # Regressionstest Review-Befund 2: § 39 Abs. 2 GKG ist eine Kappungs-,
    # keine Zulässigkeitsgrenze — vor dem Fix wurde die Anfrage abgelehnt.
    # 40 Mio -> 30 Mio; KostBRÄG 2025: 4138 + 590 x 210 = 128038,00.
    r = berechne("40000000", STICHTAG_NEU, [{"nr": "1210"}])
    assert r.wert_gekappt is True
    assert r.streitwert == Decimal("30000000.00")
    assert r.streitwert_eingabe == Decimal("40000000")
    assert r.einfachgebuehr == Decimal("128038.00")
    assert r.positionen[0].betrag == Decimal("384114.00")   # x 3,0


def test_befund2_kappung_in_rechenkette_und_warnung():
    r = berechne("30000000.01", STICHTAG_NEU, [{"nr": "1210"}])
    assert r.wert_gekappt is True
    kappungs_schritte = [s for s in r.rechenkette if s.norm == "§ 39 Abs. 2 GKG"]
    assert len(kappungs_schritte) == 1
    assert any("§ 39 Abs. 2 GKG" in w for w in r.warnungen)


def test_befund2_exakt_30_mio_keine_kappung():
    r = berechne("30000000", STICHTAG_NEU, [{"nr": "1210"}])
    assert r.wert_gekappt is False
    assert not any("§ 39" in s.norm for s in r.rechenkette)
    assert r.warnungen == []


def test_unbekannte_nr_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match="nicht unterstützt"):
        berechne("10000", STICHTAG_NEU, [{"nr": "9999"}])


def test_doppelte_nr_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match="mehrfach"):
        berechne("10000", STICHTAG_NEU, [{"nr": "1210"}, {"nr": "1210"}])


def test_leere_positionen_abgelehnt():
    with pytest.raises(GKGEingabeFehler):
        berechne("10000", STICHTAG_NEU, [])


def test_negativer_streitwert_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match=r"> 0"):
        berechne("-1", STICHTAG_NEU, [{"nr": "1210"}])


def test_summe_mehrerer_positionen():
    r = berechne("10000", STICHTAG_NEU, [{"nr": "1210"}, {"nr": "1220"}])
    summe = sum((p.betrag for p in r.positionen), Decimal("0.00"))
    assert r.gesamt == summe
