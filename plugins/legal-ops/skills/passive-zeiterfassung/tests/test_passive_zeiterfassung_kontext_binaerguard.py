"""Regressionstest (D12-Fix-Review, P2 REJECTED): eine Binärdatei in
`kontext/mandate/` darf keinen Traceback erzeugen, sondern muss als sauberer
Eingabefehler (Exit 2) enden. Root Cause war `core/context/schema.py` —
`lese_mandate()` las Mandats-Dateien ungeschützt gegen `UnicodeDecodeError`
(Reviewer-Repro: `bk2/mandate/akte.md` als Binärdatei, `--kontext bk2`).

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

from pathlib import Path

from conftest import lauf, schreibe  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaeres_mandat_im_kontext_exit2_kein_traceback(tmp_path):
    kontext = tmp_path / "kontext"
    (kontext / "mandate").mkdir(parents=True)
    (kontext / "mandate" / "akte.md").write_bytes(_PNG_BYTES)
    termine = schreibe(tmp_path / "termine.json", {"termine": []})

    ergebnis = lauf(EXECUTOR, "--termine", termine, "--kontext", kontext)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "keine gültige UTF-8-Datei" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
