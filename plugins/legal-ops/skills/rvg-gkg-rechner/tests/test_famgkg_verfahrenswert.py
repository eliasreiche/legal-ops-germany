"""Tests für core/calc/famgkg/verfahrenswert.py — Verfahrenswert nach
§§ 33 ff. FamGKG (P4).

Kein externes Orakel: borghei `legal_calc` (Referenz der übrigen
Rechner-Orakel, siehe test_orakel_borghei_rvg_gkg.py) kennt kein FamGKG —
geprüft am 2026-10-22 (scripts/legal_calc enthält nur rvg.py/gkg.py, kein
FamGKG-/Verfahrenswert-Modul). Orakel sind deshalb die im Gesetz selbst
stehenden Zahlen (web-verifiziert 2026-10-22 gegen gesetze-im-internet.de/
famgkg/__43.html, __44.html, __45.html, __50.html, __51.html, __42.html,
__35.html; Vorfassung KostRÄG 2021 über Wayback-Schnappschüsse) und
handgerechnete Fälle mit vollständigem Rechenweg im Docstring.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from famgkg.verfahrenswert import VerfahrenswertFehler, ermittle  # noqa: E402
from wertgebuehr_formel import WertgebuehrFehler  # noqa: E402

NEU = dt.date(2026, 1, 1)   # KostBRÄG 2025
ALT = dt.date(2023, 1, 1)   # KostRÄG 2021


def _verbund(ehe=None, folgesachen=None, **kw):
    d = {"ehesache": ehe or {"nettoeinkommen_monatlich": ["3000.00", "2000.00"]}}
    if folgesachen is not None:
        d["folgesachen"] = folgesachen
    d.update(kw)
    return d


# --------------------------------------------------------------------------
# § 43 FamGKG — Ehesache
# --------------------------------------------------------------------------

def test_43_ausgangswert():
    """3 x (3.000 + 2.000) = 15.000 € (§ 43 Abs. 2), zwischen 3.000 € und
    1 Mio. € (§ 43 Abs. 1 Satz 2) -> 15.000 €."""
    r = ermittle(_verbund(), NEU)
    assert r.gesamt == Decimal("15000.00")
    assert r.quelle == "executor"
    assert r.form == "verbund"
    ehe = r.gegenstaende[0]
    assert ehe.norm == "§ 43 FamGKG"
    assert [s.norm for s in ehe.rechenschritte] == [
        "§ 43 Abs. 2 FamGKG", "§ 43 Abs. 1 Satz 2 FamGKG"]


def test_43_mindestwert_greift():
    """3 x (500 + 0) = 1.500 € < 3.000 € -> 3.000 €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["500.00", "0"]}), NEU)
    assert r.gesamt == Decimal("3000.00")
    assert "unter dem Mindestwert" in r.gegenstaende[0].rechenschritte[-1].beschreibung


def test_43_hoechstwert_greift():
    """3 x (300.000 + 100.000) = 1,2 Mio. € > 1 Mio. € -> 1.000.000 €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["300000", "100000"]}), NEU)
    assert r.gesamt == Decimal("1000000.00")
    assert "über dem Höchstwert" in r.gegenstaende[0].rechenschritte[-1].beschreibung


def test_43_zuschlag_mit_begruendung_als_eingabe_markiert():
    """15.000 € + Zuschlag 5.000 € (Nutzereingabe) = 20.000 €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["3000", "2000"],
                           "zuschlag": "5000.00",
                           "begruendung": "Immobilienvermögen"}), NEU)
    ehe = r.gegenstaende[0]
    assert r.gesamt == Decimal("20000.00")
    assert ehe.quelle == "eingabe"
    zuschlag = [s for s in ehe.rechenschritte if "Ermessen" in s.norm]
    assert len(zuschlag) == 1 and zuschlag[0].quelle == "eingabe"
    assert any("Immobilienvermögen" in n for n in ehe.nutzereingaben)
    assert r.quelle == "eingabe"     # Gesamtwert enthält eine Nutzereingabe


