"""Tests für core/calc/rvg/rechner.py — Positionen, Angelegenheiten,
Anrechnung, Erhöhung, Auslagenpauschale-Deckel, Wert-Kappung § 22 Abs. 2 RVG,
Rundung, Scope-Ablehnungen (P4; inkl. Regressionstests Review-Befunde 1/3/4).
"""
from __future__ import annotations

import copy
import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO / "plugins" / "legal-ops" / "core" / "calc"))

from rvg.rechner import (  # noqa: E402
    RVGEingabeFehler,
    WERT_HOECHSTGRENZE,
    berechne,
    lade_katalog,
)

STICHTAG = dt.date(2026, 1, 1)  # KostBRÄG 2025


def _b(tatbestaende, **kwargs):
    """Kurzform: eine einzelne Angelegenheit."""
    return berechne(kwargs.pop("streitwert", "10000"),
                    kwargs.pop("stichtag", STICHTAG),
                    [{"bezeichnung": "Test", "tatbestaende": tatbestaende}],
                    **kwargs)


def _erste(r):
    """Die (einzige) Angelegenheit eines Kurzform-Ergebnisses."""
    assert len(r.angelegenheiten) == 1
    return r.angelegenheiten[0]


# --------------------------------------------------------------------------
# Grundrechnung / Festsatz-Positionen
# --------------------------------------------------------------------------

def test_festsatz_positionen_korrekt_berechnet():
    r = _b([{"nr": "3100"}, {"nr": "3104"}])
    assert r.einfachgebuehr == Decimal("652.00")
    a = _erste(r)
    pos = {p.nr: p for p in a.positionen}
    assert pos["3100"].betrag == Decimal("847.60")   # 652,00 * 1,3
    assert pos["3104"].betrag == Decimal("782.40")   # 652,00 * 1,2
    assert a.zwischensumme_gebuehren == Decimal("1630.00")


def test_festsatz_satz_override_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="gesetzlich festgelegt"):
        _b([{"nr": "3100", "satz": "2.0"}])


def test_festsatz_satz_gleichlautend_erlaubt():
    r = _b([{"nr": "3100", "satz": "1.3"}])
    assert _erste(r).positionen[0].betrag == Decimal("847.60")


# --------------------------------------------------------------------------
# Satzrahmen-Position (2300)
# --------------------------------------------------------------------------

def test_2300_satz_pflicht():
    with pytest.raises(RVGEingabeFehler, match="Pflichtangabe"):
        _b([{"nr": "2300"}])


def test_2300_satz_ausserhalb_rahmen_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="Satzrahmen"):
        _b([{"nr": "2300", "satz": "2.6"}])
    with pytest.raises(RVGEingabeFehler, match="Satzrahmen"):
        _b([{"nr": "2300", "satz": "0.4"}])


def test_2300_ueber_regelsatz_erzeugt_hinweis():
    r = _b([{"nr": "2300", "satz": "1.5"}])
    assert any("umfangreich oder schwierig" in h
               for h in _erste(r).positionen[0].hinweise)


def test_2300_am_regelsatz_kein_hinweis():
    r = _b([{"nr": "2300", "satz": "1.3"}])
    assert _erste(r).positionen[0].hinweise == []


# --------------------------------------------------------------------------
# Befund 3 (Review): Angelegenheiten — Teil-2/Teil-3-Trennung, je eigene
# Auslagenpauschale und USt
# --------------------------------------------------------------------------

def test_befund3_teil2_und_teil3_in_einer_angelegenheit_abgelehnt():
    # Geschäftsgebühr (Teil 2 VV) + Verfahrensgebühr (Teil 3 VV) in derselben
    # Angelegenheit: Eingabefehler mit Verweis auf die Gruppierung — vor dem
    # Fix wurden beide still zusammengerechnet (eine 7002, eine USt-Basis).
    with pytest.raises(RVGEingabeFehler, match="verschiedene"):
        _b([{"nr": "2300", "satz": "1.3"}, {"nr": "3100"}])
    with pytest.raises(RVGEingabeFehler, match="angelegenheiten"):
        _b([{"nr": "3104"}, {"nr": "2300", "satz": "1.3"}])


def test_befund3_teil1_loest_keine_kollision_aus():
    # Teil-1-Gebühren (1000/1003/1008) entstehen neben den Gebühren der
    # anderen Teile (Vorbem. 1 VV RVG) — zulässig neben Teil 2 wie Teil 3.
    r1 = _b([{"nr": "3100"}, {"nr": "1000"}])
    assert len(_erste(r1).positionen) == 2
    r2 = _b([{"nr": "2300", "satz": "1.3"}, {"nr": "1000"}])
    assert len(_erste(r2).positionen) == 2


