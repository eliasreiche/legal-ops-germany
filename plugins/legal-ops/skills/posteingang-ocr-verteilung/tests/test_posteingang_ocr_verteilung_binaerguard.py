"""Regressionstest: Binärdatei als --quelle/--eingang darf keinen Traceback
erzeugen, sondern muss als sauberer Eingabefehler (Exit 2) enden.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from pathlib import Path

from conftest import lauf, schreibe  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])

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


def test_cli_binaere_quelle_exit2_kein_traceback(tmp_path):
    eingang = schreibe(tmp_path / "eingang.json", _GUELTIGER_EINGANG)
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    bin_datei = tmp_path / "scan.jpg"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--eingang", eingang, "--quelle", bin_datei,
                    "--kontext", kontext)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_cli_binaerer_eingang_exit2_kein_traceback(tmp_path):
    bin_datei = tmp_path / "eingang.json"
    bin_datei.write_bytes(_PNG_BYTES)
    kontext = tmp_path / "kontext"
    kontext.mkdir()
    q = schreibe(tmp_path / "quelle.md", "x\n")

    ergebnis = lauf(EXECUTOR, "--eingang", bin_datei, "--quelle", q,
                    "--kontext", kontext)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
