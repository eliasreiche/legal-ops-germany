"""Tests für core/calc/rvg/executor.py — CLI: JSON rein, JSON-Report raus (P2).

Deckt ab: RVG-only, GKG-only und kombinierte Anfragen über die
Kommandozeile, die Schema-Beispieldateien des Skills, sowie adversariale
CLI-Inputs (kaputtes JSON, negativer/nicht-numerischer Streitwert,
unbekannte VV-Nr., Streitwert > 30 Mio., float-Präzisionsfallen wie
0,1+0,2) — jeweils sauberer Exit 2, kein Traceback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
EXECUTOR = REPO / "plugins" / "legal-ops" / "core" / "calc" / "rvg" / "executor.py"
SCHEMA = Path(__file__).resolve().parents[1] / "schema"


def _lauf(eingabe, tmp_path: Path) -> subprocess.CompletedProcess:
    eingabe_pfad = tmp_path / "anfrage.json"
    if isinstance(eingabe, str):
        eingabe_pfad.write_text(eingabe, encoding="utf-8")
    else:
        eingabe_pfad.write_text(json.dumps(eingabe), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe_pfad)],
        capture_output=True, text=True)


def _report(eingabe: dict, tmp_path: Path) -> dict:
    ergebnis = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_rvg_only(tmp_path):
    report = _report({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert "rvg" in report
    assert "gkg" not in report
    assert report["rvg"]["ergebnis"]["quelle"] == "executor"
    for schritt in report["rvg"]["rechenkette"]:
        assert schritt["quelle"] == "executor"


def test_gkg_only(tmp_path):
    report = _report({"gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "positionen": [{"nr": "1210"}]}}, tmp_path)
    assert "gkg" in report
    assert "rvg" not in report
    assert report["gkg"]["ergebnis"]["umsatzsteuerpflichtig"] is False


def test_beide_bloecke_kombiniert(tmp_path):
    report = _report({
        "rvg": {"auftragsdatum": "2026-01-01", "streitwert": "5000",
               "tatbestaende": [{"nr": "3100"}]},
        "gkg": {"verfahrenseinleitungsdatum": "2026-01-01", "streitwert": "5000",
               "positionen": [{"nr": "1210"}]},
    }, tmp_path)
    assert "rvg" in report and "gkg" in report
    assert "hinweis_getrennte_kostenarten" in report["meta"]


def test_output_datei(tmp_path):
    eingabe = tmp_path / "anfrage.json"
    eingabe.write_text(json.dumps({"rvg": {"auftragsdatum": "2026-01-01",
                                           "streitwert": "10000",
                                           "tatbestaende": [{"nr": "3100"}]}}),
                       encoding="utf-8")
    ziel = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe),
         "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["rvg"]["ergebnis"]["gesamt_verguetung"]


# --------------------------------------------------------------------------
# Schema-Beispieldateien bleiben synchron
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--input", str(SCHEMA / "beispiel-eingabe.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8"))
    erzeugt["meta"].pop("quelle_datei")
    gespeichert["meta"].pop("quelle_datei")
    assert erzeugt == gespeichert


def test_beispiel_report_berufung_synchron():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--input", str(SCHEMA / "beispiel-eingabe-berufung.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads(
        (SCHEMA / "beispiel-report-berufung.json").read_text(encoding="utf-8"))
    erzeugt["meta"].pop("quelle_datei")
    gespeichert["meta"].pop("quelle_datei")
    assert erzeugt == gespeichert
    # zwei Angelegenheiten (erste Instanz + Berufung), GKG-Berufung KV 1220.
    assert len(erzeugt["rvg"]["angelegenheiten"]) == 2
    assert erzeugt["rvg"]["ergebnis"]["gesamt_verguetung"] == "4159.76"
    assert erzeugt["gkg"]["ergebnis"]["gesamt"] == "1132.00"


def test_beispiel_eingabe_anrechnung_laeuft():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--input", str(SCHEMA / "beispiel-eingabe-anrechnung.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["rvg"]["anrechnung"] is not None
    assert report["rvg"]["anrechnung"]["anrechnungssatz"] == "0.65"


# --------------------------------------------------------------------------
# Eingabefehler → Exit 2, klare Meldung, kein Traceback
# --------------------------------------------------------------------------

def test_fehler_kaputtes_json(tmp_path):
    ergebnis = _lauf("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_datei_fehlt(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(tmp_path / "nix.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_fehler_weder_rvg_noch_gkg(tmp_path):
    ergebnis = _lauf({}, tmp_path)
    assert ergebnis.returncode == 2
    assert "mindestens einen Block" in ergebnis.stderr


def test_fehler_unbekanntes_feld_oberste_ebene(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "1",
                              "tatbestaende": [{"nr": "3100"}]},
                      "unsinn": {}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr


def test_befund5_tippfehler_feld_wird_als_solcher_gemeldet(tmp_path):
    # Regressionstest Review-Befund 5: {"foo": {}} soll "unbekanntes Feld"
    # melden (Tippfehler-Diagnose), nicht "mindestens einen Block" — vor dem
    # Fix kam die unspezifische Meldung zuerst.
    ergebnis = _lauf({"foo": {}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "unbekanntes Feld" in ergebnis.stderr
    assert "'foo'" in ergebnis.stderr
    assert "mindestens einen Block" not in ergebnis.stderr


def test_befund3_teil2_und_teil3_flach_exit_2(tmp_path):
    # Regressionstest Review-Befund 3 (Executor-Ebene): flache Kurzform mit
    # Teil-2- UND Teil-3-Tatbeständen -> Eingabefehler mit Verweis auf die
    # Angelegenheiten-Gruppierung, kein stilles Zusammenrechnen.
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "tatbestaende": [{"nr": "2300", "satz": "1.3"},
                                               {"nr": "3100"}]}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "angelegenheiten" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_befund3_angelegenheiten_form_je_eigene_pauschale(tmp_path):
    # Regressionstest Review-Befund 3: zwei Angelegenheiten -> zwei
    # 7002-Pauschalen (je bis 20 EUR) und getrennte USt-Basen.
    report = _report({"rvg": {
        "auftragsdatum": "2026-01-01", "streitwert": "10000",
        "angelegenheiten": [
            {"bezeichnung": "Außergerichtliche Vertretung",
             "tatbestaende": [{"nr": "2300", "satz": "1.3"}]},
            {"bezeichnung": "Rechtsstreit erster Instanz",
             "tatbestaende": [{"nr": "3100"}, {"nr": "3104"}]},
        ],
        "anrechnung_2300_auf_3100": True}}, tmp_path)
    bloecke = report["rvg"]["angelegenheiten"]
    assert len(bloecke) == 2
    assert bloecke[0]["ergebnis"]["auslagenpauschale"] == "20.00"
    assert bloecke[1]["ergebnis"]["auslagenpauschale"] == "20.00"
    assert report["rvg"]["anrechnung"]["anrechnungssatz"] == "0.65"
    assert "Angelegenheiten" in report["rvg"]["ergebnis"]["gesamt_hinweis"]


def test_angelegenheiten_und_tatbestaende_gleichzeitig_exit_2(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "tatbestaende": [{"nr": "3100"}],
                              "angelegenheiten": [
                                  {"tatbestaende": [{"nr": "3100"}]}]}},
                     tmp_path)
    assert ergebnis.returncode == 2
    assert "nicht beides" in ergebnis.stderr


@pytest.mark.parametrize("streitwert", ["-500", "0", "abc", "", None, "NaN", "Infinity"])
def test_fehler_negativer_nicht_numerischer_streitwert(streitwert, tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": streitwert,
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert ergebnis.returncode == 2, repr(streitwert)
    assert "Traceback" not in ergebnis.stderr, repr(streitwert)


def test_fehler_float_streitwert_praezisionsfalle(tmp_path):
    # 0.1 + 0.2 == 0.30000000000000004 als IEEE-754-float — klassische Falle.
    ergebnis = _lauf('{"rvg": {"auftragsdatum": "2026-01-01", '
                     '"streitwert": ' + repr(0.1 + 0.2) + ', '
                     '"tatbestaende": [{"nr": "3100"}]}}', tmp_path)
    assert ergebnis.returncode == 2
    assert "float" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_float_satz_praezisionsfalle(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "1000",
                              "tatbestaende": [{"nr": "2300", "satz": 0.1 + 0.2}]}},
                     tmp_path)
    assert ergebnis.returncode == 2
    assert "float" in ergebnis.stderr


def test_fehler_unbekannte_vv_nr(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "1000",
                              "tatbestaende": [{"nr": "9999"}]}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "nicht unterstützt" in ergebnis.stderr


def test_fehler_betragsrahmengebuehr_scope(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01", "streitwert": "1000",
                              "tatbestaende": [{"nr": "3102"}]}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "Betragsrahmengebühren" in ergebnis.stderr


def test_befund2_streitwert_ueber_30_mio_gkg_kappung_im_report(tmp_path):
    # Regressionstest Review-Befund 2: § 39 Abs. 2 GKG kappt, lehnt nicht ab
    # — vor dem Fix Exit 2, jetzt Exit 0 mit ausgewiesener Kappung.
    report = _report({"gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                              "streitwert": "40000000",
                              "positionen": [{"nr": "1210"}]}}, tmp_path)
    kappung = report["gkg"]["wertkappung"]
    assert kappung["gekappt"] is True
    assert kappung["norm"] == "§ 39 Abs. 2 GKG"
    assert kappung["streitwert_eingabe"] == "40000000"
    assert kappung["streitwert_angewendet"] == "30000000.00"
    assert report["gkg"]["einfachgebuehr"] == "128038.00"
    assert any("§ 39 Abs. 2 GKG" in w for w in report["gkg"]["warnungen"])


def test_befund1_streitwert_ueber_30_mio_rvg_kappung_im_report(tmp_path):
    # Regressionstest Review-Befund 1: § 22 Abs. 2 S. 1 RVG kappt den
    # Gegenstandswert — vor dem Fix wurde ungekappt weitergerechnet
    # (einfachgebuehr 142002,00 statt 107002,00).
    report = _report({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "40000000",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    kappung = report["rvg"]["wertkappung"]
    assert kappung["gekappt"] is True
    assert kappung["norm"] == "§ 22 Abs. 2 Satz 1 RVG"
    assert report["rvg"]["einfachgebuehr"] == "107002.00"
    assert any("§ 22 Abs. 2 Satz 1 RVG" in w for w in report["rvg"]["warnungen"])
    assert any(s["norm"] == "§ 22 Abs. 2 Satz 1 RVG"
               for s in report["rvg"]["rechenkette"])


def test_befund1_1008_plus_ueber_30_mio_exit_2(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "40000000",
                              "tatbestaende": [
                                  {"nr": "3100"},
                                  {"nr": "1008", "erhoeht_position": "3100",
                                   "weitere_auftraggeber": 1}]}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "§ 22 Abs. 2 Satz 2 RVG" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_kein_wertkappung_block_unter_grenze(tmp_path):
    report = _report({"rvg": {"auftragsdatum": "2026-01-01",
                              "streitwert": "10000",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert report["rvg"]["wertkappung"] is None


def test_fehler_stichtag_vor_2021(tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": "2019-01-01", "streitwert": "1000",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert ergebnis.returncode == 2
    assert "kein RVG-Tabellenstand" in ergebnis.stderr


@pytest.mark.parametrize("wert", [20260101, "2026-1-1", "01.01.2026", "2026/01/01"])
def test_fehler_datum_strikt_jjjj_mm_tt(wert, tmp_path):
    ergebnis = _lauf({"rvg": {"auftragsdatum": wert, "streitwert": "1000",
                              "tatbestaende": [{"nr": "3100"}]}}, tmp_path)
    assert ergebnis.returncode == 2, repr(wert)
    assert "JJJJ-MM-TT" in ergebnis.stderr, repr(wert)


def test_fehler_kein_json_objekt(tmp_path):
    ergebnis = _lauf("[1, 2, 3]", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON-Objekt" in ergebnis.stderr


def test_fehler_rvg_kein_objekt(tmp_path):
    ergebnis = _lauf({"rvg": "kaputt"}, tmp_path)
    assert ergebnis.returncode == 2


def test_fehler_gkg_ausschlusspaar(tmp_path):
    ergebnis = _lauf({"gkg": {"verfahrenseinleitungsdatum": "2026-01-01",
                              "streitwert": "1000",
                              "positionen": [{"nr": "1210"}, {"nr": "1211"}]}},
                     tmp_path)
    assert ergebnis.returncode == 2
    assert "schließen sich gegenseitig aus" in ergebnis.stderr
