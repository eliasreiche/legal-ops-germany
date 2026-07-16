"""Tests für die GKG-Revision (KV 1230/1232) im Instanzenzug.

Deckt ab: Revisions-Verfahrensgebühr solo, Ermäßigung, Ausschlussregel
(1230 Regelfall vs. 1232 Ermäßigung schließen sich aus, analog 1210/1211 und
1220/1222) und einen externen Orakel-Abgleich gegen rvg-rechner.de
(Live-Abgleich 2026-07-17): Streitwert 300.000 €, Berufung (KV 1220, 4,0) =
11.512,00 €.

Orakel-Werte aus der gesetzlichen Stufenformel (tabelle.py), nie frei gesetzt:
1,0-Gebühr GKG (KostBRÄG 2025) für Streitwert 10.000 € = 283,00 € (Prüfpunkt in
gebuehrentabelle.json), für 300.000 € = 2.878,00 €. Jeder Erwartungswert =
web-verifizierter Satz × 1,0-Gebühr.
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from gkg.rechner import GKGEingabeFehler, berechne  # noqa: E402

STICHTAG = dt.date(2026, 1, 1)   # KostBRÄG 2025


def test_kv1230_revision_grundfall():
    # KV 1230 (5,0): 5,0 × 283,00 = 1.415,00 €.
    r = berechne("10000", STICHTAG, [{"nr": "1230"}])
    assert r.einfachgebuehr == Decimal("283.00")
    assert r.positionen[0].betrag == Decimal("1415.00")


def test_kv1232_ermaessigung():
    # KV 1232 (3,0): 3,0 × 283,00 = 849,00 €.
    r = berechne("10000", STICHTAG, [{"nr": "1232"}])
    assert r.positionen[0].betrag == Decimal("849.00")


def test_kv1230_und_1232_gleichzeitig_abgelehnt():
    with pytest.raises(GKGEingabeFehler, match="schließen sich gegenseitig aus"):
        berechne("10000", STICHTAG, [{"nr": "1230"}, {"nr": "1232"}])


def test_kv1220_und_1230_zusammen_erlaubt():
    # Berufung (1220) und Revision (1230) sind verschiedene Instanzen, kein
    # Ausschlusspaar.
    r = berechne("10000", STICHTAG, [{"nr": "1220"}, {"nr": "1230"}])
    assert len(r.positionen) == 2


def test_externes_orakel_berufung_300k():
    # Streitwert 300.000 €, Berufung: KV 1220 (4,0). 1,0-Gebühr 2.878,00 €:
    # 4,0 × 2.878,00 = 11.512,00 € (Live-Abgleich rvg-rechner.de, 2026-07-17).
    r = berechne("300000", STICHTAG, [{"nr": "1220"}])
    assert r.einfachgebuehr == Decimal("2878.00")
    assert r.gesamt == Decimal("11512.00")
