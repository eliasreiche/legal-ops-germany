"""Beispiel-Sync-Test (P4): schema/beispiel-report.json muss exakt dem
entsprechen, was der Executor aktuell aus den vier Beispiel-EMLs in
schema/ gegen core/context/beispiel-kontext/ (read-only) erzeugt.

Verhindert, dass Beispieldatei und tatsächliches Executor-Verhalten
auseinanderlaufen (dieselbe Disziplin wie
interessenkollision-check/schema/beispiel-report.json).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
SCHEMA = SKILL_DIR / "schema"
BEISPIEL_KONTEXT = REPO / "plugins" / "legal-ops" / "core" / "context" / "beispiel-kontext"


def _neutralisiert(report: dict) -> dict:
    """`kontext_verzeichnis` und `quelle` je Dokument enthalten den beim
    Aufruf übergebenen Pfad-Präfix (absolut oder relativ, je nach cwd/
    Invocation) — für den Inhaltsvergleich auf den Dateinamen reduzieren,
    alles andere muss exakt übereinstimmen."""
    report = json.loads(json.dumps(report))  # tiefe Kopie
    report["meta"]["kontext_verzeichnis"] = "NEUTRALISIERT"
    for doc in report["dokumente"]:
        doc["quelle"] = Path(doc["quelle"]).name
    return report


def test_beispiel_report_ist_aktuell():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR), "--eml", str(SCHEMA),
         "--kontext", str(BEISPIEL_KONTEXT)],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    frisch = _neutralisiert(json.loads(ergebnis.stdout))
    checked_in = _neutralisiert(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")))

    assert frisch == checked_in, (
        "schema/beispiel-report.json ist veraltet — neu erzeugen mit:\n"
        f"python3 {EXECUTOR} --eml {SCHEMA} --kontext {BEISPIEL_KONTEXT} "
        f"--output {SCHEMA / 'beispiel-report.json'}")


def test_beispiel_emls_existieren_und_sind_fiktiv():
    erwartete = [
        "beispiel-az-im-betreff.eml",
        "beispiel-nur-parteiname.eml",
        "beispiel-kein-treffer.eml",
        "beispiel-fristverdacht.eml",
    ]
    for name in erwartete:
        pfad = SCHEMA / name
        assert pfad.is_file(), f"fehlt: {pfad}"
        inhalt = pfad.read_bytes()
        assert b".example" in inhalt, f"{name}: keine erkennbare .example-Domain (fiktiv?)"
