"""Regressionstest (D12-Fix-Review, Minor): eine Binärdatei als --opos-csv
endete zwar bereits vor dem Fix mit Exit 2 (weil `OposEingabeFehler` von
`ValueError` erbt und `UnicodeDecodeError` ebenfalls ein `ValueError` ist),
aber über den generischen `ValueError`-Fang mit der rohen Codec-Meldung
statt der einheitlichen „keine gültige UTF-8-Datei"-Formulierung. Dieser
Test verlangt die vereinheitlichte Meldung.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from pathlib import Path

from conftest import lauf  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaere_opos_csv_exit2_einheitliche_meldung(tmp_path):
    bin_datei = tmp_path / "opos.csv"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--opos-csv", bin_datei, "--stichtag", "2026-07-16")

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