def test_befund3_zwei_angelegenheiten_je_eigene_pauschale_und_ust():
    # Kern des Befunds: je Angelegenheit eine eigene 7002-Pauschale (je bis
    # 20 €) und eine eigene USt-Basis — nicht eine gemeinsame.
    r = berechne("10000", STICHTAG, [
        {"bezeichnung": "Außergerichtliche Vertretung",
         "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
        {"bezeichnung": "Rechtsstreit erster Instanz",
         "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]},
    ])
    assert len(r.angelegenheiten) == 2
    a1, a2 = r.angelegenheiten
    assert a1.auslagenpauschale == Decimal("20.00")
    assert a2.auslagenpauschale == Decimal("20.00")   # 2 x 20 €, nicht 1 x
    assert a1.ust == (a1.netto * Decimal("0.19")).quantize(Decimal("0.01"))
    assert a2.ust == (a2.netto * Decimal("0.19")).quantize(Decimal("0.01"))
    assert r.gesamt_verguetung == a1.gesamt + a2.gesamt


def test_befund3_gesamtverguetung_als_summe_beschriftet():
    r = berechne("10000", STICHTAG, [
        {"bezeichnung": "A", "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
        {"bezeichnung": "B", "tatbestaende": [{"nr": "3100"}]},
    ])
    schritte = [s for s in r.rechenkette if s.norm == "Gesamtvergütung"]
    assert len(schritte) == 1
    assert "gleicher Gläubiger" in schritte[0].beschreibung


def test_befund3_flag_override_je_angelegenheit():
    r = berechne("10000", STICHTAG, [
        {"bezeichnung": "A", "tatbestaende": [{"nr": "2300", "satz": "1.3"}],
         "umsatzsteuer": False},
        {"bezeichnung": "B", "tatbestaende": [{"nr": "3100"}]},
    ])
    a, b = r.angelegenheiten
    assert a.ust == Decimal("0.00")
    assert b.ust > 0


# --------------------------------------------------------------------------
# Erhöhungsgebühr Nr. 1008 (weitere Auftraggeber), Kappung
# --------------------------------------------------------------------------

def test_1008_erhoehung_korrekt():
    r = _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 2}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["1008"].satz == Decimal("0.6")           # 2 * 0,3
    assert pos["1008"].betrag == Decimal("391.20")       # 652,00 * 0,6


def test_1008_kappung_auf_2_0():
    r = _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 10}])
    pos = {p.nr: p for p in _erste(r).positionen}
    assert pos["1008"].satz == Decimal("2.0")
    assert any("gekappt" in w for w in r.warnungen)


def test_1008_ohne_basisposition_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="erhoeht_position"):
        _b([{"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 1}])


def test_1008_weitere_auftraggeber_muss_int_sein():
    with pytest.raises(RVGEingabeFehler):
        _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": "zwei"}])
    with pytest.raises(RVGEingabeFehler):
        _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 0}])


# --------------------------------------------------------------------------
# Befund 1 (Review): Wert-Kappung § 22 Abs. 2 Satz 1 RVG
# --------------------------------------------------------------------------

def test_befund1_wert_ueber_30_mio_wird_gekappt():
    # 40 Mio -> gekappt auf 30 Mio; KostBRÄG 2025: 3752 + 590 x 175 = 107002.
    # Vor dem Fix: 142002,00 (ungekappt weitergerechnet) — Nr. 3100 damit
    # 45.500 € überhöht.
    r = _b([{"nr": "3100"}], streitwert="40000000")
    assert r.wert_gekappt is True
    assert r.streitwert == WERT_HOECHSTGRENZE
    assert r.streitwert_eingabe == Decimal("40000000")
    assert r.einfachgebuehr == Decimal("107002.00")
    assert _erste(r).positionen[0].betrag == Decimal("139102.60")  # x 1,3


def test_befund1_kappung_in_rechenkette_und_warnung():
    r = _b([{"nr": "3100"}], streitwert="30000000.01")
    assert r.wert_gekappt is True
    kappungs_schritte = [s for s in r.rechenkette
                         if s.norm == "§ 22 Abs. 2 Satz 1 RVG"]
    assert len(kappungs_schritte) == 1
    assert any("§ 22 Abs. 2 Satz 1 RVG" in w for w in r.warnungen)


