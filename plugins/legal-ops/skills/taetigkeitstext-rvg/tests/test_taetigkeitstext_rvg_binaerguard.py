"""Regressionstest: Binärdatei als --input/--report/--pruefe-text darf keinen
Traceback erzeugen, sondern muss als sauberer Eingabefehler (Exit 2) enden.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import lauf, report as _executor_report, schreibe  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])

_MINIMAL_EINTRAG = {
    "datum": "2026-07-01", "az": "12/2026", "minuten": 30,
    "start": None, "ende": None,
    "stichworte": ["Telefonat mit Mandant"], "quelle": "manuell",
}


def _assert_sauberer_eingabefehler(ergebnis) -> None:
    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_modus1_binaeres_input_exit2_kein_traceback(tmp_path):
    bin_datei = tmp_path / "leistungen.json"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--input", bin_datei)

    _assert_sauberer_eingabefehler(ergebnis)


def test_modus2_binaerer_pruefe_text_exit2_kein_traceback(tmp_path):
    report = _executor_report(
        EXECUTOR, "--input",
        schreibe(tmp_path / "leistungen.json", {"eintraege": [_MINIMAL_EINTRAG]}))
    report_pfad = schreibe(tmp_path / "report.json", report)
    bin_datei = tmp_path / "entwurf.md"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--pruefe-text", bin_datei, "--report", report_pfad)

    _assert_sauberer_eingabefehler(ergebnis)


def test_modus2_binaeres_report_exit2_kein_traceback(tmp_path):
    entwurf = schreibe(tmp_path / "entwurf.md", "x\n")
    bin_datei = tmp_path / "report.json"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--pruefe-text", entwurf, "--report", bin_datei)

    _assert_sauberer_eingabefehler(ergebnis)
