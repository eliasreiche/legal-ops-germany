"""Regressionstest: Binärdatei als --mahnstufen-config darf keinen Traceback
erzeugen, sondern muss als sauberer Eingabefehler (Exit 2) enden.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from pathlib import Path

from conftest import lauf  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPOS_CSV = FIXTURES / "beispiel-opos.csv"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaere_mahnstufen_config_exit2_kein_traceback(tmp_path):
    bin_datei = tmp_path / "mahnstufen.json"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--opos-csv", OPOS_CSV, "--stichtag", "2026-07-16",
                    "--mahnstufen-config", bin_datei)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "kein gültiges JSON/UTF-8" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