def test_43_zuschlag_vor_hoechstwert():
    """3 x (200.000 + 100.000) = 900.000 € + 200.000 € = 1,1 Mio. € -> 1 Mio. €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["200000", "100000"],
                           "zuschlag": "200000", "begruendung": "Vermögen"}), NEU)
    assert r.gesamt == Decimal("1000000.00")


@pytest.mark.parametrize("ehe", [
    {"nettoeinkommen_monatlich": ["3000", "2000"], "zuschlag": "5000"},
    {"nettoeinkommen_monatlich": ["3000", "2000"], "begruendung": "x"},
    {"nettoeinkommen_monatlich": ["3000", "2000"], "zuschlag": "5000", "begruendung": " "},
    {"nettoeinkommen_monatlich": ["3000", "2000"], "zuschlag": "0", "begruendung": "x"},
])
def test_43_zuschlag_nur_mit_begruendung(ehe):
    with pytest.raises(VerfahrenswertFehler):
        ermittle(_verbund(ehe), NEU)


@pytest.mark.parametrize("netto", [["3000"], ["3000", "2000", "1000"], "5000", []])
def test_43_genau_zwei_ehegatten(netto):
    with pytest.raises(VerfahrenswertFehler, match="genau zwei"):
        ermittle(_verbund({"nettoeinkommen_monatlich": netto}), NEU)


def test_43_negatives_einkommen_abgelehnt():
    with pytest.raises(VerfahrenswertFehler, match=">= 0"):
        ermittle(_verbund({"nettoeinkommen_monatlich": ["-1", "2000"]}), NEU)


def test_43_float_einkommen_abgelehnt():
    with pytest.raises(WertgebuehrFehler, match="float"):
        ermittle(_verbund({"nettoeinkommen_monatlich": [3000.5, "2000"]}), NEU)


# --------------------------------------------------------------------------
# § 50 FamGKG — Versorgungsausgleich
# --------------------------------------------------------------------------

@pytest.mark.parametrize("anrechte,erwartet", [(1, "1500.00"), (2, "3000.00"), (3, "4500.00")])
def test_50_anrechte_im_verbund(anrechte, erwartet):
    """Basis 3 x (3.000 + 2.000) = 15.000 €; je Anrecht 10 % = 1.500 €."""
    r = ermittle(_verbund(folgesachen=[{"art": "versorgungsausgleich",
                                        "anzahl_anrechte": anrechte}]), NEU)
    assert r.gegenstaende[1].wert == Decimal(erwartet)
    assert r.gesamt == Decimal("15000.00") + Decimal(erwartet)


def test_50_mindestwert_greift():
    """Selbständig: 3 x (1.000 + 500) = 4.500 €; 1 Anrecht x 10 % = 450 € <
    1.000 € -> 1.000 € (§ 50 Abs. 1 Satz 2)."""
    r = ermittle({"gegenstaende": [{"art": "versorgungsausgleich", "anzahl_anrechte": 1,
                                    "nettoeinkommen_monatlich": ["1000", "500"]}]}, NEU)
    assert r.gesamt == Decimal("1000.00")
    assert "greift" in r.gegenstaende[0].rechenschritte[-1].beschreibung


def test_50_ausgleich_nach_scheidung_20_prozent():
    """Selbständig: 3 x (3.000 + 2.000) = 15.000 €; 2 Anrechte x 20 % = 6.000 €."""
    r = ermittle({"gegenstaende": [{"art": "versorgungsausgleich", "anzahl_anrechte": 2,
                                    "ausgleich_nach_scheidung": True,
                                    "nettoeinkommen_monatlich": ["3000", "2000"]}]}, NEU)
    assert r.gesamt == Decimal("6000.00")


def test_50_im_verbund_kein_eigenes_einkommen():
    with pytest.raises(VerfahrenswertFehler, match="im Verbund nicht"):
        ermittle(_verbund(folgesachen=[{"art": "versorgungsausgleich", "anzahl_anrechte": 1,
                                        "nettoeinkommen_monatlich": ["1", "1"]}]), NEU)


def test_50_selbstaendig_braucht_einkommen():
    with pytest.raises(VerfahrenswertFehler, match="nettoeinkommen_monatlich"):
        ermittle({"gegenstaende": [{"art": "versorgungsausgleich", "anzahl_anrechte": 1}]}, NEU)


@pytest.mark.parametrize("anzahl", [0, -1, True, "2", 1.0])
def test_50_anzahl_anrechte_ganzzahl_ab_1(anzahl):
    with pytest.raises(VerfahrenswertFehler):
        ermittle(_verbund(folgesachen=[{"art": "versorgungsausgleich",
                                        "anzahl_anrechte": anzahl}]), NEU)


def test_50_verbund_mit_festgesetzter_ehesache_ohne_einkommen():
    with pytest.raises(VerfahrenswertFehler, match="braucht 'ehesache.nettoeinkommen_monatlich'"):
        ermittle(_verbund({"verfahrenswert_festgesetzt": "20000"},
                          [{"art": "versorgungsausgleich", "anzahl_anrechte": 1}]), NEU)


def test_50_verbund_festgesetzte_ehesache_mit_einkommen_als_basis():
    """Ehesache festgesetzt 20.000 € (Eingabe); VA-Basis bleibt 3 x 5.000 =
    15.000 €, 1 Anrecht = 1.500 €; Gesamt 21.500 €."""
    r = ermittle(_verbund({"verfahrenswert_festgesetzt": "20000",
                           "nettoeinkommen_monatlich": ["3000", "2000"]},
                          [{"art": "versorgungsausgleich", "anzahl_anrechte": 1}]), NEU)
    assert r.gegenstaende[0].quelle == "eingabe"
    assert r.gesamt == Decimal("21500.00")


# --------------------------------------------------------------------------
# § 51 FamGKG — Unterhalt
# --------------------------------------------------------------------------

def test_51_zwoelf_monate_ohne_rueckstaende():
    """12 x 450 € = 5.400 €."""
    r = ermittle({"gegenstaende": [{"art": "kindesunterhalt", "monatsbetrag": "450.00"}]}, NEU)
    assert r.gesamt == Decimal("5400.00")
    assert [s.norm for s in r.gegenstaende[0].rechenschritte] == ["§ 51 Abs. 1 Satz 1 FamGKG"]


def test_51_mit_rueckstaenden():
    """12 x 450 € = 5.400 € + bei Einreichung fällig 1.350 € = 6.750 €."""
    r = ermittle({"gegenstaende": [{"art": "ehegattenunterhalt", "monatsbetrag": "450.00",
                                    "rueckstaende": "1350.00"}]}, NEU)
    assert r.gesamt == Decimal("6750.00")
    assert r.gegenstaende[0].rechenschritte[-1].norm == "§ 51 Abs. 2 Satz 1 FamGKG"


def test_51_befristete_forderung_hoechstens_gesamtbetrag():
    """Nur 6 Monatsbeträge gefordert: 6 x 450 € = 2.700 €."""
    r = ermittle({"gegenstaende": [{"art": "kindesunterhalt", "monatsbetrag": "450",
                                    "anzahl_monate": 6}]}, NEU)
    assert r.gesamt == Decimal("2700.00")


@pytest.mark.parametrize("monate", [0, 13, True])
def test_51_anzahl_monate_grenzen(monate):
    with pytest.raises(VerfahrenswertFehler):
        ermittle({"gegenstaende": [{"art": "kindesunterhalt", "monatsbetrag": "450",
                                    "anzahl_monate": monate}]}, NEU)


@pytest.mark.parametrize("feld,wert", [("monatsbetrag", "-1"), ("monatsbetrag", "0"),
                                       ("rueckstaende", "-5")])
def test_51_negative_betraege(feld, wert):
    g = {"art": "kindesunterhalt", "monatsbetrag": "450"}
    g[feld] = wert
    with pytest.raises(VerfahrenswertFehler):
        ermittle({"gegenstaende": [g]}, NEU)


# --------------------------------------------------------------------------
# § 45 FamGKG — Kindschaftssache (selbständig), versioniert
# --------------------------------------------------------------------------

@pytest.mark.parametrize("gegenstand,nr", [("sorge", "Nr. 1"), ("umgang", "Nr. 2"),
                                           ("auskunft", "Nr. 3"), ("herausgabe", "Nr. 4")])
def test_45_festwert_neu(gegenstand, nr):
    r = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": gegenstand}]}, NEU)
    assert r.gesamt == Decimal("5000.00")
    assert r.gegenstaende[0].norm == f"§ 45 Abs. 1 {nr} FamGKG"


def test_45_festwert_alt():
    r = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "umgang"}]}, ALT)
    assert r.gesamt == Decimal("4000.00")


def test_45_grenztag_stand():
    vorher = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge"}]},
                      dt.date(2025, 5, 31))
    nachher = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge"}]},
                       dt.date(2025, 6, 1))
    assert (vorher.gesamt, nachher.gesamt) == (Decimal("4000.00"), Decimal("5000.00"))


def test_45_sorge_und_umgang_je_ein_festwert():
    r = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge"},
                                   {"art": "kindschaftssache", "gegenstand": "umgang"}]}, NEU)
    assert r.gesamt == Decimal("10000.00")
    assert r.rechenkette[-1].norm == "§ 33 Abs. 1 Satz 1 FamGKG"


def test_45_dieselbe_kindschaftssache_doppelt_abgelehnt():
    with pytest.raises(VerfahrenswertFehler, match="mehrere Kinder"):
        ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge"},
                                   {"art": "kindschaftssache", "gegenstand": "sorge"}]}, NEU)


def test_45_unbekannter_gegenstand():
    with pytest.raises(VerfahrenswertFehler, match="gegenstand"):
        ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "vormundschaft"}]}, NEU)


# --------------------------------------------------------------------------
# § 35, § 42 Abs. 3 FamGKG
# --------------------------------------------------------------------------

def test_35_geldforderung():
    r = ermittle({"gegenstaende": [{"art": "geldforderung", "betrag": "48250.50"}]}, NEU)
    assert r.gesamt == Decimal("48250.50")
    assert r.gegenstaende[0].norm == "§ 35 FamGKG"


def test_42_auffangwert():
    r = ermittle({"gegenstaende": [{"art": "auffangwert"}]}, NEU)
    assert r.gesamt == Decimal("5000.00")
    assert r.gegenstaende[0].norm == "§ 42 Abs. 3 FamGKG"


def test_35_plus_42_zusammengerechnet():
    r = ermittle({"gegenstaende": [{"art": "geldforderung", "betrag": "10000"},
                                   {"art": "auffangwert"}]}, NEU)
    assert r.gesamt == Decimal("15000.00")


# --------------------------------------------------------------------------
# § 44 FamGKG — Verbund
# --------------------------------------------------------------------------

def test_44_kindschaftsfolgesache_prozentsatz():
    """Ehesache 15.000 €; Erhöhung 20 % = 3.000 € (unter 5.000 €); Gesamt 18.000 €."""
    r = ermittle(_verbund(folgesachen=[{"art": "kindschaftssache", "gegenstand": "sorge"}]), NEU)
    assert r.gegenstaende[1].wert == Decimal("3000.00")
    assert r.gesamt == Decimal("18000.00")
    assert "greift nicht" in r.gegenstaende[1].rechenschritte[0].beschreibung


def test_44_kindschaftsfolgesache_hoechstbetrag_greift_neu():
    """Ehesache 3 x (6.000 + 4.000) = 30.000 €; 20 % = 6.000 € > 5.000 € ->
    5.000 €; Gesamt 35.000 €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["6000", "4000"]},
                          [{"art": "kindschaftssache", "gegenstand": "umgang"}]), NEU)
    assert r.gegenstaende[1].wert == Decimal("5000.00")
    assert r.gesamt == Decimal("35000.00")


