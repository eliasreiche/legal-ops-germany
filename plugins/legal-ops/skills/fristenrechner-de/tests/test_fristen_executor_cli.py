"""Tests für core/calc/fristen/executor.py — CLI: JSON rein, JSON-Report raus (P2).

Deckt ab: Katalog-Fristart und freie Frist über die Kommandozeile, die
Schema-Beispieldateien des Skills, die Kennzeichnungen im Report
(Notfrist-Hinweis, kein technisches Fristende, teilgebietliches
Alternativ-Ende, P3-Markierung) sowie saubere Eingabefehler (Exit 2).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[5]
EXECUTOR = REPO / "plugins" / "legal-ops" / "core" / "calc" / "fristen" / "executor.py"
SCHEMA = Path(__file__).resolve().parents[1] / "schema"


def _lauf(eingabe: dict | str, tmp_path: Path) -> subprocess.CompletedProcess:
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

def test_katalog_fristart_berufung(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15",
                      "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    assert report["ergebnis"]["fristbeginn"] == "2026-01-16"
    assert report["ergebnis"]["fristende_rechnerisch"] == "2026-02-15"
    assert report["ergebnis"]["fristende"] == "2026-02-16"
    assert report["ergebnis"]["verschoben"] is True
    assert report["fristart"]["id"] == "berufung"
    assert any("Notfrist" in h for h in report["hinweise"])
    # P3: jeder Schritt ist als Executor-Ergebnis markiert.
    assert report["rechenkette"]
    for schritt in report["rechenkette"]:
        assert schritt["quelle"] == "executor"
    assert report["ergebnis"]["quelle"] == "executor"


def test_freie_frist_mit_teilgebietlichem_ende(tmp_path):
    report = _report({"ereignis_datum": "2025-08-01",
                      "dauer": 2, "einheit": "wochen",
                      "bundesland": "BY"}, tmp_path)
    assert report["ergebnis"]["fristende"] == "2025-08-15"
    assert report["ergebnis"]["fristende_bei_teilgebietlichem_feiertag"] == "2025-08-18"
    assert any("Gemeinde prüfen" in w for w in report["warnungen"])
    assert report["fristart"] is None


def test_widerspruch_mahnbescheid_kein_technisches_fristende(tmp_path):
    report = _report({"ereignis_datum": "2026-03-02",
                      "fristart": "widerspruch_mahnbescheid",
                      "bundesland": "HE"}, tmp_path)
    assert report["ergebnis"]["kein_technisches_fristende"] is True
    assert any("kein Fristende im technischen Sinn" in w
               for w in report["warnungen"])
    assert any("§ 694" in h for h in report["hinweise"])


def test_verlaengerbare_frist_hinweis(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15",
                      "fristart": "berufungsbegruendung",
                      "bundesland": "NW"}, tmp_path)
    # 2 Monate ab 15.01.2026 -> 15.03.2026 (So) -> 16.03.2026 (Mo).
    assert report["ergebnis"]["fristende"] == "2026-03-16"
    assert any("verlängerbar" in h for h in report["hinweise"])


def test_beginnfrist_ueber_cli(tmp_path):
    report = _report({"ereignis_datum": "2026-03-31",
                      "dauer": 1, "einheit": "monate",
                      "fristtyp": "beginn",
                      "bundesland": "NW"}, tmp_path)
    assert report["ergebnis"]["fristende"] == "2026-04-30"


def test_paragraf_193_abschaltbar_ueber_cli(tmp_path):
    report = _report({"ereignis_datum": "2026-01-31",
                      "dauer": 1, "einheit": "monate",
                      "bundesland": "NW",
                      "paragraf_193_anwenden": False}, tmp_path)
    assert report["ergebnis"]["fristende"] == "2026-02-28"
    assert report["ergebnis"]["verschoben"] is False


def test_output_datei(tmp_path):
    eingabe = tmp_path / "anfrage.json"
    eingabe.write_text(json.dumps({"ereignis_datum": "2026-01-15",
                                   "fristart": "berufung",
                                   "bundesland": "NW"}), encoding="utf-8")
    ziel = tmp_path / "report.json"
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe),
         "--output", str(ziel)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["ergebnis"]["fristende"] == "2026-02-16"


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
    # quelle_datei ist pfadabhängig — für den Vergleich neutralisieren.
    erzeugt["meta"].pop("quelle_datei")
    gespeichert["meta"].pop("quelle_datei")
    assert erzeugt == gespeichert


def test_beispiel_eingabe_frei_laeuft():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--input", str(SCHEMA / "beispiel-eingabe-frei.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["ergebnis"]["fristende_bei_teilgebietlichem_feiertag"] == "2025-08-18"


# --------------------------------------------------------------------------
# Eingabefehler → Exit 2, klare Meldung, kein Traceback
# --------------------------------------------------------------------------

def test_fehler_bundesland_fehlt(tmp_path):
    ergebnis = _lauf({"ereignis_datum": "2026-01-15",
                      "fristart": "berufung"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "bundesland" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_fristart_und_freie_frist_gleichzeitig(tmp_path):
    ergebnis = _lauf({"ereignis_datum": "2026-01-15",
                      "fristart": "berufung",
                      "dauer": 3, "einheit": "wochen",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "nicht beides" in ergebnis.stderr


def test_fehler_keine_fristangabe(tmp_path):
    ergebnis = _lauf({"ereignis_datum": "2026-01-15",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2


def test_fehler_unbekannte_fristart_nennt_bekannte(tmp_path):
    ergebnis = _lauf({"ereignis_datum": "2026-01-15",
                      "fristart": "einspruch_bussgeld",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "berufung" in ergebnis.stderr    # Liste der bekannten ids


def test_fehler_kaputtes_datum(tmp_path):
    ergebnis = _lauf({"ereignis_datum": "15.01.2026",
                      "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "ISO-Datum" in ergebnis.stderr


def test_fehler_kaputtes_json(tmp_path):
    ergebnis = _lauf("{kein json", tmp_path)
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr


def test_fehler_datei_fehlt(tmp_path):
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(tmp_path / "nix.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


# --------------------------------------------------------------------------
# Regressionstests aus dem adversarialen Review
# --------------------------------------------------------------------------

@pytest.mark.parametrize("eingabe", [
    # Befund 1: Datumsbereich-Überschreitungen -> Exit 2, kein Traceback.
    {"ereignis_datum": "1500-01-15", "dauer": 1, "einheit": "monate",
     "bundesland": "NW"},
    {"ereignis_datum": "4099-12-15", "dauer": 1, "einheit": "monate",
     "bundesland": "NW"},
    {"ereignis_datum": "2026-01-15", "dauer": 2100, "einheit": "jahre",
     "bundesland": "NW"},
    {"ereignis_datum": "2026-01-15", "dauer": 100000000000,
     "einheit": "tage", "bundesland": "NW"},
])
def test_befund1_bereichsgrenzen_exit_2_ohne_traceback(eingabe, tmp_path):
    ergebnis = _lauf(eingabe, tmp_path)
    assert ergebnis.returncode == 2, ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
    assert "Fehler:" in ergebnis.stderr


def test_befund2_fristtyp_override_katalog_abgelehnt(tmp_path):
    # Der Fristtyp einer Katalog-Fristart ist gesetzlich festgelegt —
    # ein abweichender Override ist ein Eingabefehler, keine stille Rechnung.
    ergebnis = _lauf({"ereignis_datum": "2026-01-13",
                      "fristart": "berufung",
                      "fristtyp": "beginn",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2
    assert "gesetzlich festgelegt" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_befund2_fristtyp_gleichlautend_erlaubt(tmp_path):
    # Redundante, aber übereinstimmende Angabe bleibt zulässig.
    report = _report({"ereignis_datum": "2026-01-13",
                      "fristart": "berufung",
                      "fristtyp": "ereignis",
                      "bundesland": "NW"}, tmp_path)
    assert report["ergebnis"]["fristende"] == "2026-02-13"


def test_befund3_paragraf_193_nur_json_boolean(tmp_path):
    # Der JSON-String "false" ist truthy — strenge Typprüfung statt bool().
    for wert in ("false", "true", 0, 1, "nein"):
        ergebnis = _lauf({"ereignis_datum": "2026-01-15",
                          "fristart": "berufung",
                          "bundesland": "NW",
                          "paragraf_193_anwenden": wert}, tmp_path)
        assert ergebnis.returncode == 2, wert
        assert "JSON-Boolean" in ergebnis.stderr, wert


def test_befund4_output_pfad_nicht_schreibbar(tmp_path):
    eingabe = tmp_path / "anfrage.json"
    eingabe.write_text(json.dumps({"ereignis_datum": "2026-01-15",
                                   "fristart": "berufung",
                                   "bundesland": "NW"}), encoding="utf-8")
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--input", str(eingabe),
         "--output", str(tmp_path / "gibt-es-nicht" / "report.json")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
    assert "geschrieben" in ergebnis.stderr


@pytest.mark.parametrize("wert", [20260115, "2026-W03-4", "2026-1-15",
                                  "20260115"])
def test_befund5_datum_strikt_jjjj_mm_tt(wert, tmp_path):
    ergebnis = _lauf({"ereignis_datum": wert,
                      "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    assert ergebnis.returncode == 2, repr(wert)
    assert "JJJJ-MM-TT" in ergebnis.stderr, repr(wert)


def test_befund6_notfrist_zitat_praezise(tmp_path):
    report = _report({"ereignis_datum": "2026-01-15",
                      "fristart": "berufung",
                      "bundesland": "NW"}, tmp_path)
    notfrist_hinweise = [h for h in report["hinweise"] if "Notfrist" in h]
    assert notfrist_hinweise
    hinweis = notfrist_hinweise[0]
    # Definition der Notfrist: § 224 Abs. 1 Satz 2 ZPO;
    # Unverlängerbarkeit: § 224 Abs. 2 ZPO — nicht Abs. 1.
    assert "§ 224 Abs. 1 Satz 2 ZPO" in hinweis
    assert "§ 224 Abs. 2 ZPO" in hinweis
    assert "nicht verlängerbar (§ 224 Abs. 1 ZPO)" not in hinweis
