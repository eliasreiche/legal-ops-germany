"""Regressionstest: Binäre abruf-meta.json im --listen-verzeichnis darf
keinen Traceback erzeugen, sondern muss als sauberer Eingabefehler (Exit 2)
enden.

Eindeutiger Testdateiname, damit er im selben pytest-Lauf nicht mit
gleichnamigen Tests anderer Skills kollidiert (mehrere Skills heißen
`executor.py`).
"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import lauf  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"

_PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x01])


def test_cli_binaere_abruf_meta_exit2_kein_traceback(tmp_path):
    parteien = tmp_path / "parteien.json"
    parteien.write_text(json.dumps([{"name": "Max Mustermann"}]), encoding="utf-8")
    listen = tmp_path / "listen"
    listen.mkdir()
    (listen / "abruf-meta.json").write_bytes(_PNG_BYTES)

    ergebnis = lauf(EXECUTOR, "--parteien", parteien, "--listen-verzeichnis", listen)

    assert ergebnis.returncode == 2, ergebnis.stderr
    assert ergebnis.stderr.startswith("Fehler:")
    assert "kein gültiges JSON/UTF-8" in ergebnis.stderr
    assert "Traceback" not in ergebnis.stderr
