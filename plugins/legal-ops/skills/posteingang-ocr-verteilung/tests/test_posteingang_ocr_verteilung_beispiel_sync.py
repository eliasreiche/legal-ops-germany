"""Beispiel-Sync-Test (P4): schema/beispiel-report.json muss exakt dem
entsprechen, was der Executor aktuell aus schema/beispiel-eingang.json +
schema/beispiel-scan.txt gegen core/context/beispiel-kontext/ (read-only)
erzeugt.

Verhindert, dass Beispieldatei und tatsächliches Executor-Verhalten
auseinanderlaufen (dieselbe Disziplin wie
email-akten-zuordnung/tests/test_email_zuordnung_beispiel_sync.py).
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
    """`eingang_datei`, `quelldateien` und `kontext_verzeichnis` enthalten den
    beim Aufruf übergebenen Pfad-Präfix (absolut oder relativ, je nach cwd/
    Invocation) — für den Inhaltsvergleich auf den Dateinamen reduzieren,
    alles andere muss exakt übereinstimmen."""
    report = json.loads(json.dumps(report))  # tiefe Kopie
    report["meta"]["eingang_datei"] = Path(report["meta"]["eingang_datei"]).name
    report["meta"]["quelldateien"] = [Path(p).name for p in report["meta"]["quelldateien"]]
    report["meta"]["kontext_verzeichnis"] = "NEUTRALISIERT"
    for datei in report["routing_plan"].get("dateien", []):
        datei["quelle"] = Path(datei["quelle"]).name
    for eintrag in report["provenienz"]:
        if eintrag.get("fundstelle"):
            eintrag["fundstelle"]["datei"] = Path(eintrag["fundstelle"]["datei"]).name
    return report


def test_beispiel_report_ist_aktuell():
    ergebnis = subprocess.run(
        [sys.executable, str(EXECUTOR),
         "--eingang", str(SCHEMA / "beispiel-eingang.json"),
         "--quelle", str(SCHEMA / "beispiel-scan.txt"),
         "--kontext", str(BEISPIEL_KONTEXT),
         "--scan-datei", str(SCHEMA / "beispiel-scan.txt")],
        capture_output=True, text=True)
    assert ergebnis.returncode == 0, ergebnis.stderr
    frisch = _neutralisiert(json.loads(ergebnis.stdout))
    checked_in = _neutralisiert(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")))

    assert frisch == checked_in, (
        "schema/beispiel-report.json ist veraltet — neu erzeugen mit:\n"
        f"cd {SCHEMA} && python3 {EXECUTOR} --eingang beispiel-eingang.json "
        f"--quelle beispiel-scan.txt --kontext ../../../core/context/beispiel-kontext "
        f"--scan-datei beispiel-scan.txt --output beispiel-report.json")


def test_beispiel_scan_existiert_und_ist_fiktiv():
    pfad = SCHEMA / "beispiel-scan.txt"
    assert pfad.is_file()
    inhalt = pfad.read_text(encoding="utf-8")
    assert "Max Mustermann" in inhalt or "Muster AG" in inhalt or "Beispiel GmbH" in inhalt, (
        "beispiel-scan.txt: keine erkennbaren Platzhalter-Namen (fiktiv?)")
