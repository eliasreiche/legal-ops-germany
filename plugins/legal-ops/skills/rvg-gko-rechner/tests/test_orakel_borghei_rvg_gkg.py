"""Orakel-Tests gegen borghei/AI-Skills-German-Law (P4).

Quelle der erwarteten Werte: https://github.com/borghei/AI-Skills-German-Law,
`scripts/legal_calc/tests.py` (Klassen `TestRVGLogik`, `TestGKGLogik`,
`TestGeshippteTabellen`) sowie `scripts/legal_calc/data/{rvg,gkg}_tabelle.json`.
Es wurde KEIN borghei-Code ausgeführt oder importiert — die dort
dokumentierten Erwartungswerte sind hier als unabhängiges Orakel gegen
unsere eigene Implementierung übertragen (Attribution: siehe NOTICE im
Repo-Root).

Übertragungs-Anpassungen (API-/Datenmodell-Unterschiede, keine inhaltlichen
Abweichungen):

* borghei modelliert die Gebührentabelle als flache Stufenliste
  `[[bis_wert, Gebühr], ...]` (direkter Tabellen-Lookup, „aufrunden auf die
  nächste Stufe"). Unser Rechner implementiert stattdessen die gesetzliche
  Stufenformel aus § 13 Abs. 1 RVG / § 34 Abs. 1 GKG selbst (Grundbetrag +
  Zuschlag je angefangenem Schritt, gestaffelt). Borgheis synthetische
  Testtabellen (`TestRVGLogik.SYNTH`, `TestGKGLogik.SYNTH`) wurden für die
  Übertragung in eine formeläquivalente Grundbetrag+Stufen-Tabelle
  umgerechnet, die an denselben Prüfwerten (1/500/501/5000/5001/7000 EUR
  bzw. 700/6000 EUR) exakt dieselben Ergebnisse liefert — Umrechnung
  nachvollziehbar im Kommentar über der jeweiligen SYNTH-Tabelle.
* borghei prüft `float`-Gleichheit (`assertEqual` auf `float`-Werten); wir
  rechnen ausschließlich mit `Decimal` (CONVENTIONS.md P3) und vergleichen
  gegen `Decimal`-Literale.
* borgheis `TestGeshippteTabellen` prüft Struktur-Invarianten der
  geshippten Tabelle (aufsteigende Werte, monoton steigende Gebühren,
  positive Zuschläge). Unsere Tabellendaten speichern Grundbetrag +
  Stufen-Zuschläge statt einer flachen Werteliste — die Invariante ist auf
  unsere Datenform übertragen (aufsteigende `bis_wert`, positive
  `schritt`/`zuschlag`) und zusätzlich operational geprüft: die aus der
  Formel berechnete 1,0-Gebühr steigt über eine aufsteigende Wertreihe
  streng monoton.

**Wichtigste dokumentierte Abweichung (P4-Pflicht):** borgheis geshippte
Tabellen (`rvg_tabelle.json`/`gkg_tabelle.json`) tragen Stand `"2025-06-01"`
(`_hinweis: "Werte nach KostBRÄG 2025"`) — borghei **kennt den
KostBRÄG-2025-Stand also**, aber **nur diesen einen**. borghei hat keine
Stichtag-/Versionierungslogik (kein Auftragsdatum- oder Anhängigkeits-
Parameter in `cli.py` / `rvg.berechne` / `gkg.berechne`) und kann daher
Aufträge/Verfahren vor dem 01.06.2025 nicht nach der damals geltenden
Fassung (KostRÄG 2021) berechnen — ein Nutzer bekäme für eine
Altangelegenheit unbemerkt den falschen (zu hohen) Tabellenstand; borghei
weist im Modul-Docstring selbst auf diese „Versionsdrift" hin. Unser
Rechner unterstützt beide Stände mit Stichtag-basierter Auswahl (§ 60
Abs. 1 RVG / § 71 Abs. 1 GKG) und weist den angewendeten Stand im Report
aus. Für den von borghei abgedeckten Zeitraum (ab 01.06.2025) liefern beide
Rechner identische 1,0-Gebühren (siehe test_orakel_geshippte_werte_*).

Weitere dokumentierte Unterschiede (keine Zahlenabweichungen):
* borghei rundet mit `round()` auf float (Bankers' Rounding); wir kaufmännisch
  mit Decimal/ROUND_HALF_UP (§ 34 Abs. 2 S. 2 GKG). An den geprüften
  Stützpunkten identisch, im Grenzfall x,xx5 kann float-`round()` abweichen.
* borghei kennt keinen Mindestbetrag (§ 13 Abs. 3 RVG / § 34 Abs. 2 S. 1 GKG,
  15 EUR; KV 1100: 36/38 EUR) — wir schon (siehe test_gkg_rechner.py).
* borghei hat keine Anrechnung Vorbem. 3 Abs. 4 VV RVG, keine
  Erhöhungsgebühr Nr. 1008, keine Wert-Kappung (§ 22 Abs. 2 RVG /
  § 39 Abs. 2 GKG, bei uns als Kappung mit Rechenketten-Ausweis) und kein
  Angelegenheits-Konzept (Teil-2-/Teil-3-Trennung mit je eigener
  Auslagenpauschale Nr. 7002 und eigener USt-Basis).
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from wertgebuehr_formel import WertgebuehrFehler, einfachgebuehr  # noqa: E402
from rvg.tabelle import lade_tabelle as rvg_lade_tabelle  # noqa: E402
from gkg.tabelle import lade_tabelle as gkg_lade_tabelle  # noqa: E402
from rvg.rechner import berechne as rvg_berechne  # noqa: E402
from gkg.rechner import berechne as gkg_berechne  # noqa: E402

STICHTAG_AKTUELL = dt.date(2026, 1, 1)  # liegt im borghei-Zeitraum (>= 01.06.2025)


# --------------------------------------------------------------------------
# Orakel: TestRVGLogik (borghei tests.py) — formeläquivalente SYNTH-Tabelle
# --------------------------------------------------------------------------
#
# borghei SYNTH: stufen=[[500,49.0],[1000,88.0],[5000,300.0]],
#                ueber_hoechstwert={schritt:1000, zuschlag:10.0}
#
# Äquivalente Grundbetrag+Stufen-Tabelle (nachgerechnet):
#   Grundbetrag 49,0 bis 500        -> 500:  49,0            (borghei: 49,0)
#   Stufe bis 1000, Schritt 500, Zuschlag 39,0 (=88,0-49,0)
#       -> 501..1000: 49,0+39,0 = 88,0                       (borghei: 88,0)
#   Stufe bis 5000, Schritt 4000, Zuschlag 212,0 (=300,0-88,0)
#       -> 1001..5000: 88,0+212,0 = 300,0                    (borghei: 300,0)
#   über Höchstwert: Schritt 1000, Zuschlag 10,0
#       -> 5001: 310,0 / 7000: 320,0                         (borghei: dito)
#
# (borgheis flache Liste hat zwischen 1000 und 5000 keine Zwischenstufen —
#  ein einzelner 4000er-Schritt bildet das exakt ab.)

RVG_SYNTH_STAND = {
    "grundbetrag": "49.0", "grundbetrag_bis_wert": "500",
    "stufen": [
        {"bis_wert": "1000", "schritt": "500", "zuschlag": "39.0"},
        {"bis_wert": "5000", "schritt": "4000", "zuschlag": "212.0"},
    ],
    "ueber_hoechstwert": {"schritt": "1000", "zuschlag": "10.0"},
    "mindestbetrag": "15.00",
}


def test_orakel_rvg_aufrundung_wertstufe():
    # borghei: TestRVGLogik.test_aufrundung_wertstufe
    assert einfachgebuehr(Decimal("1"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("49.00")
    assert einfachgebuehr(Decimal("500"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("49.00")
    assert einfachgebuehr(Decimal("501"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("88.00")
    assert einfachgebuehr(Decimal("5000"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("300.00")


def test_orakel_rvg_ueber_hoechstwert():
    # borghei: TestRVGLogik.test_ueber_hoechstwert —
    # 5001 -> 1 angefangener 1000er-Schritt -> 300+10; 7000 -> 2 -> 320.
    assert einfachgebuehr(Decimal("5001"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("310.00")
    assert einfachgebuehr(Decimal("7000"), RVG_SYNTH_STAND).einfachgebuehr == Decimal("320.00")


def test_orakel_rvg_negativ():
    # borghei: TestRVGLogik.test_negativ — Gegenstandswert 0 ist Fehler.
    with pytest.raises(WertgebuehrFehler):
        einfachgebuehr(Decimal("0"), RVG_SYNTH_STAND)


def test_orakel_rvg_berechnungslogik_invarianten():
    # borghei: TestRVGLogik.test_berechnungslogik_invarianten — gegen die
    # echte (geshippte) Tabelle, nur Logik-Invarianten geprüft:
    # Position = Einfachgebühr x Satz, Pauschale = min(20 %, 20 EUR),
    # brutto = netto x 1,19. (Übertragung: unser Rechner gruppiert in
    # Angelegenheiten; borgheis Fall — Verfahrens- + Terminsgebühr, beide
    # Teil 3 VV — ist EINE Angelegenheit.)
    r = rvg_berechne("10000", STICHTAG_AKTUELL, [
        {"bezeichnung": "Rechtsstreit", "tatbestaende": [
            {"nr": "3100"}, {"nr": "3104"}]}])
    eg = r.einfachgebuehr
    a = r.angelegenheiten[0]
    pos = {p.nr: p for p in a.positionen}
    assert pos["3100"].betrag == (eg * Decimal("1.3")).quantize(Decimal("0.01"))
    assert pos["3104"].betrag == (eg * Decimal("1.2")).quantize(Decimal("0.01"))
    assert a.zwischensumme_gebuehren == pos["3100"].betrag + pos["3104"].betrag
    erwartet_pauschale = min(
        (a.zwischensumme_gebuehren * Decimal("0.20")).quantize(Decimal("0.01")),
        Decimal("20.00"))
    assert a.auslagenpauschale == erwartet_pauschale
    assert a.gesamt == (a.netto * Decimal("1.19")).quantize(Decimal("0.01"))


# --------------------------------------------------------------------------
# Orakel: TestGKGLogik (borghei tests.py) — formeläquivalente SYNTH-Tabelle
# --------------------------------------------------------------------------
#
# borghei SYNTH: stufen=[[500,38.0],[1000,58.0],[5000,161.0]],
#                ueber_hoechstwert={schritt:1000, zuschlag:20.0}
#
# Äquivalente Grundbetrag+Stufen-Tabelle:
#   Grundbetrag 38,0 bis 500         -> 500:  38,0           (borghei: 38,0)
#   Stufe bis 1000, Schritt 500, Zuschlag 20,0 (=58,0-38,0)
#       -> 700 (1 angefangener Schritt): 58,0                (borghei: 58,0)
#   Stufe bis 5000, Schritt 4000, Zuschlag 103,0 (=161,0-58,0)
#       -> 5000: 161,0                                       (borghei: 161,0)
#   über Höchstwert: Schritt 1000, Zuschlag 20,0
#       -> 6000: 181,0                                       (borghei: 161+20)

GKG_SYNTH_STAND = {
    "grundbetrag": "38.0", "grundbetrag_bis_wert": "500",
    "stufen": [
        {"bis_wert": "1000", "schritt": "500", "zuschlag": "20.0"},
        {"bis_wert": "5000", "schritt": "4000", "zuschlag": "103.0"},
    ],
    "ueber_hoechstwert": {"schritt": "1000", "zuschlag": "20.0"},
    "mindestbetrag": "15.00",
}


def test_orakel_gkg_aufrundung():
    # borghei: TestGKGLogik.test_aufrundung
    assert einfachgebuehr(Decimal("700"), GKG_SYNTH_STAND).einfachgebuehr == Decimal("58.00")
    assert einfachgebuehr(Decimal("6000"), GKG_SYNTH_STAND).einfachgebuehr == Decimal("181.00")


def test_orakel_gkg_faktor():
    # borghei: TestGKGLogik.test_faktor — Gebühr = Einfachgebühr x Satz,
    # gegen die echte (geshippte) Tabelle, KV 1210 (Satz 3,0).
    r = gkg_berechne("10000", STICHTAG_AKTUELL, [{"nr": "1210"}])
    assert r.positionen[0].betrag == (r.einfachgebuehr * Decimal("3.0")).quantize(Decimal("0.01"))


# --------------------------------------------------------------------------
# Orakel: TestGeshippteTabellen (borghei tests.py) — Struktur-Invarianten,
# übertragen auf unser Grundbetrag+Stufen-Datenmodell.
# --------------------------------------------------------------------------

def _pruefe_struktur(tab: dict) -> None:
    assert len(tab["staende"]) >= 2, "beide Tabellenstände müssen vorhanden sein"
    for stand in tab["staende"]:
        assert stand.get("id") and stand.get("gueltig_ab") and stand.get("fundstelle")
        assert Decimal(stand["grundbetrag"]) > 0
        assert Decimal(stand["mindestbetrag"]) > 0
        werte = [Decimal(s["bis_wert"]) for s in stand["stufen"]]
        assert werte == sorted(werte), f"{stand['id']}: bis_wert muss aufsteigend sein"
        assert len(werte) == len(set(werte)), f"{stand['id']}: bis_wert doppelt"
        for s in stand["stufen"]:
            assert Decimal(s["schritt"]) > 0
            assert Decimal(s["zuschlag"]) > 0
        assert Decimal(stand["ueber_hoechstwert"]["schritt"]) > 0
        assert Decimal(stand["ueber_hoechstwert"]["zuschlag"]) > 0


def test_orakel_rvg_tabelle_struktur():
    # borghei: TestGeshippteTabellen.test_rvg_tabelle
    _pruefe_struktur(rvg_lade_tabelle())


def test_orakel_gkg_tabelle_struktur():
    # borghei: TestGeshippteTabellen.test_gkg_tabelle
    _pruefe_struktur(gkg_lade_tabelle())


@pytest.mark.parametrize("stand_id", ["kostraeg_2021", "kostbraeg_2025"])
def test_orakel_rvg_monoton_steigend(stand_id):
    # Operationale Entsprechung zu borgheis "Gebühren müssen monoton
    # steigen" — bei uns nicht direkt aus der Datenform ablesbar (keine
    # flache Werteliste), daher über die Formel selbst geprüft.
    tab = rvg_lade_tabelle()
    stand = next(s for s in tab["staende"] if s["id"] == stand_id)
    werte = [Decimal(w) for w in
             ("100", "500.01", "2000.01", "10000.01", "25000.01",
              "50000.01", "200000.01", "500000.01", "600000")]
    gebuehren = [einfachgebuehr(w, stand).einfachgebuehr for w in werte]
    assert gebuehren == sorted(gebuehren)
    assert len(set(gebuehren)) == len(gebuehren), "Gebühren dürfen nicht stagnieren"


@pytest.mark.parametrize("stand_id", ["kostraeg_2021", "kostbraeg_2025"])
def test_orakel_gkg_monoton_steigend(stand_id):
    tab = gkg_lade_tabelle()
    stand = next(s for s in tab["staende"] if s["id"] == stand_id)
    werte = [Decimal(w) for w in
             ("100", "500.01", "2000.01", "10000.01", "25000.01",
              "50000.01", "200000.01", "500000.01", "600000")]
    gebuehren = [einfachgebuehr(w, stand).einfachgebuehr for w in werte]
    assert gebuehren == sorted(gebuehren)
    assert len(set(gebuehren)) == len(gebuehren)


# --------------------------------------------------------------------------
# Orakel: geshippte Werte — Abgleich mit borgheis data/{rvg,gkg}_tabelle.json
# (Stand "2025-06-01" = unser "kostbraeg_2025") an Stützpunkten aus borgheis
# Datendateien. Bestätigt: für den von borghei abgedeckten Zeitraum liefern
# beide Implementierungen identische 1,0-Gebühren.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wert,erwartet", [
    ("500", "51.50"), ("1000", "93.00"), ("1500", "134.50"), ("2000", "176.00"),
    ("3000", "235.50"), ("4000", "295.00"), ("50000", "1357.00"),
    ("500000", "3752.00"),
])
def test_orakel_geshippte_werte_rvg(wert, erwartet):
    # borghei: data/rvg_tabelle.json (KostBRÄG 2025, ueber_hoechstwert
    # schritt=50000/zuschlag=175.0 identisch mit unserem Stand).
    tab = rvg_lade_tabelle()
    stand = next(s for s in tab["staende"] if s["id"] == "kostbraeg_2025")
    assert einfachgebuehr(Decimal(wert), stand).einfachgebuehr == Decimal(erwartet)


@pytest.mark.parametrize("wert,erwartet", [
    ("500", "40.00"), ("1000", "61.00"), ("1500", "82.00"), ("2000", "103.00"),
    ("3000", "125.50"), ("4000", "148.00"), ("50000", "638.00"),
    ("500000", "4138.00"),
])
def test_orakel_geshippte_werte_gkg(wert, erwartet):
    # borghei: data/gkg_tabelle.json (KostBRÄG 2025, ueber_hoechstwert
    # schritt=50000/zuschlag=210.0 identisch mit unserem Stand).
    tab = gkg_lade_tabelle()
    stand = next(s for s in tab["staende"] if s["id"] == "kostbraeg_2025")
    assert einfachgebuehr(Decimal(wert), stand).einfachgebuehr == Decimal(erwartet)


# --------------------------------------------------------------------------
# Dokumentierte Abweichung als Test: borghei hat nur einen Tabellenstand —
# unser Rechner liefert für einen Alt-Stichtag den KostRÄG-2021-Stand, den
# borghei nicht kennt. (Erwartungswerte aus der amtlichen Anlage 2 in der
# Fassung des KostRÄG 2021, nicht aus borghei — borghei KANN diese Werte
# nicht liefern, genau das ist die Abweichung.)
# --------------------------------------------------------------------------

def test_abweichung_borghei_kennt_kostraeg_2021_nicht():
    r = rvg_berechne("10000", dt.date(2023, 6, 1), [
        {"bezeichnung": "Rechtsstreit", "tatbestaende": [{"nr": "3100"}]}])
    assert r.tabellenstand["id"] == "kostraeg_2021"
    assert r.einfachgebuehr == Decimal("614.00")   # borghei (Stand 2025-06-01) ergäbe 652,00
    g = gkg_berechne("10000", dt.date(2023, 6, 1), [{"nr": "1210"}])
    assert g.tabellenstand["id"] == "kostraeg_2021"
    assert g.einfachgebuehr == Decimal("266.00")   # borghei ergäbe 283,00
