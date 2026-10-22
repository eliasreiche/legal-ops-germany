"""Tests für die Festwerte §§ 47–49 FamGKG und die einstweilige Anordnung
§ 41 FamGKG in core/calc/famgkg/verfahrenswert.py (P4).

Orakel sind die im Gesetz stehenden Zahlen, web-verifiziert am 2026-10-22:
gesetze-im-internet.de/famgkg/__41.html, __47.html, __48.html, __49.html
(Stand KostBRÄG 2025) und Wayback-Schnappschüsse derselben Seiten vor dem
01.06.2025 (Stand KostRÄG 2021: __47.html 2025-03-19, __48.html 2025-05-03,
__49.html 2023-10-04, __41.html 2025-05-03); Fassungsvergleich buzer.de:
einzige Änderung seit 2015 ist KostBRÄG 2025 Art. 6 (mWv 01.06.2025).

  § 47 Abs. 1  § 169 Nr. 1, 4 FamFG   2.000 € -> 3.000 €; übrige 1.000 €
  § 48 Abs. 1  § 200 Abs. 1 Nr. 1     3.000 € -> 4.000 €; Nr. 2 4.000 € -> 5.000 €
  § 48 Abs. 2  § 200 Abs. 2 Nr. 1     2.000 €; Nr. 2 3.000 € (unverändert)
  § 49 Abs. 1  § 1 GewSchG / EU-GewSchVG 2.000 € -> 3.000 €; § 2 GewSchG 3.000 € -> 4.000 €
  § 41 Satz 2  Hälfte des für die Hauptsache bestimmten Werts (unverändert)

Folgesachen-Fähigkeit: § 137 Abs. 2 Satz 1 Nr. 3 FamFG (Ehewohnungs- und
Haushaltssachen, wenn eine Entscheidung für den Fall der Scheidung zu
treffen ist); Abstammungs- und Gewaltschutzsachen nennt § 137 FamFG nicht.
Einstweilige Anordnung = selbständiges Verfahren: § 51 Abs. 3 Satz 1 FamFG.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from conftest import CALC, lauf, schreibe  # noqa: E402
from famgkg.verfahrenswert import VerfahrenswertFehler, ermittle  # noqa: E402

EXECUTOR = CALC / "rvg" / "executor.py"

NEU = dt.date(2026, 1, 1)   # KostBRÄG 2025
ALT = dt.date(2023, 1, 1)   # KostRÄG 2021


def _selbst(*gegenstaende, **kw):
    return {"gegenstaende": list(gegenstaende), **kw}


def _verbund(*folgesachen):
    return {"ehesache": {"nettoeinkommen_monatlich": ["3000.00", "2000.00"]},
            "folgesachen": list(folgesachen)}


# --------------------------------------------------------------------------
# §§ 47–49 FamGKG — Festwerte je Fallgruppe, beide Stände
# --------------------------------------------------------------------------

FESTWERTE = [
    # art, fallgruppe, norm, KostRÄG 2021, KostBRÄG 2025
    ("abstammungssache", "169_nr_1_4", "§ 47 Abs. 1 FamGKG", "2000.00", "3000.00"),
    ("abstammungssache", "169_nr_2_3", "§ 47 Abs. 1 FamGKG", "1000.00", "1000.00"),
    ("ehewohnungssache", "200_abs_1_nr_1", "§ 48 Abs. 1 FamGKG", "3000.00", "4000.00"),
    ("ehewohnungssache", "200_abs_1_nr_2", "§ 48 Abs. 1 FamGKG", "4000.00", "5000.00"),
    ("haushaltssache", "200_abs_2_nr_1", "§ 48 Abs. 2 FamGKG", "2000.00", "2000.00"),
    ("haushaltssache", "200_abs_2_nr_2", "§ 48 Abs. 2 FamGKG", "3000.00", "3000.00"),
    ("gewaltschutzsache", "1_gewschg", "§ 49 Abs. 1 FamGKG", "2000.00", "3000.00"),
    ("gewaltschutzsache", "eu_gewschvg", "§ 49 Abs. 1 FamGKG", "2000.00", "3000.00"),
    ("gewaltschutzsache", "2_gewschg", "§ 49 Abs. 1 FamGKG", "3000.00", "4000.00"),
]


@pytest.mark.parametrize("art,fg,norm,alt,neu", FESTWERTE)
@pytest.mark.parametrize("stichtag,stand", [(ALT, "alt"), (NEU, "neu")])
def test_festwert_je_fallgruppe_und_stand(art, fg, norm, alt, neu, stichtag, stand):
    r = ermittle(_selbst({"art": art, "fallgruppe": fg}), stichtag)
    erwartet = Decimal(alt if stand == "alt" else neu)
    g = r.gegenstaende[0]
    assert r.gesamt == erwartet
    assert g.wert == erwartet
    assert g.norm == norm
    assert g.quelle == "executor" and r.quelle == "executor"
    assert [s.norm for s in g.rechenschritte] == [norm]
    assert fg in g.rechenschritte[0].beschreibung
    assert any("nie an" in h for h in g.hinweise)      # Fallgruppe nie angenommen
    assert "einstweilige_anordnung" not in g.as_dict()
    assert r.warnungen == []


def test_festwert_stichtagsgrenze_01_06_2025():
    """§ 63 Abs. 1 FamGKG: Einleitung 31.05.2025 -> KostRÄG 2021 (2.000 €),
    01.06.2025 -> KostBRÄG 2025 (3.000 €)."""
    e = _selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg"})
    assert ermittle(e, dt.date(2025, 5, 31)).gesamt == Decimal("2000.00")
    assert ermittle(e, dt.date(2025, 6, 1)).gesamt == Decimal("3000.00")


def test_mehrere_festwert_gegenstaende_zusammengerechnet():
    """§ 33 Abs. 1 Satz 1: Ehewohnung (§ 1361b BGB) 4.000 € + Haushalt
    (§ 1361a BGB) 2.000 € = 6.000 € (KostBRÄG 2025)."""
    r = ermittle(_selbst({"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_1"},
                         {"art": "haushaltssache", "fallgruppe": "200_abs_2_nr_1"}), NEU)
    assert r.gesamt == Decimal("6000.00")
    assert r.rechenkette[-1].norm == "§ 33 Abs. 1 Satz 1 FamGKG"


@pytest.mark.parametrize("art", ["abstammungssache", "ehewohnungssache",
                                 "haushaltssache", "gewaltschutzsache"])
@pytest.mark.parametrize("eintrag", [{}, {"fallgruppe": "uebrige"},
                                     {"fallgruppe": None}, {"fallgruppe": 1}])
def test_fallgruppe_fehlt_oder_unbekannt_exit2(art, eintrag):
    with pytest.raises(VerfahrenswertFehler, match="fallgruppe"):
        ermittle(_selbst({"art": art, **eintrag}), NEU)


def test_fallgruppe_auch_neben_festsetzung_pflicht():
    with pytest.raises(VerfahrenswertFehler, match="fallgruppe"):
        ermittle(_selbst({"art": "gewaltschutzsache",
                          "verfahrenswert_festgesetzt": "6000.00"}), NEU)


def test_festwert_unbekanntes_feld_exit2():
    with pytest.raises(VerfahrenswertFehler, match="billigkeit"):
        ermittle(_selbst({"art": "abstammungssache", "fallgruppe": "169_nr_1_4",
                          "billigkeit": "5000"}), NEU)


@pytest.mark.parametrize("art,fg", [("abstammungssache", "169_nr_1_4"),
                                    ("gewaltschutzsache", "1_gewschg"),
                                    ("gewaltschutzsache", "2_gewschg")])
def test_abstammung_gewaltschutz_im_verbund_exit2(art, fg):
    with pytest.raises(VerfahrenswertFehler, match="keine Folgesachen"):
        ermittle(_verbund({"art": art, "fallgruppe": fg}), NEU)


@pytest.mark.parametrize("art,fg", [("ehewohnungssache", "200_abs_1_nr_1"),
                                    ("haushaltssache", "200_abs_2_nr_1")])
def test_getrenntleben_fallgruppe_im_verbund_exit2(art, fg):
    """§ 137 Abs. 2 Satz 1 Nr. 3 FamFG: nur wenn eine Entscheidung für den
    Fall der Scheidung zu treffen ist — §§ 1361a/1361b BGB (Getrenntleben)
    sind keine Folgesachen."""
    with pytest.raises(VerfahrenswertFehler, match="Fall der Scheidung"):
        ermittle(_verbund({"art": art, "fallgruppe": fg}), NEU)


def test_ehewohnung_haushalt_als_folgesache_hinzugerechnet():
    """Verbund (KostBRÄG 2025): Ehesache 3 x (3.000 + 2.000) = 15.000 € +
    Ehewohnung § 1568a BGB 5.000 € + Haushalt § 1568b BGB 3.000 € = 23.000 €
    (§ 44 Abs. 2 Satz 2 FamGKG: Werte der übrigen Folgesachen hinzugerechnet)."""
    r = ermittle(_verbund({"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_2"},
                          {"art": "haushaltssache", "fallgruppe": "200_abs_2_nr_2"}), NEU)
    assert r.form == "verbund"
    assert r.gesamt == Decimal("23000.00")
    assert [g.wert for g in r.gegenstaende] == [Decimal("15000.00"), Decimal("5000.00"),
                                                Decimal("3000.00")]
    assert all("Folgesache" in g.bezeichnung for g in r.gegenstaende[1:])


def test_ehewohnung_folgesache_stand_alt():
    """KostRÄG 2021: 15.000 € + Ehewohnung § 1568a BGB 4.000 € = 19.000 €."""
    r = ermittle(_verbund({"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_2"}), ALT)
    assert r.gesamt == Decimal("19000.00")


def test_festgesetzt_schlaegt_festwert():
    r = ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "2_gewschg",
                          "verfahrenswert_festgesetzt": "6000.00"}), NEU)
    g = r.gegenstaende[0]
    assert r.gesamt == Decimal("6000.00")
    assert g.quelle == "eingabe" and r.quelle == "eingabe"
    assert g.norm == "§ 49 Abs. 2 FamGKG (gerichtliche Festsetzung)"
    assert g.rechenschritte[0].quelle == "eingabe"


def test_festgesetzt_folgesache_ehewohnung():
    r = ermittle(_verbund({"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_2",
                           "verfahrenswert_festgesetzt": "7000.00"}), NEU)
    assert r.gesamt == Decimal("22000.00")
    assert r.gegenstaende[1].norm == "§ 48 Abs. 3 FamGKG (gerichtliche Festsetzung)"


# --------------------------------------------------------------------------
# § 41 FamGKG — einstweilige Anordnung
# --------------------------------------------------------------------------

def _ea(eintrag, stichtag=NEU):
    return ermittle(_selbst({**eintrag, "einstweilige_anordnung": True}), stichtag)


def test_ea_festwert_halbiert():
    """§ 49 Abs. 1 (§ 2 GewSchG) 4.000 € x 1/2 = 2.000 € (§ 41 Satz 2)."""
    r = _ea({"art": "gewaltschutzsache", "fallgruppe": "2_gewschg"})
    g = r.gegenstaende[0]
    assert r.gesamt == Decimal("2000.00")
    assert g.hauptsachewert == Decimal("4000.00")
    assert g.norm == "§ 49 Abs. 1 FamGKG i. V. m. § 41 Satz 2 FamGKG"
    assert [s.norm for s in g.rechenschritte] == ["§ 49 Abs. 1 FamGKG", "§ 41 Satz 2 FamGKG"]
    assert g.rechenschritte[-1].ergebnis == "2000.00"
    assert any("§ 41 Satz 1" in h and "keine Festsetzung" in h for h in g.hinweise)
    assert len(r.warnungen) == 1 and "§ 41 Satz 1" in r.warnungen[0]
    d = g.as_dict()
    assert d["einstweilige_anordnung"] is True and d["hauptsachewert"] == "4000.00"


def test_ea_festwert_stand_alt():
    """KostRÄG 2021: § 49 Abs. 1 (§ 1 GewSchG) 2.000 € -> 1.000 €."""
    r = _ea({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg"}, ALT)
    assert r.gesamt == Decimal("1000.00")


def test_ea_unterhalt_halbiert():
    """§ 51 Abs. 1: 12 x 480 € = 5.760 € -> § 41 Satz 2: 2.880 €."""
    r = _ea({"art": "kindesunterhalt", "monatsbetrag": "480.00"})
    g = r.gegenstaende[0]
    assert g.hauptsachewert == Decimal("5760.00")
    assert r.gesamt == Decimal("2880.00")
    assert g.rechenschritte[-1].norm == "§ 41 Satz 2 FamGKG"


def test_ea_versorgungsausgleich_mindestwert_vor_halbierung():
    """§ 50 Abs. 1: 1 Anrecht x 10 % x 3 x (500 + 500) = 300 € < Mindestwert
    1.000 € -> 1.000 € (für die Hauptsache bestimmter Wert); § 41 Satz 2:
    500 € (Mindestwert wird nicht erneut angewendet)."""
    r = _ea({"art": "versorgungsausgleich", "anzahl_anrechte": 1,
             "nettoeinkommen_monatlich": ["500.00", "500.00"]})
    g = r.gegenstaende[0]
    assert [s.norm for s in g.rechenschritte] == [
        "§ 50 Abs. 1 Satz 1 FamGKG", "§ 50 Abs. 1 Satz 1 FamGKG",
        "§ 50 Abs. 1 Satz 2 FamGKG", "§ 41 Satz 2 FamGKG"]
    assert g.hauptsachewert == Decimal("1000.00")
    assert r.gesamt == Decimal("500.00")


def test_ea_kindschaftssache_halbiert():
    """§ 45 Abs. 1 Nr. 2 (KostBRÄG 2025) 5.000 € -> 2.500 €."""
    assert _ea({"art": "kindschaftssache", "gegenstand": "umgang"}).gesamt == Decimal("2500.00")


@pytest.mark.parametrize("betrag,erwartet", [("1000.01", "500.01"),   # 500,005 -> 500,01
                                             ("1000.03", "500.02")])  # 500,015 -> 500,02
def test_ea_ungerader_cent_kaufmaennisch_gerundet(betrag, erwartet):
    r = _ea({"art": "geldforderung", "betrag": betrag})
    assert r.gesamt == Decimal(erwartet)
    assert "auf volle Cent gerundet" in r.gegenstaende[0].rechenschritte[-1].beschreibung


def test_ea_gerader_betrag_ohne_rundungshinweis():
    r = _ea({"art": "geldforderung", "betrag": "1000.00"})
    assert "gerundet" not in r.gegenstaende[0].rechenschritte[-1].beschreibung


def test_ea_false_aendert_nichts():
    r = ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                          "einstweilige_anordnung": False}), NEU)
    assert r.gesamt == Decimal("3000.00")
    assert "einstweilige_anordnung" not in r.gegenstaende[0].as_dict()
    assert r.warnungen == []


def test_ea_an_der_ehesache_exit2():
    with pytest.raises(VerfahrenswertFehler, match="ehesache.einstweilige_anordnung"):
        ermittle({"ehesache": {"nettoeinkommen_monatlich": ["3000", "2000"],
                               "einstweilige_anordnung": True}}, NEU)


def test_ea_im_verbund_exit2():
    with pytest.raises(VerfahrenswertFehler, match="im Verbund nicht"):
        ermittle(_verbund({"art": "kindesunterhalt", "monatsbetrag": "480.00",
                           "einstweilige_anordnung": True}), NEU)


@pytest.mark.parametrize("flag", ["true", 1, 0, None, "ja", [True]])
def test_ea_kein_boolean_exit2(flag):
    with pytest.raises(VerfahrenswertFehler, match="JSON-Boolean"):
        ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                          "einstweilige_anordnung": flag}), NEU)


def test_ea_mit_festgesetztem_wert_keine_halbierung():
    r = _ea({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
             "verfahrenswert_festgesetzt": "1200.00"})
    g = r.gegenstaende[0]
    assert r.gesamt == Decimal("1200.00")
    assert g.hauptsachewert is None
    assert g.rechenschritte[-1].norm == "§ 41 FamGKG"
    assert g.rechenschritte[-1].quelle == "eingabe"
    assert "keine Halbierung" in g.rechenschritte[-1].beschreibung
    d = g.as_dict()
    assert d["einstweilige_anordnung"] is True and "hauptsachewert" not in d
    assert r.warnungen == []


def test_ea_gemischt_mit_hauptsache_exit2():
    """§ 51 Abs. 3 Satz 1 FamFG: die einstweilige Anordnung ist ein
    selbständiges Verfahren — nie mit Hauptsache-Gegenständen summieren."""
    with pytest.raises(VerfahrenswertFehler, match="§ 51 Abs. 3 Satz 1 FamFG"):
        ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                          "einstweilige_anordnung": True},
                         {"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_1"}), NEU)


def test_ea_mehrere_gegenstaende_alle_mit_flag():
    """Gewaltschutz § 1 GewSchG 3.000 € -> 1.500 € + Ehewohnung § 1361b BGB
    4.000 € -> 2.000 € = 3.500 € (§ 33 Abs. 1 Satz 1)."""
    r = ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                          "einstweilige_anordnung": True},
                         {"art": "ehewohnungssache", "fallgruppe": "200_abs_1_nr_1",
                          "einstweilige_anordnung": True}), NEU)
    assert r.gesamt == Decimal("3500.00")


def test_ea_gesamtfestsetzung_ohne_41_warnung():
    r = ermittle(_selbst({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                          "einstweilige_anordnung": True},
                         verfahrenswert_festgesetzt="1000.00"), NEU)
    assert r.gesamt == Decimal("1000.00")
    assert r.warnungen == []


# --------------------------------------------------------------------------
# CLI: Warnungen im famgkg-Block, Positions-Plausibilität
# --------------------------------------------------------------------------

def _cli(tmp_path: Path, positionen, gegenstand=None) -> subprocess.CompletedProcess:
    gegenstand = gegenstand or {"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
                                "einstweilige_anordnung": True}
    eingabe = {"famgkg": {"verfahrenseinleitungsdatum": "2026-03-01",
                          "verfahrenswert_ermittlung": {"gegenstaende": [gegenstand]},
                          "positionen": positionen}}
    return lauf(EXECUTOR, "--input", schreibe(tmp_path / "anfrage.json", eingabe))


def test_cli_warnung_hauptsacheposition_ohne_ea_position(tmp_path):
    e = _cli(tmp_path, [{"nr": "1320"}])
    assert e.returncode == 0, e.stderr
    w = json.loads(e.stdout)["famgkg"]["warnungen"]
    assert any("§ 41 Satz 1" in x for x in w)
    assert any("KV 1320" in x and "KV 1420/1421" in x for x in w)


@pytest.mark.parametrize("positionen", [[{"nr": "1420"}], [{"nr": "1421"}],
                                        [{"nr": "1320"}, {"nr": "1420"}]])
def test_cli_keine_positionswarnung_mit_ea_position(tmp_path, positionen):
    e = _cli(tmp_path, positionen)
    assert e.returncode == 0, e.stderr
    w = json.loads(e.stdout)["famgkg"]["warnungen"]
    assert len(w) == 1 and "§ 41 Satz 1" in w[0]


def test_cli_kindschaft_ea_mit_1410_keine_positionswarnung(tmp_path):
    e = _cli(tmp_path, [{"nr": "1410"}],
             {"art": "kindschaftssache", "gegenstand": "umgang",
              "einstweilige_anordnung": True})
    assert e.returncode == 0, e.stderr
    f = json.loads(e.stdout)["famgkg"]
    assert f["verfahrenswert"]["gesamt"] == "2500.00"
    assert not any("Positionen prüfen" in x for x in f["warnungen"])


def test_cli_ohne_ea_keine_warnungen(tmp_path):
    e = _cli(tmp_path, [{"nr": "1320"}],
             {"art": "gewaltschutzsache", "fallgruppe": "1_gewschg"})
    assert e.returncode == 0, e.stderr
    f = json.loads(e.stdout)["famgkg"]
    assert f["verfahrenswert"]["gesamt"] == "3000.00"
    assert f["warnungen"] == []


@pytest.mark.parametrize("gegenstand,muster", [
    ({"art": "gewaltschutzsache"}, "fallgruppe"),
    ({"art": "gewaltschutzsache", "fallgruppe": "1_gewschg",
      "einstweilige_anordnung": "true"}, "JSON-Boolean"),
])
def test_cli_eingabefehler_exit2(tmp_path, gegenstand, muster):
    e = _cli(tmp_path, [{"nr": "1420"}], gegenstand)
    assert e.returncode == 2, e.stdout
    assert muster in e.stderr
    assert "Traceback" not in e.stderr
