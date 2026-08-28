"""Regressionstest (Binärdatei-Guard-Nachzug, analog zum email-akten-
zuordnung-Fix): eine Binärdatei in `--kontext`/`mandate/` darf keinen
Traceback erzeugen, sondern muss als sauberer Eingabefehler (Exit 2) enden.
`core/calc/retention/executor.py` liest Mandate über `lese_mandate()` aus
`core/context/schema.py`, die `UnicodeDecodeError` in `KontextEingabeFehler`
übersetzt; der Executor fängt das in `main()` ab.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from conftest import CALC, lauf  # noqa: E402

EXECUTOR = CALC / "retention" / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaeres_mandat_im_kontext_exit2_kein_traceback(tmp_path):
    kontext = tmp_path / "kontext"
    (kontext / "mandate").mkdir(parents=True)
    (kontext / "mandate" / "akte.md").write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--kontext", kontext)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
