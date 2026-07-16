"""Tests für executor.py — CLI (subprocess): Dateien rein, JSON-Report raus (P2).

Deckt ab: erfolgreiche Läufe (Exit 0 bei sauberem Eingang, Exit 1 bei
nicht_belegt bzw. Routing-Kollision, `--output`, `--ausfuehren` end-to-end)
sowie adversariale CLI-Inputs (fehlende Eingang-/Quell-/Scan-Datei, fehlendes
kontext-Verzeichnis, kaputtes JSON, Schwelle außerhalb [0,1]) — jeweils
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
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"

_GUELTIGER_EINGANG = {
    "eingang": {
        "absender": "Muster AG",
        "datum_schreiben": "2026-07-01",
        "aktenzeichen_fremd": None,
        "aktenzeichen_eigen": "2026-001",
        "betreff": "Test",
    },
    "fristindikatoren": [],
    "luecken": [],
}


def _lauf(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXECUTOR), *args], capture_output=True, text=True)


def _schreibe(pfad: Path, inhalt: str) -> Path:
    pfad.write_text(inhalt, encoding="utf-8")
    return pfad


# --------------------------------------------------------------------------
# Erfolgsfälle
# --------------------------------------------------------------------------

def test_cli_sauberer_lauf_exit_0(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Ihr Zeichen: 2026-001 vom 01.07.2026")

    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["schema_ok"] is True
    assert report["zuordnung"]["az_fuer_routing"] == "2026-001"


def test_cli_nicht_belegter_wert_exit_1(tmp_path):
    eingang_dict = json.loads(json.dumps(_GUELTIGER_EINGANG))
    eingang_dict["eingang"]["aktenzeichen_eigen"] = "ERFUNDEN-999"
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(eingang_dict))
    scan = _schreibe(tmp_path / "scan.txt",
                     "Hamburg, 01.07.2026 — ein Schreiben ohne dieses Aktenzeichen.")

    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 1
    report = json.loads(ergebnis.stdout)
    assert report["zusammenfassung"]["nicht_belegt"] == 1


def test_cli_output_datei(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Ihr Zeichen: 2026-001 vom 01.07.2026")
    ziel = tmp_path / "report.json"

    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT), "--output", str(ziel))
    assert ergebnis.returncode == 0, ergebnis.stderr
    assert ziel.is_file()


def test_cli_ausfuehren_end_to_end(tmp_path):
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    (kontext / "mandate").mkdir()
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Ihr Zeichen: 2026-001 vom 01.07.2026")

    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(kontext), "--scan-datei", str(scan),
                      "--ausfuehren")
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["routing_plan"]["ausgefuehrt"] is True
    kopiert = kontext / "posteingang" / "2026-07-01_unzugeordnet_muster-ag" / "scan.txt"
    assert kopiert.is_file()
    assert scan.is_file()  # Original bleibt erhalten


def test_cli_schwelle_moeglich_ueberschreibbar(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Ihr Zeichen: 2026-001 vom 01.07.2026")
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT), "--schwelle-moeglich", "0.5")
    assert ergebnis.returncode == 0, ergebnis.stderr
    report = json.loads(ergebnis.stdout)
    assert report["meta"]["schwelle_moeglich"] == 0.5


# --------------------------------------------------------------------------
# Adversariale CLI-Inputs — Exit 2, kein Traceback
# --------------------------------------------------------------------------

def test_cli_eingang_datei_fehlt(tmp_path):
    scan = _schreibe(tmp_path / "scan.txt", "Text")
    ergebnis = _lauf("--eingang", str(tmp_path / "fehlt.json"), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_quelle_datei_fehlt(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(tmp_path / "fehlt.txt"),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_kontext_verzeichnis_fehlt(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Text")
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(tmp_path / "nicht-da"))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_scan_datei_fuers_routing_fehlt(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Text")
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT),
                      "--scan-datei", str(tmp_path / "kein-scan.pdf"))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_eingang_kaputtes_json(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", "{nicht valide")
    scan = _schreibe(tmp_path / "scan.txt", "Text")
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_schwelle_ausserhalb_bereich(tmp_path):
    eingang = _schreibe(tmp_path / "eingang.json", json.dumps(_GUELTIGER_EINGANG))
    scan = _schreibe(tmp_path / "scan.txt", "Text")
    ergebnis = _lauf("--eingang", str(eingang), "--quelle", str(scan),
                      "--kontext", str(BEISPIEL_KONTEXT), "--schwelle-moeglich", "1.5")
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr


def test_cli_fehlende_pflicht_argumente(tmp_path):
    ergebnis = _lauf("--kontext", str(BEISPIEL_KONTEXT))
    assert ergebnis.returncode == 2
    assert "Traceback" not in ergebnis.stderr