def test_44_kindschaftsfolgesache_hoechstbetrag_alt():
    """KostRÄG 2021: Höchstbetrag 4.000 € -> 30.000 € + 4.000 € = 34.000 €."""
    r = ermittle(_verbund({"nettoeinkommen_monatlich": ["6000", "4000"]},
                          [{"art": "kindschaftssache", "gegenstand": "umgang"}]), ALT)
    assert r.gesamt == Decimal("34000.00")


def test_44_zwei_kindschaftsfolgesachen_je_erhoehung():
    """Sorge + Umgang: 15.000 € + 2 x 3.000 € = 21.000 €."""
    r = ermittle(_verbund(folgesachen=[{"art": "kindschaftssache", "gegenstand": "sorge"},
                                       {"art": "kindschaftssache", "gegenstand": "umgang"}]), NEU)
    assert r.gesamt == Decimal("21000.00")


def test_44_auskunft_keine_folgesache():
    with pytest.raises(VerfahrenswertFehler, match="§ 137 Abs. 3 FamFG"):
        ermittle(_verbund(folgesachen=[{"art": "kindschaftssache", "gegenstand": "auskunft"}]), NEU)


def test_44_verbund_voll():
    """Ehesache 15.000 + VA 2 Anrechte 3.000 + Kindesunterhalt 12 x 450 =
    5.400 + Kindschaft (Sorge) 3.000 = 26.400 €."""
    r = ermittle(_verbund(folgesachen=[
        {"art": "versorgungsausgleich", "anzahl_anrechte": 2},
        {"art": "kindesunterhalt", "monatsbetrag": "450"},
        {"art": "kindschaftssache", "gegenstand": "sorge"}]), NEU)
    assert r.gesamt == Decimal("26400.00")
    assert r.rechenkette[-1].norm == "§ 44 Abs. 1, 2 FamGKG"