def test_befund1_exakt_30_mio_keine_kappung():
    r = _b([{"nr": "3100"}], streitwert="30000000")
    assert r.wert_gekappt is False
    assert not any("§ 22" in s.norm for s in r.rechenkette)


def test_befund1_kappung_alter_tabellenstand():
    # KostRÄG 2021: 3539 + 590 x 165 = 100889,00.
    r = _b([{"nr": "3100"}], streitwert="40000000", stichtag=dt.date(2023, 1, 1))
    assert r.einfachgebuehr == Decimal("100889.00")


def test_befund1_1008_plus_ueber_30_mio_abgelehnt():
    # § 22 Abs. 2 Satz 2 RVG (je Auftraggeber 30 Mio., max. 100 Mio.) ist
    # nicht modelliert — Kombination 1008 + Wert > 30 Mio. wird abgelehnt,
    # statt möglicherweise falsch auf 30 Mio. zu kappen.
    with pytest.raises(RVGEingabeFehler, match=r"§ 22 Abs\. 2 Satz 2 RVG"):
        _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 1}],
           streitwert="40000000")


def test_befund1_1008_unter_30_mio_weiter_ok():
    r = _b([{"nr": "3100"},
            {"nr": "1008", "erhoeht_position": "3100", "weitere_auftraggeber": 1}],
           streitwert="29999999")
    assert r.wert_gekappt is False


# --------------------------------------------------------------------------
# Anrechnung Geschäftsgebühr auf Verfahrensgebühr (über zwei Angelegenheiten)
# --------------------------------------------------------------------------

def _anrechnungsfall(satz_2300="1.3", **kwargs):
    return berechne(kwargs.pop("streitwert", "10000"), STICHTAG, [
        {"bezeichnung": "Außergerichtliche Vertretung",
         "tatbestaende": [{"nr": "2300", "satz": satz_2300}]},
        {"bezeichnung": "Rechtsstreit erster Instanz",
         "tatbestaende": [{"nr": "3100"}]},
    ], anrechnung_2300_auf_3100=True, **kwargs)


def test_anrechnung_regelsatz_nicht_gedeckelt():
    # Geschäftsgebühr Satz 1,3 -> Anrechnungssatz 0,65 (< 0,75, kein Deckel).
    r = _anrechnungsfall()
    assert r.anrechnung["anrechnungssatz"] == "0.65"
    assert r.anrechnung["anrechnungsbetrag"] == "423.80"
    rechtsstreit = r.angelegenheiten[1]
    pos = {p.nr: p for p in rechtsstreit.positionen}
    assert pos["3100"].betrag == Decimal("423.80")   # 847,60 - 423,80


def test_anrechnung_nennt_beide_angelegenheiten():
    r = _anrechnungsfall()
    assert r.anrechnung["geschaeftsgebuehr_angelegenheit"] == "Außergerichtliche Vertretung"
    assert r.anrechnung["verfahrensgebuehr_angelegenheit"] == "Rechtsstreit erster Instanz"


def test_anrechnung_gedeckelt_bei_hohem_satz():
    # Geschäftsgebühr Satz 2,5 -> halbe = 1,25, gedeckelt auf 0,75.
    r = _anrechnungsfall(satz_2300="2.5")
    assert r.anrechnung["anrechnungssatz"] == "0.75"
    assert Decimal(r.anrechnung["anrechnungsbetrag"]) == Decimal("489.00")


def test_anrechnung_ohne_beide_positionen_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="anrechnung_2300_auf_3100"):
        _b([{"nr": "3100"}], anrechnung_2300_auf_3100=True)
    with pytest.raises(RVGEingabeFehler, match="anrechnung_2300_auf_3100"):
        _b([{"nr": "2300", "satz": "1.3"}], anrechnung_2300_auf_3100=True)


# --------------------------------------------------------------------------
# Auslagenpauschale-Deckel (Nr. 7002), Umsatzsteuer, Rundung, Mindestbetrag
# --------------------------------------------------------------------------

def test_auslagenpauschale_gedeckelt_bei_hoher_summe():
    r = _b([{"nr": "3100"}, {"nr": "3104"}])
    assert _erste(r).auslagenpauschale == Decimal("20.00")


def test_auslagenpauschale_nicht_gedeckelt_bei_niedriger_summe():
    r = _b([{"nr": "3100"}], streitwert="100")
    a = _erste(r)
    erwartet = min(a.zwischensumme_gebuehren * Decimal("0.20"), Decimal("20.00"))
    assert a.auslagenpauschale == erwartet.quantize(Decimal("0.01"))


