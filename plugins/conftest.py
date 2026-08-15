"""Gemeinsame Test-Hilfen für alle Skill-Tests unter `plugins/legal-ops/`.

Ersetzt drei Muster, die vorher in jeder Testdatei erneut standen:

1. `REPO = Path(__file__).resolve().parents[5]` samt der daraus gebauten
   Pfade auf `core/` und `skills/` — hier einmal als Konstanten, abgeleitet
   aus der Plugin-Wurzel statt aus einer gezählten Verzeichnistiefe.
2. `sys.path.insert(...)` auf `core/`, `core/calc/`, `core/adapters/` —
   pytest lädt diese Datei vor jedem Testmodul, der Pfad steht also schon.
3. Die subprocess-Helfer `_lauf` / `_report` und die Pfad-Neutralisierung
   der Beispiel-Sync-Tests.

Testmodule holen sich das per `from conftest import lauf, report` — pytest
legt das Verzeichnis dieser Datei dafür auf `sys.path`.

Liegt bewusst in `plugins/` statt in `plugins/legal-ops/`: `legal-ops/` ist die
Auslieferungseinheit — der Install kopiert genau dieses Verzeichnis in den
Cache (siehe `tests/test_install_smoke.py`), Test-Scaffolding gehört nicht
hinein.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent / "legal-ops"   # <repo>/plugins/legal-ops
CORE = PLUGIN / "core"
CALC = CORE / "calc"
ADAPTERS = CORE / "adapters"
SKILLS = PLUGIN / "skills"
BEISPIEL_KONTEXT = CORE / "context" / "beispiel-kontext"

# Die Rechen-Pakete unter core/ sind kein installiertes Paket, sondern werden
# flach importiert (`from gwg import rechner`, `from context import schema`).
for _pfad in (CORE, CALC, ADAPTERS):
    if str(_pfad) not in sys.path:
        sys.path.insert(0, str(_pfad))


def lauf(executor: Path | str, *args) -> subprocess.CompletedProcess:
    """Executor als Subprozess, Argumente werden zu `str` gemacht."""
    return subprocess.run(
        [sys.executable, str(executor), *(str(a) for a in args)],
        capture_output=True, text=True)


def report(executor: Path | str, *args) -> dict:
    """Wie `lauf`, besteht aber auf Exit 0 und liefert den JSON-stdout."""
    ergebnis = lauf(executor, *args)
    assert ergebnis.returncode == 0, ergebnis.stderr
    return json.loads(ergebnis.stdout)


def schreibe(pfad: Path, daten) -> Path:
    """Schreibt `daten` als JSON — oder unverändert, wenn schon ein String
    (adversariale Tests reichen bewusst kaputtes JSON durch)."""
    pfad.write_text(daten if isinstance(daten, str) else json.dumps(daten),
                    encoding="utf-8")
    return pfad


def neutralisiere(daten, felder: Iterable[str]) -> dict:
    """Tiefe Kopie, in der jeder Wert unter einem der `felder`-Schlüssel auf
    den reinen Dateinamen reduziert ist.

    Beispiel-Sync-Tests vergleichen einen frisch erzeugten Report mit dem
    eingecheckten. Pfad-Felder tragen dabei das Präfix des Aufrufs (absolut
    oder relativ, je nach cwd) — nur die Dateinamen sind vergleichbar, alles
    andere muss exakt übereinstimmen.
    """
    felder = set(felder)

    def um(wert):
        if isinstance(wert, dict):
            return {k: (_dateiname(v) if k in felder else um(v))
                    for k, v in wert.items()}
        if isinstance(wert, list):
            return [um(v) for v in wert]
        return wert

    return um(daten)


def _dateiname(wert):
    if isinstance(wert, list):
        return [Path(p).name for p in wert]
    return Path(wert).name if wert else wert
