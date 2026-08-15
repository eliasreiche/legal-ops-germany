"""Beispiel-Sync-Test (P4): schema/beispiel-report.json muss exakt dem
entsprechen, was der Executor aktuell aus den vier Beispiel-EMLs in
schema/ gegen core/context/beispiel-kontext/ (read-only) erzeugt.

Verhindert, dass Beispieldatei und tatsächliches Executor-Verhalten
auseinanderlaufen (dieselbe Disziplin wie
interessenkollision-check/schema/beispiel-report.json).
"""
from __future__ import annotations

import json
from pathlib import Path

from conftest import BEISPIEL_KONTEXT, neutralisiere, report  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
EXECUTOR = SKILL_DIR / "executor.py"
SCHEMA = SKILL_DIR / "schema"

# Pfad-Felder dieses Reports, die vom Aufruf abhängen (siehe neutralisiere).
PFADFELDER = ("kontext_verzeichnis", "quelle")


def test_beispiel_report_ist_aktuell():
    frisch = neutralisiere(
        report(EXECUTOR, "--eml", SCHEMA, "--kontext", BEISPIEL_KONTEXT),
        PFADFELDER)
    checked_in = neutralisiere(
        json.loads((SCHEMA / "beispiel-report.json").read_text(encoding="utf-8")),
        PFADFELDER)

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
