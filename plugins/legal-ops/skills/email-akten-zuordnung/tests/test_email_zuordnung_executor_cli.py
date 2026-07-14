"""Tests für executor.py — CLI (subprocess): Dateien rein, JSON-Report raus (P2).

Deckt ab: erfolgreiche Läufe (--eml Datei, --eml Verzeichnis, --input JSON,
--output, --schwelle-moeglich) sowie adversariale CLI-Inputs (kein/beide
Quell-Flags, fehlendes kontext-Verzeichnis, fehlende/leere EML-Quelle,
kaputtes JSON, falsches JSON-Schema, ungültiges Datum, Schwelle außerhalb
[0,1]) — jeweils sauberer Exit 2, kein Traceback.
"""
from __future__ import annotations

import json
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"


def _lauf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXECUTOR), *args], capture_output=True, text=True)


def _schreibe_eml(pfad: Path, betreff: str, textauszug: str = "Text.") -> None:
    msg = EmailMessage()
    msg["From"] = "Absender <a@beispiel.example>"
    msg["Subject"] = betreff
    msg["Date"] = "Sat, 20 Jun 2026 09:00:00 +0200"
    msg.set_content(textauszug)
    pfad.write_bytes(bytes(msg))


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_cli_eml_datei_gegen_beispiel_kontext(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "Az. 2026-001 - Fristsetzung", "in unserem Az. 2026-001 ...")

    ergebnis = _lauf("--eml", str(eml), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["meta"]["quelle_typ"] == "eml"
    assert report["dokumente"][0]["kandidaten"][0]["az"] == "2026-001"


def test_cli_eml_verzeichnis(tmp_path):
    _schreibe_eml(tmp_path / "a.eml", "Werbung", "Kaufen Sie jetzt!")
    _schreibe_eml(tmp_path / "b.eml", "Az. 2026-002", "unser Az. 2026-002")

    ergebnis = _lauf("--eml", str(tmp_path), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["meta"]["anzahl_dokumente"] == 2


def test_cli_input_json(tmp_path):
    eingabe = tmp_path / "metadaten.json"
    eingabe.write_text(json.dumps([
        {"absender_name": "Muster AG", "betreff": "Zahlungsaufforderung",
         "textauszug": "im Namen der Muster AG ...", "datum": "2026-06-25"},
    ]), encoding="utf-8")

    ergebnis = _lauf("--input", str(eingabe), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["meta"]["quelle_typ"] == "input"
    assert report["dokumente"][0]["kandidaten"][0]["az"] == "2026-001"


def test_cli_output_datei(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "Ohne Bezug", "Neutraler Inhalt ohne Mandatsbezug")
    ziel = tmp_path / "report.json"

    ergebnis = _lauf("--eml", str(eml), "--kontext", str(BEISPIEL_KONTEXT),
                      "--output", str(ziel))
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ziel.is_file()
    report = json.loads(ziel.read_text(encoding="utf-8"))
    assert report["dokumente"][0]["kein_treffer"] is True


def test_cli_schwelle_moeglich_ueberschreibbar(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "Neutral", "kein Bezug")
    ergebnis = _lauf("--eml", str(eml), "--kontext", str(BEISPIEL_KONTEXT),
                      "--schwelle-moeglich", "0.5")
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["meta"]["schwelle_moeglich"] == 0.5


# --------------------------------------------------------------------------
# Adversariale CLI-Inputs — Exit 2, kein Traceback
# --------------------------------------------------------------------------

def test_cli_weder_eml_noch_input(tmp_path):
    ergebnis = _lauf("--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_sowohl_eml_als_auch_input(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "X", "Y")
    eingabe = tmp_path / "m.json"
    eingabe.write_text("[]", encoding="utf-8")
    ergebnis = _lauf("--eml", str(eml), "--input", str(eingabe),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_kontext_verzeichnis_fehlt(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "X", "Y")
    ergebnis = _lauf("--eml", str(eml), "--kontext", str(tmp_path / "nicht-da"))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_eml_pfad_existiert_nicht(tmp_path):
    ergebnis = _lauf("--eml", str(tmp_path / "fehlt.eml"), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_eml_verzeichnis_ohne_eml_dateien(tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    ergebnis = _lauf("--eml", str(leer), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_input_datei_existiert_nicht(tmp_path):
    ergebnis = _lauf("--input", str(tmp_path / "fehlt.json"), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_input_kaputtes_json(tmp_path):
    eingabe = tmp_path / "kaputt.json"
    eingabe.write_text("{nicht valide", encoding="utf-8")
    ergebnis = _lauf("--input", str(eingabe), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_input_kein_array(tmp_path):
    eingabe = tmp_path / "dict.json"
    eingabe.write_text(json.dumps({"betreff": "x"}), encoding="utf-8")
    ergebnis = _lauf("--input", str(eingabe), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_input_ungueltiges_datum(tmp_path):
    eingabe = tmp_path / "m.json"
    eingabe.write_text(json.dumps([{"betreff": "x", "datum": "20.06.2026"}]), encoding="utf-8")
    ergebnis = _lauf("--input", str(eingabe), "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_schwelle_ausserhalb_bereich(tmp_path):
    eml = tmp_path / "mail.eml"
    _schreibe_eml(eml, "X", "Y")
    ergebnis = _lauf("--eml", str(eml), "--kontext", str(BEISPIEL_KONTEXT),
                      "--schwelle-moeglich", "1.5")
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
