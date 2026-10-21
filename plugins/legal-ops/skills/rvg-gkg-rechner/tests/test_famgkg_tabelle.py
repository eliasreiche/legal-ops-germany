"""Tests für core/calc/famgkg/tabelle.py — Stufenformel § 28 Abs. 1 FamGKG (P4).

Orakel: die vollständige Anlage 2 FamGKG beider Stände (in
gebuehrentabelle.json als `pruefpunkte_anlage_2` abgelegt, web-verifiziert
am 2026-10-22 gegen gesetze-im-internet.de/famgkg/anlage_2.html bzw. den
Wayback-Schnappschuss vom 2024-03-06) — die Formel muss jeden Tabellenwert
exakt reproduzieren. Dazu Stichtagswahl nach § 63 Abs. 1 FamGKG mit
Grenztagen, Mindestbetrag (§ 28 Abs. 2 Satz 1 FamGKG, über den Rechner) und
die sichtbare Höchstwert-Kappung (§ 33 Abs. 2 FamGKG). Ein externes Orakel
lag nicht vor: borghei `legal_calc` kennt kein FamGKG (geprüft 2026-10-22).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from famgkg.tabelle import (  # noqa: E402
    FamGKGTabellenFehler,
    einfachgebuehr,
    lade_tabelle,
    stand_fuer_stichtag,
)
from famgkg.rechner import berechne  # noqa: E402

STICHTAG = {"kostraeg_2021": dt.date(2023, 1, 1),
            "kostbraeg_2025": dt.date(2026, 1, 1)}


def _pruefpunkte():
    for stand in lade_tabelle()["staende"]:
        for wert, gebuehr in stand["pruefpunkte_anlage_2"].items():
            if wert != "hinweis":
                yield stand["id"], wert, gebuehr


@pytest.mark.parametrize("stand_id,wert,erwartet", list(_pruefpunkte()))
def test_anlage_2_stuetzpunkte_beider_staende(stand_id, wert, erwartet):
    r, stand = einfachgebuehr(wert, STICHTAG[stand_id])
    assert stand["id"] == stand_id
    assert str(r.einfachgebuehr) == erwartet, f"{stand_id} wert={wert}"


def test_anlage_2_vollstaendig_hinterlegt():
    # 42 Tabellenzeilen je Stand (500 € bis 500.000 €), wie im Gesetz.
    for stand in lade_tabelle()["staende"]:
        assert len(stand["pruefpunkte_anlage_2"]) - 1 == 42


def test_identisch_mit_gkg_formel():
    # Geprüft am 2026-10-22: § 28 Abs. 1 FamGKG und § 34 Abs. 1 GKG haben in
    # beiden Ständen dieselben Parameter (getrennte Dateien, gleiche Werte).
    from gkg.tabelle import lade_tabelle as gkg_tabelle
    schluessel = ("grundbetrag", "grundbetrag_bis_wert", "stufen",
                  "ueber_hoechstwert", "mindestbetrag", "gueltig_ab", "gueltig_bis")
    fam = {s["id"]: s for s in lade_tabelle()["staende"]}
    for s in gkg_tabelle()["staende"]:
        for k in schluessel:
            assert fam[s["id"]][k] == s[k], (s["id"], k)


@pytest.mark.parametrize("stichtag,stand_id", [
    (dt.date(2021, 1, 1), "kostraeg_2021"),
    (dt.date(2025, 5, 31), "kostraeg_2021"),
    (dt.date(2025, 6, 1), "kostbraeg_2025"),
])
def test_grenztage_der_staende(stichtag, stand_id):
    assert stand_fuer_stichtag(stichtag)["id"] == stand_id


def test_stichtag_vor_2021_lehnt_ab():
    with pytest.raises(FamGKGTabellenFehler, match="kein FamGKG-Tabellenstand"):
        stand_fuer_stichtag(dt.date(2020, 12, 31))
    with pytest.raises(FamGKGTabellenFehler, match="§ 63 Abs. 1 FamGKG"):
        einfachgebuehr("1000", dt.date(2019, 6, 1))


def test_mindestbetrag_15_euro_greift():
    # KV 1410 (0,3) aus 500 €: 0,3 x 40,00 = 12,00 € < 15,00 € -> 15,00 €.
    r = berechne("500", dt.date(2026, 1, 1), [{"nr": "1410"}])
    assert r.positionen[0].betrag == Decimal("15.00")
    assert r.positionen[0].mindestbetrag_gegriffen is True


def test_mindestbetrag_greift_nicht_knapp_darueber():
    # KV 1410 (0,3) aus 1.000 €: 0,3 x 61,00 = 18,30 € > 15,00 €.
    r = berechne("1000", dt.date(2026, 1, 1), [{"nr": "1410"}])
    assert r.positionen[0].betrag == Decimal("18.30")
    assert r.positionen[0].mindestbetrag_gegriffen is False


def test_hoechstwert_kappung_sichtbar():
    # § 33 Abs. 2 FamGKG: 40 Mio. -> 30 Mio.; 4138 + 590 x 210 = 128038,00.
    r = berechne("40000000", dt.date(2026, 1, 1), [{"nr": "1220"}])
    assert r.wert_gekappt is True
    assert r.verfahrenswert == Decimal("30000000.00")
    assert r.einfachgebuehr == Decimal("128038.00")
    assert any(s.norm == "§ 33 Abs. 2 FamGKG" for s in r.rechenkette)
    assert any("§ 33 Abs. 2 FamGKG" in w for w in r.warnungen)


def test_exakt_30_mio_keine_kappung():
    r = berechne("30000000", dt.date(2026, 1, 1), [{"nr": "1220"}])
    assert r.wert_gekappt is False
    assert r.warnungen == []


def test_tabelle_kappt_direkt():
    r, _ = einfachgebuehr("30000000.01", dt.date(2026, 1, 1))
    assert r.gegenstandswert == Decimal("30000000.00")
