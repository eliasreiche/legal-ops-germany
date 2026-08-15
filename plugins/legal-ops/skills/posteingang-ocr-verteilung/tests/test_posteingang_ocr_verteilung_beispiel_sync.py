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
from pathlib import Path

from conftest import BEISPIEL_KONTEXT, neutralisiere, report  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
SCHEMA = SKILL_DIR / "schema"

# Pfad-Felder dieses Reports, die vom Aufruf abhängen (siehe neutralisiere):
# meta.eingang_datei/quelldateien/kontext_verzeichnis, routing_plan.dateien[].quelle
# und provenienz[].fundstelle.datei.
PFADFELDER = ("eingang_datei", "quelldateien", "kontext_verzeichnis",
              "quelle", "datei")


def test_beispiel_report_ist_aktuell():
    frisch = neutralisiere(
        report(EXECUTOR,
               "--eingang", SCHEMA / "beispiel-eingang.json",
               "--quelle", SCHEMA / "beispiel-scan.txt",
               "--kontext", BEISPIEL_KONTEXT,
               "--scan-datei", SCHEMA / "beispiel-scan.txt"),
        PFADFELDER)
    checked_in = neutralisiere(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")),
        PFADFELDER)

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