def test_44_ohne_folgesachen():
    r = ermittle(_verbund(folgesachen=[]), NEU)
    assert r.gesamt == Decimal("15000.00")


# --------------------------------------------------------------------------
# verfahrenswert_festgesetzt
# --------------------------------------------------------------------------

def test_festgesetzt_je_gegenstand_schlaegt_berechnung():
    r = ermittle({"gegenstaende": [{"art": "kindschaftssache", "gegenstand": "sorge",
                                    "verfahrenswert_festgesetzt": "7000"}]}, NEU)
    g = r.gegenstaende[0]
    assert r.gesamt == Decimal("7000.00")
    assert r.quelle == "eingabe"
    assert g.quelle == "eingabe"
    assert g.rechenschritte[0].quelle == "eingabe"


def test_festgesetzt_kindschaftsfolgesache_ist_erhoehungsbetrag():
    r = ermittle(_verbund(folgesachen=[{"art": "kindschaftssache", "gegenstand": "sorge",
                                        "verfahrenswert_festgesetzt": "1000"}]), NEU)
    assert r.gesamt == Decimal("16000.00")
    assert "§ 44 Abs. 3 FamGKG" in r.gegenstaende[1].norm


def test_festgesetzt_fuer_das_ganze():
    r = ermittle(_verbund(verfahrenswert_festgesetzt="40000"), NEU)
    assert r.gesamt == Decimal("40000.00")
    assert r.quelle == "eingabe"
    assert r.rechenkette[-1].quelle == "eingabe"
    assert "15000.00" in r.rechenkette[-1].beschreibung   # berechneter Wert bleibt sichtbar


