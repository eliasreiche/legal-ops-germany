"""Tests für plugins/legal-ops/skills/akten-intake-strukturierer/executor.py.

Deckt ab: Normalisierung (Datum, Geld, IBAN/E-Mail/Telefon, Aktenzeichen),
die Provenienz-Prüfung (belegt/nicht_belegt inkl. abweichender Schreibweisen),
die Schema-Prüfung samt Lücken-Disziplin sowie die CLI (Aktenkopf + Quelle
rein → JSON-Report raus, Exit-Codes 0/1/2) und die Beispieldateien als
Golden-File-Round-Trip.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA = SKILL_DIR / "schema"
EXECUTOR = SKILL_DIR / "executor.py"

# Eindeutiger Modulname statt `import executor`, damit der Modulname sich nicht
# mit dem gleichnamigen Executor anderer Skills (zitat-verifier-de) im selben
# pytest-Prozess überschreibt.
_spec = importlib.util.spec_from_file_location("akten_intake_executor", EXECUTOR)
executor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(executor)


# --------------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------------

def _quelle(text: str) -> list[tuple[str, list[str]]]:
    return [("quelle.md", text.splitlines())]


def _fixture_quelle() -> list[tuple[str, list[str]]]:
    text = (FIXTURES / "quelle.md").read_text(encoding="utf-8")
    return [("quelle.md", text.splitlines())]


def _basis_aktenkopf() -> dict:
    """Minimal gültiger Aktenkopf, in den Tests gezielt mutiert."""
    return {
        "aktenkopf": {
            "kurzrubrum": "Mustermann ./. Beispiel",
            "sachverhalt_kurz": "Kurzer Testsachverhalt.",
            "eingangsdatum": "2026-04-14",
        },
        "parteien": [
            {"rolle": "mandant", "name": "Max Mustermann", "typ": "natuerlich",
             "anschrift": "Testweg 1, 10115 Berlin", "kontakt": {},
             "vertreten_durch": None},
        ],
        "fristen_hinweise": [],
        "betraege": [],
        "aktenzeichen_fremd": [],
        "luecken": [],
    }


def _lauf(aktenkopf: dict, quelle_text: str, tmp_path: Path,
          output: Path | None = None) -> subprocess.CompletedProcess:
    ak = tmp_path / "aktenkopf.json"
    ak.write_text(json.dumps(aktenkopf), encoding="utf-8")
    q = tmp_path / "quelle.md"
    q.write_text(quelle_text, encoding="utf-8")
    argv = [sys.executable, str(EXECUTOR), "--aktenkopf", str(ak), "--quelle", str(q)]
    if output is not None:
        argv += ["--output", str(output)]
    return subprocess.run(argv, capture_output=True, text=True)


# --------------------------------------------------------------------------
# Normalisierung
# --------------------------------------------------------------------------

def test_datum_kanon_iso_und_deutsch_sind_gleich():
    assert executor._datum_kanon_wert("2026-03-01") == "2026-03-01"
    assert executor._datum_kanon_wert("01.03.2026") == "2026-03-01"
    assert executor._datum_kanon_wert("1.3.2026") == "2026-03-01"


def test_datum_kanon_lehnt_unfug_ab():
    assert executor._datum_kanon_wert("2026-13-40") is None
    assert executor._datum_kanon_wert("kein datum") is None


def test_datum_in_zeile_findet_beide_formate():
    assert "2026-03-01" in executor._datum_kanons_in_zeile("... am 01.03.2026 ...")
    assert "2026-03-01" in executor._datum_kanons_in_zeile("... am 2026-03-01 ...")


def test_geld_kanon_varianten_sind_gleich():
    assert executor._geld_kanon("1.234,56 €") == "1234.56"
    assert executor._geld_kanon("1234,56 EUR") == "1234.56"
    assert executor._geld_kanon("30,00 €") == "30.00"
    assert executor._geld_kanon("30 EUR") == "30.00"


def test_iban_email_telefon_normalisierung():
    assert executor._iban_norm("DE02 1203 0000 0000 2020 51") == "DE02120300000000202051"
    assert executor._tel_norm("030 / 12 34 56") == "030123456"
    assert executor._kanon_ziel("Max@Example.ORG", "email") == "max@example.org"


def test_aktenzeichen_whitespace_wird_kollabiert():
    assert executor._ws_collapse("12   O\t345/26") == "12 O 345/26"


# --------------------------------------------------------------------------
# Provenienz
# --------------------------------------------------------------------------

def test_beleg_datum_andere_schreibweise_wird_gefunden():
    # Aktenkopf hat ISO, Quelle hat deutsches Format.
    quellen = _quelle("Eingang am 14.04.2026 in der Kanzlei.")
    beleg = executor.finde_beleg("2026-04-14", "datum", quellen)
    assert beleg is not None
    assert beleg["zeile"] == 1


def test_beleg_geld_variante_wird_gefunden():
    quellen = _quelle("Forderung: 1234,56 EUR insgesamt.")
    beleg = executor.finde_beleg("1.234,56 €", "geld", quellen)
    assert beleg is not None


def test_erfundenes_datum_bleibt_nicht_belegt():
    quellen = _quelle("Eingang am 14.04.2026.")
    beleg = executor.finde_beleg("2099-12-31", "datum", quellen)
    assert beleg is None


def test_provenienz_markiert_belegt_und_nicht_belegt():
    ak = _basis_aktenkopf()
    ak["betraege"] = [
        {"betrag": "1.234,56 €", "kontext": "belegt", "quelle_zitat": "x"},
        {"betrag": "9.999,99 €", "kontext": "erfunden", "quelle_zitat": "x"},
    ]
    prov = executor.pruefe_provenienz(ak, _quelle("Betrag 1234,56 EUR steht hier."))
    nach_pfad = {p["pfad"]: p["status"] for p in prov}
    assert nach_pfad["betraege[0].betrag"] == "belegt"
    assert nach_pfad["betraege[1].betrag"] == "nicht_belegt"
    # eingangsdatum nicht in dieser Quelle -> nicht_belegt
    assert nach_pfad["aktenkopf.eingangsdatum"] == "nicht_belegt"


# --------------------------------------------------------------------------
# Schema-Prüfung
# --------------------------------------------------------------------------

def test_schema_basis_ist_sauber():
    assert executor.pruefe_schema(_basis_aktenkopf()) == []


def test_leeres_pflichtfeld_ohne_luecke_ist_schema_fehler():
    ak = _basis_aktenkopf()
    ak["aktenkopf"]["eingangsdatum"] = ""
    fehler = executor.pruefe_schema(ak)
    assert any("aktenkopf.eingangsdatum" in f and "Lücke" in f for f in fehler)


def test_leeres_pflichtfeld_mit_luecke_ist_ok():
    ak = _basis_aktenkopf()
    ak["aktenkopf"]["eingangsdatum"] = ""
    ak["luecken"] = [{"feld": "aktenkopf.eingangsdatum",
                      "grund": "Posteingangsdatum noch nachzutragen."}]
    assert executor.pruefe_schema(ak) == []


def test_leere_partei_anschrift_ohne_luecke_ist_fehler():
    ak = _basis_aktenkopf()
    ak["parteien"][0]["anschrift"] = ""
    fehler = executor.pruefe_schema(ak)
    assert any("parteien[0].anschrift" in f for f in fehler)


def test_leere_partei_anschrift_mit_luecke_ist_ok():
    ak = _basis_aktenkopf()
    ak["parteien"][0]["anschrift"] = ""
    ak["luecken"] = [{"feld": "parteien[0].anschrift", "grund": "fehlt im Dokument"}]
    assert executor.pruefe_schema(ak) == []


def test_ungueltiges_iso_datum_ist_schema_fehler():
    ak = _basis_aktenkopf()
    ak["aktenkopf"]["eingangsdatum"] = "14.04.2026"
    fehler = executor.pruefe_schema(ak)
    assert any("ISO-Datum" in f for f in fehler)


def test_ungueltige_rolle_und_typ_sind_schema_fehler():
    ak = _basis_aktenkopf()
    ak["parteien"][0]["rolle"] = "zeuge"
    ak["parteien"][0]["typ"] = "firma"
    fehler = executor.pruefe_schema(ak)
    assert any("rolle" in f for f in fehler)
    assert any("typ" in f for f in fehler)


def test_fehlender_pflichtschluessel_ist_schema_fehler():
    ak = _basis_aktenkopf()
    del ak["parteien"]
    fehler = executor.pruefe_schema(ak)
    assert any("parteien" in f for f in fehler)


def test_frist_hinweis_ohne_zitat_ist_schema_fehler():
    ak = _basis_aktenkopf()
    ak["fristen_hinweise"] = [
        {"datum_im_text": "2026-05-02", "originalschreibweise": "02.05.2026",
         "quelle_zitat": "", "vermutete_bedeutung": "Zahlungsfrist"}]
    fehler = executor.pruefe_schema(ak)
    assert any("fristen_hinweise[0].quelle_zitat" in f for f in fehler)


def test_leere_parteienliste_ist_schema_fehler():
    ak = _basis_aktenkopf()
    ak["parteien"] = []
    fehler = executor.pruefe_schema(ak)
    assert any("mindestens eine Partei" in f for f in fehler)


# --------------------------------------------------------------------------
# Report / baue_report
# --------------------------------------------------------------------------

def test_report_vollstaendig_belegt_ist_sauber():
    ak = json.loads((FIXTURES / "aktenkopf_vollstaendig.json").read_text(encoding="utf-8"))
    report = executor.baue_report(ak, _fixture_quelle(), "aktenkopf_vollstaendig.json")
    assert report["schema_ok"] is True
    assert report["zusammenfassung"]["nicht_belegt"] == 0
    assert report["zusammenfassung"]["schema_fehler"] == 0
    assert executor.report_ist_sauber(report) is True
    assert all(p["status"] == "belegt" for p in report["provenienz"])


def test_report_mit_erfundenem_datum_ist_nicht_sauber():
    ak = json.loads((FIXTURES / "aktenkopf_vollstaendig.json").read_text(encoding="utf-8"))
    ak["fristen_hinweise"][0]["datum_im_text"] = "2099-01-01"
    report = executor.baue_report(ak, _fixture_quelle(), "x.json")
    assert report["zusammenfassung"]["nicht_belegt"] >= 1
    assert executor.report_ist_sauber(report) is False


# --------------------------------------------------------------------------
# CLI (P2: Dateien rein → JSON-Report raus, Exit-Codes)
# --------------------------------------------------------------------------

def test_cli_vollstaendig_exit0(tmp_path):
    ak = json.loads((FIXTURES / "aktenkopf_vollstaendig.json").read_text(encoding="utf-8"))
    quelle_text = (FIXTURES / "quelle.md").read_text(encoding="utf-8")
    ergebnis = _lauf(ak, quelle_text, tmp_path)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["zusammenfassung"]["nicht_belegt"] == 0


def test_cli_erfundenes_datum_exit1(tmp_path):
    ak = _basis_aktenkopf()
    ak["fristen_hinweise"] = [
        {"datum_im_text": "2099-01-01", "originalschreibweise": "01.01.2099",
         "quelle_zitat": "erfundenes Zitat", "vermutete_bedeutung": "Frist"}]
    ergebnis = _lauf(ak, "Eingang am 14.04.2026.\n", tmp_path)
    assert ergebnis.returncode == 1
    report = json.loads(ergebnis.stdout)
    status = {p["pfad"]: p["status"] for p in report["provenienz"]}
    assert status["fristen_hinweise[0].datum_im_text"] == "nicht_belegt"


def test_cli_schema_fehler_exit1(tmp_path):
    ak = _basis_aktenkopf()
    ak["aktenkopf"]["kurzrubrum"] = ""  # leer, keine Lücke
    ergebnis = _lauf(ak, "Eingang am 14.04.2026.\n", tmp_path)
    assert ergebnis.returncode == 1
    report = json.loads(ergebnis.stdout)
    assert report["schema_ok"] is False


def test_cli_fehlende_aktenkopf_datei_exit2(tmp_path):
    q = tmp_path / "quelle.md"
    q.write_text("x\n", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--aktenkopf", str(tmp_path / "fehlt.json"),
         "--quelle", str(q)], capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_cli_fehlende_quelle_exit2(tmp_path):
    ak = tmp_path / "aktenkopf.json"
    ak.write_text(json.dumps(_basis_aktenkopf()), encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--aktenkopf", str(ak),
         "--quelle", str(tmp_path / "fehlt.md")], capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "Quelldatei nicht gefunden" in ergebnis.stderr


def test_cli_kaputtes_json_exit2(tmp_path):
    ak = tmp_path / "aktenkopf.json"
    ak.write_text("{kein valides json", encoding="utf-8")
    q = tmp_path / "quelle.md"
    q.write_text("x\n", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--aktenkopf", str(ak), "--quelle", str(q)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_cli_mehrere_quellen_werden_durchsucht(tmp_path):
    ak = _basis_aktenkopf()
    ak["betraege"] = [{"betrag": "1.234,56 €", "kontext": "Forderung",
                       "quelle_zitat": "x"}]
    ak_pfad = tmp_path / "aktenkopf.json"
    ak_pfad.write_text(json.dumps(ak), encoding="utf-8")
    q1 = tmp_path / "brief.md"
    q1.write_text("Eingang am 14.04.2026.\n", encoding="utf-8")
    q2 = tmp_path / "anlage.md"
    q2.write_text("Der Betrag lautet 1234,56 EUR.\n", encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--aktenkopf", str(ak_pfad),
         "--quelle", str(q1), "--quelle", str(q2)], capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    beleg = next(p for p in report["provenienz"] if p["pfad"] == "betraege[0].betrag")
    assert beleg["fundstelle"]["datei"].endswith("anlage.md")


def test_cli_output_datei(tmp_path):
    ak = json.loads((FIXTURES / "aktenkopf_vollstaendig.json").read_text(encoding="utf-8"))
    quelle_text = (FIXTURES / "quelle.md").read_text(encoding="utf-8")
    ziel = tmp_path / "report.json"
    ergebnis = _lauf(ak, quelle_text, tmp_path, output=ziel)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["meta"]["erzeugt_von"] == "akten-intake-strukturierer/executor.py"


# --------------------------------------------------------------------------
# Beispieldateien — Golden-File-Round-Trip
# --------------------------------------------------------------------------

def test_beispiel_dateien_sind_gueltiges_json():
    for name in ("beispiel-aktenkopf.json", "beispiel-report.json"):
        json.loads((SCHEMA / name).read_text(encoding="utf-8"))


def test_beispiel_report_ist_golden_file_gegen_frischen_lauf():
    """schema/beispiel-report.json muss exakt der frischen Executor-Ausgabe
    aus beispiel-aktenkopf.json + beispiel-eingabe.md entsprechen. Bei jeder
    Verhaltensänderung neu generieren (mit dem Executor, nicht von Hand)."""
    ak = json.loads((SCHEMA / "beispiel-aktenkopf.json").read_text(encoding="utf-8"))
    quelle_text = (SCHEMA / "beispiel-eingabe.md").read_text(encoding="utf-8")
    frisch = executor.baue_report(
        ak, [("beispiel-eingabe.md", quelle_text.splitlines())],
        aktenkopf_datei="beispiel-aktenkopf.json")
    erwartet = json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8"))
    assert frisch == erwartet


def test_beispiel_aktenkopf_ist_vollstaendig_belegt():
    ak = json.loads((SCHEMA / "beispiel-aktenkopf.json").read_text(encoding="utf-8"))
    quelle_text = (SCHEMA / "beispiel-eingabe.md").read_text(encoding="utf-8")
    report = executor.baue_report(
        ak, [("beispiel-eingabe.md", quelle_text.splitlines())],
        aktenkopf_datei="beispiel-aktenkopf.json")
    assert executor.report_ist_sauber(report) is True
    assert report["zusammenfassung"]["belegt"] == report["meta"]["anzahl_kritische_werte"]


# --------------------------------------------------------------------------
# SKILL.md trägt den Haftungshinweis (keine Fristberechnung)
# --------------------------------------------------------------------------

def test_skill_md_trennt_datumsnennung_von_fristberechnung():
    inhalt = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "fristenrechner-de" in inhalt
    assert "keine Fristberechnung" in inhalt or "keine Fristenkontrolle" in inhalt
