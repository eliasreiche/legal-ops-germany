"""Regressionstest: Binärdatei als --input darf keinen Traceback erzeugen,
sondern muss als sauberer Eingabefehler (Exit 2) enden. Die alte Guard-
Klausel (`except OSError`) fängt `UnicodeDecodeError` NICHT ab — die Klasse
erbt von `ValueError`, nicht von `OSError`.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from pathlib import Path

from conftest import BEISPIEL_KONTEXT, lauf  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaeres_input_exit2_kein_traceback(tmp_path):
    bin_datei = tmp_path / "metadaten.json"
    bin_datei.write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--input", bin_datei, "--kontext", str(BEISPIEL_KONTEXT))

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