def test_festgesetzt_allein():
    r = ermittle({"verfahrenswert_festgesetzt": "12345.67"}, NEU)
    assert (r.gesamt, r.form, r.quelle) == (Decimal("12345.67"), "festgesetzt", "eingabe")


def test_festgesetzt_neben_berechnungsfeldern_abgelehnt():
    with pytest.raises(VerfahrenswertFehler, match="neben 'verfahrenswert_festgesetzt'"):
        ermittle({"gegenstaende": [{"art": "geldforderung", "betrag": "1",
                                    "verfahrenswert_festgesetzt": "7000"}]}, NEU)


def test_festgesetzt_ehesache_mit_zuschlag_abgelehnt():
    with pytest.raises(VerfahrenswertFehler, match="schließen sich aus"):
        ermittle(_verbund({"verfahrenswert_festgesetzt": "20000", "zuschlag": "1",
                           "begruendung": "x"}), NEU)


# --------------------------------------------------------------------------
# Strukturfehler
# --------------------------------------------------------------------------

@pytest.mark.parametrize("angaben,muster", [
    ({"ehesache": {"nettoeinkommen_monatlich": ["1", "1"]}, "gegenstaende": []}, "nicht beides"),
    ({"folgesachen": []}, "nur im Verbund"),
    ({}, "braucht"),
    ({"gegenstaende": []}, "nichtleere Liste"),
    ({"gegenstaende": [{"art": "zugewinn"}]}, "unbekannt"),
    ({"gegenstaende": [{"art": "ehesache"}]}, "Verbund-Form"),
    ({"gegenstaende": [{"art": "auffangwert", "wert": "1"}]}, "unbekanntes Feld"),
    ({"ehesache": {"nettoeinkommen_monatlich": ["1", "1"], "netto": "1"}}, "unbekanntes Feld"),
    ({"verbund": {}}, "unbekanntes Feld"),
    ("kaputt", "JSON-Objekt"),
])
def test_strukturfehler(angaben, muster):
    with pytest.raises(VerfahrenswertFehler, match=muster):
        ermittle(angaben, NEU)


def test_stichtag_vor_2021():
    with pytest.raises(WertgebuehrFehler, match="kein FamGKG-Tabellenstand"):
        ermittle({"gegenstaende": [{"art": "auffangwert"}]}, dt.date(2020, 1, 1))