def test_auslagenpauschale_abschaltbar():
    r = _b([{"nr": "3100"}], auslagenpauschale=False)
    assert _erste(r).auslagenpauschale == Decimal("0.00")


def test_umsatzsteuer_abschaltbar():
    r = _b([{"nr": "3100"}], umsatzsteuer=False)
    a = _erste(r)
    assert a.ust == Decimal("0.00")
    assert a.gesamt == a.netto


def test_umsatzsteuer_19_prozent():
    r = _b([{"nr": "3100"}])
    a = _erste(r)
    assert a.ust == (a.netto * Decimal("0.19")).quantize(Decimal("0.01"))
    assert a.gesamt == a.netto + a.ust


def test_mindestbetrag_realistisch_unerreichbar():
    # Der kleinste im Katalog vorkommende Satz ist 0,5 (Nr. 2300); selbst am
    # kleinsten Grundbetrag (49,00 EUR, KostRÄG 2021) ergibt das 24,50 EUR —
    # über dem Mindestbetrag von 15,00 EUR. Der Floor greift mit dem
    # aktuellen Katalog also nie über einen Festsatz/Satzrahmen allein;
    # dokumentiert hier bewusst, damit das nicht stillschweigend als Bug
    # missverstanden wird.
    r = _b([{"nr": "2300", "satz": "0.5"}], streitwert="1",
           stichtag=dt.date(2023, 1, 1))
    pos = _erste(r).positionen[0]
    assert pos.mindestbetrag_gegriffen is False
    assert pos.betrag == Decimal("24.50")


def test_mindestbetrag_greift_synthetisch():
    # Direkter Test des Floor-Mechanismus (§ 13 Abs. 3 RVG) über eine
    # synthetische Katalogposition mit sehr niedrigem Satz — der reale
    # VV-RVG-Katalog erreicht die Grenze nie (siehe Test oben), der
    # Mechanismus selbst muss trotzdem geprüft sein.
    kat = copy.deepcopy(lade_katalog())
    kat["positionen"]["9999"] = {
        "bezeichnung": "Testposition (synthetisch)", "norm": "Test",
        "art": "festsatz", "satz": "0.1", "vv_teil": 1}
    r = berechne("500", STICHTAG,
                 [{"bezeichnung": "T", "tatbestaende": [{"nr": "9999"}]}],
                 katalog=kat)
    pos = r.angelegenheiten[0].positionen[0]
    # 51,50 * 0,1 = 5,15 EUR -> unter dem Mindestbetrag von 15,00 EUR.
    assert pos.mindestbetrag_gegriffen is True
    assert pos.betrag == Decimal("15.00")


# --------------------------------------------------------------------------
# Scope-Ablehnungen und sonstige Eingabefehler
# --------------------------------------------------------------------------

def test_unbekannte_nr_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="nicht unterstützt"):
        _b([{"nr": "3102"}])   # Betragsrahmengebühr


def test_beratungshilfe_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="nicht unterstützt"):
        _b([{"nr": "2500"}])


def test_befund4_bekannt_liste_ohne_7002_7008():
    # Regressionstest Review-Befund 4: die "bekannt"-Liste der Fehlermeldung
    # darf 7002/7008 nicht als Tatbestände nennen (sie laufen über Flags).
    with pytest.raises(RVGEingabeFehler) as exc:
        _b([{"nr": "9999"}])
    meldung = str(exc.value)
    liste = meldung.split("bekannte Tatbestände:")[1].split(";")[0]
    assert "7002" not in liste
    assert "7008" not in liste
    assert "3100" in liste
    # ... aber die Flags werden erklärt:
    assert "auslagenpauschale" in meldung


def test_7002_als_tatbestand_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="Anfrage-Flags"):
        _b([{"nr": "3100"}, {"nr": "7002"}])


def test_doppelte_nr_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match="mehrfach"):
        _b([{"nr": "3100"}, {"nr": "3100"}])


def test_leere_tatbestaende_abgelehnt():
    with pytest.raises(RVGEingabeFehler):
        _b([])


def test_leere_angelegenheiten_abgelehnt():
    with pytest.raises(RVGEingabeFehler):
        berechne("10000", STICHTAG, [])


def test_negativer_streitwert_abgelehnt():
    with pytest.raises(RVGEingabeFehler, match=r"> 0"):
        _b([{"nr": "3100"}], streitwert="-500")
