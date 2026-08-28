"""Regressionstest: Binärdatei als --aktenkopf/--quelle darf keinen
Traceback erzeugen, sondern muss als sauberer Eingabefehler (Exit 2) enden.

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

_BASIS_AKTENKOPF = {
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


def test_cli_binaere_quelle_exit2_kein_traceback(tmp_path):
    ak = schreibe(tmp_path / "aktenkopf.json", _BASIS_AKTENKOPF)
    bin_datei = tmp_path / "scan.jpg"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--aktenkopf", ak, "--quelle", bin_datei)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr


def test_cli_binaerer_aktenkopf_exit2_kein_traceback(tmp_path):
    bin_datei = tmp_path / "aktenkopf.json"
    bin_datei.write_bytes(_PNG_BYTES)
    q = schreibe(tmp_path / "quelle.md", "x\n")

    ergebnis = lauf(EXECUTOR, "--aktenkopf", bin_datei, "--quelle", q)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
