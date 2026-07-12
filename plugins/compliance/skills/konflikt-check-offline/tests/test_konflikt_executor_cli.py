"""Tests für executor.py — CLI (subprocess): Dateien rein, JSON-Report raus (P2).

Deckt ab: erfolgreiche Läufe (CSV+JSON, --output, --schwelle-moeglich),
Beispieldateien-Round-Trip gegen schema/beispiel-report.json, sowie
adversariale CLI-Inputs (fehlende Datei, kaputtes JSON, fehlende
Pflichtspalte, unbekannte Dateiendung, Schwelle außerhalb [0,1]) — jeweils
sauberer Exit 2, kein Traceback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
SCHEMA = SKILL_DIR / "schema"


def _lauf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXECUTOR), *args], capture_output=True, text=True)


def _liste_csv(tmp_path: Path) -> Path:
    pfad = tmp_path / "liste.csv"
    pfad.write_text(
        "name;rolle;typ;az;notiz\n"
        "Erika Mustermann;mandant;natuerlich;12/2024;\n"
        "Schulze GmbH;gegner;juristisch;;\n",
        encoding="utf-8")
    return pfad


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_cli_csv_und_json_eingabe(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.json"
    parteien.write_text(
        '[{"name": "Erika Mustermann", "rolle": "mandant"}]', encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["zusammenfassung"]["anzahl_treffer"] == 1
    assert report["kandidaten"][0]["regel"] == "S1"


def test_cli_parteien_als_csv(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika Mustermann\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["zusammenfassung"]["anzahl_treffer"] == 1


def test_cli_output_datei(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika Mustermann\n", encoding="utf-8")
    ziel = tmp_path / "report.json"
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien),
                     "--output", str(ziel))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["zusammenfassung"]["anzahl_neue_parteien"] == 1


def test_cli_schwelle_moeglich_override(tmp_path):
    liste = tmp_path / "liste.csv"
    liste.write_text(
        "name;rolle;typ\nBeispiel Handel GmbH & Co. KG;gegner;juristisch\n",
        encoding="utf-8")
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nBeispiel Handels GmbH\n", encoding="utf-8")

    streng = _lauf("--liste", str(liste), "--parteien", str(parteien),
                   "--schwelle-moeglich", "0.99")
    assert streng.returncode == 0, streng.stderr
    assert json.loads(streng.stdout)["zusammenfassung"]["anzahl_moegliche_treffer"] == 0

    locker = _lauf("--liste", str(liste), "--parteien", str(parteien),
                   "--schwelle-moeglich", "0.90")
    assert locker.returncode == 0, locker.stderr
    report = json.loads(locker.stdout)
    assert report["zusammenfassung"]["anzahl_moegliche_treffer"] == 1
    assert report["meta"]["schwelle_moeglich"] == 0.90


def test_cli_bom_in_liste_csv_wird_toleriert(tmp_path):
    liste = tmp_path / "liste.csv"
    liste.write_bytes(
        "﻿name;rolle;typ\nErika Mustermann;mandant;natuerlich\n".encode("utf-8"))
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika Mustermann\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert json.loads(ergebnis.stdout)["zusammenfassung"]["anzahl_treffer"] == 1


# --------------------------------------------------------------------------
# Beispieldateien-Round-Trip
# --------------------------------------------------------------------------

def test_beispiel_report_synchron():
    ergebnis = _lauf("--liste", str(SCHEMA / "beispiel-mandantenliste.csv"),
                     "--parteien", str(SCHEMA / "beispiel-neue-parteien.json"))
    assert ergebnis.returncode == 0, ergebnis.stderr
    erzeugt = json.loads(ergebnis.stdout)
    gespeichert = json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8"))
    erzeugt["meta"].pop("liste_datei")
    erzeugt["meta"].pop("parteien_datei")
    gespeichert["meta"].pop("liste_datei")
    gespeichert["meta"].pop("parteien_datei")
    assert erzeugt == gespeichert


def test_beispiel_report_enthaelt_je_einen_treffer_pro_stufe():
    ergebnis = _lauf("--liste", str(SCHEMA / "beispiel-mandantenliste.csv"),
                     "--parteien", str(SCHEMA / "beispiel-neue-parteien.json"))
    report = json.loads(ergebnis.stdout)
    regeln = {k["regel"] for k in report["kandidaten"]}
    assert regeln == {"S1", "S2", "S3", "S4"}
    # Eine Partei im Beispiel hat bewusst keinen Treffer (Nichttreffer-Fall).
    assert report["zusammenfassung"]["anzahl_geprueft_paare"] > len(report["kandidaten"])


# --------------------------------------------------------------------------
# Eingabefehler -> Exit 2, klare Meldung, kein Traceback
# --------------------------------------------------------------------------

def test_fehler_liste_nicht_gefunden(tmp_path):
    ergebnis = _lauf("--liste", str(tmp_path / "nix.csv"),
                     "--parteien", str(tmp_path / "auch_nix.json"))
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_fehler_parteien_nicht_gefunden(tmp_path):
    liste = _liste_csv(tmp_path)
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(tmp_path / "nix.json"))
    assert ergebnis.returncode == 2
    assert "nicht gefunden" in ergebnis.stderr


def test_fehler_fehlende_pflichtspalte(tmp_path):
    liste = tmp_path / "liste.csv"
    liste.write_text("name;rolle\nErika;mandant\n", encoding="utf-8")
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 2
    assert "Pflichtspalte" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_unbekannte_dateiendung(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.txt"
    parteien.write_text("name\nErika\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 2
    assert "Dateiendung" in ergebnis.stderr


def test_fehler_kaputtes_json(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.json"
    parteien.write_text("[kein json", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 2
    assert "JSON" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_fehler_schwelle_ausserhalb_bereich(tmp_path):
    liste = _liste_csv(tmp_path)
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien),
                     "--schwelle-moeglich", "1.5")
    assert ergebnis.returncode == 2
    assert "0.0 und 1.0" in ergebnis.stderr


def test_fehler_ungueltige_rolle_in_liste(tmp_path):
    liste = tmp_path / "liste.csv"
    liste.write_text("name;rolle;typ\nErika;unsinn;natuerlich\n", encoding="utf-8")
    parteien = tmp_path / "parteien.csv"
    parteien.write_text("name\nErika\n", encoding="utf-8")
    ergebnis = _lauf("--liste", str(liste), "--parteien", str(parteien))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
